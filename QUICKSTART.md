# Quick Start Guide

## Get Started in 3 Steps

### 1. Deploy with Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/jaimemachado/ocr-service.git
cd ocr-service

# Start the service
docker-compose up --build

# Service will be available at http://localhost:8000
```

### 2. Test the Service

```bash
# Process a PDF (adds searchable text layer)
curl -X POST "http://localhost:8000/process-pdf" \
  -F "file=@your-document.pdf" \
  -o output.pdf

# Extract text from PDF (returns JSON)
curl -X POST "http://localhost:8000/extract-text" \
  -F "file=@your-document.pdf"
```

### 3. View API Documentation

Open in your browser:
- **Interactive API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

---

## Alternative: Local Installation

```bash
# Install system dependencies (Ubuntu/Debian)
sudo apt-get install -y poppler-utils tesseract-ocr ghostscript

# Install Python dependencies
pip install -r requirements.txt

# Run the service
python main.py
```

---

## Use with Python

```python
import requests

# Process PDF
with open("document.pdf", "rb") as f:
    response = requests.post(
        "http://localhost:8000/process-pdf",
        files={"file": f}
    )
    
with open("output.pdf", "wb") as f:
    f.write(response.content)

print("PDF processed with embedded text layer!")
```

---

## Integration with Paperless-ngx

1. Start OCR service: `docker-compose up -d`
2. Configure Paperless to use `http://ocr-service:8000/process-pdf` as pre-processor
3. PDFs will be automatically processed before import
4. Paperless will detect text and skip its own OCR

---

## Key Features

✅ Two endpoints: `/process-pdf` and `/extract-text`
✅ GPU acceleration (automatic if available)
✅ Secure file handling with automatic cleanup
✅ Input validation (100MB limit, 72-600 DPI)
✅ Production-ready with Docker
✅ Zero security vulnerabilities

---

## Documentation

- **[README.md](README.md)** - Full documentation
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Technical architecture
- **[IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)** - Implementation details

---

## Support

- View logs: `docker-compose logs -f`
- Check health: `curl http://localhost:8000/health`
- Example script: `python example.py process your-file.pdf`

---

**Ready to use! 🚀**
