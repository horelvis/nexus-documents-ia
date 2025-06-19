#!/usr/bin/env python3
"""
Utilidades para gestionar migraciones de Alembic y prevenir múltiples cabezas
"""
import os
import sys
import re
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import subprocess
import json

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class AlembicMigrationManager:
    """Gestor de migraciones de Alembic con prevención de múltiples cabezas"""
    
    def __init__(self, alembic_dir: str = "alembic/versions"):
        self.alembic_dir = Path(alembic_dir)
        if not self.alembic_dir.exists():
            raise ValueError(f"Directory {alembic_dir} does not exist")
    
    def get_all_migrations(self) -> Dict[str, Dict[str, str]]:
        """Obtiene todas las migraciones y su información"""
        migrations = {}
        
        for file_path in self.alembic_dir.glob("*.py"):
            if file_path.name == "__pycache__":
                continue
                
            with open(file_path, 'r') as f:
                content = f.read()
                
            # Extraer revision y down_revision
            revision_match = re.search(r"revision\s*=\s*['\"]([^'\"]+)['\"]", content)
            down_revision_match = re.search(r"down_revision\s*=\s*['\"]([^'\"]+)['\"]", content)
            
            # Manejar down_revision como tupla (merge migrations)
            if not down_revision_match:
                down_revision_match = re.search(r"down_revision\s*=\s*\(([^)]+)\)", content)
                if down_revision_match:
                    # Limpiar y parsear la tupla
                    down_revisions = [
                        rev.strip().strip("'\"") 
                        for rev in down_revision_match.group(1).split(',')
                    ]
                else:
                    down_revision_match = re.search(r"down_revision\s*=\s*None", content)
                    down_revisions = None if down_revision_match else []
            else:
                down_revisions = down_revision_match.group(1)
            
            if revision_match:
                migrations[revision_match.group(1)] = {
                    'file': file_path.name,
                    'down_revision': down_revisions,
                    'path': str(file_path)
                }
        
        return migrations
    
    def find_heads(self) -> List[str]:
        """Encuentra todas las cabezas (migraciones sin hijos)"""
        migrations = self.get_all_migrations()
        
        # Encontrar todos los down_revisions
        all_down_revisions = set()
        for migration in migrations.values():
            down_rev = migration['down_revision']
            if down_rev:
                if isinstance(down_rev, list):
                    all_down_revisions.update(down_rev)
                else:
                    all_down_revisions.add(down_rev)
        
        # Las cabezas son revisiones que no son down_revision de nadie
        heads = [rev for rev in migrations.keys() if rev not in all_down_revisions]
        
        return heads
    
    def get_migration_chain(self, start_revision: Optional[str] = None) -> List[Tuple[str, str]]:
        """Obtiene la cadena de migraciones desde una revisión inicial"""
        migrations = self.get_all_migrations()
        chain = []
        
        # Encontrar la migración inicial si no se especifica
        if not start_revision:
            for rev, info in migrations.items():
                if info['down_revision'] is None:
                    start_revision = rev
                    break
        
        # Construir la cadena
        current = start_revision
        visited = set()
        
        while current and current not in visited:
            visited.add(current)
            chain.append((current, migrations.get(current, {}).get('file', 'unknown')))
            
            # Encontrar la siguiente migración
            next_rev = None
            for rev, info in migrations.items():
                down_rev = info['down_revision']
                if down_rev == current or (isinstance(down_rev, list) and current in down_rev):
                    next_rev = rev
                    break
            
            current = next_rev
        
        return chain
    
    def detect_problems(self) -> Dict[str, any]:
        """Detecta problemas en las migraciones"""
        problems = {
            'multiple_heads': [],
            'orphan_migrations': [],
            'circular_dependencies': [],
            'missing_dependencies': []
        }
        
        migrations = self.get_all_migrations()
        heads = self.find_heads()
        
        # Detectar múltiples cabezas
        if len(heads) > 1:
            problems['multiple_heads'] = heads
        
        # Detectar migraciones huérfanas
        for rev, info in migrations.items():
            down_rev = info['down_revision']
            if down_rev and down_rev != 'None':
                if isinstance(down_rev, list):
                    for dr in down_rev:
                        if dr not in migrations:
                            problems['missing_dependencies'].append({
                                'revision': rev,
                                'missing': dr
                            })
                elif down_rev not in migrations:
                    problems['missing_dependencies'].append({
                        'revision': rev,
                        'missing': down_rev
                    })
        
        return problems
    
    def create_migration(self, message: str, depends_on: Optional[str] = None) -> str:
        """Crea una nueva migración con las dependencias correctas"""
        # Si no se especifica dependencia, usar la cabeza actual
        if not depends_on:
            heads = self.find_heads()
            if len(heads) == 1:
                depends_on = heads[0]
            elif len(heads) > 1:
                raise ValueError(f"Multiple heads found: {heads}. Please specify which one to depend on.")
            else:
                depends_on = None
        
        # Generar nombre de archivo
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_message = re.sub(r'[^\w\s-]', '', message).strip().replace(' ', '_')
        filename = f"{timestamp}_{safe_message}.py"
        
        # Generar ID de revisión único
        revision_id = f"{safe_message}_{timestamp}"
        
        # Template de migración
        template = f'''"""
{message}

Revision ID: {revision_id}
Revises: {depends_on if depends_on else 'None'}
Create Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '{revision_id}'
down_revision = {'"{}"'.format(depends_on) if depends_on else 'None'}
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Apply migration"""
    # TODO: Add upgrade operations here
    pass


def downgrade() -> None:
    """Revert migration"""
    # TODO: Add downgrade operations here
    pass
'''
        
        # Escribir archivo
        file_path = self.alembic_dir / filename
        with open(file_path, 'w') as f:
            f.write(template)
        
        print(f"Created migration: {file_path}")
        print(f"Revision ID: {revision_id}")
        print(f"Depends on: {depends_on if depends_on else 'None'}")
        
        return str(file_path)
    
    def fix_multiple_heads(self, target_head: Optional[str] = None) -> bool:
        """Intenta arreglar el problema de múltiples cabezas"""
        heads = self.find_heads()
        
        if len(heads) <= 1:
            print("No multiple heads detected.")
            return True
        
        print(f"Found {len(heads)} heads: {heads}")
        
        if not target_head:
            # Intentar determinar la cabeza principal basándose en las fechas
            migrations = self.get_all_migrations()
            latest_head = None
            latest_date = None
            
            for head in heads:
                file_name = migrations[head]['file']
                # Extraer fecha del nombre del archivo si es posible
                date_match = re.match(r'(\d{8})', file_name)
                if date_match:
                    date = date_match.group(1)
                    if not latest_date or date > latest_date:
                        latest_date = date
                        latest_head = head
            
            if latest_head:
                target_head = latest_head
                print(f"Using most recent head as target: {target_head}")
            else:
                print("Could not determine target head automatically.")
                return False
        
        # Crear migración de merge
        other_heads = [h for h in heads if h != target_head]
        merge_message = f"merge heads {', '.join(other_heads)} into {target_head}"
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        revision_id = f"merge_{timestamp}"
        filename = f"{timestamp}_merge_heads.py"
        
        template = f'''"""
{merge_message}

Revision ID: {revision_id}
Revises: {', '.join(heads)}
Create Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '{revision_id}'
down_revision = {tuple(heads) if len(heads) > 1 else f'"{heads[0]}"'}
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Merge migration - no operations needed"""
    pass


def downgrade() -> None:
    """Merge migration - no operations needed"""
    pass
'''
        
        file_path = self.alembic_dir / filename
        with open(file_path, 'w') as f:
            f.write(template)
        
        print(f"Created merge migration: {file_path}")
        return True
    
    def visualize_chain(self) -> None:
        """Visualiza la cadena de migraciones"""
        migrations = self.get_all_migrations()
        
        print("\n=== Migration Chain ===")
        
        # Encontrar raíces
        roots = []
        for rev, info in migrations.items():
            if info['down_revision'] is None:
                roots.append(rev)
        
        if not roots:
            print("No root migrations found!")
            return
        
        # Para cada raíz, mostrar su cadena
        for root in roots:
            print(f"\nStarting from root: {root}")
            self._print_chain(root, migrations, indent=0)
    
    def _print_chain(self, revision: str, migrations: Dict, indent: int, visited: Optional[set] = None):
        """Imprime recursivamente la cadena de migraciones"""
        if visited is None:
            visited = set()
        
        if revision in visited:
            print("  " * indent + f"└─ (circular reference to {revision})")
            return
        
        visited.add(revision)
        
        info = migrations.get(revision, {})
        print("  " * indent + f"└─ {revision} ({info.get('file', 'unknown')})")
        
        # Encontrar hijos
        children = []
        for rev, child_info in migrations.items():
            down_rev = child_info['down_revision']
            if down_rev == revision or (isinstance(down_rev, list) and revision in down_rev):
                children.append(rev)
        
        for child in children:
            self._print_chain(child, migrations, indent + 1, visited.copy())


