"""Scrape ALL Gutenberg books by fetching pages individually.
Writes to output file incrementally. Supports resuming via --start-page.
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
    parser.add_argument("--output", default="/tmp/gb_all.json")
    parser.add_argument("--start-page", type=int, default=1)
    parser.add_argument("--max-pages", type=int, default=99999)
    args = parser.parse_args()

    s = GutenbergSource()
    t0 = time.time()
    total = 0
    page = args.start_page
    existing = []
    if os.path.exists(args.output):
        try:
            with open(args.output) as f:
                existing = json.load(f)
            seen_ids = {b.get("source_id", "") for b in existing}
            print(f"Resuming: {len(existing)} books already saved")
        except:
            existing = []
            seen_ids = set()
    else:
        seen_ids = set()

    try:
        while page <= args.max_pages:
            try:
                payload = await s._get_page({"sort": "popular", "languages": "en", "copyright": "false"}, page)
            except Exception as e:
                print(f"Page {page} failed: {e}")
                page += 1
                await asyncio.sleep(2)
                continue

            results = payload.get("results", [])
            if not results:
                print(f"No more results at page {page}. Done.")
                break

            new_count = 0
            for raw in results:
                book_id = str(raw.get("id", ""))
                if book_id in seen_ids:
                    continue
                seen_ids.add(book_id)
                # Parse using the source's _parse method
                book = s._parse(raw)
                if book:
                    d = book.__dict__ if hasattr(book, "__dict__") else {}
                    existing.append({
                        "title": getattr(book, "title", "") or d.get("title", ""),
                        "author": getattr(book, "author", "") or d.get("author", ""),
                        "description": getattr(book, "description", "") or d.get("description", ""),
                        "source": "gutenberg",
                        "source_id": str(getattr(book, "source_id", "") or d.get("source_id", "")),
                        "source_url": getattr(book, "source_url", "") or d.get("source_url", ""),
                        "license_type": "public_domain",
                        "license_url": getattr(book, "license_url", "") or d.get("license_url", ""),
                        "category": getattr(book, "category", "") or d.get("category", ""),
                        "tags": getattr(book, "tags", []) or d.get("tags", []),
                        "language": getattr(book, "language", "en") or d.get("language", "en"),
                        "page_count": getattr(book, "page_count", None) or d.get("page_count"),
                        "publication_year": getattr(book, "publication_year", None) or d.get("publication_year"),
                        "cover_url": getattr(book, "cover_url", "") or d.get("cover_url", ""),
                        "download_url": getattr(book, "epub_url", "") or d.get("epub_url", ""),
                        "status": "approved",
                        "asset_verified": True,
                    })
                    new_count += 1

            total += new_count
            # Save incrementally every 10 pages
            if page % 10 == 0:
                with open(args.output, "w") as f:
                    json.dump(existing, f)
                elapsed = time.time() - t0
                print(f"Page {page}: +{new_count} (total: {len(existing)}) in {elapsed:.0f}s")

            if not payload.get("next"):
                print(f"Reached end of catalogue at page {page}.")
                break

            page += 1
            await asyncio.sleep(s.rate_limit)

        # Final save
        with open(args.output, "w") as f:
            json.dump(existing, f)
        print(f"\nDone: {len(existing)} books saved to {args.output}")

    except Exception as e:
        import traceback
        traceback.print_exc()
        # Save what we have
        with open(args.output, "w") as f:
            json.dump(existing, f)
        print(f"Saved {len(existing)} books before error.")
    finally:
        await s.close()


if __name__ == "__main__":
    asyncio.run(main())
PY