#!/usr/bin/env python3
"""gn.py — Geometry Nodes toolkit CLI.

Talks to the *live* Blender through the Blender Bridge (tools/blender-bridge),
so whatever you see on screen is what gets the modifier.

    python3 tools/gn/gn.py build                 # 重建 assets/geometry_nodes.blend
    python3 tools/gn/gn.py inputs                # 列出 node group 的參數
    python3 tools/gn/gn.py list                  # 目前 Blender 裡的 GN node groups
    python3 tools/gn/gn.py apply --object Host --collection Tiles \
        --set count_long=16 --set count_short=10 --set cell=0.2 --set seed=7
    python3 tools/gn/gn.py demo                  # 建一組示範 tiles 並套用 + 算圖

參數名稱（給 --set）:
    count_long, count_short, cell, spacing, size_random, spacing_random,
    yaw, collection_count, source_size, seed
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(os.path.dirname(HERE))
ASSET = os.path.join(WORKSPACE, "assets", "geometry_nodes.blend")
GROUPS = {"hex": "Hex Array", "array": "Array"}
MODULES = {"hex": "hex_array", "array": "array_gn"}
GROUP = GROUPS["hex"]
MODULE = MODULES["hex"]


def _find_blender():
    env = os.environ.get("BLENDER_BIN")
    if env and os.path.exists(env):
        return env
    found = shutil.which("blender")
    if found:
        return found
    # 這個 repo 以 Blender 4.5 建置；先找 4.5，再退回最新版
    for pattern in ("~/apps/blender/blender-4.5*/blender",
                    "~/apps/blender/blender-*/blender",
                    "/opt/blender*/blender",
                    "/usr/local/blender*/blender"):
        hits = sorted(glob.glob(os.path.expanduser(pattern)))
        if hits:
            return hits[-1]
    return "blender"


BLENDER = _find_blender()
BRIDGE_DIR = os.path.join(WORKSPACE, "tools", "blender-bridge")
OUT_DIR = os.path.join(WORKSPACE, ".bridge")

sys.path.insert(0, BRIDGE_DIR)
import bridge  # noqa: E402

PREAMBLE = ("import bpy, os, sys, json, math\n"
            "sys.path.insert(0, %r)\n" % HERE)

ALIASES = {
    "mode": "Mode",
    "unit_from_collection": "Unit From Collection",
    "use_collection": "Unit From Collection",
    "point_collection": "Point Collection",
    "direction": "Direction",
    "count": "Count",
    "count_x": "Count X",
    "count_y": "Count Y",
    "step": "Step",
    "gap": "Gap",
    "length": "Length",
    "length_y": "Length Y",
    "radius": "Radius",
    "arc": "Arc",
    "start_angle": "Start Angle",
    "surface": "Surface",
    "mesh_mode": "Mesh Mode",
    "density": "Density",
    "align": "Align",
    "forward_axis": "Forward Axis",
    "up_axis": "Up Axis",
    "random_offset": "Random Offset",
    "random_rotate": "Random Rotate",
    "random_scale": "Random Scale",
    "mirror": "Mirror",
    "mirror_axis": "Mirror Axis",
    "gradient_scale": "Gradient Scale",
    "gradient_rotate": "Gradient Rotate",
    "realize": "Realize",
    "count_long": "Count Long",
    "count_short": "Count Short",
    "cell": "Cell Size",
    "cell_size": "Cell Size",
    "spacing": "Spacing",
    "size_random": "Size Random",
    "spacing_random": "Spacing Random",
    "yaw": "Yaw Random",
    "yaw_random": "Yaw Random",
    "collection_count": "Collection Count",
    "scale": "Scale",
    "seed": "Seed",
}

# 讓 CLI 可以用名字設定 Int 列舉
ENUMS = {
    "Mode": {"linear": 0, "grid": 1, "radial": 2, "curve": 3,
             "mesh": 4, "collection": 5, "points": 5},
    "Spacing": {"step": 0, "gap": 1, "fit": 2},
    "Align": {"natural": 0, "forward": 1, "up": 2},
    "Mesh Mode": {"vertices": 0, "edges": 1, "faces": 2, "surface": 3},
    "Mirror Axis": {"x": 0, "y": 1, "z": 2},
    "Forward Axis": {"x": 0, "y": 1, "z": 2},
    "Up Axis": {"x": 0, "y": 1, "z": 2},
}


# --------------------------------------------------------------------- bridge
def run(code, timeout=180):
    resp = bridge.send({"code": PREAMBLE + code, "timeout": timeout},
                       timeout=timeout + 30)
    if resp.get("stdout"):
        sys.stdout.write(resp["stdout"])
    if resp.get("traceback"):
        sys.stderr.write(resp["traceback"])
    if resp.get("status") != "ok":
        raise SystemExit("Blender 端執行失敗 (%s)" % resp.get("status"))
    return resp


def op(req, timeout=180):
    req = dict(req, timeout=timeout)
    resp = bridge.send(req, timeout=timeout + 30)
    if resp.get("traceback"):
        sys.stderr.write(resp["traceback"])
    return resp


def run_json(code, timeout=180):
    """Run code whose last statement prints a JSON blob prefixed GN_JSON."""
    out = run(code, timeout=timeout)
    for line in (out.get("stdout") or "").splitlines():
        if line.startswith("GN_JSON "):
            return json.loads(line[len("GN_JSON "):])
    raise SystemExit("沒有收到 Blender 的結果")


# ------------------------------------------------------------------- commands
def cmd_build(args):
    cmd = [BLENDER, "-b", "--factory-startup", "--python",
           os.path.join(HERE, "build_asset.py"), "--", "--asset", ASSET]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    tail = (proc.stdout or "") + (proc.stderr or "")
    for line in tail.splitlines():
        if "GN_ASSET_JSON " in line:
            payload = line.split("GN_ASSET_JSON ", 1)[1]
            data = json.JSONDecoder().raw_decode(payload)[0]
            print("asset : %s" % data["asset"])
            for group in data["groups"]:
                print("group : %-10s nodes=%-4d links=%-4d  %s"
                      % (group["name"], group["nodes"], group["links"],
                         group["description"]))
            return 0
        if "Error" in line or "Traceback" in line:
            print(line, file=sys.stderr)
    print(tail[-2000:], file=sys.stderr)
    return proc.returncode or 1


def cmd_inputs(args):
    data = run_json(
        "import " + MODULE + "\n"
        "ng = bpy.data.node_groups.get(%r)\n"
        "if ng is None:\n"
        "    print('GN_JSON ' + json.dumps({'exists': False}))\n"
        "else:\n"
        "    print('GN_JSON ' + json.dumps({\n"
        "        'exists': True, 'name': ng.name, 'is_modifier': bool(ng.is_modifier),\n"
        "        'asset': bool(ng.asset_data),\n"
        "        'inputs': " + MODULE + ".inputs_summary(ng)}, ensure_ascii=False))\n" % GROUP)
    if not data.get("exists"):
        print("目前 Blender 沒有 %r（先跑 build，或 apply 會自動 append）" % GROUP)
        return 1
    print("%s  (modifier=%s, asset=%s)" % (data["name"], data["is_modifier"], data["asset"]))
    print("%-24s %-16s %-14s %s" % ("name", "type", "default", "description"))
    for row in data["inputs"]:
        print("%-24s %-16s %-14s %s" % (
            row["name"], row["type"].replace("NodeSocket", ""),
            row["default"] if row["default"] is not None else "-",
            row["description"]))
    return 0


def cmd_list(args):
    data = run_json(
        "print('GN_JSON ' + json.dumps([\n"
        "    {'name': ng.name, 'is_modifier': bool(ng.is_modifier),\n"
        "     'asset': bool(ng.asset_data),\n"
        "     'users': ng.users,\n"
        "     'nodes': len(ng.nodes)}\n"
        "    for ng in bpy.data.node_groups if ng.bl_idname == 'GeometryNodeTree'],\n"
        "    ensure_ascii=False))\n")
    if not data:
        print("（Blender 裡沒有任何 GeometryNodeTree）")
        return 0
    print("%-24s %-10s %-7s %-7s %s" % ("node group", "modifier", "asset", "users", "nodes"))
    for row in data:
        print("%-24s %-10s %-7s %-7s %d" % (
            row["name"], row["is_modifier"], row["asset"], row["users"], row["nodes"]))
    return 0


def cmd_apply(args):
    params = {}
    for item in args.set or []:
        if "=" not in item:
            raise SystemExit("--set 需要 name=value：%r" % item)
        key, value = item.split("=", 1)
        key = key.strip()
        name = ALIASES.get(key, key if key[:1].isupper() else None)
        if name is None:
            raise SystemExit("不認識的參數 %r；可用：%s" % (key, ", ".join(sorted(ALIASES))))
        raw = value.strip()
        if name in ENUMS and raw.lower() in ENUMS[name]:
            raw = str(ENUMS[name][raw.lower()])
        params[name] = raw

    code = """
