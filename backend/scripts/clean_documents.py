#!/usr/bin/env python3
"""
Script para limpiar completamente los datos de documentos de la base de datos.
USO: python scripts/clean_documents.py [options]

TABLAS QUE LIMPIA:
- documents (metadatos principales)
- document_analyses (análisis de Emma)
- document_views (auditoría de vistas)
- document_shares (compartidos)
- document_share_access_logs (logs de acceso a shares)
- document_share_recipients (destinatarios de shares)
- document_metrics (métricas de uso)
- document_tags (relación docs-tags)
- document_acls (permisos)
- document_acl_audits (auditoría de permisos)
- indexed_documents (docs de conectores externos)
- channel_documents (docs de canales)

TAMBIÉN LIMPIA EN WEAVIATE:
- Colecciones de documentos por tenant

PELIGRO: Este script elimina datos permanentemente. Úsalo solo en desarrollo.
"""

import argparse
import asyncio
import sys
import os
from typing import Optional
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db.database import get_db, engine


def get_document_tables_stats(db: Session) -> dict:
    """Obtiene estadísticas de las tablas de documentos"""
    tables = [
        'documents',
        'document_analyses',
        'document_views',
        'document_shares',
        'document_share_access_logs',
        'document_share_recipients',
        'document_metrics',
        'document_tags',
        'document_acls',
        'document_acl_audits',
        'indexed_documents',
        'channel_documents',
        'folder_markers',
    ]

    stats = {}
    for table in tables:
        try:
            result = db.execute(text(f"SELECT COUNT(*) FROM {table}"))
            count = result.scalar()
            stats[table] = count
        except Exception as e:
            stats[table] = f"Error: {str(e)}"

    return stats


def print_stats(stats: dict, title: str = "Estadísticas de tablas de documentos"):
    """Imprime estadísticas de forma legible"""
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")

    total = 0
    for table, count in stats.items():
        if isinstance(count, int):
            print(f"  {table:40} {count:>10,}")
            total += count
        else:
            print(f"  {table:40} {count}")

    print(f"{'='*60}")
    print(f"  {'TOTAL':40} {total:>10,}")
    print(f"{'='*60}\n")


