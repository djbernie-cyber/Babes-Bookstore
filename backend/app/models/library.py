"""User library: named shelves, shelf items, and reading progress.

A user owns any number of named shelves (collections of books). The
traditional "wishlist" is modelled as a user's default shelf, so existing
♡/wishlist behaviour keeps working while users gain full control of their
library with multiple named shelves and per-book reading progress.
"""
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Text, ForeignKey,
    Boolean, UniqueConstraint, Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class Shelf(Base):
    __tablename__ = "shelves"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User", backref="shelves")
    items = relationship(
        "ShelfItem",
        back_populates="shelf",
        cascade="all, delete-orphan",
        order_by="ShelfItem.created_at.desc()",
    )

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_shelf_user_name"),
        Index("ix_shelves_user_default", "user_id", "is_default"),
    )

    def __repr__(self):
        return f"<Shelf {self.id}: user={self.user_id} name={self.name!r}>"


class ShelfItem(Base):
    __tablename__ = "shelf_items"

    id = Column(Integer, primary_key=True, index=True)
    shelf_id = Column(Integer, ForeignKey("shelves.id"), nullable=False, index=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False, index=True)
    created_at = Column(DateTime, server_default=func.now())

    shelf = relationship("Shelf", back_populates="items")
    book = relationship("Book", backref="shelf_items")

    __table_args__ = (
        UniqueConstraint("shelf_id", "book_id", name="uq_shelf_item_shelf_book"),
    )

    def __repr__(self):
        return f"<ShelfItem {self.id}: shelf={self.shelf_id} book={self.book_id}>"


class ReadingProgress(Base):
    __tablename__ = "reading_progress"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False, index=True)
    percent = Column(Float, default=0.0)          # 0.0 - 1.0
    position = Column(String(500), nullable=True) # bookmark anchor / cfi
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    book = relationship("Book", backref="reading_progress")

    __table_args__ = (
        UniqueConstraint("user_id", "book_id", name="uq_reading_user_book"),
    )

    def __repr__(self):
        return f"<ReadingProgress {self.id}: user={self.user_id} book={self.book_id} {self.percent:.0%}>"