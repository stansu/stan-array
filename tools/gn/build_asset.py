"""Build the Geometry Nodes asset libraries (headless).

    blender -b --factory-startup --python tools/gn/build_asset.py -- \
        --asset assets/geometry_nodes.blend

每个 node group 存進**自己的** asset 檔（Stan Array 與 Stan Box 分開），
建立/更新 group、標記為 Asset，並存成任何專案都能 link/append 的乾淨 .blend。
"""

import argparse
import json
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import stan_array  # noqa: E402
import box_generator  # noqa: E402

CATALOG = "Geometry Nodes"

# 一個 group 一個 asset 檔（不要把它們放在一起）
MODULES = [
    (stan_array, ("geometry nodes", "array", "instancing", "hex", "curve",
                  "radial", "triangle"),
     os.path.join(WORKSPACE, "assets", "geometry_nodes.blend")),
    (box_generator, ("geometry nodes", "box", "generator", "hollow",
                     "instancing"),
     os.path.join(WORKSPACE, "assets", "box_nodes.blend")),
]


def _parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--asset", default=None,
                    help="只建這個 asset 檔（預設：全部，各自一個檔）")
    ap.add_argument("--group", default=None,
                    help="只建這個 node group（Stan Array / Stan Box）")
    return ap.parse_args(argv)


def _clean_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    for ng in list(bpy.data.node_groups):
        bpy.data.node_groups.remove(ng)
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat)
    bpy.ops.wm.read_factory_settings(use_empty=True)


def _mark_asset(ng, tags):
    if not ng.asset_data:
        ng.asset_mark()
    ng.asset_data.description = ng.description
    existing = {t.name for t in ng.asset_data.tags}
    for tag in tags:
        if tag not in existing:
            ng.asset_data.tags.new(tag)


def main():
    args = _parse_args()
    groups = []
    for module, tags, asset in MODULES:
        if args.group and module.NAME != args.group:
            continue
        if args.asset and os.path.abspath(args.asset) != os.path.abspath(asset):
            continue
        _clean_scene()
        ng = module.build()
        _mark_asset(ng, tags)
        ng.use_fake_user = True
        os.makedirs(os.path.dirname(asset), exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=asset, compress=True)
        groups.append({
            "name": ng.name,
            "asset": bpy.data.filepath,
            "description": ng.description,
            "nodes": len(ng.nodes),
            "links": len(ng.links),
            "inputs": module.inputs_summary(ng),
        })

    print("GN_ASSET_JSON " + json.dumps({
        "groups": [{k: g[k] for k in ("name", "asset", "description",
                                      "nodes", "links")} for g in groups],
        "inputs": {g["name"]: g["inputs"] for g in groups},
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
