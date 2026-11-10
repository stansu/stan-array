"""Blender Bridge — drive a *live* Blender session from outside.

安裝成 add-on 後,只要 Blender 啟動(非 --background)就會在 127.0.0.1:9877
開一個 JSON-lines socket。

    {"op": "ping"}                    版本
    {"op": "session"}                 這個會話的身分與狀態
    {"op": "scene"}                   物件 / 集合清單
    {"op": "look", ...}               視口算圖(你螢幕上看到的畫面)
    {"op": "txn_save"}                存一個可回復的快照
    {"op": "txn_revert"}              回到那個快照
    {"code": "...", "timeout": n}     在場景裡執行任意 Python

環境變數:
    BLENDER_BRIDGE_PORT   預設 9877
    BLENDER_BRIDGE_HOST   預設 127.0.0.1
    BLENDER_BRIDGE_FORCE  設 1 時連 --background 也啟動(僅供測試)

安全:本機、無認證的程式碼執行通道。只綁 127.0.0.1,不要對外開放。
"""

bl_info = {
    "name": "Blender Bridge",
    "author": "local",
    "version": (1, 1, 0),
    "blender": (3, 6, 0),
    "location": "無介面(啟動即生效)",
    "description": "Localhost socket that lets an external agent run Python and capture the viewport",
    "category": "System",
}

import io
import json
import os
import queue
import socket
import sys
import threading
import time
import traceback

import bpy

VERSION = "1.1.0"
HOST = os.environ.get("BLENDER_BRIDGE_HOST", "127.0.0.1")
PORT = int(os.environ.get("BLENDER_BRIDGE_PORT", "9877"))
FORCE = os.environ.get("BLENDER_BRIDGE_FORCE") == "1"

_HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.environ.get("BLENDER_BRIDGE_DIR") or _HERE
DEFAULT_LOOK = os.path.join(OUT_DIR, "viewport_look.png")
TXN_PATH = os.path.join(OUT_DIR, "session_txn.blend")

_jobs = queue.Queue()
_state = {"socket": None, "thread": None, "timer": None, "started": time.time(),
          "txn": None}
SHADING = {"solid": "SOLID", "material": "MATERIAL", "rendered": "RENDERED",
           "wireframe": "WIREFRAME"}


# ------------------------------------------------------------------ main loop
def _drain_jobs():
    """Timer callback: runs queued work on Blender's main thread."""
    while True:
        try:
            job = _jobs.get_nowait()
        except queue.Empty:
            break
        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        try:
            if job.get("fn") is not None:
                job["result"] = job["fn"](job.get("params") or {})
                job["status"] = "ok"
            else:
                exec(compile(job["code"], "<bridge>", "exec"),
                     {"bpy": bpy, "__name__": "__bridge__"})
                job["status"] = "ok"
        except BaseException:
            job["status"] = "error"
            job["traceback"] = traceback.format_exc()
        finally:
            sys.stdout = old_stdout
            job["stdout"] = buf.getvalue()
            job["event"].set()
    return 0.05


def _run_on_main(code=None, timeout=120, fn=None, params=None):
    job = {"code": code, "fn": fn, "params": params, "event": threading.Event(),
           "status": None, "stdout": "", "traceback": None, "result": None}
    _jobs.put(job)
    if not job["event"].wait(timeout):
        return {"status": "timeout", "stdout": "", "traceback": None, "result": None}
    return {k: job[k] for k in ("status", "stdout", "traceback", "result")}


# ----------------------------------------------------------------- helpers
def _viewport():
    window = bpy.context.window_manager.windows[0]
    areas = [a for a in window.screen.areas if a.type == "VIEW_3D"]
    if not areas:
        raise RuntimeError("no 3D viewport in the current window")
    area = max(areas, key=lambda a: a.width * a.height)
    region = next(r for r in area.regions if r.type == "WINDOW")
    return window, area, region, area.spaces.active


def _capture_viewport(params):
    if bpy.app.background:
        raise RuntimeError("viewport capture needs the GUI (no OpenGL context in background)")

    path = params.get("path") or DEFAULT_LOOK
    res = int(params.get("res") or 1200)
    window, area, region, space = _viewport()
    r3d = space.region_3d

    keep = {
        "view_location": tuple(r3d.view_location),
        "view_distance": r3d.view_distance,
        "view_perspective": r3d.view_perspective,
        "shading": space.shading.type,
        "overlays": space.overlay.show_overlays,
    }

    scene = bpy.context.scene
    old_res = (scene.render.resolution_x, scene.render.resolution_y,
               scene.render.resolution_percentage)
    scene.render.image_settings.file_format = "PNG"
    scene.render.resolution_x = res
    scene.render.resolution_y = res
    scene.render.resolution_percentage = 100

    shading = params.get("shading")
    if shading:
        space.shading.type = SHADING.get(str(shading).lower(), str(shading).upper())
    if params.get("overlays") is not None:
        space.overlay.show_overlays = bool(params["overlays"])

    used_overlays = space.overlay.show_overlays
    used_shading = space.shading.type
    framed = False
    try:
        with bpy.context.temp_override(window=window, area=area, region=region, space_data=space):
            if params.get("frame") and bpy.context.selected_objects:
                bpy.ops.view3d.view_selected(use_all_regions=False)
                framed = True
            if params.get("view") == "camera":
                r3d.view_perspective = "CAMERA"
            elif params.get("view") == "user":
                r3d.view_perspective = "PERSP"

            scene.render.filepath = path
            bpy.ops.render.opengl(write_still=True, view_context=True)
    finally:
        r3d.view_location = keep["view_location"]
        r3d.view_distance = keep["view_distance"]
        r3d.view_perspective = keep["view_perspective"]
        space.shading.type = keep["shading"]
        space.overlay.show_overlays = keep["overlays"]
        (scene.render.resolution_x, scene.render.resolution_y,
         scene.render.resolution_percentage) = old_res

    return {"path": path, "resolution": res, "framed": framed,
            "shading_used": used_shading, "overlays_used": used_overlays,
            "restored": {"shading": keep["shading"], "overlays": keep["overlays"],
                         "view_distance": round(keep["view_distance"], 2)},
            "viewport_px": [region.width, region.height]}


