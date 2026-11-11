#!/bin/sh
# Refuse to package/publish if restricted (non-redistributable) third-party assets are inside the tree. Exit 1 if any are found.
# Restricted: the pixiv VRoid VRMA motion pack (assets/chars/vrma, Readme_VRMA_MotionPack*) and the Runa Inoue VRM.
# The CMU / Quaternius clips in assets/dance/*.vrma are redistributable (see THIRD_PARTY_NOTICES.md) and are allowed.
# Use before `docker build`, tar/zip or a git push:  sh scripts/check-restricted-assets.sh [dir]
D="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
bad=$(find "$D" \( -path "$D/uat" -o -path "$D/.venv" -o -path "$D/cache" -o -path "$D/lcache" -o -path "$D/.git" \) -prune -o \( -path '*/chars/vrma/*' -o -name 'Runa_Inoue*.vrm' -o -iname 'Readme_VRMA_MotionPack*' -o -iname 'VRMA_MotionPack*' \) -print)
if [ -n "$bad" ]; then
  echo "Restricted assets found (not redistributable; see docs/GAME_CREDITS.md):"; echo "$bad"; exit 1
fi
echo "OK: no restricted VRMA motion-pack / Runa assets under $D"
