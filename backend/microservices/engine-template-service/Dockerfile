FROM python:3.9-slim

WORKDIR /app

# Install FastAPI and requirements
COPY requirements.txt .
RUN pip install fastapi uvicorn
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code
COPY app ./app

# Expose port
EXPOSE 8000

# Run app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
