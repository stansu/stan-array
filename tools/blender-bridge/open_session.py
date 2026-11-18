"""GUI 開場脚本：直接 register bridge（免安裝 addon），讓 CLI 能即時操作。

    blender --python tools/blender-bridge/open_session.py

"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import blender_bridge_addon as impl  # noqa: E402

try:
    impl.register()
    print("[open_session] bridge register ok (port %s)" % impl.PORT, flush=True)
except OSError as err:
    # addon 已被偏好啟用時會先佔端口；重複 register 無害，忽略即可
    print("[open_session] bridge already listening: %s" % err, flush=True)
