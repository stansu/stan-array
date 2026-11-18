"""Headless smoke tests for the Stan Box node group.

    blender -b --factory-startup --python tools/gn/test_box_generator.py

Builds the group from source, exercises solid / hollow / plug / shrink /
corner / instancing paths on a throwaway scene, checks stored attributes and
the enum tables shared with the CLI, and exits non-zero on the first mismatch.
"""

import os
import sys
import traceback

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import box_generator as bx  # noqa: E402
import gn  # noqa: E402  (CLI enum table — must stay in sync with bx tables)

TOL = 1e-3
FAILS = []
CHECKS = 0
ng = None


def check(name, ok, detail=""):
    global CHECKS
    CHECKS += 1
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name, "" if ok else "  " + detail))
    if not ok:
        FAILS.append(name)


def close(a, b, tol=TOL):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


DEFAULT = {
    "Size XYZ": (1.0, 1.0, 1.0), "Scale Factor": 1.0, "Vertices Per Side": 2,
    "Subdivide": 0, "Hollow": False, "Wall Thickness": 0.1, "Fill Mode": 0,
    "Shrink Faces": False, "Shrink Scale": 0.5, "Corner Mode": 0,
    "Use Instances": False, "Jitter": 0.0, "Rotation Range": 0.0,
    "Scale Random": 0.0, "Seed": 0, "Realize Instances": True,
    "Store Attributes": False, "Shade Smooth": False, "Material": None,
}


def host_cube():
    bpy.ops.mesh.primitive_cube_add(size=0.4)
    h = bpy.context.object
    h.name = "Host"
    mod = h.modifiers.new("Box", "NODES")
    mod.node_group = ng
    return h, mod


def setv(mod, name, value):
    for item in ng.interface.items_tree:
        if item.item_type == "SOCKET" and item.in_out == "INPUT" and item.name == name:
            mod[item.identifier] = value
            return
    raise KeyError(name)


def reset(mod):
    for key, value in DEFAULT.items():
        setv(mod, key, value)


def eval_mesh(host):
    """Fresh depsgraph per probe (stale caches would hide modifier changes)."""
    host.update_tag()
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    return host.evaluated_get(dg).to_mesh(), dg


def bbox(me):
    co = [v.co for v in me.vertices]
    if not co:
        return ((0.0, 0.0), (0.0, 0.0), (0.0, 0.0))
    return tuple((min(c[i] for c in co), max(c[i] for c in co)) for i in range(3))


def inst_count(host, dg):
    return sum(1 for i in dg.object_instances if i.is_instance)


