FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install OS dependencies
COPY requirements.txt .
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    poppler-utils \
    libmagic1 \
    libmagic-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application package
COPY app/ ./app/

# Expose port
EXPOSE 8003

# Run
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]