"""Headless smoke tests for the Stan Array node group.

    blender -b --factory-startup --python tools/gn/test_array.py

Builds the group from source, exercises every mode / spacing / orientation /
variation path on a throwaway scene, and checks instance transforms. Prints
one line per check and exits non-zero on the first mismatch.
"""

import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import stan_array as sa  # noqa: E402

TOL = 1e-3
FAILS = []
CHECKS = 0


def check(name, ok, detail=""):
    global CHECKS
    CHECKS += 1
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name, "" if ok else "  " + detail))
    if not ok:
        FAILS.append(name)


def close(a, b, tol=TOL):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def fresh():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def cube(size=0.4, loc=(0, 0, 0), rotz=0.0):
    bpy.ops.mesh.primitive_cube_add(size=size, location=loc)
    obj = bpy.context.object
    obj.rotation_euler = (0, 0, math.radians(rotz))
    return obj


def host_cube():
    h = cube(0.4)
    h.name = "Host"
    mod = h.modifiers.new("Array", "NODES")
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


def samples(host):
    host.update_tag()
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    out = []
    for inst in dg.object_instances:
        if not inst.is_instance:
            continue
        if inst.parent and inst.parent.original != host:
            continue
        m = inst.matrix_world
        out.append({
            "pos": tuple(round(m[r][3], 4) for r in range(3)),
            "rot": tuple(round(math.degrees(v), 2) for v in m.to_euler("XYZ")),
            "scale": tuple(round(v, 4) for v in m.to_scale()),
        })
    return out


DEFAULT = {
    "Mode": 0, "Unit From Collection": False, "Collection": None,
    "Collection Count": 1, "Direction": (1, 0, 0), "Count": 5, "Count X": 5,
    "Count Y": 5, "Grid Type": 0, "Cell Size": 0.25, "Flat Top": False,
    "Spacing Mode": 0, "Step": 1.0, "Gap": 0.1, "Length": 5.0,
    "Length Y": 5.0, "Radius": 1.0, "Arc": 360.0, "Start Angle": 0.0,
    "Curve": None, "Surface": None, "Mesh Mode": 0, "Density": 10.0,
    "Point Collection": None, "Align": 0, "Forward Axis": 1, "Up Axis": 2,
    "Random Offset": (0, 0, 0), "Random Rotate": (0, 0, 0), "Unit Scale": 1.0, "Random Scale": 0.0,
    "Seed": 0, "Mirror": False, "Mirror Axis": 0, "Gradient Scale": 1.0,
    "Gradient Rotate": 0.0, "Realize": False,
}


