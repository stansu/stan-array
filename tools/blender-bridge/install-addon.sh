#!/usr/bin/env bash
# Install the Blender Bridge add-on into Blender's addons folder.
#
#   ./install-addon.sh              # every Blender version found in ~/.config/blender
#   ./install-addon.sh 4.5          # just that version
#   ./install-addon.sh --check      # only report what is installed
#
# The add-on is a single self-contained file; it keeps its own snapshots next to
# itself unless BLENDER_BRIDGE_DIR says otherwise. A previous add-on is backed up
# as blender_bridge_addon.py.bak.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMPL="$HERE/blender_bridge_addon.py"
BASE="${XDG_CONFIG_HOME:-$HOME/.config}/blender"
BLENDER_BIN="${BLENDER_BIN:-$(command -v blender || true)}"

check=0
version=""
for arg in "$@"; do
  case "$arg" in
    --check) check=1 ;;
    *) version="$arg" ;;
  esac
done

if [[ ! -f "$IMPL" ]]; then
  echo "missing add-on: $IMPL" >&2
  exit 1
fi

targets=()
if [[ -n "$version" ]]; then
  targets+=("$BASE/$version/scripts/addons")
else
  for d in "$BASE"/*/scripts/addons; do
    [[ -d "$d" ]] && targets+=("$d")
  done
fi

if [[ ${#targets[@]} -eq 0 ]]; then
  echo "no Blender addons folder under $BASE" >&2
  echo "create one, e.g.: mkdir -p $BASE/4.5/scripts/addons" >&2
  exit 1
fi

for dir in "${targets[@]}"; do
  dest="$dir/blender_bridge_addon.py"
  if (( check )); then
    if [[ -f "$dest" ]]; then
      echo "installed: $dest"
      grep -n "^VERSION\|^PORT" "$dest" | head -3 || true
    else
      echo "not installed: $dest"
    fi
    continue
  fi
  mkdir -p "$dir"
  [[ -f "$dest" ]] && cp -p "$dest" "$dest.bak"
  cp "$IMPL" "$dest"
  echo "wrote $dest"
done

(( check )) && exit 0

echo
echo "Enable it once per Blender version (writes user preferences):"
echo "  ${BLENDER_BIN:-blender} --background --python-expr \\"
echo "    \"import bpy; bpy.ops.preferences.addon_enable(module='blender_bridge_addon'); bpy.ops.wm.save_userpref()\""
echo
echo "Then start Blender normally; the bridge listens on 127.0.0.1:9877."
echo "Verify:  python3 bridge.py '{\"op\": \"ping\"}'"
