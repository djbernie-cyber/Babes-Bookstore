"""Import the full book dataset into Netlify Blobs via the admin endpoint.
Run after deploying to Netlify.

Usage:
  python scripts/import_to_netlify.py --url https://YOUR-SITE.netlify.app --token YOUR_ADMIN_TOKEN --batch 500
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error


def main():
    parser = argparse.ArgumentParser(description="Import books into Netlify Blobs")
    parser.add_argument("--url", required=True, help="Netlify site URL (e.g. https://site.netlify.app)")
    parser.add_argument("--token", required=True, help="Admin JWT token")
    parser.add_argument("--batch", type=int, default=500, help="Books per batch")
    parser.add_argument("--input", default="data/books_full.json", help="Input JSON file")
    args = parser.parse_args()

    base = args.url.rstrip("/")
    endpoint = f"{base}/api/v1/admin/books/import"

    with open(args.input, encoding="utf-8") as f:
        books = json.load(f)
    print(f"Loaded {len(books)} books from {args.input}")

    total_imported = 0
    for i in range(0, len(books), args.batch):
        batch = books[i:i + args.batch]
        payload = json.dumps({"books": batch}).encode("utf-8")
        req = urllib.request.Request(endpoint, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {args.token}")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                total_imported += result.get("imported", 0)
                print(f"Batch {i//args.batch + 1}: imported {result.get('imported', 0)}, total now {result.get('total', '?')}")
        except urllib.error.HTTPError as e:
            print(f"Batch {i//args.batch + 1} FAILED: {e.code} {e.read().decode('utf-8')[:200]}")
            break
        except Exception as e:
            print(f"Batch {i//args.batch + 1} ERROR: {e}")
            break
        time.sleep(1)  # rate limit

    print(f"\nDone. Total imported: {total_imported}")


if __name__ == "__main__":
    main()
PY