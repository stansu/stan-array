#!/usr/bin/env python3
"""gn.py — Stan Array toolkit CLI.

Talks to the *live* Blender through the Blender Bridge (tools/blender-bridge),
so whatever you see on screen is what gets the modifier.

    python3 tools/gn/gn.py build                 # rebuild assets/geometry_nodes.blend
    python3 tools/gn/gn.py inputs                # list the node group inputs
    python3 tools/gn/gn.py list                  # node groups in the running Blender
    python3 tools/gn/gn.py apply --object Host --set mode=grid --set grid_type=hex
    python3 tools/gn/gn.py stan-demo             # render the demo scenes (headless)

All subcommands accept --group for future tools; today there is one group,
"Stan Array" (key: stan).
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
GROUPS = {"stan": "Stan Array"}
MODULES = {"stan": "stan_array"}
GROUP = GROUPS["stan"]
MODULE = MODULES["stan"]


def _find_blender():
    env = os.environ.get("BLENDER_BIN")
    if env and os.path.exists(env):
        return env
    found = shutil.which("blender")
    if found:
        return found
    # this repo is built with Blender 4.5; prefer it, then fall back to newest
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
    "collection_count": "Collection Count",
    "direction": "Direction",
    "count": "Count",
    "count_x": "Count X",
    "count_y": "Count Y",
    "grid_type": "Grid Type",
    "grid": "Grid Type",
    "cell": "Cell Size",
    "cell_size": "Cell Size",
    "flat_top": "Flat Top",
    "stagger": "Stagger",
    "stagger_repeat": "Stagger Repeat",
    "spacing_mode": "Spacing Mode",
    "spacing": "Spacing Mode",
    "step": "Step",
    "gap": "Gap",
    "length": "Length",
    "length_y": "Length Y",
    "radius": "Radius",
    "arc": "Arc",
    "start_angle": "Start Angle",
    "curve": "Curve",
    "surface": "Surface",
    "mesh_mode": "Mesh Mode",
    "density": "Density",
    "point_collection": "Point Collection",
    "align": "Align",
    "forward_axis": "Forward Axis",
    "up_axis": "Up Axis",
    "random_offset": "Random Offset",
    "random_rotate": "Random Rotate",
    "unit_scale": "Unit Scale",
    "random_scale": "Random Scale",
    "seed": "Seed",
    "mirror": "Mirror",
    "mirror_axis": "Mirror Axis",
    "gradient_scale": "Gradient Scale",
    "gradient_rotate": "Gradient Rotate",
    "realize": "Realize",
}

# Int enums can be set by name from the CLI
ENUMS = {
    "Mode": {"linear": 0, "grid": 1, "radial": 2, "curve": 3,
             "mesh": 4, "collection": 5},
    "Spacing Mode": {"step": 0, "gap": 1, "fit": 2},
    "Grid Type": {"xy": 0, "square": 0, "hex": 1, "triangle": 2, "tri": 2,
                  "brick": 3},
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
                print("group : %-12s nodes=%-4d links=%-4d  %s"
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
import json

asset = %(asset)r
group = %(group)r
target = %(target)r
coll_name = %(coll)r
params = json.loads(%(params)r)
reload = %(reload)r

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
if ng is not None and reload:
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

objects = [o for o in (coll.objects if coll else []) if o.type == 'MESH']
if "Collection Count" not in applied:
    count = max(1, len(objects))
    set_input("Collection Count", count)
    applied["Collection Count"] = count

obj.update_tag()
bpy.context.view_layer.update()
report("ok", object=obj.name, modifier=mod.name, group=ng.name,
       collection=coll.name if coll else None,
       collection_objects=max(1, len(objects)), applied=applied)
""" % dict(asset=ASSET, group=GROUP, target=args.object, coll=args.collection,
           params=json.dumps(params), reload=args.reload)

    data = run_json(code)
    if data.get("status") != "ok":
        raise SystemExit("套用失敗：%s" % json.dumps(data, ensure_ascii=False))
    print("已套用 %s → %s" % (data["group"], data["object"]))
    print("modifier : %s" % data["modifier"])
    if data.get("collection"):
        print("collection: %s（%d 個 mesh）" % (data["collection"], data["collection_objects"]))
    for key, value in data["applied"].items():
        print("  %-20s %s" % (key, value))
    return 0


def cmd_reload(args):
    code = """
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


def cmd_stan_demo(args):
    os.makedirs(os.path.join(WORKSPACE, "demo"), exist_ok=True)
    cmd = [BLENDER, "-b", "--factory-startup", "--python",
           os.path.join(HERE, "stan_array_demo.py"), "--",
           "--asset", ASSET, "--out", os.path.join(WORKSPACE, "demo"),
           "--samples", str(args.samples), "--res", str(args.res)]
    if args.only:
        cmd += ["--only", args.only]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    tail = (proc.stdout or "") + (proc.stderr or "")
    for line in tail.splitlines():
        if line.startswith(("RENDERED", "SAVED")):
            print(line)
    if proc.returncode != 0:
        print(tail[-3000:], file=sys.stderr)
        return proc.returncode
    sheet = os.path.join(HERE, "contact_sheet.py")
    subprocess.run([sys.executable, sheet, "--dir", os.path.join(WORKSPACE, "demo")])
    return 0


# ----------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Stan Array toolkit")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("build", help="重建 assets/geometry_nodes.blend")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("inputs", help="列出 node group 參數")
    p.add_argument("--group", choices=sorted(GROUPS), default="stan")
    p.set_defaults(func=cmd_inputs)

    p = sub.add_parser("list", help="列出 Blender 裡的 GN node groups")
    p.add_argument("--group", choices=sorted(GROUPS), default="stan")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("apply", help="把 Stan Array 套到物件上")
    p.add_argument("--group", choices=sorted(GROUPS), default="stan")
    p.add_argument("--object", required=True, help="目標 mesh 物件名稱")
    p.add_argument("--collection", help="Unit From Collection 的 collection 名稱")
    p.add_argument("--set", action="append", metavar="KEY=VALUE",
                   help="參數，可重複，例如 --set grid_type=hex --set cell=0.25")
    p.add_argument("--reload", action="store_true",
                   help="丟掉 session 裡的舊版 node group，重新從 asset 載入")
    p.set_defaults(func=cmd_apply, reload=False)

    p = sub.add_parser("reload", help="把 session 裡的 node group 換成 asset 的新版")
    p.add_argument("--group", choices=sorted(GROUPS), default="stan")
    p.add_argument("--force", action="store_true",
                   help="即使還有 modifier 在用也移除（會斷掉那些 modifier）")
    p.set_defaults(func=cmd_reload, force=False)

    p = sub.add_parser("stan-demo", aliases=["demo"], help="建示範場景並算圖（headless）")
    p.add_argument("--only", default="",
                   help="fence,tiles,hex,tri,lamp,bracelet,scatter,locators")
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--res", type=int, default=760)
    p.set_defaults(func=cmd_stan_demo)

    args = ap.parse_args()
    global GROUP, MODULE
    key = getattr(args, "group", "stan")
    GROUP = GROUPS[key]
    MODULE = MODULES[key]
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
