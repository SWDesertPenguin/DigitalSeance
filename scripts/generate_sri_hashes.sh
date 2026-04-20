#!/usr/bin/env bash
# Generate sha384 Subresource Integrity hashes for every CDN asset
# pinned in frontend/index.html. Prints the integrity= attribute
# value for each URL; operator pastes them into index.html.
#
# Usage:
#   bash scripts/generate_sri_hashes.sh
#
# Task T204.

set -euo pipefail

URLS=(
  "https://unpkg.com/react@18.3.1/umd/react.production.min.js"
  "https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js"
  "https://cdn.jsdelivr.net/npm/@babel/standalone@7.25.9/babel.min.js"
  "https://cdn.jsdelivr.net/npm/marked@15.0.3/marked.min.js"
  "https://cdn.jsdelivr.net/npm/dompurify@3.2.2/dist/purify.min.js"
)

for url in "${URLS[@]}"; do
  hash=$(curl -fsSL "$url" | openssl dgst -sha384 -binary | openssl base64 -A)
  echo "$url"
  echo "  integrity=\"sha384-$hash\""
  echo
done