import hex_array

asset = %(asset)r
group = %(group)r
target = %(target)r
coll_name = %(coll)r
params = json.loads(%(params)r)
fit = %(fit)r
verbose = %(verbose)r
RELOAD = %(reload)r

def report(status, **extra):
    payload = {"status": status}
    payload.update(extra)
    print("GN_JSON " + json.dumps(payload, ensure_ascii=False))

obj = bpy.data.objects.get(target)
if obj is None or obj.type != 'MESH':
    report("no_object", target=target)
    raise SystemExit(1)

coll = bpy.data.collections.get(coll_name) if coll_name else None
if coll_name and coll is None:
    report("no_collection", collection=coll_name)
    raise SystemExit(1)

ng = bpy.data.node_groups.get(group)
if ng is not None and RELOAD:
    ng.use_fake_user = False
    if ng.users == 0:
        bpy.data.node_groups.remove(ng)
        ng = None
if ng is None:
    with bpy.data.libraries.load(asset, link=False) as (src, dst):
        if group not in src.node_groups:
            report("no_group_in_asset", asset=asset)
            raise SystemExit(1)
        dst.node_groups = [group]
    ng = bpy.data.node_groups[group]

mod = obj.modifiers.get(group) or obj.modifiers.new(group, 'NODES')
mod.node_group = ng

