#!/bin/bash
# Ver la configuración activa de nginx

echo "📋 Configuración Activa de Nginx"
echo "================================"
echo ""

# 1. Ver qué archivo está activo
echo "1️⃣ Sitios habilitados:"
echo "---------------------"
ls -la /etc/nginx/sites-enabled/
echo ""

# 2. Ver el contenido del archivo activo
echo "2️⃣ Configuración activa:"
echo "------------------------"
for file in /etc/nginx/sites-enabled/*; do
    if [ -f "$file" ]; then
        echo "📄 Archivo: $file"
        echo "------------------------"
        sudo cat "$file"
        echo ""
    fi
done

# 3. Verificar que la configuración es válida
echo "3️⃣ Validación de configuración:"
echo "-------------------------------"
sudo nginx -t
echo ""

# 4. Ver qué puertos está escuchando nginx
echo "4️⃣ Puertos en uso por nginx:"
echo "----------------------------"
sudo ss -tlnp | grep nginx
echo ""

# 5. Ver el proceso nginx
echo "5️⃣ Procesos nginx activos:"
echo "--------------------------"
ps aux | grep nginx | grep -v grep
echo ""

# 6. Ver configuración principal
echo "6️⃣ Configuración principal (nginx.conf):"
echo "----------------------------------------"
sudo grep -E "include|server_names_hash" /etc/nginx/nginx.conf | grep -v "#"