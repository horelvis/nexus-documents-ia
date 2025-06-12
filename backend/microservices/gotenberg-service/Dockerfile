FROM gotenberg/gotenberg:8

# Install Python and dependencies
USER root
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    poppler-utils \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create a virtual environment
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Copy start script
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Create app user and fix permissions
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app /opt/venv

USER app

# Expose ports (Gotenberg on 3000, FastAPI on 8005)
EXPOSE 3000 8005

CMD ["/start.sh"]