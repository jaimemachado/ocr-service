"""
History service for tracking OCR processing jobs.

All operations are non-blocking and fail gracefully - errors are logged
but never propagated to callers. This ensures main OCR functionality
is never affected by history tracking issues.
"""
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image
from sqlalchemy import select, func, desc

from database import (
    ProcessingJob,
    ProcessingPage,
    get_session,
    is_database_available,
)

logger = logging.getLogger(__name__)

# Image storage configuration
IMAGES_DIR = Path("static/images")
THUMBNAIL_WIDTH = 400
THUMBNAIL_QUALITY = 80


def _ensure_images_dir() -> None:
    """Ensure images directory exists."""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)


async def create_job(filename: str) -> str | None:
    """
    Create a new processing job record.

    Args:
        filename: Original filename of the PDF

    Returns:
        Job ID if successful, None if failed
    """
    if not is_database_available():
        return None

    session = get_session()
    if session is None:
        return None

    try:
        async with session:
            job_id = str(uuid.uuid4())
            job = ProcessingJob(
                id=job_id,
                filename=filename,
                status="processing",
                created_at=datetime.utcnow(),
            )
            session.add(job)
            await session.commit()
            logger.info(f"Created job {job_id} for {filename}")
            return job_id
    except Exception as e:
        logger.warning(f"Failed to create job record: {e}")
        return None


async def add_page(
    job_id: str,
    page_number: int,
    image: Image.Image,
    text: str,
    confidence: float,
) -> bool:
    """
    Add a page record with thumbnail image.

    Args:
        job_id: Job ID
        page_number: Page number (1-indexed)
        image: PIL Image of the page
        text: Extracted text from the page
        confidence: Average confidence score

    Returns:
        True if successful, False if failed
    """
    if not is_database_available():
        return False

    session = get_session()
    if session is None:
        return False

    try:
        _ensure_images_dir()

        # Create job-specific directory
        job_images_dir = IMAGES_DIR / job_id
        job_images_dir.mkdir(parents=True, exist_ok=True)

        # Save thumbnail
        image_path = job_images_dir / f"page_{page_number}.jpg"
        thumbnail = image.copy()

        # Resize maintaining aspect ratio
        aspect = thumbnail.height / thumbnail.width
        new_height = int(THUMBNAIL_WIDTH * aspect)
        thumbnail = thumbnail.resize((THUMBNAIL_WIDTH, new_height), Image.Resampling.LANCZOS)

        # Convert to RGB if necessary (for JPEG)
        if thumbnail.mode in ("RGBA", "P"):
            thumbnail = thumbnail.convert("RGB")

        thumbnail.save(str(image_path), "JPEG", quality=THUMBNAIL_QUALITY)

        # Store relative path for web serving
        relative_path = f"/static/images/{job_id}/page_{page_number}.jpg"

        async with session:
            page = ProcessingPage(
                id=str(uuid.uuid4()),
                job_id=job_id,
                page_number=page_number,
                image_path=relative_path,
                text=text,
                confidence=confidence,
                created_at=datetime.utcnow(),
            )
            session.add(page)
            await session.commit()

        logger.debug(f"Added page {page_number} to job {job_id}")
        return True

    except Exception as e:
        logger.warning(f"Failed to add page {page_number} to job {job_id}: {e}")
        return False


async def complete_job(job_id: str, full_text: str, total_pages: int) -> bool:
    """
    Mark a job as completed.

    Args:
        job_id: Job ID
        full_text: Full extracted text
        total_pages: Total number of pages processed

    Returns:
        True if successful, False if failed
    """
    if not is_database_available():
        return False

    session = get_session()
    if session is None:
        return False

    try:
        async with session:
            result = await session.execute(
                select(ProcessingJob).where(ProcessingJob.id == job_id)
            )
            job = result.scalar_one_or_none()

            if job:
                job.status = "completed"
                job.full_text = full_text
                job.total_pages = total_pages
                job.completed_at = datetime.utcnow()
                await session.commit()
                logger.info(f"Job {job_id} completed with {total_pages} pages")
                return True

        return False

    except Exception as e:
        logger.warning(f"Failed to complete job {job_id}: {e}")
        return False


