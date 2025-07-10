#!/bin/bash
# Qdrant startup script
apt-get update
apt-get install -y docker.io docker-compose
systemctl start docker
systemctl enable docker

# Create Qdrant directory
mkdir -p /opt/qdrant/storage

# Create docker-compose file
cat > /opt/qdrant/docker-compose.yml << 'EOF'
version: "3.8"
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - ./storage:/qdrant/storage
    environment:
      - QDRANT__LOG_LEVEL=INFO
      - QDRANT__SERVICE__HTTP_PORT=6333
      - QDRANT__SERVICE__GRPC_PORT=6334
    restart: always
    mem_limit: 1g
EOF

# Start Qdrant
cd /opt/qdrant && docker-compose up -d

# Wait for Qdrant to be ready
sleep 30

# Create collections for NexusDocs360
curl -X PUT "http://localhost:6333/collections/documents" \
  -H "Content-Type: application/json" \
  -d '{"vectors": {"size": 1536, "distance": "Cosine"}}'

echo "Qdrant setup complete"