def main():
    global ng
    bpy.ops.wm.read_factory_settings(use_empty=True)
    ng = bx.build()

    check("group name", ng.name == bx.NAME, ng.name)
    check("is modifier", ng.is_modifier, str(ng.is_modifier))
    check("node/link counts", len(ng.nodes) > 30 and len(ng.links) > 40,
          "%d nodes %d links" % (len(ng.nodes), len(ng.links)))
    check("20 inputs", len(bx.inputs_summary(ng)) == 20,
          str(len(bx.inputs_summary(ng))))
    by_name = {item.name: item for item in ng.interface.items_tree
               if item.item_type == "SOCKET" and item.in_out == "INPUT"}
    check("verts-per-side min 2 (4.5 requires >= 2)",
          by_name["Vertices Per Side"].min_value == 2
          and by_name["Vertices Per Side"].default_value == 2,
          "min=%s default=%s" % (by_name["Vertices Per Side"].min_value,
                                 by_name["Vertices Per Side"].default_value))

    host, mod = host_cube()

    # ── 實心盒
    reset(mod)
    me, dg = eval_mesh(host)
    bb = bbox(me)
    check("solid default cube 8 verts / 6 faces",
          len(me.vertices) == 8 and len(me.polygons) == 6,
          "%d verts %d faces" % (len(me.vertices), len(me.polygons)))
    check("solid default bbox ±0.5",
          all(close(span, (-0.5, 0.5)) for span in bb), str(bb))
    host.to_mesh_clear()

    reset(mod)
    setv(mod, "Size XYZ", (2.0, 1.0, 0.5))
    me, dg = eval_mesh(host)
    bb = bbox(me)
    check("solid scaled bbox (±1, ±0.5, ±0.25)",
          close(bb[0], (-1.0, 1.0)) and close(bb[1], (-0.5, 0.5))
          and close(bb[2], (-0.25, 0.25)), str(bb))
    host.to_mesh_clear()

    # ── 空心：整數尺寸不挖穿；小數/負值挖穿該軸
    reset(mod)
    setv(mod, "Hollow", True)
    me, dg = eval_mesh(host)
    check("hollow integer keeps closed box",
          len(me.polygons) == 6, "%d faces" % len(me.polygons))
    host.to_mesh_clear()

    reset(mod)
    setv(mod, "Hollow", True)
    setv(mod, "Size XYZ", (1.0, 1.0, 1.5))
    me, dg = eval_mesh(host)
    bb = bbox(me)
    check("hollow z+ open cuts top face",
          len(me.polygons) == 5 and close(bb[2], (-0.75, 0.75)),
          "%d faces z=%s" % (len(me.polygons), bb[2]))
    host.to_mesh_clear()

    reset(mod)
    setv(mod, "Hollow", True)
    setv(mod, "Size XYZ", (-1.0, 1.0, 1.0))
    me, dg = eval_mesh(host)
    check("negative size opens -X face", len(me.polygons) == 5,
          "%d faces" % len(me.polygons))
    host.to_mesh_clear()

    # ── Fill Mode：Plug 只塞 Z 开口；Cube 退回實心
    reset(mod)
    setv(mod, "Hollow", True)
    setv(mod, "Size XYZ", (1.0, 1.0, 1.5))
    setv(mod, "Fill Mode", 1)
    me, dg = eval_mesh(host)
    check("plug caps z opening (12 verts / 6 faces)",
          len(me.vertices) == 12 and len(me.polygons) == 6,
          "%d verts %d faces" % (len(me.vertices), len(me.polygons)))
    host.to_mesh_clear()

    reset(mod)
    setv(mod, "Hollow", True)
    setv(mod, "Size XYZ", (1.0, 1.0, 1.5))
    setv(mod, "Fill Mode", 2)
    me, dg = eval_mesh(host)
    check("cube fill restores closed box",
          len(me.vertices) == 8 and len(me.polygons) == 6,
          "%d verts %d faces" % (len(me.vertices), len(me.polygons)))
    host.to_mesh_clear()

    reset(mod)
    setv(mod, "Hollow", True)
    setv(mod, "Size XYZ", (-1.0, 1.0, 1.0))
    setv(mod, "Fill Mode", 1)
    me, dg = eval_mesh(host)
    check("plug leaves X opening open (4.5 limitation)",
          len(me.polygons) == 5, "%d faces" % len(me.polygons))
    host.to_mesh_clear()

    # ── Shrink Faces：保留面收縮（x/y 收到 ±0.25）
    reset(mod)
    setv(mod, "Hollow", True)
    setv(mod, "Size XYZ", (1.0, 1.0, 1.5))
    setv(mod, "Shrink Faces", True)
    setv(mod, "Shrink Scale", 0.5)
    me, dg = eval_mesh(host)
    bb = bbox(me)
    check("shrink faces narrows x/y to ±0.25",
          len(me.polygons) == 5 and close(bb[0], (-0.25, 0.25))
          and close(bb[1], (-0.25, 0.25)), str(bb))
    host.to_mesh_clear()

    # ── Corner Mode：Subdivide 近似圓角
    reset(mod)
    setv(mod, "Corner Mode", 1)
    setv(mod, "Subdivide", 1)
    me, dg = eval_mesh(host)
    check("corner subdiv 1 → 26 verts / 24 faces",
          len(me.vertices) == 26 and len(me.polygons) == 24,
          "%d verts %d faces" % (len(me.vertices), len(me.polygons)))
    host.to_mesh_clear()

    # ── 實例化：2×2×2 網格點 = 8 個實例（其中一個與主機重合，26 見下）
    reset(mod)
    setv(mod, "Vertices Per Side", 3)
    setv(mod, "Use Instances", True)
    me, dg = eval_mesh(host)
    check("instances realized: 26 instances of 3x3x3 cubes",
          len(me.vertices) == 676 and len(me.polygons) == 624,
          "%d verts %d faces" % (len(me.vertices), len(me.polygons)))
    host.to_mesh_clear()

    reset(mod)
    setv(mod, "Vertices Per Side", 3)
    setv(mod, "Use Instances", True)
    setv(mod, "Realize Instances", False)
    me, dg = eval_mesh(host)
    check("raw instances: instance count > 0", inst_count(host, dg) > 0,
          "inst=%d" % inst_count(host, dg))
    host.to_mesh_clear()

    # ── Jitter + Store Attributes
    reset(mod)
    setv(mod, "Vertices Per Side", 3)
    setv(mod, "Use Instances", True)
    setv(mod, "Jitter", 0.2)
    setv(mod, "Store Attributes", True)
    me, dg = eval_mesh(host)
    bb = bbox(me)
    attrs = {a.name for a in me.attributes}
    check("store attributes present",
          {bx.ATTR_INDEX, bx.ATTR_SEED, bx.ATTR_RANDOM, bx.ATTR_SCALE} <= attrs,
          str(sorted(attrs)))
    check("jitter spreads bbox beyond ±1",
          bb[0][1] > 1.05 and bb[0][0] < -1.05, str(bb))
    host.to_mesh_clear()

    # ── Seed 決定性：同 seed 同 bbox，不同 seed 不同 bbox
    reset(mod)
    setv(mod, "Vertices Per Side", 3)
    setv(mod, "Use Instances", True)
    setv(mod, "Jitter", 0.2)
    setv(mod, "Seed", 42)
    me, dg = eval_mesh(host)
    bb_a = bbox(me)
    host.to_mesh_clear()
    me, dg = eval_mesh(host)
    bb_a2 = bbox(me)
    host.to_mesh_clear()
    setv(mod, "Seed", 43)
    me, dg = eval_mesh(host)
    bb_b = bbox(me)
    host.to_mesh_clear()
    check("seed deterministic", bb_a == bb_a2, "%s vs %s" % (bb_a, bb_a2))
    check("seed changes scatter", bb_a != bb_b, "%s vs %s" % (bb_a, bb_b))

    # ── Scale Random：1±r 範圍
    reset(mod)
    setv(mod, "Vertices Per Side", 3)
    setv(mod, "Use Instances", True)
    setv(mod, "Scale Random", 0.5)
    me, dg = eval_mesh(host)
    bb = bbox(me)
    check("scale random expands bbox past unit box",
          bb[0][1] > 1.1 and bb[0][0] < -1.1, str(bb))
    host.to_mesh_clear()

    # ── Shade Smooth / Material
    reset(mod)
    setv(mod, "Shade Smooth", True)
    me, dg = eval_mesh(host)
    check("shade smooth on all faces",
          all(p.use_smooth for p in me.polygons),
          str(sum(1 for p in me.polygons if not p.use_smooth)))
    host.to_mesh_clear()

    mat = bpy.data.materials.new("BoxMat")
    reset(mod)
    setv(mod, "Material", mat)
    me, dg = eval_mesh(host)
    slots = [s.material for s in host.evaluated_get(dg).material_slots]
    check("material slot set", mat in slots, str(slots))
    host.to_mesh_clear()

    # ── enum tables: socket ranges, descriptions and CLI names must agree
    norm = lambda n: n.lower().replace(" ", "").replace("_", "")  # noqa: E731
    for sock_name, names in (("Fill Mode", bx.FILL_NAMES),
                             ("Corner Mode", bx.CORNER_NAMES)):
        item = by_name[sock_name]
        desc = item.description or ""
        cli = gn.ENUMS.get(sock_name, {})
        ok = (item.max_value == len(names) - 1
              and all(("%d %s" % (i, n)) in desc for i, n in enumerate(names))
              and len(cli) >= len(names)
              and all(cli.get(norm(n)) == i for i, n in enumerate(names)))
        check("enum %s: range, description, CLI names" % sock_name, ok,
              "max=%s desc=%s cli=%s" % (item.max_value, desc[:40], cli))

    print("\n%d checks, %d failed" % (CHECKS, len(FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    # Blender background mode exits 0 even when the script raises, so turn
    # any exception (and any failed check) into a non-zero exit code.
    try:
        rc = main()
    except Exception:
        traceback.print_exc()
        rc = 1
    sys.exit(rc)
