"""Tiny client for the Blender Bridge add-on.

  python3 tools/blender-bridge/bridge.py '{"op": "scene"}'
  python3 tools/blender-bridge/bridge.py 'bpy.ops.mesh.primitive_cube_add()'
  python3 tools/blender-bridge/bridge.py - < snippet.py
  python3 tools/blender-bridge/bridge.py --port 9879 '{"op": "ping"}'

Environment:
  BLENDER_BRIDGE_PORT         default 9877
  BRIDGE_TIMEOUT              seconds the bridge may spend inside Blender (120)
  BRIDGE_SOCKET_TIMEOUT       client socket timeout (600)
"""
import json
import os
import socket
import sys

PORT = int(os.environ.get("BLENDER_BRIDGE_PORT", "9877"))
SERVER_TIMEOUT = int(os.environ.get("BRIDGE_TIMEOUT", "120"))
SOCKET_TIMEOUT = int(os.environ.get("BRIDGE_SOCKET_TIMEOUT", "600"))


def send(req, port=PORT, timeout=SOCKET_TIMEOUT):
    sock = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    sock.sendall((json.dumps(req) + "\n").encode("utf-8"))
    with sock.makefile("rb") as stream:
        line = stream.readline()
    sock.close()
    if not line:
        raise RuntimeError("bridge closed the connection without answering")
    return json.loads(line.decode("utf-8"))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    port = PORT
    while argv and argv[0] in ("--port", "-p"):
        port = int(argv[1])
        del argv[:2]
    arg = argv[0] if argv else "-"
    src = sys.stdin.read() if arg == "-" else arg
    try:
        req = json.loads(src)
    except ValueError:
        req = {"code": src, "timeout": SERVER_TIMEOUT}
    if "code" in req and "timeout" not in req:
        req["timeout"] = SERVER_TIMEOUT
    try:
        resp = send(req, port=port)
    except OSError as exc:
        sys.stderr.write(
            "cannot reach the Blender bridge on 127.0.0.1:%d (%s)\n"
            "start Blender with the Blender Bridge add-on enabled, or run:\n"
            "  python3 tools/blender-bridge/session.py up --headless\n"
            % (port, exc))
        return 3
    sys.stdout.write(resp.get("stdout") or "")
    if resp.get("result") is not None:
        sys.stdout.write(json.dumps(resp["result"], ensure_ascii=False, indent=1) + "\n")
    if resp.get("traceback"):
        sys.stderr.write(resp["traceback"])
    return 0 if resp.get("status") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
