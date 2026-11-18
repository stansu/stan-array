"""Render the Stan Box demo scenes (headless).

    blender -b --factory-startup --python tools/gn/box_demo.py -- \
        --asset assets/geometry_nodes.blend --out demo

Each scene is built from scratch, the Stan Box node group is appended from
the asset file, and the result is rendered with Cycles (CPU). Run
tools/gn/contact_sheet.py --prefix box_ for the combined sheet.
"""

import argparse
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.dirname(os.path.dirname(HERE))
DEFAULT_ASSET = os.path.join(WORKSPACE, "assets", "geometry_nodes.blend")
DEFAULT_OUT = os.path.join(WORKSPACE, "demo")
GROUP = "Stan Box"


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


def empty_host(name, loc=(0, 0, 0), mat=None, ng=None, values=None):
    """Empty mesh object — Stan Box generates its own geometry."""
    obj = bpy.data.objects.new(name, bpy.data.meshes.new(name))
    bpy.context.scene.collection.objects.link(obj)
    obj.location = loc
    mod = obj.modifiers.new(GROUP, "NODES")
    mod.node_group = ng
    for key, value in (values or {}).items():
        set_input(mod, ng, key, value)
    if mat:
        set_input(mod, ng, "Material", mat)  # socket 直接指定，不靠 mesh slots
    return obj


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


def floor(size=12.0, color=(0.22, 0.23, 0.24), rough=0.75):
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, -0.001))
    obj = bpy.context.object
    obj.name = "Floor"
    obj.data.materials.append(material("Floor", color, rough))
    return obj


# ------------------------------------------------------------------ scenes
def scene_solid(ng):
    """實心盒：Size XYZ × Scale Factor 直接決定尺寸。"""
    setup_world()
    setup_light()
    floor()
    cardboard = material("Cardboard", (0.60, 0.44, 0.28), 0.7)
    crate = material("Crate", (0.42, 0.30, 0.20), 0.55)
    ink = material("Ink", (0.12, 0.13, 0.16), 0.4, metal=0.2)
    empty_host("Big Box", (0.0, 0.0, 0.4), cardboard, ng,
               {"Size XYZ": (1.2, 0.8, 0.8)})
    empty_host("Small Box", (-0.85, 0.35, 0.28), crate, ng,
               {"Size XYZ": (0.55, 0.55, 0.55), "Scale Factor": 0.7})
    empty_host("Flat Box", (0.85, -0.45, 0.13), ink, ng,
               {"Size XYZ": (0.9, 0.6, 0.26)})
    camera((2.6, -3.4, 1.9), (0.0, 0.1, 0.45), 50)
    area_light((1.6, -2.2, 2.6), (0.2, 0.1, 0.4), 4.5, 220)


def scene_hollow(ng):
    """空心盒：小數尺寸 → dot(normal, offset)>0 的面被挖穿（+x/+y/+z 开口）。"""
    setup_world()
    setup_light(rot=(0.55, 0.0, 0.6))
    floor(size=8, color=(0.16, 0.16, 0.17))
    wood = material("Wood", (0.52, 0.38, 0.24), 0.6)
    empty_host("Open Box", (0.0, 0.0, 0.38), wood, ng,
               {"Size XYZ": (1.2, 0.9, 0.75), "Hollow": True})
    empty_host("Closed Box", (1.35, 0.15, 0.32), wood, ng,
               {"Size XYZ": (1.0, 1.0, 1.0)})  # 整數尺寸 → offset=0，不開口
    camera((2.4, 2.6, 2.1), (0.3, 0.3, 0.35), 50)
    area_light((2.0, 2.2, 2.4), (0.3, 0.3, 0.3), 4.5, 240)


def scene_plug(ng):
    """Fill=Plug：Z 轴开口用内塞平面補上（4.5 只塞 Z；X/Y 开口用 Fill=Cube）。"""
    setup_world()
    setup_light(rot=(0.5, 0.0, 0.5))
    floor(size=8, color=(0.16, 0.16, 0.17))
    teal = material("Teal", (0.20, 0.42, 0.42), 0.5)
    foam = material("Foam", (0.75, 0.72, 0.62), 0.8)
    empty_host("Plug Box", (0.0, 0.0, 0.75), teal, ng,
               {"Size XYZ": (1.0, 1.0, 1.5), "Hollow": True, "Fill Mode": 1,
                "Wall Thickness": 0.1})
    empty_host("Foam Insert", (1.1, 0.0, 0.2), foam, ng,
               {"Size XYZ": (0.6, 0.6, 0.4)})
    camera((2.2, -2.6, 2.3), (0.3, 0.1, 0.75), 50)
    area_light((1.8, -2.0, 2.8), (0.3, 0.1, 0.7), 4.5, 240)


def scene_scatter(ng):
    """實例化：MeshToPoints → InstanceOnPoints + Jitter / Rotation / Scale 隨機。"""
    setup_world(strength=0.6)
    setup_light(rot=(0.45, 0.1, 0.6))
    floor(size=8, color=(0.15, 0.15, 0.16))
    paper = material("Paper", (0.70, 0.62, 0.50), 0.65)
    empty_host("Scatter", (0.0, 0.0, 0.16), paper, ng,
               {"Size XYZ": (0.22, 0.16, 0.10), "Vertices Per Side": 3,
                "Use Instances": True, "Jitter": 0.45,
                "Rotation Range": 120.0, "Scale Random": 0.45,
                "Seed": 7, "Store Attributes": True})
    camera((1.8, -2.2, 1.3), (0.0, 0.0, 0.16), 50)
    area_light((1.4, -1.6, 1.9), (0.0, 0.0, 0.15), 4.0, 220)


def scene_corner(ng):
    """圓角近似：Corner Mode=Subdivide + Shade Smooth（4.5 無 Bevel 節點）。"""
    setup_world(strength=0.65)
    setup_light(rot=(0.5, 0.1, 0.7))
    floor(size=8, color=(0.16, 0.16, 0.17))
    clay = material("Clay", (0.55, 0.30, 0.22), 0.75)
    empty_host("Rounded Box", (0.0, 0.0, 0.35), clay, ng,
               {"Size XYZ": (0.9, 0.7, 0.5), "Corner Mode": 1,
                "Subdivide": 2, "Shade Smooth": True})
    camera((1.9, -2.4, 1.5), (0.0, 0.0, 0.35), 50)
    area_light((1.5, -1.8, 2.2), (0.0, 0.0, 0.35), 4.0, 220)


SCENES = {
    "solid": scene_solid,
    "hollow": scene_hollow,
    "plug": scene_plug,
    "scatter": scene_scatter,
    "corner": scene_corner,
}


def main():
    args = _args()
    os.makedirs(args.out, exist_ok=True)
    wanted = [n for n in args.only.split(",") if n] or list(SCENES)
    for name in wanted:
        ng = reset(args.asset)
        SCENES[name](ng)
        render(os.path.join(args.out, "box_%s.png" % name), args.res, args.samples)
        if name == "solid":
            blend = os.path.join(args.out, "box_demo.blend")
            bpy.ops.wm.save_as_mainfile(filepath=blend, compress=True)
            print("SAVED", blend)
    return 0


if __name__ == "__main__":
    sys.exit(main())
