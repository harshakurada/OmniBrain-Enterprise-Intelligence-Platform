from datetime import datetime
from typing import List, Optional
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy database models."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class DocumentModel(Base):
    """Stores metadata for uploaded and processed documents."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)  # SHA-256 / MD5
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False, default="application/pdf")
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="PENDING", index=True)  # PENDING, PROCESSING, COMPLETED, FAILED
    page_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    table_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    image_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    chunks: Mapped[List["DocumentChunkModel"]] = relationship(
        "DocumentChunkModel", back_populates="document", cascade="all, delete-orphan"
    )
    assets: Mapped[List["ExtractedAssetModel"]] = relationship(
        "ExtractedAssetModel", back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunkModel(Base):
    """Stores parsed chunks extracted from documents."""

    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_type: Mapped[str] = mapped_column(String(50), nullable=False, default="text")  # text, table, image_caption
    content: Mapped[str] = mapped_column(Text, nullable=False)
    vector_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    document: Mapped["DocumentModel"] = relationship("DocumentModel", back_populates="chunks")


class ExtractedAssetModel(Base):
    """Stores extracted multi-modal assets (tables, images) from documents."""

    __tablename__ = "extracted_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String(50), nullable=False)  # image, table
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    asset_path: Mapped[str] = mapped_column(String(512), nullable=False)
    caption: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    document: Mapped["DocumentModel"] = relationship("DocumentModel", back_populates="assets")