def _session_info(_params):
    info = {
        "bridge": VERSION,
        "blender": bpy.app.version_string,
        "pid": os.getpid(),
        "file": bpy.data.filepath or "(unsaved)",
        "background": bpy.app.background,
        "uptime_s": round(time.time() - _state["started"], 1),
        "objects": len(bpy.data.objects),
        "collections": len(bpy.data.collections),
        "txn": _state["txn"],
    }
    try:
        import gpu
        info["gpu_backend"] = gpu.platform.backend_type_get()
        info["gpu"] = gpu.platform.renderer_get()
    except Exception as exc:
        info["gpu"] = "unavailable (%s)" % exc
    try:
        _w, _a, region, space = _viewport()
        info["viewport_px"] = [region.width, region.height]
        info["shading"] = space.shading.type
        info["camera_view"] = space.region_3d.view_perspective
        info["view_distance"] = round(space.region_3d.view_distance, 2)
    except Exception:
        info["viewport_px"] = None
    return info


def _txn_save(_params):
    bpy.ops.wm.save_as_mainfile(filepath=TXN_PATH, copy=True)
    _state["txn"] = {"path": TXN_PATH, "at": time.time(),
                     "source": bpy.data.filepath or "(unsaved)",
                     "objects": len(bpy.data.objects)}
    return dict(_state["txn"])


def _txn_revert(_params):
    if not _state["txn"] or not os.path.exists(TXN_PATH):
        raise RuntimeError("no transaction snapshot to revert to")
    source = (_state["txn"] or {}).get("source")
    bpy.ops.wm.open_mainfile(filepath=TXN_PATH)
    _state["txn"] = None
    note = None
    if not source or source == "(unsaved)":
        note = ("the scene was unsaved, so the file label now points at the "
                "snapshot; use File > New (or open your own file) when done")
    return {"reverted_to": TXN_PATH, "note": note}


# ------------------------------------------------------------------ server
def _dispatch(req):
    op = req.get("op", "exec")
    if op == "ping":
        return {"status": "ok", "traceback": None, "result": None,
                "stdout": "Blender %s (bridge %s)\n" % (bpy.app.version_string, VERSION)}
    if op == "session":
        return _run_on_main(fn=_session_info)
    if op == "scene":
        return _run_on_main(
            "print('objects:', len(bpy.data.objects))\n"
            "for o in bpy.data.objects:\n"
            "    print('  -', o.name, o.type)\n"
            "print('collections:', [c.name for c in bpy.data.collections])\n")
    if op == "look":
        return _run_on_main(fn=_capture_viewport, params=req, timeout=req.get("timeout", 180))
    if op == "txn_save":
        return _run_on_main(fn=_txn_save, params=req)
    if op == "txn_revert":
        return _run_on_main(fn=_txn_revert, params=req)
    return _run_on_main(code=req.get("code", ""), timeout=req.get("timeout", 120))


def _handle(conn):
    stream = conn.makefile("rwb")
    for line in stream:
        try:
            req = json.loads(line.decode("utf-8"))
        except Exception as exc:
            resp = {"status": "error", "stdout": "", "traceback": str(exc), "result": None}
        else:
            resp = _dispatch(req)
        stream.write((json.dumps(resp) + "\n").encode("utf-8"))
        stream.flush()
    conn.close()


def _serve(srv):
    while True:
        try:
            conn, _ = srv.accept()
        except OSError:
            return
        threading.Thread(target=_handle, args=(conn,), daemon=True).start()


def _start():
    if _state["socket"] is not None:
        return
    if bpy.app.background and not FORCE:
        return
    try:
        os.makedirs(OUT_DIR, exist_ok=True)
    except OSError as exc:
        print("[bridge] cannot create output dir %s (%s)" % (OUT_DIR, exc))
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind((HOST, PORT))
    except OSError as exc:
        print("[bridge] cannot bind %s:%d (%s) — another instance?" % (HOST, PORT, exc))
        srv.close()
        return
    srv.listen(8)
    _state["socket"] = srv
    _state["thread"] = threading.Thread(target=_serve, args=(srv,), daemon=True)
    _state["thread"].start()
    if _state["timer"] is None:
        _state["timer"] = bpy.app.timers.register(_drain_jobs, first_interval=0.1, persistent=True)
    print("[bridge] listening on %s:%d (v%s)" % (HOST, PORT, VERSION), flush=True)


def _stop():
    srv = _state["socket"]
    if srv is not None:
        try:
            srv.close()
        except OSError:
            pass
        _state["socket"] = None
    if _state["timer"] is not None:
        try:
            bpy.app.timers.unregister(_drain_jobs)
        except Exception:
            pass
        _state["timer"] = None


def register():
    _start()


def unregister():
    _stop()


if __name__ == "__main__":
    register()
