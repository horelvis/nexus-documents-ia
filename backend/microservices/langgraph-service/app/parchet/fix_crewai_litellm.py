"""
Parche para el bug de litellm 1.72.0 usado por CrewAI 0.130.0
"""
import litellm.llms.custom_httpx.http_handler as handler

# Guardar el método original
original_close = handler.AsyncHTTPHandler.close

async def patched_close(self):
    """Versión parcheada del método close para evitar AttributeError"""
    try:
        # Verificar múltiples posibles nombres de atributo
        client = None
        for attr_name in ['client', '_client', 'http_client', '_http_client']:
            if hasattr(self, attr_name):
                client = getattr(self, attr_name)
                if client is not None:
                    break
        
        if client is not None and hasattr(client, 'aclose'):
            await client.aclose()
    except (AttributeError, RuntimeError, Exception):
        # Ignorar todos los errores relacionados con el cierre
        pass

# Aplicar el parche
handler.AsyncHTTPHandler.close = patched_close

print("✅ Parche aplicado para litellm 1.72.0 / CrewAI 0.130.0")