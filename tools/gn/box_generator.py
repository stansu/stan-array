#!/usr/bin/env python3
"""
box_generator.py — Stan Box：純 bpy 幾何節點盒生成器（Blender 4.5 目標）。

Design notes
------------
一個 modifier 節點組把「盒」做成可調參數的生成器；全部節点在 4.5 都可用：

* **尺寸**：`GeometryNodeMeshCube` 直接吃 Size 向量 = Size XYZ × Scale Factor。
* **开口判定**：`offset = dims - floor(|dims|)`。某軸 offset>0（小數尺寸）→
  +方向开口；offset<0（負尺寸）→ -方向开口。挖穿面 = `dot(normal, offset) > EPS`
  （`GeometryNodeInputNormal` + `ShaderNodeVectorMath DOT_PRODUCT`），
  保留面 = NOT cut。
* **空心**：`GeometryNodeScaleElements`(FACE) 先把保留面往中心縮（Shrink Faces），
  再 `GeometryNodeDeleteGeometry`(FACE, ONLY_FACE) 挖穿（保留邊線框架）。
* **Fill Mode**：0 None 開放盒／1 Plug 塞内塞平面（`MeshGrid`+`Transform`，
  只塞 Z 轴开口側——4.5 限制）／2 Cube 實心退回。
* **Corner Mode**：4.5 Python API 無 Bevel/MergePoints，Subdivide
  （`GeometryNodeSubdivideMesh`）+ Shade Smooth 是唯一可行的圓角近似。
* **實例化**：`MeshToPoints` → `InstanceOnPoints`；Jitter/Rotation/Scale 隨機來自
  `FunctionNodeRandomValue`(FLOAT_VECTOR)，ID = index + Seed。
* **Store Attributes**：box_index/box_seed/box_random/box_scale（INSTANCE 域）。
* **輸出**：Use Instances → Realize → SetMaterial → SetShadeSmooth。

Blender 限制（4.5）：無 GeometryNodeBevel、MergePoints、InputRandom；
`ShaderNodeVectorMath` 無 CLAMP；圓角只有 Subdivide 近似。
"""
import bpy

NAME = "Stan Box"
DESCRIPTION = (
    "盒生成器：尺寸、每邊頂點數、空心壁厚、收口面、實例化隨機化。"
    " (Box generator: size, verts per side, hollow shell, face shrink, instancing.)"
)

# --- name tables: single source of truth for socket descriptions + CLI + tests ---
FILL_NAMES = ["None", "Plug", "Cube"]
CORNER_NAMES = ["None", "Subdivide"]
AXIS_NAMES = ["X", "Y", "Z"]

ATTR_INDEX = "box_index"
ATTR_SEED = "box_seed"
ATTR_RANDOM = "box_random"
ATTR_SCALE = "box_scale"
EPS = 0.001


def _enum(names):
    return "｜".join("%d %s" % (i, nm) for i, nm in enumerate(names))


def _node(ng, type_, loc, label=None, width=160, **props):
    n = ng.nodes.new(type_)
    n.location = (float(loc[0]), float(loc[1]))
    if label:
        n.label = label
    n.width = width
    for k, v in props.items():
        setattr(n, k, v)
    return n


def _out(node, name, type_=None):
    for s in node.outputs:
        if s.name == name and (type_ is None or s.type == type_):
            return s
    raise RuntimeError("no output %r on %s" % (name, node.type))


def _in(node, name, type_=None):
    for s in node.inputs:
        if s.name == name and (type_ is None or s.type == type_):
            return s
    raise RuntimeError("no input %r(%s) on %s" % (name, type_, node.type))


def _link(ng, a, b):
    ng.links.new(a, b)


def _feed(ng, sock, value):
    """把 socket 或數值餵給輸入；非數值類型（MATERIAL/ROTATION 等）只能連結。"""
    if isinstance(value, bpy.types.NodeSocket):
        _link(ng, value, sock)
    elif sock.type == "INT":
        sock.default_value = int(value)
    elif sock.type == "BOOL":
        sock.default_value = bool(value)
    elif sock.type == "VECTOR":
        sock.default_value = value
    elif sock.type in ("FLOAT", "VALUE"):
        sock.default_value = float(value)
    else:
        raise RuntimeError("socket %r (%s) 不接受常量值 %r" %
                           (sock.name, sock.type, value))
    return sock


