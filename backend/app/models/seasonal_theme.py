from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime
from sqlalchemy.sql import func
from ..database import Base


class SeasonalTheme(Base):
    """Holiday / locale theming + shelf furniture for the reading season.

    Admins compose themes against a geographic/locale context (the region they
    serve and the seasonal window they want to celebrate). When a theme is live
    it injects CSS variables ("overrides") into the whole site and brings a
    featured shelf + club/author-birthday showcase into the homepage rotation.
    """

    __tablename__ = "seasonal_themes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    slug = Column(String(120), unique=True, nullable=False, index=True)

    #: Locale this theme speaks to, e.g. "en-KE" / "sw-KE" / "all".
    locale = Column(String(10), default="all", nullable=False)
    #: Two-letter region the admin is arranging for (ISO 3166-1 alpha-2).
    country_code = Column(String(2), nullable=True)

    #: Holiday window the theme lives inside. null = always on.
    starts_at = Column(DateTime, nullable=True)
    ends_at = Column(DateTime, nullable=True)

    is_default = Column(Boolean, default=False)
    active = Column(Boolean, default=True)

    #: JSON object of CSS custom properties injected on :root (
    #: accent, background tints, fonts, borders, corners, density...).
    overrides = Column(Text, nullable=True)
    #: JSON: {"shelf_title": str, "bundle_ids": [..], "birthdays": [{"month":..,"day":..,"author":..,"bundle_id":..,"book_ids":[..]}], "banner_url": str}
    shelf_config = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<SeasonalTheme {self.id}: {self.slug}>"


class SiteConfig(Base):
    """Single-row store for admin-arranged site furniture (homepage shelf
    layout order + featured placement) and one-off presentation settings."""

    __tablename__ = "site_config"

    id = Column(Integer, primary_key=True, default=1)
    #: JSON list of shelf module keys in display order, e.g.
    #: ["hero","seasonal","featured","author-birthdays","new","categories","bundles", ...]
    furniture = Column(Text, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())