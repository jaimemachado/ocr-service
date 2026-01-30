# OCR Service Architecture

## Service Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         OCR Service (FastAPI)                        │
│                         Port: 8000                                   │
└─────────────────────────────────────────────────────────────────────┘
```

## Endpoints

### 1. Process PDF Endpoint (`/process-pdf`)

**Purpose**: Create searchable PDFs for Paperless-ngx

```
┌────────────┐
│   Client   │
└─────┬──────┘
      │ POST /process-pdf
      │ (PDF file, DPI)
      ▼
┌─────────────────────────────────────────────┐
│          FastAPI Handler                    │
│  1. Validate file (PDF, <100MB)            │
│  2. Validate DPI (72-600)                  │
│  3. Save to temp storage                    │
└─────┬───────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────┐
│         ocrmypdf + Tesseract                │
│  1. Detect text in PDF pages                │
│  2. Recognize text with Tesseract          │
│  3. Embed text layer in PDF structure      │
│  4. Optimize output PDF                     │
└─────┬───────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────┐
│        File Response + Cleanup              │
│  1. Stream PDF to client                    │
│  2. Background task: cleanup temp files     │
└─────┬───────────────────────────────────────┘
      │
      ▼ PDF with embedded text layer
┌────────────┐
│   Client   │
└────────────┘
```

### 2. Extract Text Endpoint (`/extract-text`)

**Purpose**: Extract text with precise bounding boxes

```
┌────────────┐
│   Client   │
└─────┬──────┘
      │ POST /extract-text
      │ (PDF file, DPI)
      ▼
┌─────────────────────────────────────────────┐
│          FastAPI Handler                    │
│  1. Validate file (PDF, <100MB)            │
│  2. Validate DPI (72-600)                  │
│  3. Save to temp storage                    │
└─────┬───────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────┐
│         PDF to Image (Poppler)              │
│  Convert each page to high-res image        │
└─────┬───────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────┐
│         docTR OCR Engine                    │
│  1. Load images as DocumentFile             │
│  2. Detect text regions (blocks, lines)     │
│  3. Recognize text in each region          │
│  4. Extract bounding boxes (normalized)     │
│  5. Calculate confidence scores             │
└─────┬───────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────────────┐
│         JSON Response + Cleanup             │
│  1. Format: pages, text, bounding boxes    │
│  2. Background task: cleanup temp files     │
└─────┬───────────────────────────────────────┘
      │
      ▼ JSON with text and bounding boxes
┌────────────┐
│   Client   │
└────────────┘
```

## Component Details

### FastAPI Application Layer
- **Request validation**: File type, size, DPI range
- **Error handling**: Sanitized error messages
- **Logging**: INFO level for operations
- **Background tasks**: Automatic cleanup
- **Health checks**: `/` and `/health` endpoints

### OCR Engines

#### ocrmypdf (Tesseract)
- **Strengths**:
  - Optimized for creating searchable PDFs
  - Embeds text directly in PDF structure
  - Works on existing PDF pages
  - Supports deskewing and rotation
- **Used in**: `/process-pdf` endpoint
- **Output**: PDF with embedded text layer

#### docTR (PyTorch-based)
- **Strengths**:
  - High accuracy on complex layouts
  - Provides precise bounding boxes
  - GPU acceleration support
  - Modern deep learning architecture
- **Used in**: `/extract-text` endpoint
- **Output**: JSON with text and coordinates

### File Handling

```
Temporary File Lifecycle:
1. Upload → Secure temp directory (mkdtemp)
2. Process → Work in temp directory
3. Output → Secure temp file (NamedTemporaryFile)
4. Response → Stream to client
5. Cleanup → Background task deletes files
```

### Security Features

1. **Input Validation**
   - File type: Must be PDF
   - File size: Max 100MB
   - DPI: Range 72-600

2. **File Security**
   - Secure temp file creation (no race conditions)
   - Automatic cleanup (even on errors)
   - No sensitive data in error messages

3. **Resource Protection**
   - Size limits prevent DoS
   - DPI limits prevent memory exhaustion
   - Background cleanup prevents disk fill

## Docker Architecture

```
┌──────────────────────────────────────────────────┐
│         Docker Container                         │
│  ┌────────────────────────────────────────────┐ │
│  │  Python 3.11 Runtime                       │ │
│  │  ┌──────────────────────────────────────┐ │ │
│  │  │  System Dependencies:                │ │ │
│  │  │  • Poppler (PDF processing)          │ │ │
│  │  │  • Tesseract (OCR engine)            │ │ │
│  │  │  • Ghostscript (PDF manipulation)    │ │ │
│  │  │  • curl (health checks)              │ │ │
│  │  └──────────────────────────────────────┘ │ │
│  │  ┌──────────────────────────────────────┐ │ │
│  │  │  Python Packages:                    │ │ │
│  │  │  • FastAPI + Uvicorn                 │ │ │
│  │  │  • pdf2image                         │ │ │
│  │  │  • python-doctr[torch]               │ │ │
│  │  │  • ocrmypdf                          │ │ │
│  │  └──────────────────────────────────────┘ │ │
│  │  ┌──────────────────────────────────────┐ │ │
│  │  │  Application:                        │ │ │
│  │  │  main.py (FastAPI app)               │ │ │
│  │  └──────────────────────────────────────┘ │ │
│  └────────────────────────────────────────────┘ │
│                                                  │
│  Port: 8000 → Host: 8000                        │
│  Health Check: curl http://localhost:8000/health│
└──────────────────────────────────────────────────┘
```

## Integration with Paperless-ngx

```
┌─────────────────────┐
│   Document Source   │
│   (Scanner/Upload)  │
└──────────┬──────────┘
           │ PDF
           ▼
