"""Scrape Gutenberg books in batches using list_popular with pagination.
Supports --start-page for resuming. Appends to existing output file.
"""
import argparse
import asyncio
import json
import os
import sys
import time

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, BACKEND)

from app.sources.gutenberg import GutenbergSource


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="/tmp/gb_batch.json")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--start-page", type=int, default=1)
    args = parser.parse_args()

    s = GutenbergSource()
    t0 = time.time()
    try:
        books = await s.list_popular(limit=args.limit, start_page=args.start_page)
        print(f"Got {len(books)} books in {time.time()-t0:.1f}s")
        data = []
        for b in books:
            d = b.__dict__ if hasattr(b, "__dict__") else {}
            data.append({
                "title": getattr(b, "title", "") or d.get("title", ""),
                "author": getattr(b, "author", "") or d.get("author", ""),
                "description": getattr(b, "description", "") or d.get("description", ""),
                "source": "gutenberg",
                "source_id": str(getattr(b, "source_id", "") or d.get("source_id", "")),
                "source_url": getattr(b, "source_url", "") or d.get("source_url", ""),
                "license_type": "public_domain",
                "license_url": getattr(b, "license_url", "") or d.get("license_url", ""),
                "category": getattr(b, "category", "") or d.get("category", ""),
                "tags": getattr(b, "tags", []) or d.get("tags", []),
                "language": getattr(b, "language", "en") or d.get("language", "en"),
                "page_count": getattr(b, "page_count", None) or d.get("page_count"),
                "publication_year": getattr(b, "publication_year", None) or d.get("publication_year"),
                "cover_url": getattr(b, "cover_url", "") or d.get("cover_url", ""),
                "download_url": getattr(b, "epub_url", "") or d.get("epub_url", ""),
                "status": "approved",
                "asset_verified": True,
            })
        # Append to existing file if it exists
        existing = []
        if os.path.exists(args.output):
            try:
                with open(args.output) as f:
                    existing = json.load(f)
            except:
                existing = []
        existing.extend(data)
        # dedup by source_id
        seen = set()
        unique = []
        for b in existing:
            key = b.get("source_id", "")
            if key and key not in seen:
                seen.add(key)
                unique.append(b)
            elif not key:
                unique.append(b)
        with open(args.output, "w") as f:
            json.dump(unique, f)
        print(f"Saved {len(unique)} total books to {args.output}")
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        await s.close()


if __name__ == "__main__":
    asyncio.run(main())