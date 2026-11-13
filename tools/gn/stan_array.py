"""Stan Array — a general-purpose array modifier (Geometry Nodes).

一個 Array 節點群組，把「排列方式」與「間距算法」拆開：

  Mode           Linear / Grid / Radial / Curve / Mesh / Collection
  Spacing        Step（固定間距）/ Gap（貼齊留縫）/ Fit（給總長均分）
  Unit           Host 自身幾何，或 Collection（可隨機挑款）
  Orientation    Natural / Forward / Up
  Variation      隨機位移／旋轉／縮放、鏡像交替、沿方向漸變

Collection 模式會讀取 Point Collection 裡每個物件的「原點 + 旋轉」，
把單元放在那裡（locator 物件本身不顯示）；Mesh 模式可放在頂點／邊中點／
面中心，或隨機灑在表面上。

節點圖分區：
  ① 單位與尺寸 → ② 間距 → ③ 排列（六個分支）→ ④ 方向
  → ⑤ 實例化 → ⑥ 變化 → ⑦ 輸出

純 bpy；由 tools/gn/build_asset.py 在無頭 Blender 裡呼叫。
"""

import math

import bpy

NAME = "Stan Array"
DESCRIPTION = (
    "通用陣列：線性／網格（XY・Hex・Triangle）／環狀／曲線／Mesh 頂點邊面／"
    "Collection 物件軸心；間距支援固定、貼齊留縫、總長均分；可隨機與鏡像。"
)

C_UNIT = (0.20, 0.28, 0.36)
C_SPACE = (0.26, 0.30, 0.36)
C_LAYOUT = (0.22, 0.30, 0.22)
C_RADIAL = (0.30, 0.26, 0.34)
C_CURVE = (0.24, 0.30, 0.34)
C_MESH = (0.34, 0.28, 0.20)
C_POINT = (0.30, 0.22, 0.28)
C_ORIENT = (0.34, 0.30, 0.18)
C_INST = (0.22, 0.30, 0.30)
C_VARY = (0.32, 0.24, 0.24)
C_OUT = (0.24, 0.32, 0.24)

MODE_NAMES = ["Linear", "Grid", "Radial", "Curve", "Mesh", "Collection"]
GRID_NAMES = ["XY", "Hex", "Triangle"]
SPACING_NAMES = ["Step", "Gap", "Fit"]
ALIGN_NAMES = ["Natural", "Forward", "Up"]
MESH_NAMES = ["Vertices", "Edges", "Faces", "Surface"]

ATTR_ROT = "arr_rot"
ATTR_FWD = "arr_fwd"
ATTR_NRM = "arr_nrm"


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


def _link(ng, a, b):
    ng.links.new(a, b)


def _math(ng, op, loc, a=None, b=None, c=None, label=None):
    n = _node(ng, "ShaderNodeMath", loc, label=label, width=160, operation=op)
    for i, value in enumerate((a, b, c)):
        if value is None:
            continue
        sock = n.inputs[i]
        if isinstance(value, bpy.types.NodeSocket):
            _link(ng, value, sock)
        else:
            sock.default_value = float(value)
    return n.outputs[0]


def _vmath(ng, op, loc, a=None, b=None, c=None, label=None):
    n = _node(ng, "ShaderNodeVectorMath", loc, label=label, width=170, operation=op)
    for i, value in enumerate((a, b, c)):
        if value is None:
            continue
        sock = n.inputs[i]
        if isinstance(value, bpy.types.NodeSocket):
            _link(ng, value, sock)
        else:
            sock.default_value = value
    if op in ("DOT_PRODUCT", "LENGTH", "DISTANCE"):
        return n.outputs["Value"]
    return n.outputs["Vector"]


def _scale_vec(ng, loc, vec, factor, label=None):
    n = _node(ng, "ShaderNodeVectorMath", loc, label=label, width=170, operation="SCALE")
    _link(ng, vec, _in(n, "Vector"))
    _link(ng, factor, _in(n, "Scale"))
    return _out(n, "Vector")


def _xyz(ng, loc, x=None, y=None, z=None, label=None):
    n = _node(ng, "ShaderNodeCombineXYZ", loc, label=label, width=150)
    for axis, value in (("X", x), ("Y", y), ("Z", z)):
        if value is None:
            continue
        sock = _in(n, axis)
        if isinstance(value, bpy.types.NodeSocket):
            _link(ng, value, sock)
        else:
            sock.default_value = float(value)
    return _out(n, "Vector")


def _separate(ng, loc, vec, label=None):
    n = _node(ng, "ShaderNodeSeparateXYZ", loc, label=label, width=150)
    _link(ng, vec, _in(n, "Vector"))
    return n


def _index_switch(ng, loc, data_type, index, values, label=None, width=200):
    n = _node(ng, "GeometryNodeIndexSwitch", loc, label=label, width=width,
              data_type=data_type)
    while len(n.index_switch_items) < len(values):
        n.index_switch_items.new()
    _link(ng, index, n.inputs["Index"])
    for i, value in enumerate(values):
        sock = n.inputs[i + 1]
        if isinstance(value, bpy.types.NodeSocket):
            _link(ng, value, sock)
        else:
            sock.default_value = value
    return n.outputs[0]


def _switch(ng, loc, input_type, cond, false, true, label=None):
    n = _node(ng, "GeometryNodeSwitch", loc, label=label, width=170,
              input_type=input_type)
    _link(ng, cond, _in(n, "Switch"))
    for name, value in (("False", false), ("True", true)):
        sock = _in(n, name)
        if isinstance(value, bpy.types.NodeSocket):
            _link(ng, value, sock)
        else:
            sock.default_value = value
    return _out(n, "Output")


def _compare(ng, loc, op, a, b, data_type="FLOAT", label=None):
    n = _node(ng, "FunctionNodeCompare", loc, label=label, width=160,
              data_type=data_type, operation=op)
    for name, value in (("A", a), ("B", b)):
        sock = _in(n, name)
        if isinstance(value, bpy.types.NodeSocket):
            _link(ng, value, sock)
        elif sock.type == "INT":
            sock.default_value = int(value)
        else:
            sock.default_value = float(value)
    return n.outputs["Result"]


def _store(ng, geom, name, value, loc, label=None):
    n = _node(ng, "GeometryNodeStoreNamedAttribute", loc, label=label, width=180,
              data_type="FLOAT_VECTOR", domain="POINT")
    _in(n, "Name").default_value = name
    _link(ng, geom, _in(n, "Geometry"))
    _link(ng, value, _in(n, "Value"))
    return n.outputs["Geometry"]


def _store_orientation(ng, geom, rot, fwd, nrm, loc):
    """把每點的 基礎旋轉 / 前方 / 上方 存成屬性，選完分支後再讀取。"""
    g = _store(ng, geom, ATTR_ROT, rot, (loc[0], loc[1] + 240), label="rot")
    g = _store(ng, g, ATTR_FWD, fwd, (loc[0] + 200, loc[1] + 120), label="fwd")
    g = _store(ng, g, ATTR_NRM, nrm, (loc[0] + 400, loc[1]), label="nrm")
    return g


