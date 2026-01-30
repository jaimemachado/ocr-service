"""
OCR Service - FastAPI application for processing PDFs with OCR
"""
import os
import tempfile
import logging
import shutil
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from pdf2image import convert_from_path
from doctr.io import DocumentFile
from doctr.models import ocr_predictor
import ocrmypdf
from PIL import Image

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
MIN_DPI = 72
MAX_DPI = 600
DEFAULT_DPI = 300

# Initialize FastAPI app
app = FastAPI(
    title="OCR Service",
    description="PDF OCR processing service using docTR and ocrmypdf",
    version="1.0.0"
)

# Initialize docTR OCR model (loaded once at startup)
ocr_model = None


@app.on_event("startup")
async def startup_event():
    """Initialize OCR model on startup"""
    global ocr_model
    logger.info("Loading docTR OCR model...")
    # Use pretrained model for both detection and recognition
    ocr_model = ocr_predictor(pretrained=True)
    logger.info("OCR model loaded successfully")


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "OCR Service",
        "version": "1.0.0"
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "ocr_model_loaded": ocr_model is not None
    }


def validate_dpi(dpi: int) -> int:
    """
    Validate DPI parameter
    
    Args:
        dpi: DPI value to validate
    
    Returns:
        Validated DPI value
    
    Raises:
        HTTPException: If DPI is out of valid range
    """
    if dpi < MIN_DPI or dpi > MAX_DPI:
        raise HTTPException(
            status_code=400,
            detail=f"DPI must be between {MIN_DPI} and {MAX_DPI}"
        )
    return dpi


async def save_upload_file(upload_file: UploadFile, destination: Path) -> int:
    """
    Save uploaded file and validate size
    
    Args:
        upload_file: The uploaded file
        destination: Path to save the file
    
    Returns:
        Size of the file in bytes
    
    Raises:
        HTTPException: If file is too large
    """
    file_size = 0
    with open(destination, "wb") as f:
        while True:
            chunk = await upload_file.read(1024 * 1024)  # Read 1MB at a time
            if not chunk:
                break
            file_size += len(chunk)
            if file_size > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB"
                )
            f.write(chunk)
    return file_size


def cleanup_file(filepath: str):
    """
    Background task to clean up temporary files
    
    Args:
        filepath: Path to the file to delete
    """
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"Cleaned up temporary file: {filepath}")
    except Exception as e:
        logger.error(f"Error cleaning up file {filepath}: {e}")


def pdf_to_images(pdf_path: str, dpi: int = DEFAULT_DPI) -> List[Image.Image]:
    """
    Convert PDF pages to images using Poppler
    
    Args:
        pdf_path: Path to the PDF file
        dpi: Resolution for image conversion
    
    Returns:
        List of PIL Image objects
    """
    logger.info(f"Converting PDF to images at {dpi} DPI")
    images = convert_from_path(pdf_path, dpi=dpi)
    logger.info(f"Converted {len(images)} pages to images")
    return images


def run_ocr_on_images(images: List[Image.Image]) -> dict:
    """
    Run docTR OCR on images
    
    Args:
        images: List of PIL Image objects
    
    Returns:
        OCR result dictionary with text and bounding boxes
    """
    logger.info(f"Running OCR on {len(images)} images")
    
    # Convert PIL images to format docTR expects
    doc = DocumentFile.from_images(images)
    
    # Run OCR
    result = ocr_model(doc)
    
    # Extract results
    ocr_data = {
        "pages": [],
        "full_text": ""
    }
    
    # Process each page
    for page_idx, page in enumerate(result.pages):
        page_text = []
        page_blocks = []
        
        for block in page.blocks:
            for line in block.lines:
                line_text = []
                for word in line.words:
                    word_text = word.value
                    line_text.append(word_text)
                    
                    # Get bounding box (normalized coordinates)
                    bbox = word.geometry
                    page_blocks.append({
                        "text": word_text,
                        "confidence": word.confidence,
                        "bbox": bbox
                    })
                
                page_text.append(" ".join(line_text))
        
        page_full_text = "\n".join(page_text)
        ocr_data["pages"].append({
            "page_number": page_idx + 1,
            "text": page_full_text,
            "blocks": page_blocks
        })
        ocr_data["full_text"] += page_full_text + "\n\n"
    
    logger.info(f"OCR completed, extracted {len(ocr_data['full_text'])} characters")
    return ocr_data


