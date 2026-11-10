"""Build the Geometry Nodes asset library (headless).

    blender -b --factory-startup --python tools/gn/build_asset.py -- \
        --asset assets/geometry_nodes.blend

Creates/refreshes every node group in this package, marks them as assets and
saves a clean .blend that any project can link or append from. Node groups are
added to the "Geometry Nodes" asset catalog when the catalog file is writable.
"""

import argparse
import json
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import hex_array  # noqa: E402

DEFAULT_ASSET = os.path.join(WORKSPACE, "assets", "geometry_nodes.blend")
CATALOG = "Geometry Nodes"


def _parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--asset", default=DEFAULT_ASSET)
    return ap.parse_args(argv)


def _clean_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)


def _mark_asset(ng):
    if not ng.asset_data:
        ng.asset_mark()
    ng.asset_data.description = ng.description or hex_array.DESCRIPTION
    existing = {t.name for t in ng.asset_data.tags}
    for tag in ("geometry nodes", "hex", "array", "instancing"):
        if tag not in existing:
            ng.asset_data.tags.new(tag)


def main():
    args = _parse_args()
    os.makedirs(os.path.dirname(args.asset), exist_ok=True)
    _clean_scene()

    ng = hex_array.build()
    _mark_asset(ng)
    ng.use_fake_user = True

    bpy.ops.wm.save_as_mainfile(filepath=args.asset, compress=True)
    summary = {
        "asset": bpy.data.filepath,
        "node_group": ng.name,
        "is_modifier": bool(ng.is_modifier),
        "asset_marked": bool(ng.asset_data),
        "inputs": hex_array.inputs_summary(ng),
    }
    print("GN_ASSET_JSON " + json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