# 依 socket 型別轉值
applied = {}
for item in ng.interface.items_tree:
    if item.item_type != 'SOCKET' or item.in_out != 'INPUT':
        continue
    name = item.name
    if name in params:
        raw = params[name]
        if item.socket_type == 'NodeSocketInt':
            value = int(float(raw))
        elif item.socket_type == 'NodeSocketFloat':
            value = float(raw)
        elif item.socket_type == 'NodeSocketBool':
            value = str(raw).lower() in ("1", "true", "yes", "on")
        else:
            value = raw
        mod[item.identifier] = value
        applied[name] = value

def set_input(name, value):
    for it in ng.interface.items_tree:
        if it.item_type == 'SOCKET' and it.in_out == 'INPUT' and it.name == name:
            mod[it.identifier] = value
            return True
    raise KeyError(name)

if coll is not None:
    set_input("Collection", coll)

# Collection 內物件數 + 原始尺寸（fit 用）
objects = [o for o in (coll.objects if coll else []) if o.type == 'MESH']
count = max(1, len(objects))
source = 0.0
for o in objects:
    source = max(source, max(o.dimensions))
if "Collection Count" not in applied:
    set_input("Collection Count", count)
    applied["Collection Count"] = count


bpy.context.view_layer.update()
report("ok", object=obj.name, modifier=mod.name, group=ng.name,
       collection=coll.name if coll else None,
       collection_objects=count, applied=applied,
       modifier_inputs=len([i for i in ng.interface.items_tree
                            if i.item_type == 'SOCKET' and i.in_out == 'INPUT']))