def main():
    """Función principal para uso desde línea de comandos"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Alembic migration management utilities')
    parser.add_argument('command', choices=['check', 'create', 'fix', 'visualize'],
                       help='Command to execute')
    parser.add_argument('--message', '-m', help='Migration message (for create command)')
    parser.add_argument('--depends-on', '-d', help='Revision to depend on (for create command)')
    parser.add_argument('--target-head', '-t', help='Target head for merge (for fix command)')
    
    args = parser.parse_args()
    
    manager = AlembicMigrationManager()
    
    if args.command == 'check':
        problems = manager.detect_problems()
        if any(problems.values()):
            print("Problems detected:")
            for problem_type, issues in problems.items():
                if issues:
                    print(f"\n{problem_type}:")
                    print(json.dumps(issues, indent=2))
        else:
            print("No problems detected!")
    
    elif args.command == 'create':
        if not args.message:
            print("Error: --message is required for create command")
            sys.exit(1)
        manager.create_migration(args.message, args.depends_on)
    
    elif args.command == 'fix':
        success = manager.fix_multiple_heads(args.target_head)
        if success:
            print("Fix applied successfully!")
        else:
            print("Could not fix automatically. Manual intervention required.")
            sys.exit(1)
    
    elif args.command == 'visualize':
        manager.visualize_chain()


if __name__ == '__main__':
    main()