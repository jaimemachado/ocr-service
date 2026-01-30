"""
Database models and connection for OCR processing history.

Uses SQLAlchemy async with SQLite for storing processing history.
All operations are designed to fail gracefully without affecting main OCR functionality.
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import String, Text, Float, Integer, ForeignKey, DateTime, Index
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

logger = logging.getLogger(__name__)

# Database configuration
DATABASE_DIR = Path("data")
DATABASE_PATH = DATABASE_DIR / "ocr.db"
DATABASE_URL = f"sqlite+aiosqlite:///{DATABASE_PATH}"

# Global engine and session factory
engine: Any = None
async_session_factory: async_sessionmaker[AsyncSession] | None = None


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""

    pass


class ProcessingJob(Base):
    """Model for PDF processing jobs."""

    __tablename__ = "processing_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="processing")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_pages: Mapped[int] = mapped_column(Integer, default=0)
    full_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationship to pages
    pages: Mapped[list["ProcessingPage"]] = relationship(
        "ProcessingPage", back_populates="job", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("idx_jobs_created", "created_at"),)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "filename": self.filename,
            "status": self.status,
            "error_message": self.error_message,
            "total_pages": self.total_pages,
            "full_text": self.full_text,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class ProcessingPage(Base):
    """Model for individual PDF pages."""

    __tablename__ = "processing_pages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("processing_jobs.id"), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationship to job
    job: Mapped["ProcessingJob"] = relationship("ProcessingJob", back_populates="pages")

    __table_args__ = (Index("idx_pages_job", "job_id"),)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "job_id": self.job_id,
            "page_number": self.page_number,
            "image_path": self.image_path,
            "text": self.text,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


async def init_database() -> bool:
    """
    Initialize database connection and create tables.

    Returns:
        True if initialization succeeded, False otherwise
    """
    global engine, async_session_factory

    try:
        # Ensure data directory exists
        DATABASE_DIR.mkdir(parents=True, exist_ok=True)

        # Create async engine
        engine = create_async_engine(DATABASE_URL, echo=False)

        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Create session factory
        async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

        logger.info(f"Database initialized at {DATABASE_PATH}")
        return True

    except Exception as e:
        logger.warning(f"Database initialization failed (history will be unavailable): {e}")
        engine = None
        async_session_factory = None
        return False


async def close_database() -> None:
    """Close database connection."""
    global engine, async_session_factory

    if engine:
        await engine.dispose()
        engine = None
        async_session_factory = None
        logger.info("Database connection closed")


def get_session() -> AsyncSession | None:
    """
    Get a database session.

    Returns:
        AsyncSession if available, None if database is not initialized
    """
    if async_session_factory is None:
        return None
    return async_session_factory()


def is_database_available() -> bool:
    """Check if database is available."""
    return async_session_factory is not None
