FROM gotenberg/gotenberg:edge

USER root

# Install Python and dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Copy start script
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Create app user and fix permissions
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app

USER app

# Expose ports (Gotenberg on 3000, FastAPI on 8005)
EXPOSE 3000 8005

CMD ["/start.sh"]