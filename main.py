"""
OCR Service - FastAPI application for processing PDFs with OCR.

Uses docTR for accurate text extraction and PyMuPDF for creating searchable PDFs.
Includes processing history tracking with web UI dashboard.
"""
import logging
import os
import shutil
import tempfile
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import cv2
import fitz
import numpy as np
from doctr.io import DocumentFile
from doctr.models import ocr_predictor
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image
import statistics

import database
import history_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
MIN_DPI = 72
MAX_DPI = 600
DEFAULT_DPI = 300

# OCR model storage
ocr_model: Any = None

# Templates
templates = Jinja2Templates(directory="templates")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for startup and shutdown events."""
    global ocr_model

    # Initialize OCR model
    logger.info("Loading docTR OCR model...")
    ocr_model = ocr_predictor(pretrained=True)
    logger.info("OCR model loaded successfully")

    # Initialize database (non-blocking - app works without it)
    db_available = await database.init_database()
    if db_available:
        logger.info("History database initialized")
    else:
        logger.warning("History database unavailable - history will not be recorded")

    # Ensure static directories exist
    Path("static/images").mkdir(parents=True, exist_ok=True)

    yield

    # Cleanup
    await database.close_database()
    logger.info("Shutting down OCR service")


# Initialize FastAPI app
app = FastAPI(
    title="OCR Service",
    description="PDF OCR processing service using docTR and PyMuPDF",
    version="2.0.0",
    lifespan=lifespan,
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.middleware("http")
async def add_security_headers(
    request: Request, call_next: Callable[[Request], Awaitable[Any]]
) -> Any:
    """Add security headers to all responses."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.get("/")
async def root() -> dict[str, str]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "OCR Service",
        "version": "2.0.0",
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    """Health check endpoint with detailed status."""
    return {
        "status": "healthy",
        "ocr_model_loaded": ocr_model is not None,
        "history_available": database.is_database_available(),
    }


# =============================================================================
# History Endpoints
# =============================================================================


@app.get("/history", response_class=HTMLResponse)
async def history_page(
    request: Request,
    page: int = Query(1, ge=1),
    q: str | None = Query(None),
) -> HTMLResponse:
    """Render the processing history dashboard."""
    # Get jobs for display
    result = await history_service.get_jobs(page=page, limit=20, search=q)

    # Count completed and failed jobs
    completed_count = 0
    failed_count = 0
    for job in result["jobs"]:
        if job["status"] == "completed":
            completed_count += 1
        elif job["status"] == "failed":
            failed_count += 1

    return templates.TemplateResponse(
        "history.html",
        {
            "request": request,
            "jobs": result["jobs"],
            "total": result["total"],
            "page": result["page"],
            "pages": result["pages"],
            "search": q,
            "history_available": database.is_database_available(),
            "completed_count": completed_count,
            "failed_count": failed_count,
        },
    )


@app.get("/api/history")
async def api_get_history(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    q: str | None = Query(None),
) -> dict[str, Any]:
    """Get paginated processing history."""
    return await history_service.get_jobs(page=page, limit=limit, search=q)


@app.get("/api/history/{job_id}")
async def api_get_job(job_id: str) -> JSONResponse:
    """Get a single job with its pages."""
    job = await history_service.get_job(job_id)
    if job is None:
        return JSONResponse(status_code=404, content={"error": "Job not found"})
    return JSONResponse(content=job)


@app.get("/history/{job_id}/detail", response_class=HTMLResponse)
async def history_job_detail(request: Request, job_id: str) -> HTMLResponse:
    """Return a server-rendered HTML fragment with job details.

    This endpoint is intended for HTMX requests from the history UI and
    returns the `templates/job_detail.html` partial rendered with the
    job data.
    """
    job = await history_service.get_job(job_id)
    if job is None:
        # Render a small not-found fragment
        return HTMLResponse(
            "<div class='p-4 text-sm text-gray-600'>Job not found</div>",
            status_code=404,
        )

    return templates.TemplateResponse("job_detail.html", {"request": request, "job": job})


@app.delete("/api/history/{job_id}")
async def api_delete_job(job_id: str) -> JSONResponse:
    """Delete a job and its associated images."""
    success = await history_service.delete_job(job_id)
    if not success:
        return JSONResponse(status_code=404, content={"error": "Job not found or delete failed"})
    return JSONResponse(content={"success": True})


