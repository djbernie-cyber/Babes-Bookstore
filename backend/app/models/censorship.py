from sqlalchemy import Column, Integer, String, Boolean, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..database import Base


class CensorshipStatus(str):
    BANNED = "banned"
    RESTRICTED = "restricted"
    CONTESTED = "contested"


class CensorshipRecord(Base):
    """Why a book is (or was) banned, by country/regime.

    Powers the 'Illegal Books Catalog' — public-domain works the world has
    tried to silence, with the story of each ban so a reader can decide for
    themselves. Books stay read-anyway: records exist to explain, not gate.
    """

    __tablename__ = "censorship_records"

    id = Column(Integer, primary_key=True, index=True)
    #: The work's suppression record is a historical fact; carrying an edition
    #: is a separate licensing decision. Book is NULL for works still in
    #: copyright (most of the modern African / postcolonial canon) so the
    #: archive can document a ban without claiming to host the book.
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=True, index=True)
    #: Fallback identity for records with no carried edition. At least one of
    #: book_id / work_title is always present (enforced by check constraint).
    work_title = Column(String(240), nullable=True, index=True)
    work_author = Column(String(180), nullable=True)
    work_year = Column(String(24), nullable=True)
    #: ISO 3166-1 alpha-2 country code (e.g. "US", "ZA", "GB", "X" for transnational).
    country_code = Column(String(2), nullable=False, index=True)
    country_name = Column(String(80), nullable=True)
    status = Column(String(20), default=CensorshipStatus.BANNED, index=True)
    ban_reason = Column(Text, nullable=False)          # the "why banned" essay
    banned_since = Column(String(40), nullable=True)   # free-text year/era
    source_url = Column(Text, nullable=True)           # to the documented source
    notes = Column(Text, nullable=True)

    #: moderation flow — users can flag, super-admins verify.
    verified = Column(Boolean, default=True)
    verified_by = Column(String(60), default="seed")
    proposed_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # flags by users

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    book = relationship("Book", backref="censorship_records")

    def __repr__(self):
        return f"<CensorshipRecord {self.id}: book={self.book_id} {self.country_code} {self.status}>"