def clean_document_related_tables(db: Session, tenant_id: Optional[str] = None, confirm: bool = False) -> bool:
    """
    Limpia todas las tablas relacionadas con documentos.

    Args:
        db: Sesión de base de datos
        tenant_id: Si se especifica, solo limpia datos de ese tenant
        confirm: Si es False, solo muestra preview

    Returns:
        True si se ejecutó correctamente
    """

    # Mostrar estadísticas antes
    print("\n📊 ESTADÍSTICAS ANTES DE LIMPIAR:")
    stats_before = get_document_tables_stats(db)
    print_stats(stats_before)

    if not confirm:
        print("⚠️  Modo preview. Para ejecutar la limpieza, usa --confirm")
        return False

    tenant_filter = f"WHERE tenant_id = '{tenant_id}'" if tenant_id else ""
    doc_tenant_filter = f"WHERE tenant_id = '{tenant_id}'" if tenant_id else ""

    print(f"\n🚨 INICIANDO LIMPIEZA {'(tenant: ' + tenant_id + ')' if tenant_id else '(TODOS LOS TENANTS)'}...")
    print(f"   Timestamp: {datetime.now().isoformat()}")

    try:
        # Orden de eliminación respetando foreign keys (hijos primero)
        delete_queries = [
            # 1. Auditorías y logs (sin dependencias)
            ("document_acl_audits", f"DELETE FROM document_acl_audits {tenant_filter}"),
            ("document_share_access_logs", f"DELETE FROM document_share_access_logs {tenant_filter}"),
            ("document_share_recipients", f"DELETE FROM document_share_recipients {tenant_filter}"),

            # 2. Tablas con FK a documents
            ("document_analyses", f"DELETE FROM document_analyses {tenant_filter}"),
            ("document_views", f"DELETE FROM document_views {tenant_filter}"),
            ("document_shares", f"DELETE FROM document_shares {tenant_filter}"),
            ("document_metrics", f"DELETE FROM document_metrics {tenant_filter}"),
            ("document_acls", f"DELETE FROM document_acls {tenant_filter}"),

            # 3. Junction tables
            ("document_tags", f"""
                DELETE FROM document_tags
                WHERE document_id IN (
                    SELECT id FROM documents {doc_tenant_filter}
                )
            """),

            # 4. Documentos externos
            ("indexed_documents", f"DELETE FROM indexed_documents {tenant_filter}"),
            ("channel_documents", f"""
                DELETE FROM channel_documents
                WHERE channel_id IN (
                    SELECT id FROM information_channels {tenant_filter}
                )
            """),

            # 5. Marcadores de carpetas
            ("folder_markers", f"DELETE FROM folder_markers {tenant_filter}"),

            # 6. Documentos principales (al final)
            ("documents", f"DELETE FROM documents {doc_tenant_filter}"),
        ]

        for table_name, query in delete_queries:
            try:
                # Clean up the query (remove extra whitespace)
                clean_query = ' '.join(query.split())
                result = db.execute(text(clean_query))
                deleted = result.rowcount
                print(f"   ✅ {table_name}: {deleted:,} registros eliminados")
            except Exception as e:
                print(f"   ⚠️  {table_name}: Error - {str(e)}")

        db.commit()

        # Mostrar estadísticas después
        print("\n📊 ESTADÍSTICAS DESPUÉS DE LIMPIAR:")
        stats_after = get_document_tables_stats(db)
        print_stats(stats_after)

        print("✅ Limpieza de base de datos completada exitosamente")
        return True

    except Exception as e:
        print(f"\n❌ Error durante la limpieza: {str(e)}")
        db.rollback()
        return False


def clean_weaviate_collections(tenant_id: Optional[str] = None, confirm: bool = False) -> bool:
    """
    Limpia las colecciones de Weaviate relacionadas con documentos.

    Args:
        tenant_id: Si se especifica, solo limpia colecciones de ese tenant
        confirm: Si es False, solo muestra preview
    """
    try:
        import weaviate
        from app.core.config import settings

        weaviate_url = getattr(settings, 'WEAVIATE_URL', 'http://localhost:8080')

        print(f"\n🔍 Conectando a Weaviate: {weaviate_url}")

        client = weaviate.Client(weaviate_url)

        # Obtener todas las colecciones
        schema = client.schema.get()
        collections = [c['class'] for c in schema.get('classes', [])]

        # Filtrar colecciones de documentos
        doc_collections = [c for c in collections if c.startswith('nexus_') and '_documents' in c.lower()]

        if tenant_id:
            # Normalizar tenant_id para el formato de colección
            normalized_tenant = tenant_id.replace('-', '_').lower()
            doc_collections = [c for c in doc_collections if normalized_tenant in c.lower()]

        print(f"\n📋 Colecciones de documentos encontradas: {len(doc_collections)}")
        for col in doc_collections:
            # Obtener conteo de objetos
            try:
                result = client.query.aggregate(col).with_meta_count().do()
                count = result.get('data', {}).get('Aggregate', {}).get(col, [{}])[0].get('meta', {}).get('count', 0)
                print(f"   - {col}: {count:,} objetos")
            except:
                print(f"   - {col}: (no se pudo obtener conteo)")

        if not confirm:
            print("\n⚠️  Modo preview. Para eliminar colecciones, usa --confirm")
            return False

        print("\n🚨 Eliminando colecciones...")
        for col in doc_collections:
            try:
                client.schema.delete_class(col)
                print(f"   ✅ {col}: eliminada")
            except Exception as e:
                print(f"   ⚠️  {col}: Error - {str(e)}")

        print("✅ Limpieza de Weaviate completada")
        return True

    except ImportError:
        print("⚠️  Weaviate client no disponible. Saltando limpieza de Weaviate.")
        return False
    except Exception as e:
        print(f"❌ Error conectando a Weaviate: {str(e)}")
        return False


