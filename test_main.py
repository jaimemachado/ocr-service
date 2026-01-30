"""
Basic tests for OCR Service
"""
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_root_endpoint():
    """Test root endpoint"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "OCR Service"


def test_health_endpoint():
    """Test health check endpoint"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "ocr_model_loaded" in data


def test_process_pdf_no_file():
    """Test process-pdf endpoint without file"""
    response = client.post("/process-pdf")
    assert response.status_code == 422  # Validation error


def test_extract_text_no_file():
    """Test extract-text endpoint without file"""
    response = client.post("/extract-text")
    assert response.status_code == 422  # Validation error


def test_process_pdf_wrong_file_type():
    """Test process-pdf with non-PDF file"""
    files = {"file": ("test.txt", b"test content", "text/plain")}
    response = client.post("/process-pdf", files=files)
    assert response.status_code == 400
    assert "must be a PDF" in response.json()["detail"]