async def fail_job(job_id: str, error_message: str) -> bool:
    """
    Mark a job as failed.

    Args:
        job_id: Job ID
        error_message: Error description

    Returns:
        True if successful, False if failed
    """
    if not is_database_available():
        return False

    session = get_session()
    if session is None:
        return False

    try:
        async with session:
            result = await session.execute(
                select(ProcessingJob).where(ProcessingJob.id == job_id)
            )
            job = result.scalar_one_or_none()

            if job:
                job.status = "failed"
                job.error_message = error_message
                job.completed_at = datetime.utcnow()
                await session.commit()
                logger.info(f"Job {job_id} marked as failed: {error_message}")
                return True

        return False

    except Exception as e:
        logger.warning(f"Failed to mark job {job_id} as failed: {e}")
        return False


async def get_jobs(
    page: int = 1,
    limit: int = 20,
    search: str | None = None,
) -> dict[str, Any]:
    """
    Get paginated list of jobs.

    Args:
        page: Page number (1-indexed)
        limit: Number of items per page
        search: Optional filename search query

    Returns:
        Dictionary with jobs list and pagination info
    """
    if not is_database_available():
        return {"jobs": [], "total": 0, "page": page, "limit": limit, "pages": 0}

    session = get_session()
    if session is None:
        return {"jobs": [], "total": 0, "page": page, "limit": limit, "pages": 0}

    try:
        async with session:
            # Build query
            query = select(ProcessingJob)

            if search:
                query = query.where(ProcessingJob.filename.ilike(f"%{search}%"))

            # Get total count
            count_query = select(func.count()).select_from(query.subquery())
            total_result = await session.execute(count_query)
            total = total_result.scalar() or 0

            # Get paginated results
            offset = (page - 1) * limit
            query = query.order_by(desc(ProcessingJob.created_at)).offset(offset).limit(limit)
            result = await session.execute(query)
            jobs = result.scalars().all()

            return {
                "jobs": [job.to_dict() for job in jobs],
                "total": total,
                "page": page,
                "limit": limit,
                "pages": (total + limit - 1) // limit,
            }

    except Exception as e:
        logger.warning(f"Failed to get jobs: {e}")
        return {"jobs": [], "total": 0, "page": page, "limit": limit, "pages": 0}


async def get_job(job_id: str) -> dict[str, Any] | None:
    """
    Get a single job with its pages.

    Args:
        job_id: Job ID

    Returns:
        Job dictionary with pages, or None if not found
    """
    if not is_database_available():
        return None

    session = get_session()
    if session is None:
        return None

    try:
        async with session:
            # Get job
            result = await session.execute(
                select(ProcessingJob).where(ProcessingJob.id == job_id)
            )
            job = result.scalar_one_or_none()

            if not job:
                return None

            # Get pages
            pages_result = await session.execute(
                select(ProcessingPage)
                .where(ProcessingPage.job_id == job_id)
                .order_by(ProcessingPage.page_number)
            )
            pages = pages_result.scalars().all()

            job_dict = job.to_dict()
            job_dict["pages"] = [page.to_dict() for page in pages]
            return job_dict

    except Exception as e:
        logger.warning(f"Failed to get job {job_id}: {e}")
        return None


async def delete_job(job_id: str) -> bool:
    """
    Delete a job and its associated images.

    Args:
        job_id: Job ID

    Returns:
        True if successful, False if failed
    """
    if not is_database_available():
        return False

    session = get_session()
    if session is None:
        return False

    try:
        async with session:
            # Get job
            result = await session.execute(
                select(ProcessingJob).where(ProcessingJob.id == job_id)
            )
            job = result.scalar_one_or_none()

            if not job:
                return False

            # Delete from database (cascades to pages)
            await session.delete(job)
            await session.commit()

        # Delete images directory
        job_images_dir = IMAGES_DIR / job_id
        if job_images_dir.exists():
            shutil.rmtree(job_images_dir)

        logger.info(f"Deleted job {job_id}")
        return True

    except Exception as e:
        logger.warning(f"Failed to delete job {job_id}: {e}")
        return False
