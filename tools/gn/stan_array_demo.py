"""Render the Stan Array demo scenes (headless).

    blender -b --factory-startup --python tools/gn/stan_array_demo.py -- \
        --asset assets/geometry_nodes.blend --out demo

Each scene is built from scratch, the Stan Array node group is appended from
the asset file, and the result is rendered with Cycles (CPU). Run
tools/gn/contact_sheet.py (system Python + Pillow) for the combined sheet.
"""

import argparse
import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(os.path.dirname(HERE))
DEFAULT_ASSET = os.path.join(WORKSPACE, "assets", "geometry_nodes.blend")
DEFAULT_OUT = os.path.join(WORKSPACE, "demo")
GROUP = "Stan Array"


def _args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--asset", default=DEFAULT_ASSET)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--only", default="")
    ap.add_argument("--samples", type=int, default=32)
    ap.add_argument("--res", type=int, default=760)
    return ap.parse_args(argv)


def reset(asset):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    with bpy.data.libraries.load(asset, link=False) as (src, dst):
        if GROUP not in src.node_groups:
            raise SystemExit("asset 裡沒有 %r" % GROUP)
        dst.node_groups = [GROUP]
    return bpy.data.node_groups[GROUP]


def set_input(mod, ng, name, value):
    for item in ng.interface.items_tree:
        if item.item_type == "SOCKET" and item.in_out == "INPUT" and item.name == name:
            mod[item.identifier] = value
            return
    raise KeyError(name)


def material(name, color, rough=0.5, metal=0.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    return mat


def mesh_object(name, mesh, mat=None):
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    if mat:
        obj.data.materials.append(mat)
    return obj


def box(name, size, loc, mat, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    obj = bpy.context.object
    obj.name = name
    obj.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    return obj


def empty_host(name, loc=(0, 0, 0), rot=(0, 0, 0)):
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = rot
    return obj


def apply_array(host, ng, values):
    mod = host.modifiers.new(GROUP, "NODES")
    mod.node_group = ng
    for key, value in values.items():
        set_input(mod, ng, key, value)
    return mod


def look_at(cam, target):
    cam.rotation_euler = (Vector(target) - cam.location).to_track_quat("-Z", "Y").to_euler()


def setup_world(strength=0.9, color=(0.045, 0.05, 0.06)):
    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (*color, 1.0)
    bg.inputs[1].default_value = strength


def setup_light(angle=0.25, energy=3.6, rot=(0.72, 0.1, 0.85)):
    sun_data = bpy.data.lights.new("Sun", "SUN")
    sun_data.energy = energy
    sun_data.angle = angle
    sun = bpy.data.objects.new("Sun", sun_data)
    sun.rotation_euler = rot
    bpy.context.scene.collection.objects.link(sun)
    return sun


def area_light(loc, target, size=3.0, energy=120.0):
    data = bpy.data.lights.new("Fill", "AREA")
    data.energy = energy
    data.size = size
    obj = bpy.data.objects.new("Fill", data)
    obj.location = loc
    bpy.context.scene.collection.objects.link(obj)
    look_at(obj, target)
    return obj


def camera(loc, target, lens=50.0):
    data = bpy.data.cameras.new("Camera")
    data.lens = lens
    cam = bpy.data.objects.new("Camera", data)
    cam.location = loc
    bpy.context.scene.collection.objects.link(cam)
    look_at(cam, target)
    bpy.context.scene.camera = cam
    return cam


def render(path, res, samples):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.render.resolution_x = res
    scene.render.resolution_y = int(res * 0.75)
    scene.render.resolution_percentage = 100
    scene.view_settings.view_transform = "AgX"
    scene.render.film_transparent = False
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("RENDERED", path)


def floor(size=30.0, color=(0.30, 0.31, 0.32), rough=0.7):
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, -0.001))
    obj = bpy.context.object
    obj.name = "Floor"
    obj.data.materials.append(material("Floor", color, rough))
    return obj


