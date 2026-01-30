FROM python:3.11-slim-bullseye

# Install system dependencies for Poppler, Tesseract, and other requirements
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        poppler-utils \
        tesseract-ocr \
        tesseract-ocr-eng \
        ghostscript \
        libgl1 \
        libglu1-mesa \
        libx11-6 \
        libxext6 \
        libsm6 \
        libxrender1 \
        libglib2.0-0 \
        libcairo2 \
        libpango-1.0-0 \
        libgdk-pixbuf2.0-0 \
        libfontconfig1 \
        libfreetype6 \
        zlib1g \
        pkg-config \
        build-essential \
        libjpeg-dev \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