# =============================================================================
# Utility Functions
# =============================================================================


def validate_dpi(dpi: int) -> int:
    """
    Validate DPI parameter.

    Args:
        dpi: DPI value to validate

    Returns:
        Validated DPI value

    Raises:
        HTTPException: If DPI is out of valid range
    """
    if dpi < MIN_DPI or dpi > MAX_DPI:
        raise HTTPException(
            status_code=400, detail=f"DPI must be between {MIN_DPI} and {MAX_DPI}"
        )
    return dpi


async def save_upload_file(upload_file: UploadFile, destination: Path) -> int:
    """
    Save uploaded file and validate size.

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
                    detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024*1024)}MB",
                )
            f.write(chunk)
    return file_size


def cleanup_file(filepath: str) -> None:
    """
    Background task to clean up temporary files.

    Args:
        filepath: Path to the file to delete
    """
    try:
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"Cleaned up temporary file: {filepath}")
    except Exception as e:
        logger.error(f"Error cleaning up file {filepath}: {e}")


def pdf_to_images(pdf_path: str, dpi: int = DEFAULT_DPI) -> list[Image.Image]:
    """
    Convert PDF pages to PIL images using PyMuPDF.

    Args:
        pdf_path: Path to the PDF file
        dpi: Resolution for image conversion

    Returns:
        List of PIL Image objects
    """
    logger.info(f"Converting PDF to images at {dpi} DPI")
    images: list[Image.Image] = []
    zoom = dpi / 72  # PyMuPDF default is 72 DPI

    doc = fitz.open(pdf_path)
    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            # Create transformation matrix for desired DPI
            mat = fitz.Matrix(zoom, zoom)
            # Render page to pixmap
            pix = page.get_pixmap(matrix=mat)
            # Convert to PIL Image
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(img)
    finally:
        doc.close()

    logger.info(f"Converted {len(images)} pages to images")
    return images


def preprocess_image_for_ocr(image: Image.Image) -> Image.Image:
    """
    Preprocess image using OpenCV to improve OCR accuracy.

    Applies:
    - Grayscale conversion
    - Noise reduction
    - Adaptive thresholding for binarization
    - Contrast enhancement

    Args:
        image: PIL Image to preprocess

    Returns:
        Preprocessed PIL Image
    """
    # Convert PIL to OpenCV format (numpy array)
    img_array = np.array(image)

    # Convert to grayscale if needed
    if len(img_array.shape) == 3:
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    else:
        gray = img_array

    # Apply denoising
    denoised = cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7, searchWindowSize=21)

    # Apply adaptive thresholding for better binarization
    # This works better than Otsu for documents with varying lighting
    binary = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )

    # Convert back to RGB for docTR (it expects color images)
    rgb = cv2.cvtColor(binary, cv2.COLOR_GRAY2RGB)

    return Image.fromarray(rgb)


def run_ocr_on_images(
    images: list[Image.Image], preprocess: bool = True
) -> tuple[Any, list[tuple[int, int]]]:
    """
    Run docTR OCR on images.

    Args:
        images: List of PIL Image objects
        preprocess: Whether to apply OpenCV preprocessing

    Returns:
        Tuple of (docTR result object, list of image dimensions)

    Raises:
        RuntimeError: If OCR model is not initialized
    """
    if ocr_model is None:
        raise RuntimeError("OCR model not initialized")

    logger.info(f"Running OCR on {len(images)} images (preprocess={preprocess})")

    # Store original dimensions for text positioning
    dimensions = [(img.width, img.height) for img in images]

    # Optionally preprocess images
    if preprocess:
        processed_images = [preprocess_image_for_ocr(img) for img in images]
    else:
        processed_images = images

    # Save images to temporary files for docTR (it expects file paths)
    temp_dir = tempfile.mkdtemp()
    image_paths: list[str] = []
    try:
        for i, img in enumerate(processed_images):
            img_path = os.path.join(temp_dir, f"page_{i}.png")
            img.save(img_path, "PNG")
            image_paths.append(img_path)

        # Load images via docTR
        doc = DocumentFile.from_images(image_paths)

        # Run OCR
        result = ocr_model(doc)

        logger.info("OCR completed successfully")
        return result, dimensions

    finally:
        # Cleanup temp files
        shutil.rmtree(temp_dir, ignore_errors=True)


def embed_text_layer(
    input_pdf_path: str, output_pdf_path: str, ocr_result: Any, dimensions: list[tuple[int, int]]
) -> None:
    """
    Embed invisible text layer into PDF using PyMuPDF.

    The text is positioned according to bounding boxes from docTR OCR results.
    Text is made invisible but selectable/searchable.

    Args:
        input_pdf_path: Path to input PDF
        output_pdf_path: Path to output PDF with text layer
        ocr_result: docTR OCR result object
        dimensions: List of (width, height) tuples for each page image
    """
    logger.info("Embedding text layer with PyMuPDF")

    doc = fitz.open(input_pdf_path)

    try:
        for page_idx, page in enumerate(ocr_result.pages):
            if page_idx >= len(doc):
                break

            pdf_page = doc[page_idx]
            page_rect = pdf_page.rect

            # Scale factors to convert normalized coordinates to PDF coordinates
            scale_x = page_rect.width
            scale_y = page_rect.height

            for block in page.blocks:
                for line in block.lines:
                    for word in line.words:
                        # Get word text and bounding box
                        text = word.value
                        # docTR bbox is ((x0, y0), (x1, y1)) in normalized coordinates [0,1]
                        bbox = word.geometry
                        x0, y0 = bbox[0]
                        y1 = bbox[1][1]

                        # Convert normalized coordinates to PDF coordinates
                        pdf_x0 = x0 * scale_x
                        pdf_y0 = y0 * scale_y
                        pdf_y1 = y1 * scale_y

                        # Calculate font size based on box height
                        box_height = pdf_y1 - pdf_y0
                        font_size = max(1, box_height * 0.8)

                        # Insert invisible text (render mode 3 = invisible)
                        pdf_page.insert_text(
                            point=fitz.Point(pdf_x0, pdf_y1 - box_height * 0.15),
                            text=text,
                            fontsize=font_size,
                            fontname="helv",
                            render_mode=3,  # Invisible text
                        )

        # Save the modified PDF
        doc.save(output_pdf_path, garbage=4, deflate=True)
        logger.info("Text layer embedded successfully")

    finally:
        doc.close()


def extract_ocr_data(ocr_result: Any) -> dict[str, Any]:
    """
    Extract text and bounding box data from docTR result.

    Args:
        ocr_result: docTR OCR result object

    Returns:
        Dictionary with pages, blocks, and full text
    """
    ocr_data: dict[str, Any] = {"pages": [], "full_text": ""}

    for page_idx, page in enumerate(ocr_result.pages):
        words: list[dict[str, Any]] = []

        for block in page.blocks:
            for line in block.lines:
                for word in line.words:
                    bbox = word.geometry
                    x0, y0 = float(bbox[0][0]), float(bbox[0][1])
                    x1, y1 = float(bbox[1][0]), float(bbox[1][1])
                    words.append(
                        {
                            "text": word.value,
                            "confidence": float(word.confidence),
                            "x0": x0,
                            "y0": y0,
                            "x1": x1,
                            "y1": y1,
                            "cx": (x0 + x1) / 2.0,
                            "cy": (y0 + y1) / 2.0,
                        }
                    )

        # If no words, append empty page
        if not words:
            ocr_data["pages"].append(
                {
                    "page_number": page_idx + 1,
                    "text": "",
                    "blocks": [],
                    "avg_confidence": 0.0,
                }
            )
            ocr_data["full_text"] += "\n\n"
            continue

        # Estimate a typical line height from word bboxes (normalized coordinates)
        heights = [w["y1"] - w["y0"] for w in words if w["y1"] > w["y0"]]
        line_h = statistics.median(heights) if heights else 0.03

        # Sort words by vertical center then by x0
        words.sort(key=lambda w: (w["cy"], w["x0"]))

        # Cluster words into lines using vertical proximity
        lines: list[list[dict[str, Any]]] = []
        current_line: list[dict[str, Any]] = []
        current_y: float = 0.0

        for w in words:
            if current_line == []:
                current_line = [w]
                current_y = w["cy"]
                continue

            # if the vertical distance is small, consider same line
            if abs(w["cy"] - current_y) <= max(0.5 * line_h, 0.01):
                current_line.append(w)
                # update running line center
                current_y = (current_y * (len(current_line) - 1) + w["cy"]) / len(current_line)
            else:
                lines.append(current_line)
                current_line = [w]
                current_y = w["cy"]

        if current_line:
            lines.append(current_line)

        # Build text with paragraph breaks when vertical gap is large
        page_lines_text: list[str] = []
        page_blocks: list[dict[str, Any]] = []
        page_conf_sum = 0.0
        page_word_count = 0

        for i, line in enumerate(lines):
            # sort words in line by x0
            line.sort(key=lambda w: w["x0"])
            line_text = " ".join([w["text"] for w in line])
            page_lines_text.append(line_text)

            # collect word-level blocks
            for w in line:
                page_blocks.append(
                    {
                        "text": w["text"],
                        "confidence": w["confidence"],
                        "bbox": [[w["x0"], w["y0"]], [w["x1"], w["y1"]]],
                    }
                )
                page_conf_sum += w["confidence"]
                page_word_count += 1

            # determine if a paragraph break is needed by comparing to next line's cy
            if i < len(lines) - 1:
                this_cy = statistics.mean([w["cy"] for w in line])
                next_cy = statistics.mean([w["cy"] for w in lines[i + 1]])
                gap = next_cy - this_cy
                # if gap significantly larger than line height, insert paragraph separator
                if gap > max(1.5 * line_h, 0.02):
                    page_lines_text.append("")

        page_full_text = "\n".join(page_lines_text)
        avg_confidence = page_conf_sum / page_word_count if page_word_count > 0 else 0.0

        ocr_data["pages"].append(
            {
                "page_number": page_idx + 1,
                "text": page_full_text,
                "blocks": page_blocks,
                "avg_confidence": avg_confidence,
            }
        )

        ocr_data["full_text"] += page_full_text + "\n\n"

    return ocr_data


# =============================================================================
# OCR Endpoints
# =============================================================================


@app.post("/process-pdf", response_class=FileResponse)
async def process_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF file to process"),
    dpi: int = DEFAULT_DPI,
    preprocess: bool = True,
) -> FileResponse:
    """
    Process a PDF file with OCR and return a searchable PDF.

    Pipeline:
    1. Convert PDF pages to images (PyMuPDF)
    2. Preprocess images for OCR (OpenCV) - optional
    3. Run OCR to extract text (docTR)
    4. Embed invisible text layer (PyMuPDF)

    Args:
        background_tasks: FastAPI background tasks for cleanup
        file: Uploaded PDF file
        dpi: Resolution for PDF to image conversion (default: 300, range: 72-600)
        preprocess: Whether to apply OpenCV preprocessing (default: True)

    Returns:
        PDF file with embedded searchable text layer
    """
    filename = file.filename or "document.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    dpi = validate_dpi(dpi)
    temp_dir = tempfile.mkdtemp()

    # Create history job (non-blocking)
    job_id: str | None = None
    try:
        job_id = await history_service.create_job(filename)
    except Exception as e:
        logger.warning(f"History unavailable: {e}")

    try:
        temp_path = Path(temp_dir)

        # Save uploaded PDF
        input_pdf_path = temp_path / "input.pdf"
        logger.info(f"Saving uploaded PDF: {filename}")
        file_size = await save_upload_file(file, input_pdf_path)
        logger.info(f"Saved PDF: {file_size / (1024*1024):.2f}MB")

        # Convert PDF to images
        images = pdf_to_images(str(input_pdf_path), dpi=dpi)

        # Run OCR with docTR
        ocr_result, dimensions = run_ocr_on_images(images, preprocess=preprocess)

        # Extract OCR data for history
        ocr_data = extract_ocr_data(ocr_result)

        # Save to history (non-blocking)
        if job_id:
            try:
                for i, (img, page_data) in enumerate(zip(images, ocr_data["pages"])):
                    await history_service.add_page(
                        job_id=job_id,
                        page_number=i + 1,
                        image=img,
                        text=page_data["text"],
                        confidence=page_data.get("avg_confidence", 0.0),
                    )
                await history_service.complete_job(
                    job_id=job_id,
                    full_text=ocr_data["full_text"],
                    total_pages=len(images),
                )
            except Exception as e:
                logger.warning(f"History save failed: {e}")

        # Embed text layer into PDF
        output_pdf_path = temp_path / "output.pdf"
        embed_text_layer(str(input_pdf_path), str(output_pdf_path), ocr_result, dimensions)

        # Copy to persistent temp file
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".pdf", delete=False) as tmp_file:
            final_output_path = tmp_file.name
            with open(output_pdf_path, "rb") as src:
                shutil.copyfileobj(src, tmp_file)

        # Schedule cleanup
        background_tasks.add_task(cleanup_file, final_output_path)
        background_tasks.add_task(shutil.rmtree, temp_dir)

        return FileResponse(
            path=final_output_path,
            media_type="application/pdf",
            filename=f"ocr_{filename}",
        )

    except HTTPException:
        shutil.rmtree(temp_dir, ignore_errors=True)
        # Mark job as failed (non-blocking)
        if job_id:
            try:
                await history_service.fail_job(job_id, "Processing failed")
            except Exception:
                pass
        raise
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        # Mark job as failed (non-blocking)
        if job_id:
            try:
                await history_service.fail_job(job_id, str(e))
            except Exception:
                pass
        logger.error(f"Error processing PDF: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="An error occurred while processing the PDF"
        )


@app.post("/extract-text")
async def extract_text(
    file: UploadFile = File(..., description="PDF file to process"),
    dpi: int = DEFAULT_DPI,
    preprocess: bool = True,
) -> dict[str, Any]:
    """
    Extract text from PDF using OCR without modifying the PDF.

    Args:
        file: Uploaded PDF file
        dpi: Resolution for PDF to image conversion (default: 300, range: 72-600)
        preprocess: Whether to apply OpenCV preprocessing (default: True)

    Returns:
        JSON with extracted text and bounding boxes
    """
    filename = file.filename or "document.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="File must be a PDF")

    dpi = validate_dpi(dpi)
    temp_dir = tempfile.mkdtemp()

    # Create history job (non-blocking)
    job_id: str | None = None
    try:
        job_id = await history_service.create_job(filename)
    except Exception as e:
        logger.warning(f"History unavailable: {e}")

    try:
        temp_path = Path(temp_dir)

        # Save uploaded PDF
        input_pdf_path = temp_path / "input.pdf"
        logger.info(f"Saving uploaded PDF: {filename}")
        file_size = await save_upload_file(file, input_pdf_path)
        logger.info(f"Saved PDF: {file_size / (1024*1024):.2f}MB")

        # Convert PDF to images
        images = pdf_to_images(str(input_pdf_path), dpi=dpi)

        # Run OCR
        ocr_result, _ = run_ocr_on_images(images, preprocess=preprocess)

        # Extract data from OCR result
        ocr_data = extract_ocr_data(ocr_result)

        # Save to history (non-blocking)
        if job_id:
            try:
                for i, (img, page_data) in enumerate(zip(images, ocr_data["pages"])):
                    await history_service.add_page(
                        job_id=job_id,
                        page_number=i + 1,
                        image=img,
                        text=page_data["text"],
                        confidence=page_data.get("avg_confidence", 0.0),
                    )
                await history_service.complete_job(
                    job_id=job_id,
                    full_text=ocr_data["full_text"],
                    total_pages=len(images),
                )
            except Exception as e:
                logger.warning(f"History save failed: {e}")

        shutil.rmtree(temp_dir, ignore_errors=True)

        return {
            "filename": filename,
            "pages": ocr_data["pages"],
            "full_text": ocr_data["full_text"],
        }

    except HTTPException:
        shutil.rmtree(temp_dir, ignore_errors=True)
        # Mark job as failed (non-blocking)
        if job_id:
            try:
                await history_service.fail_job(job_id, "Text extraction failed")
            except Exception:
                pass
        raise
    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        # Mark job as failed (non-blocking)
        if job_id:
            try:
                await history_service.fail_job(job_id, str(e))
            except Exception:
                pass
        logger.error(f"Error extracting text: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="An error occurred while extracting text from the PDF"
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