# ------------------------------------------------------------------ scenes
def scene_fence(ng):
    setup_world()
    setup_light()
    floor()
    baluster = bpy.data.meshes.new("Baluster")
    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.018, depth=0.82,
                                        location=(0, 0, 0.41))
    tmp = bpy.context.object
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    tmp.data.materials.append(material("Baluster", (0.62, 0.60, 0.55), 0.45))
    baluster = tmp.data
    bpy.data.objects.remove(tmp, do_unlink=True)

    host = empty_host("Fence")
    apply_array(host, ng, {
        "Mode": 0, "Direction": (1, 0, 0), "Count": 17, "Spacing Mode": 1,
        "Gap": 0.075, "Unit From Collection": False,
    })
    # 把 baluster 放進 host 的 modifier 需要 host 本身有幾何：改用 mesh 當 host
    host.data = baluster
    bpy.context.view_layer.update()

    rail = material("Rail", (0.55, 0.36, 0.20), 0.35)
    box("Top Rail", (2.30, 0.035, 0.055), (1.05, 0, 0.805), rail)
    box("Bottom Rail", (2.30, 0.030, 0.045), (1.05, 0, 0.145), rail)
    post = material("Post", (0.50, 0.32, 0.18), 0.4)
    box("Post L", (0.075, 0.075, 0.95), (-0.09, 0, 0.475), post)
    box("Post R", (0.075, 0.075, 0.95), (2.19, 0, 0.475), post)
    box("Hedge", (4.2, 0.5, 1.9), (1.05, 0.75, 0.95),
        material("Hedge", (0.07, 0.13, 0.07), 0.85))
    camera((1.15, -4.3, 1.55), (1.15, 0.2, 0.55), 50)
    area_light((2.4, -2.6, 3.2), (1.0, 0.2, 0.5), 4.5, 240)


def scene_tiles(ng):
    setup_world()
    setup_light(rot=(0.55, 0.0, 0.6))
    floor(size=8, color=(0.16, 0.16, 0.17), rough=0.8)

    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0))
    tile = bpy.context.object
    tile.scale = (0.30, 0.30, 0.022)
    bpy.ops.object.transform_apply(scale=True)
    tile.data.materials.append(material("Tile", (0.78, 0.70, 0.55), 0.35))
    tile.data = tile.data

    host = tile
    host.rotation_euler = (math.radians(90), 0, 0)
    apply_array(host, ng, {
        "Mode": 1, "Count X": 9, "Count Y": 7, "Spacing Mode": 1, "Gap": 0.015,
    })
    bpy.context.view_layer.update()

    grout = material("Grout", (0.14, 0.16, 0.17), 0.8)
    box("Backing", (2.95, 0.05, 2.30), (1.25, 0.06, 0.93), grout)
    box("Frame Bottom", (3.05, 0.08, 0.06), (1.25, 0.03, -0.02),
        material("Frame", (0.12, 0.12, 0.12), 0.5))
    # 陶盆 + 植物，給一點比例感
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.16, depth=0.28,
                                        location=(2.55, -0.45, 0.14))
    pot = bpy.context.object
    pot.data.materials.append(material("Pot", (0.35, 0.20, 0.13), 0.6))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.22, location=(2.55, -0.45, 0.44))
    bush = bpy.context.object
    bush.data.materials.append(material("Bush", (0.10, 0.20, 0.10), 0.75))
    camera((4.3, -4.9, 1.95), (1.25, 0, 0.92), 50)
    area_light((3.6, -3.0, 3.6), (1.2, 0, 1.0), 5.0, 300)


