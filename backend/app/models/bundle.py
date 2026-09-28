from sqlalchemy import (
    JSON,
    Column,
    String,
    Text,
    Boolean,
    Integer,
    DateTime,
    ForeignKey,
)
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
    tags = Column(JSON, nullable=True)

    meta_title = Column(String(200), nullable=True)
    meta_description = Column(String(500), nullable=True)

    active = Column(Boolean, default=True, index=True)
    featured = Column(Boolean, default=False, index=True)
    bundle_type = Column(String(50), default="curated")

    # NULL means this bundle is a product: curated, admin-made, or the
    # anonymous one-off checkout needs. Set means it is a reader's own
    # collection -- excluded from the public listing, invisible to anyone but
    # the owner, and not purchasable. See b7c8d9e0f1a2 for why the distinction
    # has to live in the catalogue table rather than only in the API.
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    bundle_books = relationship(
        "BundleBook",
        back_populates="bundle",
        cascade="all, delete-orphan",
        order_by="BundleBook.sort_order",
    )
    purchases = relationship("Purchase", back_populates="bundle")
    owner = relationship("User", back_populates="owned_bundles")

    @property
    def is_personal(self) -> bool:
        """True for a reader's own collection rather than a product."""
        return self.owner_id is not None

    def visible_to(self, user) -> bool:
        """Whether `user` may see this bundle at all.

        Products are public. A personal bundle is only ever visible to the
        reader who made it -- not to other signed-in readers, and not to
        admins. Admins get at them through the database and the admin tooling,
        which is the point: these are someone else's reading lists, and
        "admin can see it" is how a shared catalogue starts selling books back
        to the people who brought them in.
        """
        return self.owner_id is None or (user is not None and user.id == self.owner_id)

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