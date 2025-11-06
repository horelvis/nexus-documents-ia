#!/bin/bash
# Check nginx status and configuration

echo "🔍 Checking Nginx Status"
echo "======================="
echo ""

# Check if nginx is running
echo "1️⃣ Nginx service status:"
sudo systemctl status nginx | head -10

echo ""
echo "2️⃣ Nginx configuration test:"
sudo nginx -t

echo ""
echo "3️⃣ Enabled sites:"
ls -la /etc/nginx/sites-enabled/

echo ""
echo "4️⃣ Nginx error log (last 20 lines):"
sudo tail -20 /var/log/nginx/error.log

echo ""
echo "5️⃣ Current nginx configuration for pre.nexusdocs360.app:"
if [ -f /etc/nginx/sites-enabled/pre.nexusdocs360.app ]; then
    sudo cat /etc/nginx/sites-enabled/pre.nexusdocs360.app
else
    echo "❌ Configuration file not found"
fi

echo ""
echo "6️⃣ Current nginx configuration for pre-api.nexusdocs360.app:"
if [ -f /etc/nginx/sites-enabled/pre-api.nexusdocs360.app ]; then
    sudo cat /etc/nginx/sites-enabled/pre-api.nexusdocs360.app
else
    echo "❌ Configuration file not found"
fi

echo ""
echo "7️⃣ Checking DNS resolution from server:"
echo "Frontend: $(dig +short pre.nexusdocs360.app)"
echo "API: $(dig +short pre-api.nexusdocs360.app)"

echo ""
echo "8️⃣ Testing Cloud Run URLs from nginx server:"
echo -n "Backend direct: "
curl -s -o /dev/null -w "%{http_code}" https://nexus-backend-pre-300252412370.europe-west1.run.app/health || echo "failed"
echo -n "Frontend direct: "
curl -s -o /dev/null -w "%{http_code}" https://nexus-frontend-pre-300252412370.europe-west1.run.app/ || echo "failed"