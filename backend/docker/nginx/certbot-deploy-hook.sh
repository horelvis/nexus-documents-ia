#!/bin/sh
# Deploy hook invoked by certbot after successful renewal/issuance.
# Copies the new certificates to the shared directory and signals nginx to reload.
#
# Certificate paths:
#   Source: /etc/letsencrypt/live/$CERTBOT_DOMAIN/{fullchain,privkey}.pem
#   Target: /certs/{cert,key}.pem  (bind-mounted from frontend/apps/on-premise/certificates/)
#
# This keeps the same cert.pem / key.pem filenames that tls-proxy and KeyCloak expect.

set -eu

: "${CERTBOT_DOMAIN:?CERTBOT_DOMAIN is required}"

LIVE_DIR="/etc/letsencrypt/live/${CERTBOT_DOMAIN}"
CERT_DIR="/certs"
TRIGGER="/var/www/certbot/.reload"

echo "[deploy-hook] Deploying new certificate for ${CERTBOT_DOMAIN}..."

# Backup existing certs (if any)
if [ -f "${CERT_DIR}/cert.pem" ]; then
  cp "${CERT_DIR}/cert.pem" "${CERT_DIR}/cert.pem.bak"
  cp "${CERT_DIR}/key.pem"  "${CERT_DIR}/key.pem.bak"
fi

# Copy Let's Encrypt certs to the shared directory
cp "${LIVE_DIR}/fullchain.pem" "${CERT_DIR}/cert.pem"
cp "${LIVE_DIR}/privkey.pem"   "${CERT_DIR}/key.pem"
chmod 644 "${CERT_DIR}/cert.pem"
chmod 600 "${CERT_DIR}/key.pem"

echo "[deploy-hook] Certificates deployed. Signaling nginx reload..."
touch "$TRIGGER"

echo "[deploy-hook] Done. KeyCloak will pick up new certs on next restart."
