FROM python:3.11-slim

WORKDIR /app/backend

# Copy shared requirements
COPY requirements.txt .

# Copy worker requirements
COPY microservices/background-worker/requirements.txt microservices/background-worker/

# Install dependencies
RUN pip install --no-cache-dir -r microservices/background-worker/requirements.txt

# Copy shared app code
COPY app app

# Copy worker code
COPY microservices/background-worker microservices/background-worker

ENV PYTHONPATH=/app/backend
WORKDIR /app/backend/microservices/background-worker
RUN chmod +x start.sh

EXPOSE 8100
CMD ["./start.sh"]