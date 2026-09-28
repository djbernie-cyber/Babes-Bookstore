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
from sqlalchemy import event
from datetime import datetime
import enum
from ..database import Base
from ..services.search_filters import book_search_text


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

    #: Why this book was withdrawn from the catalogue, if it was. Set by the
    #: licence audit and by manual rejection. Nullable: a book that has never
    #: been rejected has no reason, which is the normal case.
    rejected_reason = Column(Text, nullable=True)
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

    #: Lower-cased, diacritic-stripped haystack of title + author +
    #: description + tags + isbn, maintained by the mapper events below.
    #: Queries match folded tokens against this, so a reader who types
    #: "dvorak" or "ngugi" finds "Dvořák" and "Ngũgĩ". ILIKE cannot fold
    #: accents on the stored side, and Postgres' unaccent extension is not
    #: available on the SQLite the tests run against.
    search_text = Column(Text, nullable=True)

    status = Column(
        SQLEnum(BookStatus, name="book_status"),
        default=BookStatus.PENDING,
        index=True,
    )

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_books_source_source_id", "source", "source_id", unique=True),
        # Storefront hot path: approved+verified lists sorted newest-first.
        Index("ix_books_status_license_created", "status", "license_verified", "created_at"),
        # Browse-by filters used on the catalog pages.
        Index("ix_books_category_status", "category", "status", "license_verified"),
        Index("ix_books_source_status", "source", "status", "license_verified"),
    )
    # Note: `title` is indexed via Column(index=True) above. The Postgres
    # trigram (GIN) indexes for fuzzy title/author search are created in the
    # initial Alembic migration, since pg_trgm is Postgres-only.

    def __repr__(self):
        return f"<Book {self.id}: {self.title[:50]}>"


def _refresh_search_text(mapper, connection, target):
    """Keep ``search_text`` in step with the fields it is built from.

    Done here rather than at each call site because books are written by a
    dozen ingest and admin paths; a column that only some of them maintain
    silently rots, and a stale row is worse than no row because it looks
    authoritative.
    """
    target.search_text = book_search_text(
        target.title, target.author, target.description, target.tags, target.isbn
    )


event.listen(Book, "before_insert", _refresh_search_text)
event.listen(Book, "before_update", _refresh_search_text)