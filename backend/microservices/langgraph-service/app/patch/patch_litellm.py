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
            lines = f.readlines()
        
        # Buscar y reemplazar el método problemático línea por línea
        modified = False
        for i, line in enumerate(lines):
            # Buscar la línea del método close
            if 'async def close(self):' in line:
                # Encontrar el índice de la siguiente línea
                if i + 1 < len(lines) and 'await self.client.aclose()' in lines[i + 1]:
                    # Reemplazar las líneas problemáticas
                    indent = len(lines[i]) - len(lines[i].lstrip())
                    lines[i] = ' ' * indent + 'async def close(self):\n'
                    lines[i + 1] = ' ' * (indent + 4) + 'try:\n'
                    lines.insert(i + 2, ' ' * (indent + 8) + 'if hasattr(self, "client") and self.client is not None:\n')
                    lines.insert(i + 3, ' ' * (indent + 12) + 'await self.client.aclose()\n')
                    lines.insert(i + 4, ' ' * (indent + 4) + 'except (AttributeError, RuntimeError):\n')
                    lines.insert(i + 5, ' ' * (indent + 8) + 'pass\n')
                    modified = True
                    break
        
        if modified:
            # Escribir el archivo modificado
            with open(handler_file, 'w') as f:
                f.writelines(lines)
            
            print("✅ Archivo litellm parcheado exitosamente")
            return True
        else:
            print("⚠️ No se encontró el código a reemplazar en litellm")
            return False
            
    except Exception as e:
        print(f"❌ Error parcheando archivo: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    patch_litellm_source()