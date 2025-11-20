FROM python:3.11-slim

WORKDIR /app

# Install system dependencies required by unstructured
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    poppler-utils \
    pandoc \
    tesseract-ocr \
    libtesseract-dev \
    libmagic1 \
    libmagic-dev \
    ffmpeg \
    libxml2 \
    libxslt1.1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
ENV PIP_DEFAULT_TIMEOUT=120 \
    PIP_RETRIES=5 \
    PIP_NO_CACHE_DIR=1 \
    ONNX_DISABLE_GPU=1 \
    NLTK_DATA=/app/nltk_data
RUN pip install --prefer-binary -r requirements.txt

# Copy application code
COPY app/ ./app/

# Pre-install NLTK data required by unstructured to avoid runtime downloads
RUN python -c "from app.core.nltk_bootstrap import prepare_nltk_data; prepare_nltk_data()"

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
