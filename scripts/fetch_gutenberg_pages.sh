#!/bin/bash
# Fetch Gutenberg pages via curl and save raw JSON
OUTDIR="/tmp/gb_pages"
mkdir -p "$OUTDIR"
for i in $(seq 1 100); do
    if [ -f "$OUTDIR/page_$i.json" ]; then
        echo "Page $i already fetched, skipping"
        continue
    fi
    curl -s "https://gutendex.com/books/?copyright=false&page=$i&sort=popular" -o "$OUTDIR/page_$i.json" 2>/dev/null
    echo "Fetched page $i"
    sleep 0.5
done
echo "Done fetching 100 pages"