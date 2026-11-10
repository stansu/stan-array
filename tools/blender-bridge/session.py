"""Tiny session manager for the Blender bridge.

  python3 tools/blender-bridge/session.py status [--port 9877]
  python3 tools/blender-bridge/session.py up     [--port 9877] [--headless] [--blender PATH] [--wait 40]

`status` prints the live session identity (or "down").
`up` reuses a running session if the port answers, otherwise launches one:
    --headless  -> blender -b + headless_server.py (worker, no GUI)
    default     -> normal GUI launch; the bridge add-on starts itself
It waits for the port, then prints the session.

BLENDER_BIN overrides the Blender executable path.

Note: a GUI launched *from inside the agent sandbox* has no GPU (/dev/dri is
not exposed), so it falls back to software rendering. Launch it yourself for GPU.
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge as bridge_client  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def _find_blender_bin():
    """$BLENDER_BIN → PATH → common install dirs."""
    env = os.environ.get("BLENDER_BIN")
    if env and os.path.exists(env):
        return env
    found = shutil.which("blender")
    if found:
        return found
    for pattern in ("~/apps/blender/blender-*/blender",
                    "/opt/blender*/blender",
                    "/usr/local/blender*/blender"):
        hits = sorted(glob.glob(os.path.expanduser(pattern)))
        if hits:
            return hits[-1]
    return "blender"


DEFAULT_BLENDER = _find_blender_bin()


def probe(port):
    try:
        return bridge_client.send({"op": "session"}, port=port, timeout=5)
    except OSError:
        return None


def wait_for(port, seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        resp = probe(port)
        if resp and resp.get("status") == "ok":
            return resp
        time.sleep(0.5)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["status", "up"])
    ap.add_argument("--port", type=int, default=int(os.environ.get("BLENDER_BRIDGE_PORT", "9877")))
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--blender", default=os.environ.get("BLENDER_BIN", DEFAULT_BLENDER))
    ap.add_argument("--wait", type=int, default=60)
    args = ap.parse_args()

    resp = probe(args.port)
    if args.action == "status":
        if not resp or resp.get("status") != "ok":
            print("session: down (port %d)" % args.port)
            return 1
        print(json.dumps(resp.get("result"), ensure_ascii=False, indent=1))
        return 0

    if resp and resp.get("status") == "ok":
        print("reusing the running session on %d" % args.port)
        print(json.dumps(resp.get("result"), ensure_ascii=False, indent=1))
        return 0

    env = dict(os.environ, BLENDER_BRIDGE_PORT=str(args.port))
    if args.headless:
        env["BLENDER_BRIDGE_FORCE"] = "1"
        cmd = [args.blender, "-b", "--factory-startup", "--python",
               os.path.join(HERE, "headless_server.py")]
        log = open(os.path.join(HERE, "session_headless.log"), "ab")
        proc = subprocess.Popen(cmd, env=env, stdout=log, stderr=log, start_new_session=True)
        print("launched headless worker (pid %d) on port %d" % (proc.pid, args.port))
    else:
        cmd = [args.blender]
        proc = subprocess.Popen(cmd, env=env, start_new_session=True)
        print("launched GUI Blender (pid %d); the add-on opens port %d" % (proc.pid, args.port))

    resp = wait_for(args.port, args.wait)
    if resp is None:
        print("session did not come up within %ds — check the Blender log" % args.wait)
        return 2
    print(json.dumps(resp.get("result"), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
