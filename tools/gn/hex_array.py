"""Hex Array — a reusable hexagonal-lattice instancer (Geometry Nodes).

蜂巢狀排列：nx × ny 個格點，奇數列水平錯開半格；每個格點放一個 Collection
裡的物件，可隨機挑選、隨機大小、隨機旋轉、隨機間距。

輸入:
  Collection        單元物件來源（多個時隨機挑選）
  Count Long        長邊方向的格數 (X)
  Count Short       短邊方向的列數 (Y)
  Cell Size         六角單元外徑（頂點到頂點, 公尺）→ 決定格距
  Spacing           中心距倍率，1.0 = 六角緊貼
  Stagger Columns   False = pointy-top（行沿 X 錯開）；True = flat-top（列沿 Y 錯開）
  Size Random       單元大小隨機幅度 (± 比例)
  Spacing Random    格點位置抖動（相對間距的比例）
  Yaw Random        每格繞 Z 的隨機旋轉（1 = 一整圈）
  Collection Count  Collection 裡的物件數，用於隨機挑選
  Scale             單元大小倍率
  Seed              亂數種子

節點圖分區:
  ① 格距   → ② 格點      主線（左→右）
  ③ 錯位   → ④ 抖動 → ⑤ 定位（下方）
  ⑥ 單元   → ⑦ 大小 → ⑧ 旋轉（上方）
  ⑨ 實例化 → 輸出

純 bpy，沒有 bpy 以外的相依；`build_asset.py` 會在無頭 Blender 裡呼叫。
"""

import math

import bpy

NAME = "Hex Array"
DESCRIPTION = ("蜂巢狀陣列：長/短邊格數、間距與大小可設亂數；"
               "每格從 Collection 隨機取一個物件。")
SQRT3 = math.sqrt(3.0)

C_LATTICE = (0.19, 0.30, 0.42)
C_STAGGER = (0.24, 0.36, 0.24)
C_JITTER = (0.36, 0.27, 0.40)
C_PLACE = (0.20, 0.33, 0.33)
C_CELL = (0.40, 0.32, 0.20)
C_SIZE = (0.32, 0.24, 0.38)
C_YAW = (0.38, 0.30, 0.22)
C_OUT = (0.22, 0.34, 0.24)


# --------------------------------------------------------------------- helpers
def _node(ng, type_, loc, label=None, width=None, **props):
    n = ng.nodes.new(type_)
    n.location = loc
    if label:
        n.label = label
    if width:
        n.width = width
    for key, value in props.items():
        setattr(n, key, value)
    return n


def _out(node, name, type_=None):
    for s in node.outputs:
        if s.name == name and (type_ is None or s.type == type_) and s.enabled:
            return s
    for s in node.outputs:
        if s.name == name and (type_ is None or s.type == type_):
            return s
    raise KeyError("%s has no output %r" % (node.bl_idname, name))


def _in(node, name, type_=None):
    """Return the *enabled* input socket with this name (Vector/Value/Int 同名)."""
    for s in node.inputs:
        if s.name != name:
            continue
        if type_ is not None and s.type != type_:
            continue
        if getattr(s, "enabled", True):
            return s
    for s in node.inputs:
        if s.name == name and (type_ is None or s.type == type_):
            return s
    raise KeyError("%s has no input %r" % (node.bl_idname, name))


def _math(ng, op, loc, a=None, b=None, c=None, label=None):
    n = _node(ng, "ShaderNodeMath", loc, label=label, width=180, operation=op)
    for i, value in enumerate((a, b, c)):
        if value is None:
            continue
        sock = n.inputs[i]
        if isinstance(value, bpy.types.NodeSocket):
            ng.links.new(value, sock)
        else:
            sock.default_value = float(value)
    return n.outputs[0]


def _link(ng, a, b):
    ng.links.new(a, b)


def _random(ng, data_type, loc, seed_socket, lo, hi, label=None, probability=None):
    n = _node(ng, "FunctionNodeRandomValue", loc, label=label, width=170)
    n.data_type = data_type
    for name, value in (("Min", lo), ("Max", hi)):
        sock = _in(n, name)
        if isinstance(value, bpy.types.NodeSocket):
            ng.links.new(value, sock)
        elif sock.type == "INT":
            sock.default_value = int(value)
        else:
            sock.default_value = value
    if probability is not None:
        _in(n, "Probability").default_value = probability
    _link(ng, seed_socket, _in(n, "Seed"))
    want = {"FLOAT": "VALUE", "INT": "INT", "FLOAT_VECTOR": "VECTOR"}[data_type]
    for sock in n.outputs:
        if sock.type == want and sock.enabled:
            return sock
    raise RuntimeError("Random Value has no enabled %s output" % want)


