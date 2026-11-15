#!/bin/sh
# Netlify (Drop and CLI) skips folders named node_modules, so the icon fonts Expo exports to
# dist/assets/node_modules/... never get uploaded and icons render as empty boxes. Rename + rewrite refs.
set -e
cd "$(dirname "$0")/.."
[ -d dist/assets/node_modules ] || { echo "nothing to fix"; exit 0; }
mv dist/assets/node_modules dist/assets/nm
grep -rl "/assets/node_modules/" dist | while read f; do
  perl -pi -e 's#/assets/node_modules/#/assets/nm/#g' "$f"
done
echo "fixed: fonts now under dist/assets/nm"
