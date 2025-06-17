"""
Parche para litellm 1.72.0 - Debe llamarse explícitamente
"""
import sys

def apply_litellm_patch():
    """Aplica el parche para el bug de AsyncHTTPHandler"""
    try:
        # Importar solo si litellm está disponible
        import litellm.llms.custom_httpx.http_handler as handler
        
        # Verificar si ya está parcheado
        if hasattr(handler.AsyncHTTPHandler.close, '_patched'):
            print("✅ Parche ya aplicado")
            return True
        
        # Guardar método original
        original_close = handler.AsyncHTTPHandler.close
        
        async def patched_close(self):
            """Versión parcheada del close"""
            try:
                # Buscar el cliente HTTP
                client = getattr(self, 'client', None)
                if client is None:
                    client = getattr(self, '_client', None)
                
                if client is not None and hasattr(client, 'aclose'):
                    await client.aclose()
            except Exception:
                # Ignorar cualquier error durante el cierre
                pass
        
        # Marcar como parcheado
        patched_close._patched = True
        
        # Aplicar el parche
        handler.AsyncHTTPHandler.close = patched_close
        
        print("✅ Parche litellm aplicado exitosamente")
        return True
        
    except ImportError:
        print("⚠️  litellm no disponible")
        return False
    except Exception as e:
        print(f"❌ Error aplicando parche: {e}")
        return False

# Auto-aplicar si se importa directamente
if __name__ == "__main__":
    apply_litellm_patch()