"""
Basic tests for OCR Service.
"""
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_root_endpoint() -> None:
    """Test root endpoint returns healthy status."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "OCR Service"
    assert data["version"] == "2.0.0"


def test_health_endpoint() -> None:
    """Test health check endpoint returns status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "ocr_model_loaded" in data


def test_process_pdf_no_file() -> None:
    """Test process-pdf endpoint without file returns validation error."""
    response = client.post("/process-pdf")
    assert response.status_code == 422


def test_extract_text_no_file() -> None:
    """Test extract-text endpoint without file returns validation error."""
    response = client.post("/extract-text")
    assert response.status_code == 422


def test_process_pdf_wrong_file_type() -> None:
    """Test process-pdf with non-PDF file returns error."""
    files = {"file": ("test.txt", b"test content", "text/plain")}
    response = client.post("/process-pdf", files=files)
    assert response.status_code == 400
    assert "must be a PDF" in response.json()["detail"]


def test_extract_text_wrong_file_type() -> None:
    """Test extract-text with non-PDF file returns error."""
    files = {"file": ("test.txt", b"test content", "text/plain")}
    response = client.post("/extract-text", files=files)
    assert response.status_code == 400
    assert "must be a PDF" in response.json()["detail"]


def test_process_pdf_invalid_dpi() -> None:
    """Test process-pdf with invalid DPI returns error."""
    files = {"file": ("test.pdf", b"%PDF-1.4 test", "application/pdf")}
    response = client.post("/process-pdf", files=files, params={"dpi": 10})
    assert response.status_code == 400
    assert "DPI must be between" in response.json()["detail"]


def test_extract_text_invalid_dpi() -> None:
    """Test extract-text with invalid DPI returns error."""
    files = {"file": ("test.pdf", b"%PDF-1.4 test", "application/pdf")}
    response = client.post("/extract-text", files=files, params={"dpi": 1000})
    assert response.status_code == 400
    assert "DPI must be between" in response.json()["detail"]
