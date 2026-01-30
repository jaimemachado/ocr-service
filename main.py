"""
OCR Service - FastAPI application for processing PDFs with OCR
"""
import os
import tempfile
import logging
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
from pdf2image import convert_from_path
from doctr.io import DocumentFile
from doctr.models import ocr_predictor
import ocrmypdf
from PIL import Image

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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


def pdf_to_images(pdf_path: str, dpi: int = 300) -> List[Image.Image]:
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
        raise


@app.post("/process-pdf", response_class=FileResponse)
async def process_pdf(
    file: UploadFile = File(..., description="PDF file to process"),
    dpi: int = 300
):
    """
    Process a PDF file with OCR and return the PDF with embedded text layer
    
    Args:
        file: Uploaded PDF file
        dpi: Resolution for PDF to image conversion (default: 300)
    
    Returns:
        PDF file with embedded text layer
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    # Create temporary directory for processing
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Save uploaded PDF
        input_pdf_path = temp_path / "input.pdf"
        logger.info(f"Saving uploaded PDF: {file.filename}")
        
        with open(input_pdf_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        try:
            # Step 1: Convert PDF to images
            images = pdf_to_images(str(input_pdf_path), dpi=dpi)
            
            # Step 2: Run docTR OCR on images
            ocr_data = run_ocr_on_images(images)
            
            # Log extracted text preview
            preview = ocr_data["full_text"][:200]
            logger.info(f"Extracted text preview: {preview}...")
            
            # Step 3: Use ocrmypdf to embed text layer
            output_pdf_path = temp_path / "output.pdf"
            embed_text_layer(str(input_pdf_path), str(output_pdf_path))
            
            # Return the processed PDF
            return FileResponse(
                path=str(output_pdf_path),
                media_type="application/pdf",
                filename=f"ocr_{file.filename}"
            )
        
        except Exception as e:
            logger.error(f"Error processing PDF: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error processing PDF: {str(e)}"
            )


@app.post("/extract-text")
async def extract_text(
    file: UploadFile = File(..., description="PDF file to process"),
    dpi: int = 300
):
    """
    Extract text from PDF using OCR without modifying the PDF
    
    Args:
        file: Uploaded PDF file
        dpi: Resolution for PDF to image conversion (default: 300)
    
    Returns:
        JSON with extracted text and bounding boxes
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    # Create temporary directory for processing
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        # Save uploaded PDF
        input_pdf_path = temp_path / "input.pdf"
        logger.info(f"Saving uploaded PDF: {file.filename}")
        
        with open(input_pdf_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        try:
            # Convert PDF to images
            images = pdf_to_images(str(input_pdf_path), dpi=dpi)
            
            # Run docTR OCR on images
            ocr_data = run_ocr_on_images(images)
            
            return {
                "filename": file.filename,
                "pages": ocr_data["pages"],
                "full_text": ocr_data["full_text"]
            }
        
        except Exception as e:
            logger.error(f"Error extracting text: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error extracting text: {str(e)}"
            )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
