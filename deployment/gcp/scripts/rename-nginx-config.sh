#!/bin/bash
# Renombrar configuración de nginx de nexusdocs360-simple a nexusdocs360

set -e

echo "🔧 Renombrando configuración de nginx"
echo "==================================="
echo ""

# 1. Verificar estado actual
echo "1️⃣ Estado actual:"
echo "Sites available:"
ls -la /etc/nginx/sites-available/ | grep nexusdocs
echo ""
echo "Sites enabled:"
ls -la /etc/nginx/sites-enabled/ | grep nexusdocs
echo ""

# 2. Copiar el archivo con el nuevo nombre
echo "2️⃣ Copiando configuración..."
sudo cp /etc/nginx/sites-available/nexusdocs360-simple /etc/nginx/sites-available/nexusdocs360

# 3. Eliminar el enlace antiguo
echo "3️⃣ Eliminando enlace antiguo..."
sudo rm -f /etc/nginx/sites-enabled/nexusdocs360-simple

# 4. Crear nuevo enlace
echo "4️⃣ Creando nuevo enlace..."
sudo ln -sf /etc/nginx/sites-available/nexusdocs360 /etc/nginx/sites-enabled/nexusdocs360

# 5. Verificar
echo "5️⃣ Verificando configuración..."
if sudo nginx -t; then
    echo "✅ Configuración válida"
    
    # 6. Recargar nginx
    echo ""
    echo "6️⃣ Recargando nginx..."
    sudo systemctl reload nginx
    
    # 7. Eliminar archivo antiguo
    echo ""
    echo "7️⃣ Limpiando archivos antiguos..."
    sudo rm -f /etc/nginx/sites-available/nexusdocs360-simple
    
    echo ""
    echo "✅ Configuración renombrada exitosamente!"
else
    echo "❌ Error en configuración"
    # Revertir cambios
    echo "Revirtiendo cambios..."
    sudo rm -f /etc/nginx/sites-enabled/nexusdocs360
    sudo ln -sf /etc/nginx/sites-available/nexusdocs360-simple /etc/nginx/sites-enabled/nexusdocs360-simple
    exit 1
fi

# 8. Mostrar estado final
echo ""
echo "8️⃣ Estado final:"
echo "Sites available:"
ls -la /etc/nginx/sites-available/ | grep nexusdocs || echo "No files found"
echo ""
echo "Sites enabled:"
ls -la /etc/nginx/sites-enabled/ | grep nexusdocs || echo "No files found"

# 9. Test
echo ""
echo "9️⃣ Probando servicios..."
echo "API:"
curl -s https://pre-api.nexusdocs360.app/health
echo ""
echo "Frontend:"
curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" https://pre.nexusdocs360.app/