def scene_lamp(ng):
    setup_world(strength=0.45, color=(0.03, 0.035, 0.045))
    setup_light(angle=0.35, energy=2.2, rot=(0.65, 0.15, 0.7))
    floor(size=10, color=(0.11, 0.11, 0.12), rough=0.85)

    brass = material("Brass", (0.72, 0.54, 0.26), 0.28, 0.85)
    glow = material("Bulb", (1.0, 0.78, 0.5), 0.3)
    bsdf = glow.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Emission Color"].default_value = (1.0, 0.72, 0.42, 1.0)
    bsdf.inputs["Emission Strength"].default_value = 4.0

    bpy.ops.mesh.primitive_cube_add(size=1, location=(0.31, 0, 0))
    arm = bpy.context.object
    arm.scale = (0.62, 0.022, 0.022)
    bpy.ops.object.transform_apply(location=True, scale=True)
    arm.data.materials.append(brass)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.042, location=(0.62, 0, 0))
    tip = bpy.context.object
    tip.data.materials.append(glow)
    tip.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.join()
    arm = bpy.context.object
    host = arm
    host.location = (0, 0, 1.02)
    apply_array(host, ng, {
        "Mode": 2, "Count": 12, "Radius": 0.0, "Arc": 360.0, "Align": 0,
    })
    bpy.context.view_layer.update()

    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.05, depth=1.00,
                                        location=(0, 0, 0.50))
    col = bpy.context.object
    col.data.materials.append(brass)
    bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.20, depth=0.025,
                                        location=(0, 0, 1.02))
    hub = bpy.context.object
    hub.data.materials.append(brass)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.055, location=(0, 0, 1.06))
    finial = bpy.context.object
    finial.data.materials.append(brass)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.13, minor_radius=0.008,
                                     location=(0, 0, 0.72))
    ring = bpy.context.object
    ring.data.materials.append(brass)

    camera((1.85, -2.05, 1.75), (0, 0, 0.95), 45)
    area_light((1.7, -2.0, 2.5), (0, 0, 0.9), 3.0, 150)


def scene_bracelet(ng):
    setup_world(strength=0.7, color=(0.05, 0.05, 0.06))
    setup_light(angle=0.3, energy=3.0)
    floor(size=10, color=(0.18, 0.17, 0.16), rough=0.8)

    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=0.052)
    bead = bpy.context.object
    bpy.ops.object.shade_smooth()
    bead.data.materials.append(material("Bead", (0.20, 0.55, 0.52), 0.25, 0.4))
    host = bead
    host.location = (0, 0, 0.62)
    host.rotation_euler = (math.radians(64), 0, math.radians(12))

    cu = bpy.data.curves.new("Bead Path", "CURVE")
    cu.dimensions = "3D"
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(3)
    pts = [(0.0, 0.0, 0.0), (0.42, 0.12, 0.10), (0.18, 0.38, -0.04),
           (-0.10, 0.10, 0.06)]
    for p, q in zip(sp.bezier_points, pts):
        p.co = q
        p.handle_left_type = "AUTO"
        p.handle_right_type = "AUTO"
    sp.use_cyclic_u = True
    curve = bpy.data.objects.new("Bead Path", cu)
    bpy.context.scene.collection.objects.link(curve)
    curve.location = (0, 0, 0.62)

    apply_array(host, ng, {
        "Mode": 3, "Curve": curve, "Spacing Mode": 0, "Step": 0.115,
        "Random Scale": 0.0, "Gradient Scale": 1.0,
    })
    bpy.context.view_layer.update()
    camera((1.15, -1.25, 1.15), (0.02, 0.06, 0.60), 52)
    area_light((1.2, -1.0, 1.8), (0, 0, 0.6), 2.5, 120)


