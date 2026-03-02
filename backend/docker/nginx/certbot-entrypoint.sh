#!/bin/sh
# Certbot sidecar entrypoint.
# Obtains/renews Let's Encrypt certificates and copies them to the shared
# certificate directory used by tls-proxy and KeyCloak.
#
# Behaviour:
#   1. Wait for nginx to serve port 80 (HTTP-01 challenge needs it)
#   2. If LE cert already exists → attempt renewal
#   3. If no LE cert → request a new one (certbot certonly --webroot)
#   4. On success → deploy hook copies certs + signals nginx reload
#   5. On failure → self-signed certs remain untouched (graceful fallback)
#   6. Sleep 12 hours, then loop (certbot only renews if <30 days remain)

set -eu

: "${CERTBOT_DOMAIN:?CERTBOT_DOMAIN is required}"
: "${CERTBOT_EMAIL:?CERTBOT_EMAIL is required}"
: "${CERTBOT_STAGING:=false}"

LIVE_DIR="/etc/letsencrypt/live/${CERTBOT_DOMAIN}"
DEPLOY_HOOK="/opt/certbot/deploy-hook.sh"

# --- Wait for nginx to be reachable on port 80 ---
echo "[certbot] Waiting for nginx (tls-proxy) on port 80..."
tries=0
max_tries=60
while [ $tries -lt $max_tries ]; do
  if wget -q --spider "http://tls-proxy:80/.well-known/acme-challenge/" 2>/dev/null; then
    echo "[certbot] nginx is ready."
    break
  fi
  tries=$((tries + 1))
  sleep 5
done
if [ $tries -eq $max_tries ]; then
  echo "[certbot] WARNING: nginx not reachable after ${max_tries} attempts. Proceeding anyway..."
fi

# --- Build certbot flags ---
STAGING_FLAG=""
if [ "$CERTBOT_STAGING" = "true" ]; then
  STAGING_FLAG="--staging"
  echo "[certbot] Using Let's Encrypt STAGING environment (test certs)."
fi

# --- Main loop ---
while true; do
  if [ -d "$LIVE_DIR" ]; then
    # Certificate exists — attempt renewal
    echo "[certbot] Existing certificate found. Attempting renewal..."
    certbot renew \
      --webroot -w /var/www/certbot \
      --deploy-hook "$DEPLOY_HOOK" \
      --quiet \
      $STAGING_FLAG \
      || echo "[certbot] WARNING: Renewal failed. Will retry in 12 hours."
  else
    # No certificate — request a new one
    echo "[certbot] No certificate found for ${CERTBOT_DOMAIN}. Requesting new certificate..."
    certbot certonly \
      --webroot -w /var/www/certbot \
      -d "$CERTBOT_DOMAIN" \
      --email "$CERTBOT_EMAIL" \
      --agree-tos \
      --no-eff-email \
      --non-interactive \
      $STAGING_FLAG \
      && {
        echo "[certbot] Certificate obtained successfully!"
        # Run deploy hook manually after first issuance
        sh "$DEPLOY_HOOK"
      } \
      || echo "[certbot] WARNING: Certificate request failed. Self-signed certs remain active."
  fi

  echo "[certbot] Next renewal check in 12 hours."
  sleep 43200
done