def embed_text_layer(input_pdf_path: str, output_pdf_path: str) -> None:
    """
    Use ocrmypdf to embed text layer in PDF
    
    Note: This performs OCR using Tesseract (via ocrmypdf) to create a 
    searchable PDF with an embedded text layer. This is separate from the 
    docTR OCR which is used for text extraction and bounding boxes.
    
    Args:
        input_pdf_path: Path to input PDF
        output_pdf_path: Path to output PDF with text layer
    """
    logger.info("Embedding text layer with ocrmypdf")
    
    try:
        ocrmypdf.ocr(
            input_pdf_path,
            output_pdf_path,
            deskew=True,
            rotate_pages=True,
            remove_background=False,
            optimize=1,
            skip_text=False,  # Always OCR, even if text exists
            force_ocr=True,   # Force OCR on all pages
            redo_ocr=False,
            use_threads=True
        )
        logger.info("Text layer embedded successfully")
    except Exception as e:
        logger.error(f"Error embedding text layer: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to embed text layer in PDF"
        )


@app.post("/process-pdf", response_class=FileResponse)
async def process_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF file to process"),
    dpi: int = DEFAULT_DPI
):
    """
    Process a PDF file with OCR and return the PDF with embedded text layer
    
    This endpoint uses ocrmypdf to create a searchable PDF with embedded text layer.
    The output is ready for import into Paperless-ngx which will skip its own OCR.
    
    Args:
        background_tasks: FastAPI background tasks for cleanup
        file: Uploaded PDF file
        dpi: Resolution for PDF to image conversion (default: 300, range: 72-600)
    
    Returns:
        PDF file with embedded text layer
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    # Validate DPI
    dpi = validate_dpi(dpi)
    
    # Create a unique temporary directory for this request
    temp_dir = tempfile.mkdtemp()
    
    try:
        temp_path = Path(temp_dir)
        
        # Save uploaded PDF with size validation
        input_pdf_path = temp_path / "input.pdf"
        logger.info(f"Saving uploaded PDF: {file.filename}")
        file_size = await save_upload_file(file, input_pdf_path)
        logger.info(f"Saved PDF: {file_size / (1024*1024):.2f}MB")
        
        # Use ocrmypdf to embed text layer
        output_pdf_path = temp_path / "output.pdf"
        embed_text_layer(str(input_pdf_path), str(output_pdf_path))
        
        # Copy output to a persistent temporary location using secure temp file
        with tempfile.NamedTemporaryFile(mode='wb', suffix=".pdf", delete=False) as tmp_file:
            final_output_path = tmp_file.name
            with open(output_pdf_path, 'rb') as src:
                shutil.copyfileobj(src, tmp_file)
        
        # Schedule cleanup of both files/directories
        background_tasks.add_task(cleanup_file, final_output_path)
        background_tasks.add_task(shutil.rmtree, temp_dir)
        
        # Return the processed PDF
        return FileResponse(
            path=final_output_path,
            media_type="application/pdf",
            filename=f"ocr_{file.filename}"
        )
    
    except HTTPException:
        # Clean up on known errors
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    except Exception as e:
        # Clean up on unexpected errors
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.error(f"Error processing PDF: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing the PDF"
        )


@app.post("/extract-text")
async def extract_text(
    file: UploadFile = File(..., description="PDF file to process"),
    dpi: int = DEFAULT_DPI
):
    """
    Extract text from PDF using OCR without modifying the PDF
    
    This endpoint uses docTR to extract text and bounding boxes for analysis.
    Use this when you need the OCR data without embedding it in the PDF.
    
    Args:
        file: Uploaded PDF file
        dpi: Resolution for PDF to image conversion (default: 300, range: 72-600)
    
    Returns:
        JSON with extracted text and bounding boxes
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    # Validate DPI
    dpi = validate_dpi(dpi)
    
    # Create temporary directory for processing
    temp_dir = tempfile.mkdtemp()
    
    try:
        temp_path = Path(temp_dir)
        
        # Save uploaded PDF with size validation
        input_pdf_path = temp_path / "input.pdf"
        logger.info(f"Saving uploaded PDF: {file.filename}")
        file_size = await save_upload_file(file, input_pdf_path)
        logger.info(f"Saved PDF: {file_size / (1024*1024):.2f}MB")
        
        # Convert PDF to images
        images = pdf_to_images(str(input_pdf_path), dpi=dpi)
        
        # Run docTR OCR on images
        ocr_data = run_ocr_on_images(images)
        
        # Clean up
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        return {
            "filename": file.filename,
            "pages": ocr_data["pages"],
            "full_text": ocr_data["full_text"]
        }
    
    except HTTPException:
        # Clean up on known errors
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    except Exception as e:
        # Clean up on unexpected errors
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.error(f"Error extracting text: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An error occurred while extracting text from the PDF"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