def scene_scatter(ng):
    setup_world(strength=0.55, color=(0.05, 0.055, 0.065))
    setup_light(angle=0.2, energy=3.2, rot=(0.6, 0.1, 0.9))

    # 起伏地形
    bpy.ops.mesh.primitive_plane_add(size=6.0, location=(0, 0, 0))
    terrain = bpy.context.object
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.subdivide(number_cuts=24)
    bpy.ops.object.mode_set(mode="OBJECT")
    tex = bpy.data.textures.new("Dune", "CLOUDS")
    tex.noise_scale = 0.75
    disp = terrain.modifiers.new("Dune", "DISPLACE")
    disp.texture = tex
    disp.strength = 0.28
    bpy.ops.object.modifier_apply(modifier=disp.name)
    terrain.data.materials.append(material("Sand", (0.32, 0.25, 0.16), 0.9))

    bpy.ops.mesh.primitive_cone_add(vertices=5, radius1=0.018, radius2=0.0,
                                    depth=0.30, location=(0, 0, 0.15))
    blade = bpy.context.object
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    blade.data.materials.append(material("Grass", (0.11, 0.20, 0.06), 0.5))
    host = empty_host("Grass")
    apply_array(host, ng, {
        "Mode": 4, "Surface": terrain, "Mesh Mode": 3, "Density": 42.0,
        "Align": 0, "Random Rotate": (6, 6, 180), "Random Scale": 0.55,
        "Random Offset": (0.02, 0.02, 0.0), "Seed": 9,
    })
    # 讓草使用 blade 的 mesh
    host.data = blade.data
    bpy.data.objects.remove(blade, do_unlink=True)
    bpy.context.view_layer.update()
    camera((2.35, -2.55, 1.15), (0.0, 0.0, 0.18), 50)
    area_light((2.5, -2.0, 2.6), (0, 0, 0.2), 3.0, 160)



def scene_locators(ng):
    setup_world(strength=0.7, color=(0.05, 0.05, 0.06))
    setup_light(angle=0.25, energy=3.4)
    floor(size=12, color=(0.17, 0.16, 0.15), rough=0.85)

    stones = bpy.data.collections.new("Stones")
    bpy.context.scene.collection.children.link(stones)
    stone_mat = material("Stone", (0.55, 0.52, 0.47), 0.65)
    for i in range(6):
        x = i * 0.52
        y = 0.20 * math.sin(i * 0.9)
        z = 0.02
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.17, depth=0.04,
                                            location=(x, y, z),
                                            rotation=(0, 0, math.radians(28 * i)))
        st = bpy.context.object
        st.name = "Marker %d" % i
        st.data.materials.append(stone_mat)
        for c in list(st.users_collection):
            c.objects.unlink(st)
        stones.objects.link(st)

    # 棋子 + 指向 +X 的小箭頭
    dark = material("Pawn", (0.10, 0.16, 0.28), 0.35, 0.3)
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.055, depth=0.24,
                                        location=(0, 0, 0.12))
    pawn = bpy.context.object
    pawn.data.materials.append(dark)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.075, location=(0, 0, 0.30))
    head = bpy.context.object
    head.data.materials.append(dark)
    head.select_set(True)
    pawn.select_set(True)
    bpy.context.view_layer.objects.active = pawn
    bpy.ops.object.join()
    pawn = bpy.context.object
    bpy.ops.mesh.primitive_cone_add(vertices=12, radius1=0.035, radius2=0.0,
                                    depth=0.11, location=(0.16, 0, 0.30),
                                    rotation=(0, math.radians(90), 0))
    arrow = bpy.context.object
    arrow.data.materials.append(material("Arrow", (0.85, 0.45, 0.15), 0.4))
    arrow.select_set(True)
    pawn.select_set(True)
    bpy.context.view_layer.objects.active = pawn
    bpy.ops.object.join()
    pawn = bpy.context.object

    apply_array(pawn, ng, {
        "Mode": 5, "Point Collection": stones, "Align": 0,
    })
    bpy.context.view_layer.update()
    camera((2.8, -3.2, 1.65), (1.35, 0.1, 0.22), 50)
    area_light((2.6, -2.2, 2.8), (1.2, 0, 0.3), 4.0, 200)