def _math(ng, op, loc, a, b=None, label=None, width=120):
    """ShaderNodeMath；依啟用 socket 依序餵 a/b。回傳 Value socket。"""
    n = _node(ng, "ShaderNodeMath", loc, label=label, width=width, operation=op)
    socks = [s for s in n.inputs if s.enabled]
    for sock, value in zip(socks, (a, b)):
        if value is None:
            continue
        _feed(ng, sock, value)
    return n.outputs["Value"]


def _vm(ng, op, loc, a=None, b=None, label=None, width=150):
    """ShaderNodeVectorMath。4.5 輸入 socket 全名為 Vector/Scale（非 A/B），
    依「啟用順序」餵入：a→第一個啟用 Vector，b→第二個啟用 Vector；
    b 若為常數 float 且節點有啟用 Scale（如 SCALE），餵 Scale。
    回傳輸出 socket（DOT_PRODUCT 等輸出為 Value）。"""
    n = _node(ng, "ShaderNodeVectorMath", loc, label=label, width=width, operation=op)
    vecs = [s for s in n.inputs if s.enabled and s.type == "VECTOR"]
    scale = [s for s in n.inputs if s.enabled and s.type == "VALUE"]
    if a is not None and vecs:
        _feed(ng, vecs[0], a)
    if b is not None:
        constant = not isinstance(b, bpy.types.NodeSocket) and not isinstance(b, tuple)
        if scale and constant:
            _feed(ng, scale[0], b)
        elif len(vecs) > 1:
            _feed(ng, vecs[1], b)
    enabled = [s for s in n.outputs if getattr(s, "enabled", True)]
    for s in enabled:
        if s.name == "Vector":
            return s
    return enabled[0] if enabled else n.outputs[0]


def _separate(ng, vec, loc, label=None):
    n = _node(ng, "ShaderNodeSeparateXYZ", loc, label=label, width=140)
    _link(ng, vec, _in(n, "Vector"))
    return [n.outputs[k] for k in ("X", "Y", "Z")]


def _xyz(ng, x, y, z, loc, label=None):
    n = _node(ng, "ShaderNodeCombineXYZ", loc, label=label, width=140)
    for axis, value in (("X", x), ("Y", y), ("Z", z)):
        if value is None:
            continue
        _feed(ng, _in(n, axis), value)
    return n.outputs["Vector"]


def _b(ng, op, loc, a, b=None, label=None, width=130):
    """FunctionNodeBooleanMath；依啟用 socket 依序餵 a/b。回傳 Boolean socket。"""
    n = _node(ng, "FunctionNodeBooleanMath", loc, label=label, width=width, operation=op)
    socks = [s for s in n.inputs if s.enabled]
    for sock, value in zip(socks, (a, b)):
        if value is None:
            continue
        _feed(ng, sock, value)
    return n.outputs["Boolean"]


def _cmp(ng, op, loc, a, b=None, data_type="FLOAT", mode=None, label=None, width=140):
    """FunctionNodeCompare；依 data_type 選 A/B socket。回傳 Result socket。"""
    n = _node(ng, "FunctionNodeCompare", loc, label=label, width=width,
              data_type=data_type, operation=op)
    if mode is not None:
        n.mode = mode
    sock_type = {"FLOAT": "VALUE", "INT": "INT", "VECTOR": "VECTOR",
                 "STRING": "STRING"}[data_type]
    for name, value in (("A", a), ("B", b)):
        if value is None:
            continue
        _feed(ng, _in(n, name, sock_type), value)
    return n.outputs["Result"]


def _switch(ng, loc, cond, false, true, input_type="GEOMETRY", label=None, width=170):
    """GeometryNodeSwitch。回傳 Output socket。"""
    n = _node(ng, "GeometryNodeSwitch", loc, label=label, width=width,
              input_type=input_type)
    _link(ng, cond, _in(n, "Switch"))
    for name, value in (("False", false), ("True", true)):
        if value is None:
            continue
        _feed(ng, _in(n, name), value)
    return n.outputs["Output"]


def _index_switch(ng, loc, data_type, index, values, label=None, width=200):
    """GeometryNodeIndexSwitch。回傳 Output socket。"""
    n = _node(ng, "GeometryNodeIndexSwitch", loc, label=label, width=width,
              data_type=data_type)
    while len(n.index_switch_items) < len(values):
        n.index_switch_items.new()
    _link(ng, index, n.inputs["Index"])
    for i, value in enumerate(values):
        if value is None:
            continue
        _feed(ng, n.inputs[i + 1], value)
    return n.outputs[0]


