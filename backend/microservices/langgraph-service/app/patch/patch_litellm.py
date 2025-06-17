"""
Parche directo que modifica el archivo fuente de litellm
"""
import os
import sys

def patch_litellm_source():
    """Modifica directamente el código fuente de litellm"""
    try:
        # Encontrar la ubicación del archivo
        import litellm.llms.custom_httpx.http_handler
        handler_file = litellm.llms.custom_httpx.http_handler.__file__
        
        print(f"📁 Parcheando archivo: {handler_file}")
        
        # Leer el archivo
        with open(handler_file, 'r') as f:
            content = f.read()
        
        # Buscar y reemplazar el método problemático
        old_close = """    async def close(self):
        await self.client.aclose()"""
        
        new_close = """    async def close(self):
        try:
            if hasattr(self, 'client') and self.client is not None:
                await self.client.aclose()
        except (AttributeError, RuntimeError):
            pass"""
        
        # Reemplazar
        if old_close in content:
            content = content.replace(old_close, new_close)
            
            # Escribir el archivo modificado
            with open(handler_file, 'w') as f:
                f.write(content)
            
            print("✅ Archivo litellm parcheado exitosamente")
            return True
        else:
            print("⚠️ No se encontró el código a reemplazar")
            return False
            
    except Exception as e:
        print(f"❌ Error parcheando archivo: {e}")
        return False

if __name__ == "__main__":
    patch_litellm_source()