def main():
    global ng
    fresh()
    ng = sa.build()
    host, mod = host_cube()

    reset(mod)
    got = samples(host)
    check("linear step count", len(got) == 5, str(len(got)))
    check("linear step positions",
          [g["pos"] for g in got] == [(0, 0, 0), (1, 0, 0), (2, 0, 0),
                                      (3, 0, 0), (4, 0, 0)],
          str([g["pos"] for g in got]))

    reset(mod)
    setv(mod, "Spacing Mode", 1)
    setv(mod, "Gap", 0.2)
    got = samples(host)
    check("linear gap (size 0.4 + gap 0.2 = 0.6)",
          close(got[-1]["pos"], (2.4, 0, 0)), str(got[-1]["pos"]))

    reset(mod)
    setv(mod, "Spacing Mode", 2)
    got = samples(host)
    check("linear fit: edges 0..5",
          close(got[0]["pos"], (0.2, 0, 0)) and close(got[-1]["pos"], (4.8, 0, 0)),
          str([got[0]["pos"], got[-1]["pos"]]))

    reset(mod)
    setv(mod, "Mode", 1)
    setv(mod, "Count X", 3)
    setv(mod, "Count Y", 2)
    got = samples(host)
    positions = sorted(g["pos"] for g in got)
    check("grid 3x2 starts at origin",
          positions == [(0, 0, 0), (0, 1, 0), (1, 0, 0), (1, 1, 0),
                        (2, 0, 0), (2, 1, 0)], str(positions))

    # grids: hex and triangle share the staggered lattice code
    reset(mod)
    setv(mod, "Mode", 1)
    setv(mod, "Count X", 3)
    setv(mod, "Count Y", 2)
    setv(mod, "Grid Type", 1)
    setv(mod, "Cell Size", 0.25)
    got = samples(host)
    hex_expected = [(0, 0, 0), (0.2165, 0, 0), (0.433, 0, 0),
                    (0.1083, 0.1875, 0), (0.3248, 0.1875, 0), (0.5413, 0.1875, 0)]
    check("hex pointy positions",
          all(close(g["pos"], e) for g, e in zip(got, hex_expected)),
          str([g["pos"] for g in got]))
    setv(mod, "Flat Top", True)
    got = samples(host)
    check("hex flat-top first row",
          close(got[1]["pos"], (0.1875, 0.1083, 0)), str(got[1]["pos"]))
    setv(mod, "Flat Top", False)
    setv(mod, "Grid Type", 2)
    setv(mod, "Step", 0.2)
    got = samples(host)
    check("triangle lattice", close(got[3]["pos"], (0.1, 0.1732, 0)),
          str(got[3]["pos"]))

    reset(mod)
    setv(mod, "Mode", 2)
    setv(mod, "Count", 4)
    got = samples(host)
    check("radial 4 positions",
          [g["pos"] for g in got] == [(1, 0, 0), (0, 1, 0), (-1, 0, 0), (0, -1, 0)],
          str([g["pos"] for g in got]))
    check("radial rotations", [g["rot"][2] for g in got] == [0, 90, -180, -90],
          str([g["rot"][2] for g in got]))

    # curve
    cu = bpy.data.curves.new("Path", "CURVE")
    cu.dimensions = "3D"
    sp = cu.splines.new("POLY")
    sp.points.add(1)
    sp.points[0].co = (0, 0, 0, 1)
    sp.points[1].co = (4, 0, 0, 1)
    curve = bpy.data.objects.new("Path", cu)
    bpy.context.scene.collection.objects.link(curve)
    reset(mod)
    setv(mod, "Mode", 3)
    setv(mod, "Curve", curve)
    setv(mod, "Spacing Mode", 2)
    got = samples(host)
    check("curve fit 5 points", len(got) == 5 and close(got[-1]["pos"], (4, 0, 0)),
          str([g["pos"] for g in got]))

    # mesh vertices
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=3, y_subdivisions=3, size=2)
    surf = bpy.context.object
    surf.name = "Surface"
    reset(mod)
    setv(mod, "Mode", 4)
    setv(mod, "Surface", surf)
    got = samples(host)
    check("mesh vertices 4x4", len(got) == 16, str(len(got)))
    check("mesh natural normal = identity",
          all(close(g["rot"], (0, 0, 0)) for g in got), str(got[0]["rot"]))

    # collection locators
    coll = bpy.data.collections.new("Locators")
    bpy.context.scene.collection.children.link(coll)
    for name, loc, rotz in (("A", (1, 0, 0), 90.0), ("B", (-1, 0, 0), 0.0)):
        o = cube(0.2, loc, rotz)
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
    reset(mod)
    setv(mod, "Mode", 5)
    setv(mod, "Point Collection", coll)
    got = samples(host)
    check("collection locators count", len(got) == 2, str(len(got)))
    check("collection locators transform",
          close(got[0]["pos"], (1, 0, 0)) and abs(got[0]["rot"][2] - 90) < 0.1
          and close(got[1]["pos"], (-1, 0, 0)), str(got))

    # alignment
    reset(mod)
    setv(mod, "Align", 1)
    setv(mod, "Forward Axis", 1)
    got = samples(host)
    check("linear forward Y", abs(got[0]["rot"][2] + 90) < 0.1, str(got[0]["rot"]))

    # mirror
    reset(mod)
    setv(mod, "Mirror", True)
    got = samples(host)
    check("mirror X on odd copies",
          close(got[1]["scale"], (-1, 1, 1)) or close(got[1]["scale"], (-1, -1, -1)),
          str(got[1]["scale"]))

    # gradient
    reset(mod)
    setv(mod, "Gradient Scale", 2.0)
    got = samples(host)
    check("gradient scale 1 -> 2",
          close(got[0]["scale"], (1, 1, 1)) and close(got[-1]["scale"], (2, 2, 2)),
          str([got[0]["scale"], got[-1]["scale"]]))

    # realize
    reset(mod)
    setv(mod, "Realize", True)
    host.update_tag()
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = host.evaluated_get(dg).to_mesh()
    check("realize gives 5 cubes (40 verts / 30 faces)",
          len(me.vertices) == 40 and len(me.polygons) == 30,
          "%d verts %d faces" % (len(me.vertices), len(me.polygons)))

    print("\n%d checks, %d failed" % (CHECKS, len(FAILS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