def _rand(ng, loc, data_type, lo, hi, id_sock, label=None, width=170):
    """FunctionNodeRandomValue；Min/Max/Value 依 data_type 選 socket。回傳 Value socket。"""
    n = _node(ng, "FunctionNodeRandomValue", loc, label=label, width=width,
              data_type=data_type)
    want = {"FLOAT_VECTOR": "VECTOR", "FLOAT": "VALUE"}[data_type]
    _feed(ng, _in(n, "Min", want), lo)
    _feed(ng, _in(n, "Max", want), hi)
    _link(ng, id_sock, _in(n, "ID", "INT"))
    return _out(n, "Value", want)


def _store(ng, geom, name, value, loc, label=None, data_type="FLOAT_VECTOR",
           domain="INSTANCE", width=180):
    n = _node(ng, "GeometryNodeStoreNamedAttribute", loc, label=label, width=width,
              data_type=data_type, domain=domain)
    _in(n, "Name").default_value = name
    _link(ng, geom, _in(n, "Geometry", "GEOMETRY"))
    sock = _in(n, "Value")
    if isinstance(value, bpy.types.NodeSocket):
        _link(ng, value, sock)
    elif data_type == "INT":
        sock.default_value = int(value)
    elif data_type == "FLOAT":
        sock.default_value = float(value)
    else:
        sock.default_value = value
    return n.outputs["Geometry"]


def _frame(ng, label, color, sockets, label_size=26):
    nodes = []
    seen = set()
    for s in sockets:
        n = s.node if hasattr(s, "node") else s
        if n.bl_idname == "NodeFrame" or id(n) in seen:
            continue
        seen.add(id(n))
        nodes.append(n)
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


