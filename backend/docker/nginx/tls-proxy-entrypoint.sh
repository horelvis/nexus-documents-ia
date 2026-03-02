#!/bin/sh
# Custom entrypoint for tls-proxy (nginx).
# Starts nginx in the foreground and polls for a reload trigger file
# created by the certbot sidecar after certificate renewal.
#
# Why polling instead of inotifywait?
#   - Zero extra dependencies (nginx:alpine has no inotify-tools)
#   - 30s polling is perfectly fine for cert renewals (happens every ~60 days)

set -eu

TRIGGER="/var/www/certbot/.reload"

# Ensure the webroot directory exists (even without the certbot profile)
mkdir -p /var/www/certbot

# Background loop: watch for reload trigger
(
  while true; do
    sleep 30
    if [ -f "$TRIGGER" ]; then
      echo "[tls-proxy] Certificate change detected, reloading nginx..."
      nginx -s reload && rm -f "$TRIGGER"
    fi
  done
) &

# Start nginx in the foreground (PID 1)
exec nginx -g 'daemon off;'