""" % dict(asset=ASSET, group=GROUP, target=args.object, coll=args.collection,
           params=json.dumps(params), fit=args.fit, verbose=args.verbose,
           reload=args.reload)

    data = run_json(code)
    if data.get("status") != "ok":
        raise SystemExit("套用失敗：%s" % json.dumps(data, ensure_ascii=False))
    print("已套用 %s → %s" % (data["group"], data["object"]))
    print("modifier : %s" % data["modifier"])
    if data.get("collection"):
        print("collection: %s（%d 個 mesh）" % (data["collection"], data["collection_objects"]))
    for key, value in data["applied"].items():
        print("  %-18s %s" % (key, value))
    return 0


def cmd_reload(args):
    """把 session 裡的舊 node group 換成 assets 裡整理好的版本。"""
    code = """
import hex_array
asset, group = %(asset)r, %(group)r
ng = bpy.data.node_groups.get(group)
removed = False
if ng is not None:
    ng.use_fake_user = False
    if ng.users == 0 or %(force)r:
        bpy.data.node_groups.remove(ng)
        removed = True
        ng = None
if ng is None:
    if not os.path.exists(asset):
        print("GN_JSON " + json.dumps({"status": "missing_asset", "asset": asset}))
        raise SystemExit(1)
    with bpy.data.libraries.load(asset, link=False) as (src, dst):
        dst.node_groups = [group]
    ng = bpy.data.node_groups[group]
print("GN_JSON " + json.dumps({
    "status": "ok", "removed_old": removed, "group": ng.name,
    "nodes": len(ng.nodes),
    "frames": [n.label for n in ng.nodes if n.bl_idname == "NodeFrame"],
}, ensure_ascii=False))
""" % dict(asset=ASSET, group=GROUP, force=args.force)

    data = run_json(code)
    if data.get("status") != "ok":
        raise SystemExit(json.dumps(data, ensure_ascii=False))
    print("%s → %d 個節點、%d 個分區（舊版%s）" % (
        data["group"], data["nodes"], len(data["frames"]),
        "已移除" if data["removed_old"] else "未動"))
    for label in data["frames"]:
        print("  ·", label)
    return 0


DEMO_CODE = r"""
import bpy, json
from mathutils import Vector

GROUP = "Hex Array"
ASSET = %(asset)r
RELOAD = %(reload)r
CELL = 0.25
RADIUS = CELL / 2.0

def purge(names):
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)

def material(name, color, rough=0.45):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    return mat

purge(["Hex Array Demo", "Hex Demo Floor", "Hex Demo Camera", "Hex Demo Sun",
       "Tile A", "Tile B", "Tile C"])
old = bpy.data.collections.get("Hex Tiles")
if old is not None:
    bpy.data.collections.remove(old)
tiles = bpy.data.collections.new("Hex Tiles")
bpy.context.scene.collection.children.link(tiles)

def hex_prism(name, depth, color, post=None, rough=0.45):
    bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=RADIUS, depth=depth,
                                        location=(0, 0, 0))
    obj = bpy.context.object
    obj.name = name
    obj.data.name = name
    obj.data.materials.append(material("mat " + name, color, rough))
    if post:
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=post[0],
                                            depth=post[1],
                                            location=(0, 0, depth / 2 + post[1] / 2))
        stub = bpy.context.object
        stub.data.materials.append(material("mat " + name + " post", color, rough))
        for c in list(stub.users_collection):
            c.objects.unlink(stub)
        tiles.objects.link(stub)
        stub.select_set(True)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.join()
        obj = bpy.context.object
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    tiles.objects.link(obj)
    return obj

