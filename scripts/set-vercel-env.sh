#!/usr/bin/env bash
set -euo pipefail
FILE="${1:-.env}"
[ -f "$FILE" ] || { echo "Missing $FILE"; exit 1; }

while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in ''|\#*) continue ;; esac
  key="${line%%=*}"
  value="${line#*=}"
  [ -z "$value" ] && { echo "skip $key (empty)"; continue; }
  for target in production preview development; do
    vercel env rm "$key" "$target" -y >/dev/null 2>&1 || true
    printf '%s' "$value" | vercel env add "$key" "$target" >/dev/null
  done
  echo "set  $key"
done < "$FILE"
echo "Done. Redeploy with: vercel --prod"