# ----------------------------------------------------------------------- build
def build(name=NAME):
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
    geo_in.description = "主機幾何（本生成器不使用，保留 modifier 介面）"

    p_size = itf.new_panel("① 尺寸 Size")
    p_grid = itf.new_panel("② 網格 Grid")
    p_hollow = itf.new_panel("③ 空心 Hollow")
    p_rand = itf.new_panel("④ 實例 Instances")
    p_out = itf.new_panel("⑤ 輸出 Output")

    def sock(nm, typ, default=None, panel=None, desc="", minv=None, maxv=None,
             subtype=None):
        s = itf.new_socket(nm, in_out="INPUT", socket_type=typ, parent=panel)
        if default is not None:
            s.default_value = default
        if desc:
            s.description = desc
        if minv is not None:
            s.min_value = minv
        if maxv is not None:
            s.max_value = maxv
        if subtype is not None:
            s.subtype = subtype
        return s

    sock("Size XYZ", "NodeSocketVector", (1.0, 1.0, 1.0), p_size, minv=-100.0,
         maxv=100.0, subtype="TRANSLATION",
         desc="盒的尺寸；非整數的軸會被挖穿（小數 → +方向开口，負值 → -方向开口）")
    sock("Scale Factor", "NodeSocketFloat", 1.0, p_size, minv=0.0, maxv=100.0,
         subtype="FACTOR", desc="整體倍率，乘上 Size XYZ")
    sock("Vertices Per Side", "NodeSocketInt", 2, p_grid, minv=2, maxv=16,
         desc="立方體每邊頂點數（2 = 基本盒；4.5 要求每邊 ≥2，1 會退化成單點）；"
              "3 → 3×3×3 = 27 個實例點")
    sock("Subdivide", "NodeSocketInt", 0, p_grid, minv=0, maxv=6,
         desc="細分層數（配 Corner Mode=Subdivide 的圓角近似）")
    sock("Hollow", "NodeSocketBool", False, p_hollow,
         desc="開啟空心：沿开口軸挖穿面（保留邊線框架）")
    sock("Wall Thickness", "NodeSocketFloat", 0.1, p_hollow, minv=0.0, maxv=100.0,
         subtype="DISTANCE", desc="壁厚：内塞平面尺寸 = |尺寸| - 2×壁厚")
    sock("Fill Mode", "NodeSocketInt", 0, p_hollow, minv=0, maxv=len(FILL_NAMES) - 1,
         desc=_enum(FILL_NAMES) + "\nNone 開放 / Plug 塞平面（僅 Z 轴开口側，4.5 限制）/ Cube 實心")
    sock("Shrink Faces", "NodeSocketBool", False, p_hollow,
         desc="把保留的面往盒中心縮，收口成 chevron 磚")
    sock("Shrink Scale", "NodeSocketFloat", 0.5, p_hollow, minv=0.0, maxv=1.0,
         subtype="FACTOR", desc="收縮比例：0 = 收到中心，1 = 不縮")
    sock("Corner Mode", "NodeSocketInt", 0, p_hollow, minv=0,
         maxv=len(CORNER_NAMES) - 1,
         desc=_enum(CORNER_NAMES) + "\n4.5 無 Bevel 節點：Subdivide + Shade Smooth 近似圓角")
    sock("Use Instances", "NodeSocketBool", False, p_rand,
         desc="True = 把盒實例化到網格頂點（每邊頂點數決定實例量）")
    sock("Jitter", "NodeSocketFloat", 0.0, p_rand, minv=0.0, maxv=100.0,
         subtype="DISTANCE", desc="每實例隨機位移半徑")
    sock("Rotation Range", "NodeSocketFloat", 0.0, p_rand, minv=0.0, maxv=6.283185,
         desc="每實例隨機旋轉幅度（弧度）")
    sock("Scale Random", "NodeSocketFloat", 0.0, p_rand, minv=0.0, maxv=2.0,
         subtype="FACTOR", desc="每實例隨機大小幅度（1 = ±100%）")
    sock("Seed", "NodeSocketInt", 0, p_rand, minv=0, maxv=9999, desc="隨機種子")
    sock("Realize Instances", "NodeSocketBool", True, p_out,
         desc="True = 展開實例為真實 mesh（Use Instances=False 時無作用）")
    sock("Store Attributes", "NodeSocketBool", False, p_out,
         desc="存 %s/%s/%s/%s 於 INSTANCE 域（Realize 後轉 point 域）"
              % (ATTR_INDEX, ATTR_SEED, ATTR_RANDOM, ATTR_SCALE))
    sock("Shade Smooth", "NodeSocketBool", False, p_out, desc="平滑着色")
    sock("Material", "NodeSocketMaterial", None, p_out, desc="指定材質槽")

    geo_out = itf.new_socket("Geometry", in_out="OUTPUT",
                             socket_type="NodeSocketGeometry", parent=p_out)
    geo_out.description = "生成的盒（或盒實例）"

    # 介面值走 NodeGroupInput/NodeGroupOutput（items_tree socket 不可直接連結）
    gi = _node(ng, "NodeGroupInput", (-1960, 320), label="inputs", width=200)
    go = _node(ng, "NodeGroupOutput", (2260, 320), label="output", width=160)

    def S(nm):
        return _out(gi, nm)

    # ── 幀框分組（明確節點清單，避免座標窗口重疊）
    f_size, f_grid, f_hollow, f_plug, f_inst, f_out = [], [], [], [], [], []

    def reg(group, sock_or_node):
        group.append(sock_or_node)
        return sock_or_node

    # ── ① 尺寸：dims = Size×Scale；offset = dims - floor(|dims|)（开口方向）
    dims = reg(f_size, _vm(ng, "MULTIPLY", (-1700, 240), S("Size XYZ"),
                           S("Scale Factor"), label="dims"))
    dims_abs = reg(f_size, _vm(ng, "ABSOLUTE", (-1540, 240), dims, label="|dims|"))
    snapped = reg(f_size, _vm(ng, "FLOOR", (-1380, 240), dims_abs, label="floor"))
    offset = reg(f_size, _vm(ng, "SUBTRACT", (-1220, 240), dims, snapped,
                             label="offset"))

    # ── ② 外層盒
    verts = S("Vertices Per Side")
    cube = _node(ng, "GeometryNodeMeshCube", (-1060, 240), label="cube", width=150)
    _feed(ng, _in(cube, "Size", "VECTOR"), dims)
    for axis in AXIS_NAMES:
        _link(ng, verts, _in(cube, "Vertices " + axis, "INT"))
    outer = reg(f_grid, _out(cube, "Mesh", "GEOMETRY"))

    # ── ③ 空心：内塞尺寸 + 法線點積判定 + 收縮 + 挖穿
    wall_x2 = reg(f_hollow, _math(ng, "MULTIPLY", (-1600, -60), S("Wall Thickness"),
                                  2.0, label="2×wall"))
    inner = reg(f_hollow, _vm(ng, "SUBTRACT", (-1440, -60), dims_abs, wall_x2,
                              label="inner"))
    isep = _separate(ng, inner, (-1280, -60), label="inner xyz")
    f_hollow.extend(isep)

    normal = reg(f_hollow, _node(ng, "GeometryNodeInputNormal", (-1280, -260),
                                 label="normal", width=140).outputs["Normal"])
    dot = reg(f_hollow, _vm(ng, "DOT_PRODUCT", (-1100, -260), offset, normal,
                            label="n·offset"))
    cut = reg(f_hollow, _cmp(ng, "GREATER_THAN", (-940, -260), dot, EPS,
                             label="cut faces"))
    keep = reg(f_hollow, _b(ng, "NOT", (-800, -260), cut, label="keep faces"))

    scaled = _node(ng, "GeometryNodeScaleElements", (-900, 60), label="shrink",
                   width=170, domain="FACE")
    _feed(ng, _in(scaled, "Geometry", "GEOMETRY"), outer)
    _feed(ng, _in(scaled, "Selection", "BOOLEAN"), keep)
    _feed(ng, _in(scaled, "Scale", "VALUE"), S("Shrink Scale"))
    shrink_gate = reg(f_hollow, _switch(ng, (-720, 60), S("Shrink Faces"), outer,
                                        _out(scaled, "Geometry", "GEOMETRY"),
                                        label="shrink on/off"))

    delete = _node(ng, "GeometryNodeDeleteGeometry", (-560, 60), label="hollow cut",
                   width=170, domain="FACE", mode="ONLY_FACE")
    _feed(ng, _in(delete, "Geometry", "GEOMETRY"), shrink_gate)
    _feed(ng, _in(delete, "Selection", "BOOLEAN"), cut)
    hollowed = reg(f_hollow, _out(delete, "Geometry", "GEOMETRY"))

    # ── ③ Plug：内塞平面（只塞 Z 轴开口側；X/Y 开口請用 Fill=Cube 或 Hollow=False）
    oz = reg(f_plug, _separate(ng, offset, (-1100, -440), label="offset z")[2])
    z_open = reg(f_plug, _b(ng, "OR", (-820, -440),
                             _cmp(ng, "GREATER_THAN", (-960, -400), oz, EPS,
                                  label="z open +"),
                             _cmp(ng, "LESS_THAN", (-960, -480), oz, -EPS,
                                  label="z open -"),
                             label="z open"))
    grid = _node(ng, "GeometryNodeMeshGrid", (-900, -560), label="plug grid", width=150)
    _feed(ng, _in(grid, "Size X", "VALUE"), isep[0])
    _feed(ng, _in(grid, "Size Y", "VALUE"), isep[1])
    _feed(ng, _in(grid, "Vertices X", "INT"), verts)
    _feed(ng, _in(grid, "Vertices Y", "INT"), verts)
    plug_mesh = reg(f_plug, _out(grid, "Mesh", "GEOMETRY"))
    zsign = reg(f_plug, _math(ng, "SIGN", (-860, -660), oz, label="sign z"))
    ztrans = reg(f_plug, _math(ng, "MULTIPLY", (-740, -660), zsign,
                               _math(ng, "MULTIPLY", (-880, -740), isep[2], 0.5,
                                     label="inner z/2"), label="plug z"))
    plug_tr = _node(ng, "GeometryNodeTransform", (-620, -560), label="plug move",
                    width=150)
    _feed(ng, _in(plug_tr, "Geometry", "GEOMETRY"), plug_mesh)
    _feed(ng, _in(plug_tr, "Translation", "VECTOR"), _xyz(ng, 0.0, 0.0, ztrans,
                                                           (-740, -820), label="plug xyz"))
    empty = _node(ng, "GeometryNodeDeleteGeometry", (-1900, -560), label="empty",
                  width=140, domain="POINT", mode="ALL")
    _feed(ng, _in(empty, "Geometry", "GEOMETRY"), _out(gi, "Geometry"))
    plug_gate = reg(f_plug, _switch(ng, (-460, -560), z_open,
                                    _out(empty, "Geometry", "GEOMETRY"),
                                    _out(plug_tr, "Geometry", "GEOMETRY"),
                                    label="plug if z open"))

    # ── Fill Mode / Hollow 門閂
    fill_join = _node(ng, "GeometryNodeJoinGeometry", (-420, 200), label="fill join",
                      width=150)
    _feed(ng, _in(fill_join, "Geometry", "GEOMETRY"), hollowed)
    # 4.5：JoinGeometry 的 Geometry 輸入可接受多條連結
    _link(ng, plug_gate, _in(fill_join, "Geometry", "GEOMETRY"))
    fill_join_out = _out(fill_join, "Geometry", "GEOMETRY")
    fill = _index_switch(ng, (-280, 320), "GEOMETRY", S("Fill Mode"),
                         [hollowed, fill_join_out, outer], label="fill mode")
    hollow_gate = _switch(ng, (-140, 320), S("Hollow"), outer, fill,
                          label="hollow on/off")

    # ── Corner：Subdivide 圓角近似（4.5 無 Bevel）
    corner_gate = _switch(ng, (-140, 520),
                          _cmp(ng, "GREATER_THAN", (-260, 560), S("Corner Mode"),
                               0.0, data_type="INT", label="corner on"),
                          0, S("Subdivide"), input_type="INT", label="corner gate")
    subdiv = _node(ng, "GeometryNodeSubdivideMesh", (-20, 320), label="subdivide",
                   width=150)
    _feed(ng, _in(subdiv, "Mesh", "GEOMETRY"), hollow_gate)
    _feed(ng, _in(subdiv, "Level", "INT"), corner_gate)
    mesh = _out(subdiv, "Mesh", "GEOMETRY")

    # ── ④ 實例化
    to_pts = _node(ng, "GeometryNodeMeshToPoints", (220, 320), label="to points",
                   width=150)
    _feed(ng, _in(to_pts, "Mesh", "GEOMETRY"), mesh)
    # MeshToPoints 無 Index 輸出 → GeometryNodeInputIndex 取點序號作隨機 ID
    index = _node(ng, "GeometryNodeInputIndex", (340, 420), label="index",
                  width=120).outputs["Index"]
    seed = S("Seed")
    idmix = _math(ng, "ADD", (240, -300), index, seed, label="id+seed")

    rot_rand = _rand(ng, (420, -360), "FLOAT_VECTOR",
                     _math(ng, "MULTIPLY", (320, -420), S("Rotation Range"), -0.5,
                           label="-r/2"),
                     _math(ng, "MULTIPLY", (320, -480), S("Rotation Range"), 0.5,
                           label="+r/2"), idmix, label="rot rand")
    jit_rand = _rand(ng, (560, -360), "FLOAT_VECTOR",
                     _math(ng, "MULTIPLY", (460, -420), S("Jitter"), -1.0, label="-j"),
                     _math(ng, "MULTIPLY", (460, -480), S("Jitter"), 1.0, label="+j"),
                     idmix, label="jitter rand")
    scl_rand = _rand(ng, (700, -360), "FLOAT_VECTOR",
                     _math(ng, "SUBTRACT", (600, -420), 1.0, S("Scale Random"),
                           label="1-r"),
                     _math(ng, "ADD", (600, -480), 1.0, S("Scale Random"), label="1+r"),
                     idmix, label="scale rand")

    # 4.5：InstanceOnPoints 無 Translation 輸入 → Jitter 走 SetPosition
    set_pos = _node(ng, "GeometryNodeSetPosition", (420, 320), label="jitter",
                    width=160)
    _feed(ng, _in(set_pos, "Geometry", "GEOMETRY"), _out(to_pts, "Points", "GEOMETRY"))
    _feed(ng, _in(set_pos, "Offset", "VECTOR"), jit_rand)
    points = _out(set_pos, "Geometry", "GEOMETRY")

    inst = _node(ng, "GeometryNodeInstanceOnPoints", (620, 320), label="instances",
                 width=180)
    _feed(ng, _in(inst, "Points", "GEOMETRY"), points)
    _feed(ng, _in(inst, "Instance", "GEOMETRY"), mesh)
    _link(ng, rot_rand, _in(inst, "Rotation"))
    _feed(ng, _in(inst, "Scale", "VECTOR"), scl_rand)

    # Store Attributes（INSTANCE 域）
    stored = _out(inst, "Instances", "GEOMETRY")
    g1 = _store(ng, stored, ATTR_INDEX, index, (760, 160), label="store idx",
                data_type="INT")
    g2 = _store(ng, g1, ATTR_SEED, seed, (900, 100), label="store seed",
                data_type="INT")
    r_f = _rand(ng, (760, -520), "FLOAT", 0.0, 1.0, idmix, label="rand f")
    g3 = _store(ng, g2, ATTR_RANDOM, r_f, (1040, 40), label="store rand",
                data_type="FLOAT")
    g4 = _store(ng, g3, ATTR_SCALE, scl_rand, (1180, -20), label="store scale")
    store_gate = _switch(ng, (1300, 120), S("Store Attributes"), stored, g4,
                         label="store on/off")

    chose = _switch(ng, (1440, 320), S("Use Instances"), mesh, store_gate,
                    label="use instances")
    realize = _node(ng, "GeometryNodeRealizeInstances", (1600, 320), label="realize",
                    width=170)
    _feed(ng, _in(realize, "Geometry", "GEOMETRY"), chose)
    realize_gate = _switch(ng, (1760, 320), S("Realize Instances"), chose,
                           _out(realize, "Geometry", "GEOMETRY"),
                           label="realize on/off")

    # ── ⑤ 輸出
    with_mat = _node(ng, "GeometryNodeSetMaterial", (1920, 320), label="material",
                     width=170)
    _feed(ng, _in(with_mat, "Geometry", "GEOMETRY"), realize_gate)
    _feed(ng, _in(with_mat, "Material"), S("Material"))
    shaded = _node(ng, "GeometryNodeSetShadeSmooth", (2080, 320), label="shade smooth",
                   width=170, domain="FACE")
    _feed(ng, _in(shaded, "Geometry", "GEOMETRY"), _out(with_mat, "Geometry", "GEOMETRY"))
    _feed(ng, _in(shaded, "Shade Smooth", "BOOLEAN"), S("Shade Smooth"))
    _link(ng, _out(shaded, "Geometry", "GEOMETRY"), _in(go, "Geometry"))

    # 幀框：分區上色（socket 與 node 皆可，_frame 會去重）
    _frame(ng, "① 尺寸 Size", (0.30, 0.55, 0.90), f_size)
    _frame(ng, "② 網格 Grid", (0.35, 0.80, 0.35), f_grid + [cube])
    _frame(ng, "③ 空心 Hollow", (0.85, 0.55, 0.25), f_hollow + [scaled, delete])
    _frame(ng, "③ Plug 塞面", (0.70, 0.45, 0.25), f_plug + [grid, plug_tr, empty])
    f_inst += [to_pts, set_pos, index.node, idmix.node, rot_rand.node,
               jit_rand.node, scl_rand.node, inst, stored.node, g1.node,
               g2.node, r_f.node, g3.node, g4.node, store_gate.node]
    _frame(ng, "④ 實例 Instances", (0.80, 0.35, 0.55), f_inst)
    f_out += [fill_join, fill.node, hollow_gate.node, corner_gate.node, subdiv,
              chose.node, realize, realize_gate.node, with_mat, shaded, go]
    _frame(ng, "⑤ 輸出 Output", (0.55, 0.35, 0.80), f_out)

    assert len(ng.nodes) > 30, "too few nodes"
    assert len(ng.links) > 40, "too few links"
    return ng


# ---------------------------------------------------------------- interface map
def inputs_summary(ng=None):
    ng = ng or bpy.data.node_groups.get(NAME)
    if ng is None:
        return []
    rows = []
    for item in ng.interface.items_tree:
        if item.item_type != "SOCKET" or item.in_out != "INPUT":
            continue
        panel = ""
        p = item.parent
        while p is not None and p.item_type == "PANEL":
            panel = p.name
            p = p.parent
        default = getattr(item, "default_value", None)
        if isinstance(default, float):
            default = round(default, 6)
        elif hasattr(default, "__len__") and not isinstance(default, str):
            default = tuple(round(v, 6) for v in default)
        rows.append({
            "name": item.name,
            "type": item.socket_type,
            "default": default,
            "min": getattr(item, "min_value", None),
            "max": getattr(item, "max_value", None),
            "panel": panel,
            "description": getattr(item, "description", ""),
        })
    return rows


def main(argv=None):
    argv = argv or []
    ng = build()
    print("GN_BOX_OK %s nodes=%d links=%d inputs=%d" %
          (ng.name, len(ng.nodes), len(ng.links), len(inputs_summary(ng))))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv[3:] if len(sys.argv) > 3 else sys.argv[1:]))
