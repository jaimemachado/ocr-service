# OCR Service

A FastAPI-based microservice for processing PDF files with OCR (Optical Character Recognition). This service uses docTR for text detection and recognition, and ocrmypdf to embed text layers into PDFs.

## Features

- 📄 **PDF Processing**: Upload and process PDF files with OCR
- 🔍 **Text Extraction**: Extract text and bounding boxes from PDFs using docTR
- 📝 **Text Layer Embedding**: Embed searchable text layer using ocrmypdf
- 🚀 **GPU Support**: Automatically uses GPU if available for faster processing
- 🐳 **Docker Ready**: Includes Docker and docker-compose configurations

## Requirements

### System Dependencies

- Python 3.11+
- Poppler (for PDF to image conversion)
- Tesseract OCR (for ocrmypdf)
- Ghostscript (for PDF manipulation)

### Python Dependencies

All Python dependencies are listed in `requirements.txt`:
- FastAPI
- Uvicorn
- python-doctr (for OCR)
- ocrmypdf (for text layer embedding)
- pdf2image (for PDF to image conversion)
- And more...

## Installation

### Option 1: Local Installation

1. Install system dependencies:

   **Ubuntu/Debian:**
   ```bash
   sudo apt-get update
   sudo apt-get install -y poppler-utils tesseract-ocr tesseract-ocr-eng ghostscript
   ```

   **macOS:**
   ```bash
   brew install poppler tesseract ghostscript
   ```

2. Create a virtual environment and install Python dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Run the service:
   ```bash
   python main.py
   ```
   
   Or using uvicorn directly:
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```

### Option 2: Docker

1. Build and run with docker-compose:
   ```bash
   docker-compose up --build
   ```

2. Or build and run with Docker directly:
   ```bash
   docker build -t ocr-service .
   docker run -p 8000:8000 ocr-service
   ```

## Usage

Once the service is running, you can access:
- **API Documentation**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

### API Endpoints

#### 1. Process PDF (Main Endpoint)

**POST** `/process-pdf`

Processes a PDF file with OCR and returns a PDF with embedded text layer (ready for Paperless).

**Parameters:**
- `file`: PDF file to process (multipart/form-data)
- `dpi`: Optional, resolution for conversion (default: 300)

**Example using curl:**
```bash
curl -X POST "http://localhost:8000/process-pdf" \
  -F "file=@document.pdf" \
  -o output.pdf
```

**Example using Python:**
```python
import requests

with open("document.pdf", "rb") as f:
    response = requests.post(
        "http://localhost:8000/process-pdf",
        files={"file": f}
    )
    
with open("output.pdf", "wb") as f:
    f.write(response.content)
```

#### 2. Extract Text Only

**POST** `/extract-text`

Extracts text and bounding boxes from PDF without modifying the original file.

**Parameters:**
- `file`: PDF file to process (multipart/form-data)
- `dpi`: Optional, resolution for conversion (default: 300)

**Returns:** JSON with extracted text and bounding boxes

**Example:**
```bash
curl -X POST "http://localhost:8000/extract-text" \
  -F "file=@document.pdf" \
  | jq .
```

**Response format:**
```json
{
  "filename": "document.pdf",
  "pages": [
    {
      "page_number": 1,
      "text": "Extracted text from page 1...",
      "blocks": [
        {
          "text": "word",
          "confidence": 0.95,
          "bbox": [[x1, y1], [x2, y2]]
        }
      ]
    }
  ],
  "full_text": "Complete text from all pages..."
}
```

## Integration with Paperless-ngx

This service is designed to work with Paperless-ngx by pre-processing PDFs with OCR:

1. Configure Paperless-ngx to use this service as a pre-processor
2. Send PDFs to this service first to add text layer
3. Paperless-ngx will detect the text layer and skip its own OCR

This approach is faster and can use GPU acceleration for better performance.

## Performance

- **CPU Mode**: Processes ~1-2 pages per second
- **GPU Mode**: Processes ~5-10 pages per second (depending on GPU)
- **Memory**: ~2-4GB RAM for typical documents

## Development

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio httpx

# Run tests
pytest
```

### Project Structure

```
ocr-service/
├── main.py              # FastAPI application
├── requirements.txt     # Python dependencies
├── Dockerfile          # Docker configuration
├── docker-compose.yml  # Docker Compose configuration
├── .gitignore         # Git ignore file
└── README.md          # This file
```

## How It Works

1. **Upload**: Client uploads a PDF file
2. **Save**: PDF is saved to temporary storage
3. **Convert**: PDF pages are converted to images using Poppler
4. **OCR**: docTR processes images to detect and recognize text
5. **Embed**: ocrmypdf embeds the text layer into the original PDF
6. **Return**: Processed PDF with searchable text is returned

## Troubleshooting

### GPU Not Detected

Make sure you have CUDA installed and PyTorch with CUDA support:
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

### Memory Issues

For large PDFs, consider:
- Reducing DPI (e.g., `dpi=200` instead of 300)
- Processing pages in batches
- Increasing Docker memory limits

### Poppler Not Found

Make sure Poppler is installed and in your PATH:
```bash
# Test poppler installation
pdftoppm -v
```

## License

MIT License

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.
