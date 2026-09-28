"""Who may see a book, and who may have the file.

These are two different questions and conflating them is what made the
catalogue feel censored. A reader asking "does this book exist, and who wrote
it?" is answered by the catalogue. A reader asking "may I take the file home?"
is answered by the licence position. Hiding a title from the first question
because the second is unresolved loses the reader nothing and gains nothing
legally -- it just makes the catalogue look smaller than it is.

So:

* discoverable -- may appear in listings, search, categories, authors, home.
  Requires editorial approval only.
* sellable -- may be downloaded, read, bundled or purchased. Requires
  approval AND a confirmed licence position.

The delivery gate stays. The storefront tells buyers every book is verified
public domain or openly licensed; if an unconfirmed file were downloadable
that sentence would be false, and the person who finds out would be a
customer who paid for it. Making a title findable costs nothing and misleads
no one, so that is the half that gets relaxed.

Stated once, here, because the previous version of this policy was
copy-pasted across a dozen call sites and had already drifted.
"""
from sqlalchemy import and_

from ..models.book import Book, BookStatus


def discoverable():
    """Books a reader may find: approved, regardless of licence state."""
    return Book.status == BookStatus.APPROVED


def sellable():
    """Books whose file may be delivered: approved and licence-confirmed."""
    return and_(Book.status == BookStatus.APPROVED, Book.asset_verified.is_(True))


def is_sellable(book) -> bool:
    """Row-level check, for the places that already hold a Book instance."""
    return bool(
        book is not None
        and book.status == BookStatus.APPROVED
        and book.asset_verified
    )


def delivery_block_reason(book) -> str | None:
    """Why the file cannot be delivered, or None if it can.

    The wording is shown to the reader, so it says what is actually true
    rather than implying a legal judgement has been made about the work.
    """
    if book is None:
        return "Book not found"
    if book.status != BookStatus.APPROVED:
        return "This book has not been approved for the catalogue yet"
    if not book.asset_verified:
        return (
            "Listed for reference only — its licence status is still being "
            "confirmed, so the file is not available yet"
        )
    return None