hex_prism("Tile A", 0.020, (0.22, 0.24, 0.27))
hex_prism("Tile B", 0.060, (0.85, 0.55, 0.25))
hex_prism("Tile C", 0.014, (0.20, 0.55, 0.52), post=(0.045, 0.05))
tiles.hide_viewport = True
tiles.hide_render = True

# 地板
bpy.ops.mesh.primitive_plane_add(size=12, location=(0, 0, -0.02))
floor = bpy.context.object
floor.name = "Hex Demo Floor"
floor.data.materials.append(material("mat Floor", (0.55, 0.55, 0.56), 0.6))

# 主機物件（空 mesh + modifier）
mesh = bpy.data.meshes.new("Hex Array Demo")
host = bpy.data.objects.new("Hex Array Demo", mesh)
bpy.context.scene.collection.objects.link(host)

ng = bpy.data.node_groups.get(GROUP)
if ng is not None and RELOAD:
    ng.use_fake_user = False
    bpy.data.node_groups.remove(ng)
    ng = None
if ng is None:
    with bpy.data.libraries.load(ASSET, link=False) as (src, dst):
        dst.node_groups = [GROUP]
    ng = bpy.data.node_groups[GROUP]
mod = host.modifiers.get(GROUP) or host.modifiers.new(GROUP, 'NODES')
mod.node_group = ng

stamps = {"Collection": tiles, "Count Long": 14, "Count Short": 9,
          "Cell Size": CELL, "Spacing": 1.0, "Size Random": 0.0,
          "Spacing Random": 0.0, "Yaw Random": 0.0, "Stagger Columns": False,
          "Collection Count": 3, "Scale": 1.0, "Seed": 3}

def set_input(name, value):
    for it in ng.interface.items_tree:
        if it.item_type == 'SOCKET' and it.in_out == 'INPUT' and it.name == name:
            mod[it.identifier] = value
            return
    raise KeyError(name)

def get_input(name):
    for it in ng.interface.items_tree:
        if it.item_type == 'SOCKET' and it.in_out == 'INPUT' and it.name == name:
            return mod[it.identifier]
    raise KeyError(name)

for key, value in stamps.items():
    set_input(key, value)

# 燈光 / 世界 / 相機
sun = bpy.data.objects.new("Hex Demo Sun", bpy.data.lights.new("Hex Demo Sun", 'SUN'))
sun.data.energy = 3.2
sun.data.angle = 0.18
sun.rotation_euler = (0.75, 0.15, 0.9)
bpy.context.scene.collection.objects.link(sun)

world = bpy.context.scene.world or bpy.data.worlds.new("World")
bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
bg.inputs[0].default_value = (0.045, 0.05, 0.06, 1.0)
bg.inputs[1].default_value = 1.0

cam_data = bpy.data.cameras.new("Hex Demo Camera")
cam = bpy.data.objects.new("Hex Demo Camera", cam_data)
bpy.context.scene.collection.objects.link(cam)
cam.location = Vector((3.1, -3.6, 2.35))
target = Vector((0.0, 0.0, 0.0))
cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
cam_data.lens = 42
bpy.context.scene.camera = cam

scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 40
scene.cycles.use_denoising = True
scene.render.resolution_x = 1100
scene.render.resolution_y = 800
scene.render.film_transparent = False
scene.view_settings.view_transform = 'AgX'
scene.render.filepath = %(render)r
bpy.ops.render.render(write_still=True)