def _frame(ng, label, color, nodes, label_size=26):
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
    return len(ng.nodes)


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
    geo_in.description = "主機物件的幾何（Unit = Host 時就是被複製的單元）"

    p_main = itf.new_panel("① 排列 Arrangement")
    p_main.description = "Mode 0 Linear｜1 Grid｜2 Radial｜3 Curve｜4 Mesh｜5 Collection"
    p_radial = itf.new_panel("② 環狀 Radial")
    p_src = itf.new_panel("③ 曲線與網格 Curve & Mesh")
    p_orient = itf.new_panel("④ 方向 Orientation")
    p_vary = itf.new_panel("⑤ 變化 Variation")
    p_out = itf.new_panel("⑥ 輸出 Output")

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

    sock("Mode", "NodeSocketInt", 0, p_main, minv=0, maxv=5,
         desc="0 Linear 線性 ｜ 1 Grid 網格 ｜ 2 Radial 環狀 ｜ "
              "3 Curve 曲線 ｜ 4 Mesh 頂點/邊/面/表面 ｜ 5 Collection 物件軸心")
    sock("Unit From Collection", "NodeSocketBool", False, p_main,
         desc="False = 複製主物件自己的幾何；True = 從 Collection 取單元（可隨機挑款）")
    sock("Collection", "NodeSocketCollection", None, p_main,
         desc="Unit From Collection = True 時的單元來源")
    sock("Collection Count", "NodeSocketInt", 1, p_main, minv=1, maxv=999,
         desc="Collection 裡的 mesh 物件數，用於隨機挑款（CLI 會自動填）")
    sock("Direction", "NodeSocketVector", (1.0, 0.0, 0.0), p_main,
         desc="Linear 的排列方向（物件座標系；長度不影響間距）")
    sock("Count", "NodeSocketInt", 5, p_main, minv=1, maxv=512,
         desc="Linear / Radial / Curve(Fit) 的數量")
    sock("Count X", "NodeSocketInt", 5, p_main, minv=1, maxv=512, desc="Grid 的 X 數量")
    sock("Count Y", "NodeSocketInt", 5, p_main, minv=1, maxv=512, desc="Grid 的 Y 數量")
    sock("Grid Type", "NodeSocketInt", 0, p_main, minv=0, maxv=2,
         desc="0 XY 方格 ｜ 1 Hex 蜂巢 ｜ 2 Triangle 三角晶格")
    sock("Cell Size", "NodeSocketFloat", 0.25, p_main, minv=0.0001,
         subtype="DISTANCE",
         desc="Hex 的六角外徑（頂點到頂點）；Flat Top 時整個晶格轉 90°")
    sock("Flat Top", "NodeSocketBool", False, p_main,
         desc="Hex 的平頂方向（False = pointy-top，True = flat-top）")
    sock("Spacing Mode", "NodeSocketInt", 0, p_main, minv=0, maxv=2,
         desc="0 Step 固定間距 ｜ 1 Gap 依尺寸貼齊留縫 ｜ 2 Fit 給總長均分"
              "（Hex / Triangle 用自己的 Cell Size / Step，不受此項影響）")
    sock("Step", "NodeSocketFloat", 1.0, p_main, minv=0.0, subtype="DISTANCE",
         desc="Step 模式的中心距")
    sock("Gap", "NodeSocketFloat", 0.1, p_main, minv=0.0, subtype="DISTANCE",
         desc="Gap 模式的單元間縫隙")
    sock("Length", "NodeSocketFloat", 5.0, p_main, minv=0.0, subtype="DISTANCE",
         desc="Fit 模式：Linear 的總長、Grid 的 X 總長（外緣對齊）")
    sock("Length Y", "NodeSocketFloat", 5.0, p_main, minv=0.0, subtype="DISTANCE",
         desc="Fit 模式：Grid 的 Y 總長")
    sock("Radius", "NodeSocketFloat", 1.0, p_radial, minv=0.0, subtype="DISTANCE",
         desc="Radial 的半徑")
    sock("Arc", "NodeSocketFloat", 360.0, p_radial, minv=0.1, maxv=360.0,
         desc="Radial 的角度範圍（度）；360 = 整圈")
    sock("Start Angle", "NodeSocketFloat", 0.0, p_radial,
         desc="Radial 的起始角度（度）")
    sock("Curve", "NodeSocketObject", None, p_src, desc="Curve 模式的曲線物件")
    sock("Surface", "NodeSocketObject", None, p_src,
         desc="Mesh 模式的表面物件；留空 = 使用主物件自己的幾何")
    sock("Mesh Mode", "NodeSocketInt", 0, p_src, minv=0, maxv=3,
         desc="0 頂點 ｜ 1 邊中點 ｜ 2 面中心 ｜ 3 表面隨機（Density）")
    sock("Density", "NodeSocketFloat", 10.0, p_src, minv=0.0,
         desc="Mesh Mode = Surface 時的每平方公尺點數")
    sock("Point Collection", "NodeSocketCollection", None, p_src,
         desc="Collection 模式：讀每個物件的原點與旋轉（物件本身不會顯示）")
    sock("Align", "NodeSocketInt", 0, p_orient, minv=0, maxv=2,
         desc="0 Natural 各模式預設 ｜ 1 Forward 前方軸對齊 ｜ 2 Up 上方軸對齊")
    sock("Forward Axis", "NodeSocketInt", 1, p_orient, minv=0, maxv=2,
         desc="0 X ｜ 1 Y（Blender 慣例）｜ 2 Z")
    sock("Up Axis", "NodeSocketInt", 2, p_orient, minv=0, maxv=2,
         desc="0 X ｜ 1 Y ｜ 2 Z")
    sock("Random Offset", "NodeSocketVector", (0.0, 0.0, 0.0), p_vary,
         desc="每份的隨機位移幅度（公尺）")
    sock("Random Rotate", "NodeSocketVector", (0.0, 0.0, 0.0), p_vary,
         desc="每份的隨機旋轉幅度（度，XYZ）")
    sock("Unit Scale", "NodeSocketFloat", 1.0, p_vary, minv=0.0,
         desc="所有單元的整體大小倍率（1 = 原始大小）")
    sock("Random Scale", "NodeSocketFloat", 0.0, p_vary, minv=0.0, maxv=1.0,
         subtype="FACTOR", desc="每份的隨機大小幅度（± 比例）")
    sock("Seed", "NodeSocketInt", 0, p_vary)
    sock("Mirror", "NodeSocketBool", False, p_vary,
         desc="每隔一份鏡像（沿 Mirror Axis）")
    sock("Mirror Axis", "NodeSocketInt", 0, p_vary, minv=0, maxv=2,
         desc="0 X ｜ 1 Y ｜ 2 Z")
    sock("Gradient Scale", "NodeSocketFloat", 1.0, p_vary, minv=0.0,
         desc="沿排列順序從 1 漸變到這個倍率")
    sock("Gradient Rotate", "NodeSocketFloat", 0.0, p_vary,
         desc="沿排列順序總共額外旋轉幾度（繞 Z）")
    sock("Realize", "NodeSocketBool", False, p_out,
         desc="True = 輸出實際 mesh（布林、匯出用）；False = 輸出實例（較快）")

    geo_out = itf.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    geo_out.description = "陣列結果"

    # ================================================================ 節點圖
    gi = _node(ng, "NodeGroupInput", (-3600, 0), label="參數", width=220)
    go = _node(ng, "NodeGroupOutput", (2700, 0), label="輸出", width=150)

    # ------------------------------------------------------------ ① 單位與尺寸
    start = _section(ng)
    ci_units = _node(ng, "GeometryNodeCollectionInfo", (-3300, 900),
                     label="Unit Collection", width=180)
    _in(ci_units, "Separate Children").default_value = True
    _in(ci_units, "Reset Children").default_value = True
    _link(ng, _out(gi, "Collection"), _in(ci_units, "Collection"))

    units_real = _node(ng, "GeometryNodeRealizeInstances", (-3100, 900),
                       label="Realize（量尺寸）", width=180)
    _link(ng, _out(ci_units, "Instances"), _in(units_real, "Geometry"))

    unit_bb = _node(ng, "GeometryNodeBoundBox", (-2900, 900), label="Unit BBox", width=160)
    _link(ng, _out(units_real, "Geometry"), _in(unit_bb, "Geometry"))

    host_bb = _node(ng, "GeometryNodeBoundBox", (-2900, 1150), label="Host BBox", width=160)
    _link(ng, _out(gi, "Geometry"), _in(host_bb, "Geometry"))

    size_coll = _vmath(ng, "SUBTRACT", (-2700, 900), _out(unit_bb, "Max"),
                       _out(unit_bb, "Min"), label="集合尺寸")
    size_host = _vmath(ng, "SUBTRACT", (-2700, 1150), _out(host_bb, "Max"),
                       _out(host_bb, "Min"), label="主體尺寸")
    size = _switch(ng, (-2500, 1000), "VECTOR", _out(gi, "Unit From Collection"),
                   size_host, size_coll, label="單元尺寸")
    unit_geo = _switch(ng, (-2500, 700), "GEOMETRY", _out(gi, "Unit From Collection"),
                       _out(gi, "Geometry"), _out(ci_units, "Instances"),
                       label="單元幾何")
    _frame(ng, "① 單位與尺寸　Unit / BBox", C_UNIT, list(ng.nodes)[start:])

    # ------------------------------------------------------------ ② 間距數值
    start = _section(ng)
    size_sep = _separate(ng, (-3200, 200), size, label="size XYZ")
    direction_n = _vmath(ng, "NORMALIZE", (-3200, 450), _out(gi, "Direction"),
                         label="方向（單位化）")
    size_abs = _vmath(ng, "ABSOLUTE", (-3200, 300), size, label="|尺寸|")
    dir_abs = _vmath(ng, "ABSOLUTE", (-3200, 100), direction_n, label="|方向|")
    extent = _vmath(ng, "DOT_PRODUCT", (-3000, 300), size_abs, dir_abs,
                    label="沿方向的投影長")

    one = _math(ng, "MAXIMUM", (-3200, -100), _out(gi, "Count"), 1.0, label="max(N,1)")
    count_m1 = _math(ng, "MAXIMUM", (-3000, -100),
                     _math(ng, "SUBTRACT", (-3200, -100), one, 1.0, label="N − 1"),
                     1.0, label="max(N−1,1)")
    fit_step = _math(ng, "MAXIMUM", (-2500, 0),
                     _math(ng, "DIVIDE", (-2700, 0),
                           _math(ng, "SUBTRACT", (-2900, 0), _out(gi, "Length"),
                                 extent, label="總長 − 單元"),
                           count_m1, label="Fit 間距"),
                     0.0, label="≥ 0")
    gap_step = _math(ng, "ADD", (-2700, 200), extent, _out(gi, "Gap"), label="尺寸 + 縫")
    step_sel = _index_switch(ng, (-2300, 100), "FLOAT", _out(gi, "Spacing Mode"),
                             [_out(gi, "Step"), gap_step, fit_step],
                             label="間距模式")
    step_vec = _scale_vec(ng, (-2100, 250), direction_n, step_sel, label="方向 × 間距")
    _frame(ng, "② 間距　Step / Gap / Fit", C_SPACE,
           list(ng.nodes)[start:] + [size_sep])

    # ------------------------------------------------------------ ③ 排列
    # Linear ---------------------------------------------------------------
    start = _section(ng)
    is_fit = _compare(ng, (-2350, 350), "EQUAL", _out(gi, "Spacing Mode"), 2,
                      data_type="INT", label="Fit?")
    fit_shift = _scale_vec(ng, (-2150, 450), direction_n,
                           _math(ng, "MULTIPLY", (-2350, 450), extent, 0.5,
                                 label="單元一半"), label="Fit 起點")
    lin_start = _switch(ng, (-1950, 450), "VECTOR", is_fit,
                        _xyz(ng, (-2150, 600)), fit_shift, label="起點")
    line = _node(ng, "GeometryNodeMeshLine", (-1750, 600), label="Mesh Line", width=170)
    _link(ng, _out(gi, "Count"), _in(line, "Count"))
    _link(ng, step_vec, _in(line, "Offset"))
    _link(ng, lin_start, _in(line, "Start Location"))
    lin_pts = _node(ng, "GeometryNodeMeshToPoints", (-1550, 600), label="Points", width=150)
    lin_pts.mode = "VERTICES"
    _link(ng, _out(line, "Mesh"), _in(lin_pts, "Mesh"))
    lin_geom = _store_orientation(ng, _out(lin_pts, "Points"),
                                  _xyz(ng, (-1350, 750)),
                                  direction_n,
                                  _xyz(ng, (-1350, 480), z=1.0),
                                  (-1350, 700))
    _frame(ng, "③-A Linear　固定方向", C_LAYOUT, list(ng.nodes)[start:])

    # Grid -----------------------------------------------------------------
    start = _section(ng)
    gx_n = _math(ng, "MAXIMUM", (-2500, -400), _out(gi, "Count X"), 1.0)
    gy_n = _math(ng, "MAXIMUM", (-2500, -600), _out(gi, "Count Y"), 1.0)
    gx_m1 = _math(ng, "MAXIMUM", (-2350, -400),
                  _math(ng, "SUBTRACT", (-2500, -400), gx_n, 1.0), 1.0)
    gy_m1 = _math(ng, "MAXIMUM", (-2350, -600),
                  _math(ng, "SUBTRACT", (-2500, -600), gy_n, 1.0), 1.0)
    fit_x = _math(ng, "MAXIMUM", (-2200, -300),
                  _math(ng, "DIVIDE", (-2350, -300),
                        _math(ng, "SUBTRACT", (-2500, -300), _out(gi, "Length"),
                              size_sep.outputs["X"], label="Lx − sx"),
                        gx_m1, label="Fit X"),
                  0.0)
    fit_y = _math(ng, "MAXIMUM", (-2200, -500),
                  _math(ng, "DIVIDE", (-2350, -500),
                        _math(ng, "SUBTRACT", (-2500, -500), _out(gi, "Length Y"),
                              size_sep.outputs["Y"], label="Ly − sy"),
                        gy_m1, label="Fit Y"),
                  0.0)
    gap_x = _math(ng, "ADD", (-2200, -150), size_sep.outputs["X"],
                  _out(gi, "Gap"))
    gap_y = _math(ng, "ADD", (-2200, -700), size_sep.outputs["Y"],
                  _out(gi, "Gap"))
    step_x = _index_switch(ng, (-1900, -250), "FLOAT", _out(gi, "Spacing Mode"),
                           [_out(gi, "Step"), gap_x, fit_x], label="step X")
    step_y = _index_switch(ng, (-1900, -550), "FLOAT", _out(gi, "Spacing Mode"),
                           [_out(gi, "Step"), gap_y, fit_y], label="step Y")
    grid_fit = _compare(ng, (-2350, -800), "EQUAL", _out(gi, "Spacing Mode"), 2,
                        data_type="INT", label="Fit?")
    fit_x_half = _switch(ng, (-2200, -800), "FLOAT", grid_fit, 0.0,
                         _math(ng, "MULTIPLY", (-2350, -950), size_sep.outputs["X"], 0.5))
    fit_y_half = _switch(ng, (-2200, -950), "FLOAT", grid_fit, 0.0,
                         _math(ng, "MULTIPLY", (-2350, -1100), size_sep.outputs["Y"], 0.5))

    gidx = _node(ng, "GeometryNodeInputIndex", (-2500, -1300), label="i", width=140)
    col = _math(ng, "FLOORED_MODULO", (-2300, -1250), _out(gidx, "Index"), gx_n,
                label="col")
    row = _math(ng, "FLOOR", (-2300, -1400),
                _math(ng, "DIVIDE", (-2450, -1400), _out(gidx, "Index"), gx_n),
                label="row")
    odd_row = _math(ng, "FLOORED_MODULO", (-2150, -1550), row, 2.0, label="row 奇偶")
    odd_col = _math(ng, "FLOORED_MODULO", (-2150, -1700), col, 2.0, label="col 奇偶")

    # XY：方格
    sq_pos = _xyz(ng, (-1850, -350),
                  x=_math(ng, "ADD", (-2050, -250),
                          _math(ng, "MULTIPLY", (-2200, -250), col, step_x),
                          fit_x_half),
                  y=_math(ng, "ADD", (-2050, -500),
                          _math(ng, "MULTIPLY", (-2200, -500), row, step_y),
                          fit_y_half))

    # Hex：pointy-top / flat-top
    sqrt3 = math.sqrt(3.0)
    cell_r = _math(ng, "MULTIPLY", (-2500, -1900), _out(gi, "Cell Size"), 0.5,
                   label="R = D/2")
    p_dx = _math(ng, "MULTIPLY", (-2350, -1850), cell_r, sqrt3, label="√3·R")
    p_dy = _math(ng, "MULTIPLY", (-2350, -2000), cell_r, 1.5, label="1.5·R")
    f_dx = _math(ng, "MULTIPLY", (-2350, -2150), cell_r, 1.5)
    f_dy = _math(ng, "MULTIPLY", (-2350, -2300), cell_r, sqrt3)
    p_x = _math(ng, "ADD", (-2050, -1850),
                _math(ng, "MULTIPLY", (-2200, -1850), col, p_dx),
                _math(ng, "MULTIPLY", (-2200, -2000), odd_row,
                      _math(ng, "MULTIPLY", (-2350, -2000), p_dx, 0.5)))
    p_y = _math(ng, "MULTIPLY", (-2050, -2100), row, p_dy)
    f_x = _math(ng, "MULTIPLY", (-2050, -2250), col, f_dx)
    f_y = _math(ng, "ADD", (-2050, -2400),
                _math(ng, "MULTIPLY", (-2200, -2400), row, f_dy),
                _math(ng, "MULTIPLY", (-2200, -2550), odd_col,
                      _math(ng, "MULTIPLY", (-2350, -2550), f_dy, 0.5)))
    hex_x = _switch(ng, (-1850, -1900), "FLOAT", _out(gi, "Flat Top"), p_x, f_x)
    hex_y = _switch(ng, (-1850, -2150), "FLOAT", _out(gi, "Flat Top"), p_y, f_y)
    hex_pos = _xyz(ng, (-1650, -2000), x=hex_x, y=hex_y)

    # Triangle：真正的三角形貼磚
    #   單元是「質心在原點、頂點朝 +Y」的三角形
    #   質心落在蜂巢晶格上，up / down 以 col 奇偶交錯 180°
    tri_a = _out(gi, "Step")
    tri_h = _math(ng, "MULTIPLY", (-2350, -2800), tri_a, sqrt3 / 2.0,
                  label="h = √3/2·a")
    tri_half = _math(ng, "MULTIPLY", (-2350, -2950), tri_a, 0.5, label="a/2")
    tri_third = _math(ng, "DIVIDE", (-2350, -3100), tri_h, 3.0, label="h/3")
    tri_off = _math(ng, "MULTIPLY", (-2050, -2950), odd_row, tri_half,
                    label="band 錯 a/2")
    t_x = _math(ng, "ADD", (-1850, -2850),
                _math(ng, "MULTIPLY", (-2050, -2850), col, tri_half),
                _math(ng, "ADD", (-2050, -3000), tri_half, tri_off))
    t_y = _math(ng, "ADD", (-1850, -3100),
                _math(ng, "MULTIPLY", (-2050, -3100), row, tri_h),
                _math(ng, "MULTIPLY", (-2050, -3250),
                      _math(ng, "ADD", (-2200, -3250), odd_col, 1.0), tri_third))
    tri_pos = _xyz(ng, (-1650, -2950), x=t_x, y=t_y)
    tri_rot = _xyz(ng, (-1650, -3250),
                   z=_math(ng, "MULTIPLY", (-1850, -3250), odd_col, math.pi,
                           label="down → 180°"))

    grid_is_tri = _compare(ng, (-1500, -2800), "EQUAL", _out(gi, "Grid Type"), 2,
                           data_type="INT", label="Tri?")
    grid_rot = _switch(ng, (-1300, -2900), "VECTOR", grid_is_tri,
                       _xyz(ng, (-1500, -3000)), tri_rot, label="格子旋轉")

    grid_pos = _index_switch(ng, (-1500, -1500), "VECTOR", _out(gi, "Grid Type"),
                             [sq_pos, hex_pos, tri_pos], label="Grid Type")
    g_total = _math(ng, "MULTIPLY", (-1300, -1000), gx_n, gy_n, label="Nx·Ny")
    g_pts = _node(ng, "GeometryNodePoints", (-1050, -1000), label="Points", width=160)
    _link(ng, g_total, _in(g_pts, "Count"))
    _link(ng, grid_pos, _in(g_pts, "Position"))
    grid_geom = _store_orientation(ng, _out(g_pts, "Points"),
                                   grid_rot,
                                   _xyz(ng, (-850, -1050), x=1.0),
                                   _xyz(ng, (-850, -1250), z=1.0),
                                   (-850, -900))
    _frame(ng, "③-B Grid　XY / Hex / Triangle", C_LAYOUT, list(ng.nodes)[start:])

    # Radial ---------------------------------------------------------------
    start = _section(ng)
    arc_rad = _math(ng, "MULTIPLY", (-2500, -1100), _out(gi, "Arc"),
                    math.pi / 180.0, label="Arc → rad")
    full = _compare(ng, (-2500, -1250), "GREATER_EQUAL", _out(gi, "Arc"), 359.999,
                    label="整圈？")
    denom = _switch(ng, (-2300, -1200), "FLOAT", full, count_m1, one, label="分母")
    ang_step = _math(ng, "DIVIDE", (-2100, -1100), arc_rad, denom, label="每份角度")
    idx_r = _node(ng, "GeometryNodeInputIndex", (-2500, -1450), label="i", width=140)
    angle = _math(ng, "MULTIPLY", (-1900, -1250), _out(idx_r, "Index"), ang_step,
                  label="i × 角度")
    angle = _math(ng, "ADD", (-1750, -1250), angle,
                  _math(ng, "MULTIPLY", (-2300, -1400), _out(gi, "Start Angle"),
                        math.pi / 180.0, label="起始角"), label="角度")
    cos_a = _math(ng, "COSINE", (-1550, -1150), angle, label="cos")
    sin_a = _math(ng, "SINE", (-1550, -1350), angle, label="sin")
    r_cos = _math(ng, "MULTIPLY", (-1350, -1150), _out(gi, "Radius"), cos_a)
    r_sin = _math(ng, "MULTIPLY", (-1350, -1350), _out(gi, "Radius"), sin_a)
    rad_pts = _node(ng, "GeometryNodePoints", (-1150, -1200), label="Points", width=160)
    _link(ng, _out(gi, "Count"), _in(rad_pts, "Count"))
    _link(ng, _xyz(ng, (-1350, -1550), x=r_cos, y=r_sin), _in(rad_pts, "Position"))
    rad_rot = _xyz(ng, (-950, -1050), z=angle)
    rad_fwd = _xyz(ng, (-950, -1250),
                   x=_math(ng, "MULTIPLY", (-1150, -1250), sin_a, -1.0), y=cos_a)
    rad_nrm = _xyz(ng, (-950, -1450), x=cos_a, y=sin_a)
    rad_geom = _store_orientation(ng, _out(rad_pts, "Points"), rad_rot, rad_fwd, rad_nrm,
                                  (-750, -1150))
    _frame(ng, "③-C Radial　環狀", C_RADIAL, list(ng.nodes)[start:])

    # Curve ----------------------------------------------------------------
    start = _section(ng)
    curve_info = _node(ng, "GeometryNodeObjectInfo", (-2500, -1950), label="Curve", width=180)
    curve_info.transform_space = "ORIGINAL"
    _link(ng, _out(gi, "Curve"), _in(curve_info, "Object"))
    ext_xy = _vmath(ng, "DISTANCE", (-2300, -1800),
                    _xyz(ng, (-2450, -1800), x=size_sep.outputs["X"],
                         y=size_sep.outputs["Y"]),
                    _xyz(ng, (-2450, -1930)), label="XY 對角（Gap 用）")
    curve_gap = _math(ng, "ADD", (-2100, -1800), ext_xy, _out(gi, "Gap"))
    curve_step = _index_switch(ng, (-1900, -1850), "FLOAT", _out(gi, "Spacing Mode"),
                               [_out(gi, "Step"), curve_gap, 0.0], label="曲線間距")
    resample_len = _node(ng, "GeometryNodeResampleCurve", (-1700, -1800),
                         label="Resample 長度", width=180, mode="LENGTH")
    _link(ng, _out(curve_info, "Geometry"), _in(resample_len, "Curve"))
    _link(ng, curve_step, _in(resample_len, "Length"))
    resample_cnt = _node(ng, "GeometryNodeResampleCurve", (-1700, -2000),
                         label="Resample 數量", width=180, mode="COUNT")
    _link(ng, _out(curve_info, "Geometry"), _in(resample_cnt, "Curve"))
    _link(ng, _out(gi, "Count"), _in(resample_cnt, "Count"))
    curve_fit = _compare(ng, (-1900, -2100), "EQUAL", _out(gi, "Spacing Mode"), 2,
                         data_type="INT", label="Fit?")
    curve_res = _switch(ng, (-1500, -1900), "GEOMETRY", curve_fit,
                        _out(resample_len, "Curve"), _out(resample_cnt, "Curve"),
                        label="Fit / Step")
    c2p = _node(ng, "GeometryNodeCurveToPoints", (-1300, -1900),
                label="Curve to Points", width=190, mode="EVALUATED")
    _link(ng, curve_res, _in(c2p, "Curve"))
    curve_rot = _node(ng, "FunctionNodeRotationToEuler", (-1050, -1700),
                      label="Rotation → Euler", width=180)
    _link(ng, _out(c2p, "Rotation"), _in(curve_rot, "Rotation"))
    curve_geom = _store_orientation(ng, _out(c2p, "Points"),
                                    _out(curve_rot, "Euler"),
                                    _out(c2p, "Tangent"),
                                    _out(c2p, "Normal"),
                                    (-850, -1800))
    _frame(ng, "③-D Curve　沿曲線", C_CURVE, list(ng.nodes)[start:])

    # Mesh -----------------------------------------------------------------
    start = _section(ng)
    surf_info = _node(ng, "GeometryNodeObjectInfo", (-2500, -2650), label="Surface", width=180)
    surf_info.transform_space = "ORIGINAL"
    _link(ng, _out(gi, "Surface"), _in(surf_info, "Object"))
    surf_ds = _node(ng, "GeometryNodeAttributeDomainSize", (-2300, -2550),
                    label="Surface 有幾點？", width=180)
    surf_ds.component = "MESH"
    _link(ng, _out(surf_info, "Geometry"), _in(surf_ds, "Geometry"))
    surf_has = _compare(ng, (-2100, -2550), "GREATER_THAN",
                        _out(surf_ds, "Point Count"), 0, label="有表面？")
    surface_geo = _switch(ng, (-1900, -2650), "GEOMETRY", surf_has,
                          _out(gi, "Geometry"), _out(surf_info, "Geometry"),
                          label="Surface 或 自身")

    m2p_v = _node(ng, "GeometryNodeMeshToPoints", (-1650, -2400), label="Vertex", width=160)
    m2p_v.mode = "VERTICES"
    m2p_e = _node(ng, "GeometryNodeMeshToPoints", (-1650, -2600), label="Edge 中點", width=160)
    m2p_e.mode = "EDGES"
    m2p_f = _node(ng, "GeometryNodeMeshToPoints", (-1650, -2800), label="Face 中心", width=160)
    m2p_f.mode = "FACES"
    for n in (m2p_v, m2p_e, m2p_f):
        _link(ng, surface_geo, _in(n, "Mesh"))
    dist = _node(ng, "GeometryNodeDistributePointsOnFaces", (-1650, -3050),
                 label="Surface 隨機", width=190)
    _link(ng, surface_geo, _in(dist, "Mesh"))
    _link(ng, _out(gi, "Density"), _in(dist, "Density"))
    _link(ng, _out(gi, "Seed"), _in(dist, "Seed"))
    mesh_pts = _index_switch(ng, (-1400, -2700), "GEOMETRY", _out(gi, "Mesh Mode"),
                             [_out(m2p_v, "Points"), _out(m2p_e, "Points"),
                              _out(m2p_f, "Points"), _out(dist, "Points")],
                             label="Mesh 模式")

    idm = _node(ng, "GeometryNodeInputIndex", (-2500, -3250), label="i", width=140)
    nrm_field = _node(ng, "GeometryNodeInputNormal", (-2500, -3400), label="Normal", width=160)
    pos_field = _node(ng, "GeometryNodeInputPosition", (-2500, -3750),
                      label="Position", width=150)
    n_vert = _node(ng, "GeometryNodeSampleIndex", (-2200, -3250), label="頂點法線", width=180,
                   data_type="FLOAT_VECTOR", domain="POINT")
    _link(ng, surface_geo, _in(n_vert, "Geometry"))
    _link(ng, _out(nrm_field, "Normal"), _in(n_vert, "Value"))
    _link(ng, _out(idm, "Index"), _in(n_vert, "Index"))
    n_face = _node(ng, "GeometryNodeSampleIndex", (-2200, -3500), label="面法線", width=180,
                   data_type="FLOAT_VECTOR", domain="FACE")
    _link(ng, surface_geo, _in(n_face, "Geometry"))
    _link(ng, _out(nrm_field, "Normal"), _in(n_face, "Value"))
    _link(ng, _out(idm, "Index"), _in(n_face, "Index"))
    # Sample Nearest Surface 的 Value 是純量；法線要分三個分量各取一次
    nrm_sep = _separate(ng, (-2500, -3600), _out(nrm_field, "Normal"),
                        label="法線分量")
    edge_n = []
    for i, comp in enumerate(("X", "Y", "Z")):
        n = _node(ng, "GeometryNodeSampleNearestSurface", (-2250 + i * 170, -3600),
                  label="最近表面 %s" % comp, width=180)
        _link(ng, surface_geo, _in(n, "Mesh"))
        _link(ng, nrm_sep.outputs[comp], _in(n, "Value"))
        _link(ng, _out(pos_field, "Position"), _in(n, "Sample Position"))
        edge_n.append(_out(n, "Value"))
    n_edge = _xyz(ng, (-1750, -3600), x=edge_n[0], y=edge_n[1], z=edge_n[2],
                  label="最近表面法線")
    mesh_nrm = _index_switch(ng, (-1900, -3400), "VECTOR", _out(gi, "Mesh Mode"),
                             [_out(n_vert, "Value"), n_edge,
                              _out(n_face, "Value"), _out(dist, "Normal")],
                             label="法線")

    edge_ab = _node(ng, "GeometryNodeInputMeshEdgeVertices", (-2500, -3950),
                    label="Edge V1/V2", width=170)
    edge_dir = _vmath(ng, "SUBTRACT", (-2300, -3950),
                      _out(edge_ab, "Position 2"), _out(edge_ab, "Position 1"))
    edge_dir = _vmath(ng, "NORMALIZE", (-2100, -3950), edge_dir, label="邊方向")
    e_dir = _node(ng, "GeometryNodeSampleIndex", (-1900, -3950), label="每點的邊方向",
                  width=190, data_type="FLOAT_VECTOR", domain="EDGE")
    _link(ng, surface_geo, _in(e_dir, "Geometry"))
    _link(ng, edge_dir, _in(e_dir, "Value"))
    _link(ng, _out(idm, "Index"), _in(e_dir, "Index"))
    mesh_fwd = _index_switch(ng, (-1600, -3650), "VECTOR", _out(gi, "Mesh Mode"),
                             [_out(n_vert, "Value"), _out(e_dir, "Value"),
                              _out(n_face, "Value"), _out(dist, "Normal")],
                             label="前方")
    mesh_align_z = _node(ng, "FunctionNodeAlignRotationToVector", (-1300, -3500),
                         label="Z → 法線", width=180, axis="Z")
    _link(ng, mesh_nrm, _in(mesh_align_z, "Vector"))
    mesh_rot = _node(ng, "FunctionNodeRotationToEuler", (-1100, -3500),
                     label="→ Euler", width=170)
    _link(ng, _out(mesh_align_z, "Rotation"), _in(mesh_rot, "Rotation"))
    mesh_geom = _store_orientation(ng, mesh_pts, _out(mesh_rot, "Euler"),
                                   mesh_fwd, mesh_nrm, (-900, -3250))
    _frame(ng, "③-E Mesh　頂點／邊／面／表面", C_MESH, list(ng.nodes)[start:])

    # Collection -----------------------------------------------------------
    start = _section(ng)
    pc = _node(ng, "GeometryNodeCollectionInfo", (-2500, -4650),
               label="Point Collection", width=190)
    _in(pc, "Separate Children").default_value = True
    _in(pc, "Reset Children").default_value = False
    _link(ng, _out(gi, "Point Collection"), _in(pc, "Collection"))
    pc_ds = _node(ng, "GeometryNodeAttributeDomainSize", (-2300, -4500),
                  label="幾個物件", width=180)
    pc_ds.component = "INSTANCES"
    _link(ng, _out(pc, "Instances"), _in(pc_ds, "Geometry"))
    pc_count = _out(pc_ds, "Instance Count")
    pc_idx = _node(ng, "GeometryNodeInputIndex", (-2500, -4850), label="i", width=140)
    pc_pos_field = _node(ng, "GeometryNodeInputPosition", (-2500, -5000),
                         label="Position", width=150)
    pc_rot_field = _node(ng, "GeometryNodeInputInstanceRotation", (-2500, -5150),
                         label="Instance Rotation", width=180)
    pc_pos = _node(ng, "GeometryNodeSampleIndex", (-2100, -4650), label="位置", width=180,
                   data_type="FLOAT_VECTOR", domain="INSTANCE")
    _link(ng, _out(pc, "Instances"), _in(pc_pos, "Geometry"))
    _link(ng, _out(pc_pos_field, "Position"), _in(pc_pos, "Value"))
    _link(ng, _out(pc_idx, "Index"), _in(pc_pos, "Index"))
    pc_rot = _node(ng, "GeometryNodeSampleIndex", (-2100, -4900), label="旋轉", width=180,
                   data_type="QUATERNION", domain="INSTANCE")
    _link(ng, _out(pc, "Instances"), _in(pc_rot, "Geometry"))
    _link(ng, _out(pc_rot_field, "Rotation"), _in(pc_rot, "Value"))
    _link(ng, _out(pc_idx, "Index"), _in(pc_rot, "Index"))
    pc_rot_q = _out(pc_rot, "Value")
    pc_euler = _node(ng, "FunctionNodeRotationToEuler", (-1900, -4900),
                     label="→ Euler", width=170)
    _link(ng, pc_rot_q, _in(pc_euler, "Rotation"))
    pc_fwd = _node(ng, "FunctionNodeRotateVector", (-1900, -5100), label="X 軸", width=170)
    _link(ng, _xyz(ng, (-2100, -5100), x=1.0), _in(pc_fwd, "Vector"))
    _link(ng, pc_rot_q, _in(pc_fwd, "Rotation"))
    pc_nrm = _node(ng, "FunctionNodeRotateVector", (-1900, -5300), label="Z 軸", width=170)
    _link(ng, _xyz(ng, (-2100, -5300), z=1.0), _in(pc_nrm, "Vector"))
    _link(ng, pc_rot_q, _in(pc_nrm, "Rotation"))
    pc_pts = _node(ng, "GeometryNodePoints", (-1500, -4750), label="Points", width=160)
    _link(ng, pc_count, _in(pc_pts, "Count"))
    _link(ng, _out(pc_pos, "Value"), _in(pc_pts, "Position"))
    pc_geom = _store_orientation(ng, _out(pc_pts, "Points"),
                                 _out(pc_euler, "Euler"),
                                 _out(pc_fwd, "Vector"),
                                 _out(pc_nrm, "Vector"),
                                 (-1250, -4800))
    _frame(ng, "③-F Collection　讀物件原點＋旋轉", C_POINT, list(ng.nodes)[start:])

    # ------------------------------------------------------------ 選分支
    points = _index_switch(ng, (-700, 300), "GEOMETRY", _out(gi, "Mode"),
                           [lin_geom, grid_geom, rad_geom,
                            curve_geom, mesh_geom, pc_geom],
                           label="Mode → 點集", width=220)

    # ------------------------------------------------------------ ④ 方向
    start = _section(ng)
    na_rot = _node(ng, "GeometryNodeInputNamedAttribute", (-500, 600),
                   label="rot", width=170, data_type="FLOAT_VECTOR")
    _in(na_rot, "Name").default_value = ATTR_ROT
    na_fwd = _node(ng, "GeometryNodeInputNamedAttribute", (-500, 400),
                   label="fwd", width=170, data_type="FLOAT_VECTOR")
    _in(na_fwd, "Name").default_value = ATTR_FWD
    na_nrm = _node(ng, "GeometryNodeInputNamedAttribute", (-500, 200),
                   label="nrm", width=170, data_type="FLOAT_VECTOR")
    _in(na_nrm, "Name").default_value = ATTR_NRM

    natural = _node(ng, "FunctionNodeEulerToRotation", (-200, 650),
                    label="Natural", width=170)
    _link(ng, _out(na_rot, "Attribute"), _in(natural, "Euler"))

    fwd_rots = []
    for i, axis in enumerate(("X", "Y", "Z")):
        n = _node(ng, "FunctionNodeAlignRotationToVector", (-200, 350 - i * 150),
                  label="Forward %s" % axis, width=180, axis=axis)
        _link(ng, _out(na_fwd, "Attribute"), _in(n, "Vector"))
        fwd_rots.append(_out(n, "Rotation"))
    up_rots = []
    for i, axis in enumerate(("X", "Y", "Z")):
        n = _node(ng, "FunctionNodeAlignRotationToVector", (-200, -150 - i * 150),
                  label="Up %s" % axis, width=180, axis=axis)
        _link(ng, _out(na_nrm, "Attribute"), _in(n, "Vector"))
        up_rots.append(_out(n, "Rotation"))
    fwd_rot = _index_switch(ng, (50, 200), "ROTATION", _out(gi, "Forward Axis"),
                            fwd_rots, label="Forward Axis")
    up_rot = _index_switch(ng, (50, -250), "ROTATION", _out(gi, "Up Axis"),
                           up_rots, label="Up Axis")
    final_rot = _index_switch(ng, (350, 0), "ROTATION", _out(gi, "Align"),
                              [_out(natural, "Rotation"), fwd_rot, up_rot],
                              label="Align")
    _frame(ng, "④ 方向　Natural / Forward / Up", C_ORIENT, list(ng.nodes)[start:])

    # ------------------------------------------------------------ ⑤ 實例化
    start = _section(ng)
    seed_idx = _math(ng, "ADD", (450, -300), _out(gi, "Seed"), 7.0, label="種子 +7")
    max_idx = _math(ng, "MAXIMUM", (450, -450),
                    _math(ng, "SUBTRACT", (450, -450), _out(gi, "Collection Count"), 1.0,
                          label="Count − 1"),
                    0.0, label="最大 index")
    pick = _node(ng, "FunctionNodeRandomValue", (650, -350), label="隨機挑款", width=180)
    pick.data_type = "INT"
    _in(pick, "Min").default_value = 0
    _link(ng, max_idx, _in(pick, "Max"))
    _link(ng, seed_idx, _in(pick, "Seed"))

    inst = _node(ng, "GeometryNodeInstanceOnPoints", (850, 200),
                 label="Instance on Points", width=200)
    _link(ng, points, _in(inst, "Points"))
    _link(ng, unit_geo, _in(inst, "Instance"))
    _link(ng, _out(gi, "Unit From Collection"), _in(inst, "Pick Instance"))
    _link(ng, _out(pick, "Value"), _in(inst, "Instance Index"))
    _link(ng, final_rot, _in(inst, "Rotation"))
    _frame(ng, "⑤ 實例化", C_INST, list(ng.nodes)[start:])
    instancing = _out(inst, "Instances")

    # ------------------------------------------------------------ ⑥ 變化
    start = _section(ng)
    inst_ds = _node(ng, "GeometryNodeAttributeDomainSize", (1100, -150),
                    label="份數", width=160)
    inst_ds.component = "INSTANCES"
    _link(ng, instancing, _in(inst_ds, "Geometry"))
    inst_n = _out(inst_ds, "Instance Count")
    idx_v = _node(ng, "GeometryNodeInputIndex", (1100, 100), label="i", width=140)
    denom_v = _math(ng, "MAXIMUM", (1250, -50),
                    _math(ng, "SUBTRACT", (1250, -50), inst_n, 1.0, label="份數 − 1"),
                    1.0)
    t = _math(ng, "DIVIDE", (1400, 100), _out(idx_v, "Index"), denom_v,
              label="t = i / (n−1)")

    seed_r = _math(ng, "ADD", (1100, -400), _out(gi, "Seed"), 13.0)
    rnd_rot = _node(ng, "FunctionNodeRandomValue", (1300, -400),
                    label="亂數方向", width=170)
    rnd_rot.data_type = "FLOAT_VECTOR"
    _in(rnd_rot, "Min").default_value = (-1.0, -1.0, -1.0)
    _in(rnd_rot, "Max").default_value = (1.0, 1.0, 1.0)
    _link(ng, seed_r, _in(rnd_rot, "Seed"))
    rot_amp = _node(ng, "ShaderNodeVectorMath", (1300, -600),
                    label="度 → rad", width=170, operation="SCALE")
    _link(ng, _out(gi, "Random Rotate"), _in(rot_amp, "Vector"))
    _in(rot_amp, "Scale").default_value = math.pi / 180.0
    rnd_rot_v = _vmath(ng, "MULTIPLY", (1500, -450), _out(rnd_rot, "Value"),
                       _out(rot_amp, "Vector"), label="隨機旋轉")
    twist = _math(ng, "MULTIPLY", (1500, -700), t,
                  _math(ng, "MULTIPLY", (1500, -850), _out(gi, "Gradient Rotate"),
                        math.pi / 180.0, label="deg → rad"), label="漸變扭轉")
    euler_all = _vmath(ng, "ADD", (1700, -450), rnd_rot_v,
                       _xyz(ng, (1700, -700), z=twist), label="旋轉總和")
    rot_inst = _node(ng, "FunctionNodeEulerToRotation", (1900, -450),
                     label="→ Rotation", width=170)
    _link(ng, euler_all, _in(rot_inst, "Euler"))
    rotated = _node(ng, "GeometryNodeRotateInstances", (2100, -150),
                    label="Rotate Instances", width=190)
    _link(ng, instancing, _in(rotated, "Instances"))
    _link(ng, _out(rot_inst, "Rotation"), _in(rotated, "Rotation"))

    seed_s = _math(ng, "ADD", (1100, -1050), _out(gi, "Seed"), 29.0)
    one_minus = _math(ng, "SUBTRACT", (1100, -1200), 1.0, _out(gi, "Random Scale"))
    one_plus = _math(ng, "ADD", (1100, -1350), 1.0, _out(gi, "Random Scale"))
    rnd_s = _node(ng, "FunctionNodeRandomValue", (1300, -1150),
                  label="亂數大小", width=170)
    rnd_s.data_type = "FLOAT"
    _link(ng, one_minus, _in(rnd_s, "Min"))
    _link(ng, one_plus, _in(rnd_s, "Max"))
    _link(ng, seed_s, _in(rnd_s, "Seed"))
    grad_s = _math(ng, "MULTIPLY", (1300, -1350),
                   _math(ng, "SUBTRACT", (1300, -1350), _out(gi, "Gradient Scale"), 1.0,
                         label="終點 − 1"),
                   t)
    grad_s = _math(ng, "ADD", (1450, -1350), grad_s, 1.0, label="1 → 終點")
    factor = _math(ng, "MULTIPLY", (1600, -1150),
                   _math(ng, "MULTIPLY", (1450, -1150), _out(rnd_s, "Value"), grad_s,
                         label="隨機 × 漸變"),
                   _out(gi, "Unit Scale"), label="大小倍率")

    odd = _math(ng, "FLOORED_MODULO", (1100, -1550), _out(idx_v, "Index"), 2.0,
                label="奇偶")
    odd_b = _compare(ng, (1300, -1550), "GREATER_THAN", odd, 0.5, label="奇數份？")
    and_b = _node(ng, "FunctionNodeBooleanMath", (1500, -1550),
                  label="Mirror 且奇數", width=150, operation="AND")
    _link(ng, _out(gi, "Mirror"), and_b.inputs[0])
    _link(ng, odd_b, and_b.inputs[1])
    sign = _switch(ng, (1700, -1550), "FLOAT", _out(and_b, "Boolean"), 1.0, -1.0,
                   label="鏡像正負")
    mirrored = _math(ng, "MULTIPLY", (1900, -1350), factor, sign, label="大小 × 鏡像")
    scale_vec = _index_switch(ng, (2000, -1750), "VECTOR", _out(gi, "Mirror Axis"),
                              [_xyz(ng, (1780, -1700), x=mirrored, y=factor, z=factor),
                               _xyz(ng, (1780, -1850), x=factor, y=mirrored, z=factor),
                               _xyz(ng, (1780, -2000), x=factor, y=factor, z=mirrored)],
                              label="大小 + 鏡像")
    scaled = _node(ng, "GeometryNodeScaleInstances", (2300, -150),
                   label="Scale Instances", width=190)
    _link(ng, _out(rotated, "Instances"), _in(scaled, "Instances"))
    _link(ng, scale_vec, _in(scaled, "Scale"))

    seed_o = _math(ng, "ADD", (1100, -2100), _out(gi, "Seed"), 41.0)
    rnd_off = _node(ng, "FunctionNodeRandomValue", (1300, -2100),
                    label="亂數位移", width=170)
    rnd_off.data_type = "FLOAT_VECTOR"
    _in(rnd_off, "Min").default_value = (-1.0, -1.0, -1.0)
    _in(rnd_off, "Max").default_value = (1.0, 1.0, 1.0)
    _link(ng, seed_o, _in(rnd_off, "Seed"))
    off = _vmath(ng, "MULTIPLY", (1500, -2100), _out(rnd_off, "Value"),
                 _out(gi, "Random Offset"), label="位移")
    moved = _node(ng, "GeometryNodeSetPosition", (2300, -450),
                  label="Set Position", width=180)
    _link(ng, _out(scaled, "Instances"), _in(moved, "Geometry"))
    _link(ng, off, _in(moved, "Offset"))
    _frame(ng, "⑥ 變化　隨機 / 鏡像 / 漸變", C_VARY, list(ng.nodes)[start:])

    # ------------------------------------------------------------ ⑦ 輸出
    start = _section(ng)
    realized = _node(ng, "GeometryNodeRealizeInstances", (2300, -750),
                     label="Realize", width=170)
    _in(realized, "Realize All").default_value = True
    _link(ng, _out(moved, "Geometry"), _in(realized, "Geometry"))
    final = _switch(ng, (2500, -300), "GEOMETRY", _out(gi, "Realize"),
                    _out(moved, "Geometry"), _out(realized, "Geometry"),
                    label="輸出實例 / mesh")
    _link(ng, final, go.inputs["Geometry"])
    _frame(ng, "⑦ 輸出", C_OUT, list(ng.nodes)[start:])

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
                     "panel": item.parent.name if getattr(item, "parent", None) else "",
                     "description": getattr(item, "description", "")})
    return rows