def list_tenants(db: Session):
    """Lista los tenants disponibles"""
    try:
        result = db.execute(text("""
            SELECT t.id, t.name, t.slug,
                   COUNT(d.id) as document_count
            FROM tenants t
            LEFT JOIN documents d ON d.tenant_id = t.id
            GROUP BY t.id, t.name, t.slug
            ORDER BY document_count DESC
        """))

        tenants = result.fetchall()

        print(f"\n📋 Tenants encontrados: {len(tenants)}")
        print(f"{'='*70}")
        print(f"  {'ID':36} {'Nombre':20} {'Documentos':>10}")
        print(f"{'='*70}")

        for tenant in tenants:
            print(f"  {tenant[0]:36} {(tenant[1] or tenant[2] or 'N/A')[:20]:20} {tenant[3]:>10,}")

        print(f"{'='*70}\n")

    except Exception as e:
        print(f"❌ Error listando tenants: {str(e)}")


def vacuum_tables(db: Session):
    """Ejecuta VACUUM en las tablas de documentos para recuperar espacio"""
    print("\n🧹 Ejecutando VACUUM en tablas de documentos...")

    tables = [
        'documents', 'document_analyses', 'document_views',
        'document_shares', 'document_metrics', 'document_tags',
        'indexed_documents', 'channel_documents'
    ]

    # VACUUM requiere autocommit
    connection = engine.connect()
    connection.execute(text("COMMIT"))

    for table in tables:
        try:
            connection.execute(text(f"VACUUM ANALYZE {table}"))
            print(f"   ✅ {table}: VACUUM completado")
        except Exception as e:
            print(f"   ⚠️  {table}: {str(e)}")

    connection.close()
    print("✅ VACUUM completado")


def main():
    parser = argparse.ArgumentParser(
        description='Herramienta de limpieza de documentos para NouxCubeIA',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python scripts/clean_documents.py --stats
  python scripts/clean_documents.py --list-tenants
  python scripts/clean_documents.py --clean-db --confirm
  python scripts/clean_documents.py --clean-db --tenant abc123 --confirm
  python scripts/clean_documents.py --clean-weaviate --confirm
  python scripts/clean_documents.py --clean-all --confirm
        """
    )

    parser.add_argument('--stats', action='store_true',
                        help='Mostrar estadísticas de tablas de documentos')
    parser.add_argument('--list-tenants', action='store_true',
                        help='Listar tenants y sus documentos')
    parser.add_argument('--clean-db', action='store_true',
                        help='Limpiar tablas de documentos en PostgreSQL')
    parser.add_argument('--clean-weaviate', action='store_true',
                        help='Limpiar colecciones de Weaviate')
    parser.add_argument('--clean-all', action='store_true',
                        help='Limpiar tanto PostgreSQL como Weaviate')
    parser.add_argument('--vacuum', action='store_true',
                        help='Ejecutar VACUUM después de limpiar')
    parser.add_argument('--tenant', type=str,
                        help='ID del tenant a limpiar (opcional)')
    parser.add_argument('--confirm', action='store_true',
                        help='Confirmar acciones destructivas')

    args = parser.parse_args()

    if not any([args.stats, args.list_tenants, args.clean_db, args.clean_weaviate, args.clean_all]):
        parser.print_help()
        return

    # Obtener sesión de base de datos
    db_gen = get_db()
    db = next(db_gen)

    try:
        if args.stats:
            stats = get_document_tables_stats(db)
            print_stats(stats)

        if args.list_tenants:
            list_tenants(db)

        if args.clean_db or args.clean_all:
            clean_document_related_tables(db, args.tenant, args.confirm)

            if args.vacuum and args.confirm:
                vacuum_tables(db)

        if args.clean_weaviate or args.clean_all:
            clean_weaviate_collections(args.tenant, args.confirm)

    finally:
        db.close()


if __name__ == "__main__":
    main()