print("GN_JSON " + json.dumps({
    "rendered": scene.render.filepath,
    "collection": tiles.name,
    "tiles": [o.name for o in tiles.objects],
    "host": host.name,
    "modifier": mod.name,
    "params": {k: get_input(k) for k in stamps if k != "Collection"},
}, ensure_ascii=False))
"""


def cmd_demo(args):
    os.makedirs(OUT_DIR, exist_ok=True)
    render_path = os.path.join(OUT_DIR, "hex_demo.png")
    code = DEMO_CODE % dict(asset=ASSET, render=render_path, reload=args.reload)
    data = run_json(code, timeout=600)
    print("demo 完成：%s" % data["rendered"])
    print("collection %s: %s" % (data["collection"], ", ".join(data["tiles"])))
    print("host: %s / modifier: %s" % (data["host"], data["modifier"]))

    run("obj = bpy.data.objects['Hex Array Demo']\n"
        "bpy.ops.object.select_all(action='DESELECT')\n"
        "obj.select_set(True)\n"
        "bpy.context.view_layer.objects.active = obj\n")
    op({"op": "look", "path": os.path.join(OUT_DIR, "hex_demo_view.png"),
        "res": 1100, "shading": "MATERIAL", "frame": True, "overlays": False},
       timeout=180)
    print("viewport: %s" % os.path.join(OUT_DIR, "hex_demo_view.png"))
    return 0


def cmd_array_demo(args):
    os.makedirs(os.path.join(WORKSPACE, "demo"), exist_ok=True)
    cmd = [BLENDER, "-b", "--factory-startup", "--python",
           os.path.join(HERE, "array_demo.py"), "--",
           "--asset", ASSET, "--out", os.path.join(WORKSPACE, "demo"),
           "--samples", str(args.samples), "--res", str(args.res)]
    if args.only:
        cmd += ["--only", args.only]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    tail = (proc.stdout or "") + (proc.stderr or "")
    for line in tail.splitlines():
        if line.startswith(("RENDERED", "CONTACT")):
            print(line)
    if proc.returncode != 0:
        print(tail[-3000:], file=sys.stderr)
    return proc.returncode


# ----------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Geometry Nodes toolkit")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("build", help="重建 assets/geometry_nodes.blend（全部 node group）")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("inputs", help="列出 node group 參數")
    p.add_argument("--group", choices=sorted(GROUPS), default="hex")
    p.set_defaults(func=cmd_inputs)

    p = sub.add_parser("list", help="列出 Blender 裡的 GN node groups")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("apply", help="把工具套到物件上")
    p.add_argument("--object", required=True, help="目標 mesh 物件名稱")
    p.add_argument("--group", choices=sorted(GROUPS), default="hex")
    p.add_argument("--collection", help="單元 collection 名稱")
    p.add_argument("--set", action="append", metavar="KEY=VALUE",
                   help="參數，可重複，例如 --set cell=0.3")
    p.add_argument("--no-fit", dest="fit", action="store_false",
                   help="不要自動用 collection 量到的尺寸設定 Source Size")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("--reload", action="store_true",
                   help="丟掉 session 裡的舊版 node group，重新從 asset 載入")
    p.set_defaults(func=cmd_apply, fit=True, verbose=False, reload=False)

    p = sub.add_parser("reload", help="把 session 裡的 node group 換成 asset 的新版")
    p.add_argument("--group", choices=sorted(GROUPS), default="hex")
    p.add_argument("--force", action="store_true",
                   help="即使還有 modifier 在用也移除（會斷掉那些 modifier）")
    p.set_defaults(func=cmd_reload, force=False)

    p = sub.add_parser("demo", help="建 Hex Array 示範場景、套用並算圖")
    p.add_argument("--reload", action="store_true",
                   help="丟掉 session 裡的舊版 node group，重新從 asset 載入")
    p.set_defaults(func=cmd_demo, reload=False)

    p = sub.add_parser("array-demo", help="建 Array 示範場景並算圖（headless）")
    p.add_argument("--only", default="", help="fence,tiles,lamp,bracelet,scatter,locators")
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--res", type=int, default=760)
    p.set_defaults(func=cmd_array_demo)

    args = ap.parse_args()
    global GROUP, MODULE
    key = getattr(args, "group", "hex")
    GROUP = GROUPS[key]
    MODULE = MODULES[key]
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
