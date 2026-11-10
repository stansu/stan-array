# Blender Bridge

Drive a **running Blender** from a script: the add-on opens a JSON-lines socket on
`127.0.0.1:9877`, so anything local can execute Python inside Blender, capture the
viewport, and save/roll back a snapshot of the scene.

It is optional here — only the `tools/gn/gn.py` CLI needs it. The node group in
`assets/` works without it.

## Files

| File | Purpose |
|---|---|
| `blender_bridge_addon.py` | The add-on: socket server + a job queue that runs `bpy` work on Blender's main thread |
| `bridge.py` | Client: send one JSON request or a Python snippet, print stdout / result |
| `bb` | Tiny wrapper around `bridge.py` |
| `session.py` | `status` / `up` — reuse a running session or launch one (`--headless` for a worker) |
| `headless_server.py` | Keeps a `blender -b` process alive as an interactive session |
| `look.py` | Example snippet: capture the viewport exactly as the user sees it (GUI only) |
| `install-addon.sh` | Copy the add-on into `~/.config/blender/<ver>/scripts/addons` |

## Install

```bash
./install-addon.sh            # every Blender version found in ~/.config/blender
./install-addon.sh 4.5        # just that version
./install-addon.sh --check    # report only
```

Then enable it once per Blender version:

```bash
blender --background --python-expr \
  "import bpy; bpy.ops.preferences.addon_enable(module='blender_bridge_addon'); bpy.ops.wm.save_userpref()"
```

Start Blender normally; the bridge listens on `127.0.0.1:9877`.

## Protocol

One JSON object per line; the reply is one JSON object per line.

| Request | Effect |
|---|---|
| `{"op":"ping"}` | Blender and bridge versions |
| `{"op":"session"}` | pid, file, object count, GPU, viewport size, current shading |
| `{"op":"scene"}` | list objects and collections |
| `{"op":"look","path":"...","shading":"material","overlays":true,"view":"camera","frame":true}` | viewport OpenGL render (needs the GUI) |
| `{"op":"txn_save"}` / `{"op":"txn_revert"}` | save / restore a scene snapshot |
| `{"code":"...","timeout":120}` | execute Python with `bpy` ready |

Environment: `BLENDER_BRIDGE_PORT` (9877), `BLENDER_BRIDGE_HOST` (127.0.0.1),
`BLENDER_BRIDGE_FORCE=1` (open the socket even in `--background`),
`BLENDER_BRIDGE_DIR` (where `look` images and snapshots go; defaults to this folder).

## Usage

```bash
# is a session alive?
python3 session.py status

# no GUI around? run a headless worker instead
python3 session.py up --headless --port 9879
BLENDER_BRIDGE_PORT=9879 ./bb '{"op": "ping"}'

# talk to the open Blender
python3 bb '{"op": "session"}'
python3 bb '{"op": "look", "path": "/tmp/look.png", "shading": "material"}'
python3 bb 'import bpy; bpy.ops.mesh.primitive_cube_add(size=2); print(len(bpy.data.objects))'
./bb - < snippet.py

# snapshot before something risky
python3 bb '{"op": "txn_save"}'
python3 bb '{"op": "txn_revert"}'
```

## Security

This is an **unauthenticated local code-execution channel**. It binds to
`127.0.0.1` only — do not port-forward it, do not bind `0.0.0.0`, and do not run it
on a machine you do not trust.
