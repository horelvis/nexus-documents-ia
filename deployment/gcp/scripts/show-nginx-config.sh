#!/bin/bash
# Show nginx configuration

echo "📋 Nginx Configuration"
echo "===================="
echo ""

# Show active sites
echo "1️⃣ Active sites:"
echo "---------------"
ls -la /etc/nginx/sites-enabled/
echo ""

# Show main configuration
echo "2️⃣ Main nginx config (/etc/nginx/nginx.conf):"
echo "--------------------------------------------"
sudo cat /etc/nginx/nginx.conf | grep -v "^#" | grep -v "^$" | head -20
echo "..."
echo ""

# Show site configuration
echo "3️⃣ Site configuration (/etc/nginx/sites-enabled/nexusdocs360):"
echo "-------------------------------------------------------------"
if [ -f /etc/nginx/sites-enabled/nexusdocs360 ]; then
    sudo cat /etc/nginx/sites-enabled/nexusdocs360
else
    echo "File not found!"
    echo "Checking sites-available:"
    ls -la /etc/nginx/sites-available/
fi
echo ""

# Test configuration
echo "4️⃣ Configuration test:"
echo "--------------------"
sudo nginx -t
echo ""

# Show nginx status
echo "5️⃣ Nginx status:"
echo "---------------"
sudo systemctl status nginx --no-pager | head -10
echo ""

# Show recent error logs
echo "6️⃣ Recent error logs:"
echo "-------------------"
sudo tail -5 /var/log/nginx/error.log 2>/dev/null || echo "No recent errors"
echo ""

# Show certificates
echo "7️⃣ SSL Certificates:"
echo "------------------"
sudo ls -la /etc/letsencrypt/live/ 2>/dev/null || echo "No certificates found"