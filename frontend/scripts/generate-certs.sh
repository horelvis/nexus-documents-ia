#!/bin/bash

# Create certificates directory
mkdir -p certificates

# Generate self-signed certificate for localhost
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout certificates/localhost-key.pem \
  -out certificates/localhost.pem \
  -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"

echo "SSL certificates generated in ./certificates/"
echo "- localhost.pem (certificate)"
echo "- localhost-key.pem (private key)"