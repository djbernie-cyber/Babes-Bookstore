from sqlalchemy import (
    Column,
    String,
    Text,
    Boolean,
    Integer,
    DateTime,
    JSON,
    Enum as SQLEnum,
    Index,
)
from sqlalchemy.sql import func
from datetime import datetime
import enum
from ..database import Base


class BookStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class VerificationMethod(str, enum.Enum):
    AUTO = "auto"
    MANUAL = "manual"


class Book(Base):
    __tablename__ = "books"

    id = Column(Integer, primary_key=True, index=True)

    title = Column(String(500), nullable=False, index=True)
    author = Column(String(300), nullable=True, index=True)
    description = Column(Text, nullable=True)
    isbn = Column(String(20), nullable=True, index=True)

    source = Column(String(50), nullable=False, index=True)
    source_id = Column(String(200), nullable=True)
    source_url = Column(Text, nullable=True)
    source_metadata = Column(JSON, nullable=True)

    license_type = Column(String(50), nullable=False, index=True)
    license_url = Column(Text, nullable=True)
    license_verified = Column(Boolean, default=False)
    verified_by = Column(String(50), default=VerificationMethod.AUTO.value)
    verified_at = Column(DateTime, nullable=True)

    pdf_path = Column(String(500), nullable=True)
    epub_path = Column(String(500), nullable=True)
    cover_path = Column(String(500), nullable=True)

    category = Column(String(100), nullable=True, index=True)
    tags = Column(JSON, nullable=True)
    language = Column(String(10), default="en")
    page_count = Column(Integer, nullable=True)
    publication_year = Column(Integer, nullable=True)

    status = Column(
        SQLEnum(BookStatus, name="book_status"),
        default=BookStatus.PENDING,
        index=True,
    )

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_books_source_source_id", "source", "source_id", unique=True),
    )
    # Note: `title` is indexed via Column(index=True) above. The Postgres
    # trigram (GIN) indexes for fuzzy title/author search are created in the
    # initial Alembic migration, since pg_trgm is Postgres-only.

    def __repr__(self):
        return f"<Book {self.id}: {self.title[:50]}>"