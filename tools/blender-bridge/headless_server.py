"""Keep-alive bridge for headless Blender (the "worker" half of session management).

Turns a `blender -b` process into a long-lived session:

    BLENDER_BRIDGE_PORT=9879 blender -b --python process/headless_server.py

The main thread runs this loop, so bpy work stays on the main thread exactly as
in the GUI variant; the socket thread only enqueues.
"""
import importlib.util
import os
import sys
import time

os.environ.setdefault("BLENDER_BRIDGE_FORCE", "1")

IMPL = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "blender_bridge_addon.py")
spec = importlib.util.spec_from_file_location("blender_bridge_impl", IMPL)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
bridge.register()

print("[headless] session up on %s:%d" % (bridge.HOST, bridge.PORT), flush=True)

try:
    while True:
        bridge._drain_jobs()   # processes queued jobs on the main thread
        time.sleep(0.03)
except KeyboardInterrupt:
    print("[headless] interrupted", flush=True)
finally:
    bridge.unregister()
