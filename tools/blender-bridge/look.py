"""Capture the *actual* 3D viewport the user is looking at (OpenGL viewport render).

Unlike scene renders this uses the viewport's own view and shading (solid /
material / rendered, wireframe, overlays), so it shows what is really on screen.

Run:  python3 tools/blender-bridge/bridge.py - < tools/blender-bridge/look.py
      (or simply: bridge.py '{"op": "look", "path": "/tmp/view.png"}')

The output path comes from $BLENDER_BRIDGE_LOOK, else viewport_look.png next to
this file (or in the working directory when this snippet is sent over the bridge).
"""
import os

import bpy

try:
    _HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:            # sent as a snippet: no __file__
    _HERE = os.getcwd()
OUT = os.environ.get("BLENDER_BRIDGE_LOOK") or os.path.join(_HERE, "viewport_look.png")

window = bpy.context.window_manager.windows[0]
areas = [a for a in window.screen.areas if a.type == "VIEW_3D"]
if not areas:
    raise RuntimeError("no 3D viewport found")
area = max(areas, key=lambda a: a.width * a.height)
region = next(r for r in area.regions if r.type == "WINDOW")
space = area.spaces.active

print("viewport %dx%d  shading=%s  overlays=%s  camera_view=%s"
      % (region.width, region.height, space.shading.type,
         space.overlay.show_overlays, space.region_3d.view_perspective))

scene = bpy.context.scene
scene.render.image_settings.file_format = "PNG"
scene.render.resolution_x = 1200
scene.render.resolution_y = 1200
scene.render.filepath = OUT

with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
    bpy.ops.render.opengl(write_still=True, view_context=True)

print("saved", OUT)
