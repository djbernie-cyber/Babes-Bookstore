"""Recovery script: re-scrape books from all sources and export to JSON for
import into Netlify Blobs (NoSQL store).

Usage:
  cd backend
  python -m scripts.recover_books --output ../data/books_export.json --limit 500

Then import via the Netlify Function admin endpoint or manually upload to Blobs.

Note: Full re-scrape of ~96,000 books takes hours. Run in batches.
"""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.sources.registry import SourceRegistry
from app.database import AsyncSessionLocal
from app.models.book import Book, BookStatus
from sqlalchemy import select


async def scrape_source(source_name: str, limit: int = 100, start_page: int = 1):
    """Scrape books from a single source and return list of dicts."""
    reg = SourceRegistry()
    source = reg.get(source_name)
    books = []
    try:
        async for book_data in source.scrape(limit=limit, start_page=start_page):
            books.append({
                "title": book_data.get("title", ""),
                "author": book_data.get("author", ""),
                "description": book_data.get("description", ""),
                "source": source_name,
                "source_id": book_data.get("source_id", ""),
                "source_url": book_data.get("source_url", ""),
                "license_type": book_data.get("license_type", "public_domain"),
                "license_url": book_data.get("license_url", ""),
                "category": book_data.get("category", ""),
                "tags": book_data.get("tags", []),
                "language": book_data.get("language", "en"),
                "page_count": book_data.get("page_count"),
                "publication_year": book_data.get("publication_year"),
                "cover_url": book_data.get("cover_url", ""),
                "download_url": book_data.get("download_url", ""),
                "status": "approved",
                "asset_verified": book_data.get("asset_verified", False),
            })
            if len(books) >= limit:
                break
    except Exception as e:
        print(f"Error scraping {source_name}: {e}")
    finally:
        await source.close()
    return books


async def main():
    parser = argparse.ArgumentParser(description="Re-scrape books and export to JSON")
    parser.add_argument("--output", default="books_export.json", help="Output JSON file")
    parser.add_argument("--sources", nargs="+", default=None, help="Sources to scrape (default: all)")
    parser.add_argument("--limit", type=int, default=100, help="Books per source")
    parser.add_argument("--start-page", type=int, default=1, help="Start page")
    args = parser.parse_args()

    reg = SourceRegistry()
    sources = args.sources or list(reg._classes.keys())

    all_books = []
    for src in sources:
        print(f"Scraping {src} (limit={args.limit})...")
        books = await scrape_source(src, limit=args.limit, start_page=args.start_page)
        all_books.extend(books)
        print(f"  -> {len(books)} books from {src}")

    # Assign sequential IDs
    for i, b in enumerate(all_books, 1):
        b["id"] = i

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(all_books, f, ensure_ascii=False, indent=2)

    print(f"\nExported {len(all_books)} books to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
PY