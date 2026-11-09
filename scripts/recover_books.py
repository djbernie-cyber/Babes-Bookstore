"""Recovery script: re-scrape books from all sources and export to JSON for
import into Netlify Blobs (NoSQL store).

Usage:
  cd backend
  DEBUG=true SECRET_KEY=x DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/babes_bookstore \\
    python ../scripts/recover_books.py --output ../data/books_export.json --limit 500

Then import via the Netlify Function admin endpoint or manually upload to Blobs.

Note: Full re-scrape of ~96,000 books takes hours. Run in batches per source.
"""
import argparse
import asyncio
import inspect
import json
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, BACKEND)

from app.sources.registry import SourceRegistry


async def scrape_source(source_name: str, limit: int = 100, start_page: int = 1):
    """Scrape books from a single source and return list of dicts."""
    reg = SourceRegistry()
    source = reg.get(source_name)
    items = []
    try:
        # Use harvest_catalogue for Gutenberg (fetches all pages concurrently)
        if source_name == "gutenberg" and hasattr(source, "harvest_catalogue"):
            items = await source.harvest_catalogue(limit=limit)
        else:
            try:
                if "start_page" in inspect.signature(source.list_popular).parameters:
                    items = await source.list_popular(limit, start_page=start_page)
                else:
                    items = await source.list_popular(limit)
            except TypeError:
                items = await source.list_popular(limit)
    except Exception as e:
        print(f"  Error fetching {source_name}: {e}")
        items = []
    finally:
        await source.close()

    books = []
    for book_data in items:
        # book_data may be a dict or an object
        if hasattr(book_data, "__dict__"):
            d = book_data.__dict__
        elif isinstance(book_data, dict):
            d = book_data
        else:
            d = {}
        books.append({
            "title": d.get("title", "") if isinstance(d, dict) else getattr(book_data, "title", ""),
            "author": d.get("author", "") if isinstance(d, dict) else getattr(book_data, "author", ""),
            "description": d.get("description", "") if isinstance(d, dict) else getattr(book_data, "description", ""),
            "source": source_name,
            "source_id": (d.get("source_id", "") if isinstance(d, dict) else getattr(book_data, "source_id", "")),
            "source_url": (d.get("source_url", "") if isinstance(d, dict) else getattr(book_data, "source_url", "")),
            "license_type": (d.get("license_type", "public_domain") if isinstance(d, dict) else getattr(book_data, "license_type", "public_domain")),
            "license_url": (d.get("license_url", "") if isinstance(d, dict) else getattr(book_data, "license_url", "")),
            "category": (d.get("category", "") if isinstance(d, dict) else getattr(book_data, "category", "")),
            "tags": (d.get("tags", []) if isinstance(d, dict) else getattr(book_data, "tags", [])),
            "language": (d.get("language", "en") if isinstance(d, dict) else getattr(book_data, "language", "en")),
            "page_count": (d.get("page_count") if isinstance(d, dict) else getattr(book_data, "page_count", None)),
            "publication_year": (d.get("publication_year") if isinstance(d, dict) else getattr(book_data, "publication_year", None)),
            "cover_url": (d.get("cover_url", "") if isinstance(d, dict) else getattr(book_data, "cover_url", "")),
            "download_url": (d.get("download_url", "") if isinstance(d, dict) else getattr(book_data, "download_url", "")),
            "status": "approved",
            "asset_verified": (d.get("asset_verified", False) if isinstance(d, dict) else getattr(book_data, "asset_verified", False)),
        })
    return books[:limit]


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

    out_dir = os.path.dirname(os.path.abspath(args.output))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(all_books, f, ensure_ascii=False, indent=2)

    print(f"\nExported {len(all_books)} books to {args.output}")


if __name__ == "__main__":
    asyncio.run(main())