def scene_hex(ng):
    setup_world(strength=0.55, color=(0.05, 0.05, 0.06))
    setup_light(angle=0.3, energy=3.2, rot=(0.7, 0.1, 0.8))
    floor(size=10, color=(0.18, 0.17, 0.16), rough=0.85)

    tiles = bpy.data.collections.new("Hex Tiles")
    bpy.context.scene.collection.children.link(tiles)
    palette = [("Terracotta", (0.68, 0.34, 0.21)),
               ("Mustard", (0.78, 0.56, 0.18)),
               ("Teal", (0.16, 0.45, 0.42))]
    for i, (name, color) in enumerate(palette):
        bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.112, depth=0.03,
                                            location=(0, 0, 0))
        o = bpy.context.object
        o.name = "Hex %d" % i
        o.data.materials.append(material("Hex " + name, color, 0.4))
        for c in list(o.users_collection):
            c.objects.unlink(o)
        tiles.objects.link(o)

    host = empty_host("Hex Wall")
    host.rotation_euler = (math.radians(90), 0, 0)
    apply_array(host, ng, {
        "Mode": 1, "Grid Type": 1, "Count X": 12, "Count Y": 10,
        "Cell Size": 0.22, "Flat Top": False,
        "Unit From Collection": True, "Collection": tiles, "Collection Count": 3,
        "Seed": 5,
    })
    bpy.context.view_layer.update()
    box("Hex Backing", (2.42, 0.05, 1.90), (1.02, 0.06, 0.86),
        material("Hex Backing", (0.10, 0.10, 0.11), 0.8))
    box("Hex Frame", (2.52, 0.07, 0.06), (1.02, 0.03, -0.05),
        material("Hex Frame", (0.09, 0.09, 0.09), 0.6))
    camera((2.95, -3.35, 1.55), (1.05, 0, 0.85), 50)
    area_light((2.6, -2.2, 2.8), (1.0, 0, 1.0), 4.0, 230)


def scene_tri(ng):
    setup_world(strength=0.5, color=(0.04, 0.045, 0.05))
    setup_light(angle=0.3, energy=2.8, rot=(0.65, 0.1, 0.75))
    floor(size=10, color=(0.10, 0.10, 0.11), rough=0.85)

    side = 0.24
    radius = side / math.sqrt(3.0)
    tiles = bpy.data.collections.new("Tri Tiles")
    bpy.context.scene.collection.children.link(tiles)
    palette = [("Terracotta", (0.68, 0.34, 0.21)),
               ("Mustard", (0.78, 0.56, 0.18)),
               ("Teal", (0.16, 0.45, 0.42))]
    for i, (name, color) in enumerate(palette):
        bpy.ops.mesh.primitive_cylinder_add(vertices=3, radius=radius, depth=0.03,
                                            location=(0, 0, 0))
        o = bpy.context.object
        o.name = "Tri %d" % i
        o.data.materials.append(material("Tri " + name, color, 0.4))
        for c in list(o.users_collection):
            c.objects.unlink(o)
        tiles.objects.link(o)

    host = empty_host("Tri Wall")
    host.rotation_euler = (math.radians(90), 0, 0)
    apply_array(host, ng, {
        "Mode": 1, "Grid Type": 2, "Count X": 13, "Count Y": 8,
        "Step": side,
        "Unit From Collection": True, "Collection": tiles, "Collection Count": 3,
        "Seed": 8,
    })
    bpy.context.view_layer.update()
    box("Tri Backing", (2.02, 0.05, 1.86), (0.90, 0.06, 0.82),
        material("Tri Backing", (0.05, 0.05, 0.06), 0.8))
    box("Tri Frame", (2.12, 0.07, 0.06), (0.90, 0.03, -0.12),
        material("Tri Frame", (0.04, 0.04, 0.05), 0.55))
    camera((3.0, -3.45, 1.6), (0.90, 0, 0.82), 52)
    area_light((2.5, -2.0, 2.7), (0.9, 0, 0.85), 3.8, 220)


SCENES = {
    "fence": scene_fence,
    "tiles": scene_tiles,
    "hex": scene_hex,
    "tri": scene_tri,
    "lamp": scene_lamp,
    "bracelet": scene_bracelet,
    "scatter": scene_scatter,
    "locators": scene_locators,
}


def main():
    args = _args()
    os.makedirs(args.out, exist_ok=True)
    wanted = [n for n in args.only.split(",") if n] or list(SCENES)
    for name in wanted:
        ng = reset(args.asset)
        SCENES[name](ng)
        render(os.path.join(args.out, "stan_%s.png" % name), args.res, args.samples)
        if name == "fence":
            blend = os.path.join(args.out, "stan_array_demo.blend")
            bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)
            print("SAVED", blend)
    return 0


if __name__ == "__main__":
    sys.exit(main())