┌─────────────────────┐
│   OCR Service       │
│   (This Service)    │
│  /process-pdf       │
└──────────┬──────────┘
           │ PDF with text layer
           ▼
┌─────────────────────┐
│  Paperless-ngx      │
│  • Detects text     │
│  • Skips OCR        │
│  • Indexes document │
│  • Stores in DB     │
└─────────────────────┘
```

## Performance Characteristics

### CPU Mode
- **Speed**: ~1-2 pages/second
- **Memory**: 2-4GB RAM
- **Best for**: Small deployments, occasional use

### GPU Mode
- **Speed**: ~5-10 pages/second (depending on GPU)
- **Memory**: 2-4GB RAM + GPU memory
- **Best for**: High-volume processing, production

### Bottlenecks
1. **PDF to Image**: Poppler conversion (CPU-bound)
2. **OCR Processing**: 
   - docTR: GPU-accelerated if available
   - Tesseract: CPU-bound (multi-threaded)
3. **File I/O**: Disk speed for large files

## Configuration Options

### Environment Variables
- `HOST`: Server host (default: 0.0.0.0)
- `PORT`: Server port (default: 8000)
- `LOG_LEVEL`: Logging level (default: INFO)

### Code Constants (main.py)
- `MAX_FILE_SIZE`: 100MB (configurable)
- `MIN_DPI`: 72 (configurable)
- `MAX_DPI`: 600 (configurable)
- `DEFAULT_DPI`: 300 (configurable)

## Error Handling

```
Error Type          → HTTP Status → Client Message
─────────────────────────────────────────────────────
Not a PDF           → 400        → "File must be a PDF"
File too large      → 413        → "File too large. Max 100MB"
Invalid DPI         → 400        → "DPI must be between 72 and 600"
OCR failure         → 500        → "Failed to embed text layer in PDF"
Unexpected error    → 500        → "An error occurred while processing"

Note: Detailed errors logged server-side only
```

## Deployment Recommendations

### Development
```bash
python main.py
# Or: uvicorn main:app --reload
```

### Production (Docker)
```bash
docker-compose up -d
```

### Production (Manual)
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Scaling
- Use reverse proxy (nginx) for load balancing
- Deploy multiple containers with docker-compose scale
- Use Kubernetes for auto-scaling
- GPU nodes for high-volume processing

## Monitoring

### Health Checks
- `GET /`: Basic status
- `GET /health`: Service health + model status

### Logs
- Request/response logging
- Processing time metrics
- Error tracking
- File size statistics

### Metrics (Recommended)
- Request rate
- Processing time per page
- Error rate
- Queue depth (if using task queue)
