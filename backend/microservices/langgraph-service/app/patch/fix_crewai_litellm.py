"""
Parche robusto para litellm 1.72.0 sin dependencias problemáticas
"""

def apply_patch():
    """Aplica el parche de forma robusta"""
    try:
        # Importar el módulo específico
        import litellm.llms.custom_httpx.http_handler as handler
        
        # Verificar si ya está parcheado
        if hasattr(handler.AsyncHTTPHandler, '_is_patched'):
            return True
        
        # Crear el nuevo método close
        async def safe_close(self):
            """Método close seguro que no falla"""
            # No hacer nada - evitar el error completamente
            pass
        
        # Reemplazar el método
        handler.AsyncHTTPHandler.close = safe_close
        handler.AsyncHTTPHandler._is_patched = True
        
        print("✅ Parche aplicado exitosamente")
        return True
        
    except Exception as e:
        print(f"❌ Error aplicando parche: {e}")
        return False

# Aplicar inmediatamente al importar
apply_patch()