def _seed(ng, base_socket, offset, loc, label=None):
    return _math(ng, "ADD", loc, base_socket, offset, label=label)


def _frame(ng, label, color, nodes, label_size=26):
    """把 nodes 收進一個有標題的 frame（節點位置以絕對座標給）。"""
    nodes = [n for n in nodes if n is not None]
    if not nodes:
        return None
    frame = ng.nodes.new("NodeFrame")
    frame.label = label
    frame.label_size = label_size
    frame.use_custom_color = True
    frame.color = color
    min_x = min(n.location.x for n in nodes)
    max_y = max(n.location.y for n in nodes)
    frame.location = (min_x - 40.0, max_y + 90.0)
    for n in nodes:
        abs_loc = n.location.copy()
        n.parent = frame
        n.location = (abs_loc.x - frame.location.x, abs_loc.y - frame.location.y)
    return frame


def _section(ng):
    """Section helper: remember where this section starts in ng.nodes."""
    return len(ng.nodes)


# ----------------------------------------------------------------------- build
def build(name=NAME):
    """(Re)create the node group and return it."""
    ng = bpy.data.node_groups.get(name)
    if ng is not None and ng.bl_idname != "GeometryNodeTree":
        raise RuntimeError("%r exists but is a %s" % (name, ng.bl_idname))
    if ng is None:
        ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    ng.nodes.clear()
    ng.interface.clear()
    ng.is_modifier = True
    ng.description = DESCRIPTION
    ng.color_tag = "GEOMETRY"

    itf = ng.interface
    geo_in = itf.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    geo_in.description = "（未使用）主機物件的幾何"

    coll = itf.new_socket("Collection", in_out="INPUT", socket_type="NodeSocketCollection")
    coll.description = "六角單元的物件來源；多個物件時隨機挑選"

    s_nx = itf.new_socket("Count Long", in_out="INPUT", socket_type="NodeSocketInt")
    s_nx.default_value = 12
    s_nx.min_value = 1
    s_nx.max_value = 512
    s_nx.description = "長邊方向（X）的格數"

    s_ny = itf.new_socket("Count Short", in_out="INPUT", socket_type="NodeSocketInt")
    s_ny.default_value = 8
    s_ny.min_value = 1
    s_ny.max_value = 512
    s_ny.description = "短邊方向（Y）的列數"

    s_cell = itf.new_socket("Cell Size", in_out="INPUT", socket_type="NodeSocketFloat")
    s_cell.default_value = 0.25
    s_cell.min_value = 0.0001
    s_cell.subtype = "DISTANCE"
    s_cell.description = "六角單元外徑（頂點到頂點）"

    s_spacing = itf.new_socket("Spacing", in_out="INPUT", socket_type="NodeSocketFloat")
    s_spacing.default_value = 1.0
    s_spacing.min_value = 0.01
    s_spacing.description = "中心距倍率：1.0 = 六角緊貼，>1 拉開"

    s_stagger = itf.new_socket("Stagger Columns", in_out="INPUT",
                               socket_type="NodeSocketBool")
    s_stagger.default_value = False
    s_stagger.description = ("False = pointy-top（行沿 X 錯開；Blender 預設 6 邊柱體）；"
                             "True = flat-top（列沿 Y 錯開）")

    s_size_rnd = itf.new_socket("Size Random", in_out="INPUT", socket_type="NodeSocketFloat")
    s_size_rnd.default_value = 0.0
    s_size_rnd.min_value = 0.0
    s_size_rnd.max_value = 1.0
    s_size_rnd.subtype = "FACTOR"
    s_size_rnd.description = "單元大小的隨機幅度（± 比例）"

    s_space_rnd = itf.new_socket("Spacing Random", in_out="INPUT", socket_type="NodeSocketFloat")
    s_space_rnd.default_value = 0.0
    s_space_rnd.min_value = 0.0
    s_space_rnd.max_value = 1.0
    s_space_rnd.subtype = "FACTOR"
    s_space_rnd.description = "格點位置抖動（相對間距的比例）"

    s_yaw = itf.new_socket("Yaw Random", in_out="INPUT", socket_type="NodeSocketFloat")
    s_yaw.default_value = 0.0
    s_yaw.min_value = 0.0
    s_yaw.max_value = 1.0
    s_yaw.subtype = "FACTOR"
    s_yaw.description = "每格繞 Z 隨機旋轉（1 = 一整圈）"

    s_count = itf.new_socket("Collection Count", in_out="INPUT", socket_type="NodeSocketInt")
    s_count.default_value = 1
    s_count.min_value = 1
    s_count.max_value = 999
    s_count.description = "Collection 裡的物件數，用於隨機挑選"

    s_scale = itf.new_socket("Scale", in_out="INPUT", socket_type="NodeSocketFloat")
    s_scale.default_value = 1.0
    s_scale.min_value = 0.0
    s_scale.description = "單元大小倍率（1 = 物件原始大小）；Size Random 會再乘上隨機量"

    s_seed = itf.new_socket("Seed", in_out="INPUT", socket_type="NodeSocketInt")
    s_seed.default_value = 0

    geo_out = itf.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    geo_out.description = "實例化後的六角陣列"

    # ================================================================ 節點圖
    gi = _node(ng, "NodeGroupInput", (-2650, 420), label="參數", width=170)
    go = _node(ng, "NodeGroupOutput", (1150, -150), label="輸出", width=150)

    # ------------------------------------------------------------ ① 格距
    start = _section(ng)
    narrow = _math(ng, "MULTIPLY", (-2350, 560), _out(gi, "Cell Size"), 0.75,
                   label="窄邊 0.75·D")
    wide = _math(ng, "MULTIPLY", (-2350, 380), _out(gi, "Cell Size"), SQRT3 / 2.0,
                 label="寬邊 0.866·D")

    dx_base = _node(ng, "GeometryNodeSwitch", (-2130, 560), label="dx 基準", width=170,
                    input_type="FLOAT")
    _link(ng, _out(gi, "Stagger Columns"), _in(dx_base, "Switch"))
    _link(ng, wide, _in(dx_base, "False"))
    _link(ng, narrow, _in(dx_base, "True"))

    dy_base = _node(ng, "GeometryNodeSwitch", (-2130, 380), label="dy 基準", width=170,
                    input_type="FLOAT")
    _link(ng, _out(gi, "Stagger Columns"), _in(dy_base, "Switch"))
    _link(ng, narrow, _in(dy_base, "False"))
    _link(ng, wide, _in(dy_base, "True"))

    dx = _math(ng, "MULTIPLY", (-1910, 560), _out(dx_base, "Output"),
               _out(gi, "Spacing"), label="dx × Spacing")
    dy = _math(ng, "MULTIPLY", (-1910, 380), _out(dy_base, "Output"),
               _out(gi, "Spacing"), label="dy × Spacing")
    _frame(ng, "① 格距　dx / dy（pointy ↔ flat）", C_LATTICE, list(ng.nodes)[start:])

    # ------------------------------------------------------------ ② 格點
    start = _section(ng)
    nx_m1 = _math(ng, "SUBTRACT", (-1660, 580), _out(gi, "Count Long"), 1.0,
                  label="N − 1")
    ny_m1 = _math(ng, "SUBTRACT", (-1660, 380), _out(gi, "Count Short"), 1.0,
                  label="N − 1")
    size_x = _math(ng, "MULTIPLY", (-1460, 580), dx, nx_m1, label="格點寬")
    size_y = _math(ng, "MULTIPLY", (-1460, 380), dy, ny_m1, label="格點高")

    grid = _node(ng, "GeometryNodeMeshGrid", (-1240, 470), label="Grid", width=170)
    _link(ng, size_x, _in(grid, "Size X"))
    _link(ng, size_y, _in(grid, "Size Y"))
    _link(ng, _out(gi, "Count Long"), _in(grid, "Vertices X"))
    _link(ng, _out(gi, "Count Short"), _in(grid, "Vertices Y"))

    points = _node(ng, "GeometryNodeMeshToPoints", (-1020, 470), label="只留頂點", width=150,
                   mode="VERTICES")
    _link(ng, _out(grid, "Mesh"), _in(points, "Mesh"))
    _frame(ng, "② 格點　Grid → Points", C_LATTICE, list(ng.nodes)[start:])

    # ------------------------------------------------------------ ③ 錯位
    start = _section(ng)
    pos = _node(ng, "GeometryNodeInputPosition", (-2600, -250), label="座標", width=150)
    sep = _node(ng, "ShaderNodeSeparateXYZ", (-2420, -250), label="X / Y", width=130)
    _link(ng, _out(pos, "Position"), _in(sep, "Vector"))

    row = _math(ng, "ROUND", (-2200, -130),
                _math(ng, "DIVIDE", (-2360, -130), _out(sep, "Y"), dy, label="Y ÷ dy"),
                label="列 = round(Y/dy)")
    row_p = _math(ng, "FLOORED_MODULO", (-2000, -130), row, 2.0, label="奇偶")
    shift_x = _math(ng, "MULTIPLY", (-1800, -130),
                    _math(ng, "MULTIPLY", (-2000, -270), row_p, dx, label="奇偶 × dx"), 0.5,
                    label="X 錯開 dx/2")

    col = _math(ng, "ROUND", (-2200, -520),
                _math(ng, "DIVIDE", (-2360, -520), _out(sep, "X"), dx, label="X ÷ dx"),
                label="行 = round(X/dx)")
    col_p = _math(ng, "FLOORED_MODULO", (-2000, -520), col, 2.0, label="奇偶")
    shift_y = _math(ng, "MULTIPLY", (-1800, -520),
                    _math(ng, "MULTIPLY", (-2000, -660), col_p, dy, label="奇偶 × dy"), 0.5,
                    label="Y 錯開 dy/2")

    stagger_x = _node(ng, "GeometryNodeSwitch", (-1580, -130), label="錯位 X", width=170,
                      input_type="FLOAT")
    _link(ng, _out(gi, "Stagger Columns"), _in(stagger_x, "Switch"))
    _link(ng, shift_x, _in(stagger_x, "False"))
    _in(stagger_x, "True").default_value = 0.0

    stagger_y = _node(ng, "GeometryNodeSwitch", (-1580, -520), label="錯位 Y", width=170,
                      input_type="FLOAT")
    _link(ng, _out(gi, "Stagger Columns"), _in(stagger_y, "Switch"))
    _in(stagger_y, "False").default_value = 0.0
    _link(ng, shift_y, _in(stagger_y, "True"))
    _frame(ng, "③ 錯位　用座標推列／行，奇數列（行）錯開半格", C_STAGGER,
           list(ng.nodes)[start:])

    # ------------------------------------------------------------ ④ 抖動
    start = _section(ng)
    jitter_mag = _math(ng, "MULTIPLY", (-1900, -1000),
                       _math(ng, "MULTIPLY", (-2070, -1000), dx, 0.5, label="dx / 2"),
                       _out(gi, "Spacing Random"), label="抖動幅度")
    jitter_neg = _math(ng, "MULTIPLY", (-1700, -1000), jitter_mag, -1.0, label="− 幅度")
    seed1 = _seed(ng, _out(gi, "Seed"), 11, (-1900, -1200), label="種子 +11")
    seed2 = _seed(ng, _out(gi, "Seed"), 23, (-1900, -1380), label="種子 +23")
    jx = _random(ng, "FLOAT", (-1500, -1200), seed1, jitter_neg, jitter_mag,
                 label="抖動 X")
    jy = _random(ng, "FLOAT", (-1500, -1380), seed2, jitter_neg, jitter_mag,
                 label="抖動 Y")
    _frame(ng, "④ 抖動　Spacing Random", C_JITTER, list(ng.nodes)[start:])

    # ------------------------------------------------------------ ⑤ 定位
    start = _section(ng)
    off_x = _math(ng, "ADD", (-1250, -130), _out(stagger_x, "Output"), jx, label="X 位移")
    off_y = _math(ng, "ADD", (-1250, -520), _out(stagger_y, "Output"), jy, label="Y 位移")
    offset = _node(ng, "ShaderNodeCombineXYZ", (-1030, -330), label="位移向量", width=150)
    _link(ng, off_x, _in(offset, "X"))
    _link(ng, off_y, _in(offset, "Y"))

    placed = _node(ng, "GeometryNodeSetPosition", (-800, -150), label="Set Position",
                   width=170)
    _link(ng, _out(points, "Points"), _in(placed, "Geometry"))
    _link(ng, _out(offset, "Vector"), _in(placed, "Offset"))
    _frame(ng, "⑤ 定位　錯位 + 抖動 → Set Position", C_PLACE, list(ng.nodes)[start:])

    # ------------------------------------------------------------ ⑥ 單元
    start = _section(ng)
    ci = _node(ng, "GeometryNodeCollectionInfo", (-450, 760), label="Collection",
               width=180)
    _in(ci, "Separate Children").default_value = True
    _in(ci, "Reset Children").default_value = True
    ci.transform_space = "ORIGINAL"
    _link(ng, _out(gi, "Collection"), _in(ci, "Collection"))

    max_index = _math(ng, "MAXIMUM", (-650, 1030),
                      _math(ng, "SUBTRACT", (-820, 1030),
                            _out(gi, "Collection Count"), 1.0, label="Count − 1"),
                      0.0, label="最大 index")
    seed3 = _seed(ng, _out(gi, "Seed"), 37, (-820, 880), label="種子 +37")
    pick = _random(ng, "INT", (-450, 930), seed3, 0, max_index, label="隨機 index")
    _frame(ng, "⑥ 單元　Collection Info + 隨機挑選", C_CELL, list(ng.nodes)[start:])

    # ------------------------------------------------------------ ⑦ 大小
    start = _section(ng)
    size_lo = _math(ng, "SUBTRACT", (150, 1130), 1.0, _out(gi, "Size Random"),
                    label="1 − 隨機")
    size_hi = _math(ng, "ADD", (150, 940), 1.0, _out(gi, "Size Random"),
                    label="1 + 隨機")
    seed4 = _seed(ng, _out(gi, "Seed"), 53, (-60, 1290), label="種子 +53")
    size_rnd = _random(ng, "FLOAT", (150, 1290), seed4, size_lo, size_hi,
                       label="大小倍率")
    scale = _math(ng, "MULTIPLY", (340, 1050), _out(gi, "Scale"), size_rnd,
                  label="Scale × 隨機")
    scale_vec = _node(ng, "ShaderNodeCombineXYZ", (550, 1050), label="Scale 向量",
                      width=150)
    for axis in ("X", "Y", "Z"):
        _link(ng, scale, _in(scale_vec, axis))
    _frame(ng, "⑦ 大小　Scale × Size Random", C_SIZE, list(ng.nodes)[start:])

    # ------------------------------------------------------------ ⑧ 旋轉
    start = _section(ng)
    seed5 = _seed(ng, _out(gi, "Seed"), 71, (-150, 1600), label="種子 +71")
    yaw01 = _random(ng, "FLOAT", (60, 1600), seed5, 0.0, 1.0, label="亂數 0…1")
    yaw_turn = _math(ng, "MULTIPLY", (260, 1740), yaw01, 2.0 * math.pi, label="× 2π")
    yaw = _math(ng, "MULTIPLY", (450, 1600), yaw_turn, _out(gi, "Yaw Random"),
                label="× Yaw Random")
    yaw_vec = _node(ng, "ShaderNodeCombineXYZ", (650, 1600), label="Yaw（Z）", width=150)
    _link(ng, yaw, _in(yaw_vec, "Z"))
    rot = _node(ng, "FunctionNodeEulerToRotation", (860, 1600), label="Yaw → Rotation",
                width=180)
    _link(ng, _out(yaw_vec, "Vector"), _in(rot, "Euler"))
    _frame(ng, "⑧ 旋轉　Yaw Random", C_YAW, list(ng.nodes)[start:])

    # ------------------------------------------------------------ ⑨ 實例化
    start = _section(ng)
    inst = _node(ng, "GeometryNodeInstanceOnPoints", (760, -150),
                 label="Instance on Points", width=190)
    _link(ng, _out(placed, "Geometry"), _in(inst, "Points"))
    _link(ng, _out(ci, "Instances"), _in(inst, "Instance"))
    _in(inst, "Pick Instance").default_value = True
    _link(ng, pick, _in(inst, "Instance Index"))
    _link(ng, _out(rot, "Rotation"), _in(inst, "Rotation"))
    _link(ng, _out(scale_vec, "Vector"), _in(inst, "Scale"))

    _link(ng, _out(inst, "Instances"), go.inputs["Geometry"])
    _frame(ng, "⑨ 實例化 → 輸出", C_OUT, list(ng.nodes)[start:] + [go])

    return ng


def inputs_summary(ng):
    rows = []
    for item in ng.interface.items_tree:
        if item.item_type != "SOCKET" or item.in_out != "INPUT":
            continue
        default = getattr(item, "default_value", None)
        if isinstance(default, float):
            default = round(default, 6)
        elif hasattr(default, "__len__") and not isinstance(default, str):
            default = tuple(round(v, 6) for v in default)
        rows.append({"name": item.name, "type": item.socket_type,
                     "default": default, "min": getattr(item, "min_value", None),
                     "max": getattr(item, "max_value", None),
                     "description": getattr(item, "description", "")})
    return rows
