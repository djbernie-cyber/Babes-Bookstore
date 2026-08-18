from sqlalchemy import (
    Column,
    String,
    Text,
    Boolean,
    Integer,
    DateTime,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base
from ..config import settings


class Bundle(Base):
    __tablename__ = "bundles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    slug = Column(String(200), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    long_description = Column(Text, nullable=True)
    price_cents = Column(Integer, nullable=False, default=settings.STANDARD_PRICE_PENCE)
    currency = Column(String(10), nullable=False, default=settings.CURRENCY)
    cover_image_path = Column(String(500), nullable=True)

    category = Column(String(100), nullable=True, index=True)
    tags = Column(ARRAY(String), nullable=True)

    meta_title = Column(String(200), nullable=True)
    meta_description = Column(String(500), nullable=True)

    active = Column(Boolean, default=True, index=True)
    featured = Column(Boolean, default=False, index=True)
    bundle_type = Column(String(50), default="curated")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    bundle_books = relationship(
        "BundleBook",
        back_populates="bundle",
        cascade="all, delete-orphan",
        order_by="BundleBook.sort_order",
    )
    purchases = relationship("Purchase", back_populates="bundle")

    def __repr__(self):
        return f"<Bundle {self.id}: {self.name}>"


class BundleBook(Base):
    __tablename__ = "bundle_books"

    bundle_id = Column(Integer, ForeignKey("bundles.id", ondelete="CASCADE"), primary_key=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), primary_key=True)
    sort_order = Column(Integer, default=0)

    bundle = relationship("Bundle", back_populates="bundle_books")
    book = relationship("Book")

    def __repr__(self):
        return f"<BundleBook bundle={self.bundle_id} book={self.book_id}>"