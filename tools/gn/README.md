# Stan Geometry Nodes 工具庫（GN）

兩個可重跑的 Geometry Nodes group，**各存自己的資產檔**（Stan Box 不與 Stan Array 放在一起）：

- `Stan Array`：通用陣列 — Linear／Grid（XY・Hex・
  Triangle・Brick・Herringbone・Chevron・Basket Weave）／Radial／Curve／Mesh／Collection，間距支援 Step／Gap／Fit，
  可隨機、鏡像、漸變。
- `Stan Box`：盒生成器 — `Size XYZ` × `Scale Factor`、小數尺寸挖成空心盒、
  Plug／Cube 填充、收口面、圓角近似、頂點網格實例化（jitter／旋轉／大小隨機）。

完整參數表與常用排法在[根目錄 README](../../README.md)。

## 檔案

| 路徑 | 說明 |
|---|---|
| [`stan_array.py`](stan_array.py) | `Stan Array` node group 的產生器（純 bpy，可重跑、可版控）。 |
| [`box_generator.py`](box_generator.py) | `Stan Box` node group 的產生器（純 bpy，4.5 目标；66 nodes / 108 links）。 |
| [`stan_array_demo.py`](stan_array_demo.py) | 十一個陣列示範場景與 Cycles 算圖（headless）。 |
| [`box_demo.py`](box_demo.py) | 五個盒示範場景與 Cycles 算圖（headless）；存 `demo/box_demo.blend`。 |
| [`contact_sheet.py`](contact_sheet.py) | 拼 contact sheet；`--prefix stan_` → `stan_contact.png`、`--prefix box_` → `box_contact.png`（需要 Pillow）。 |
| [`test_stan_array.py`](test_stan_array.py) | 無頭煙霧測試（43 項：每個模式、七種晶格／排法、brick 錯位、chevron 斜切與貼合、間距、方向、鏡像、漸變、Realize、Fit 退化守衛、enum 表一致性）。 |
| [`test_box_generator.py`](test_box_generator.py) | 無頭煙霧測試（27 項：尺寸×倍率、每邊 ≥2、开口方向、整數不開口、Plug/Cube、壁厚、收口、圓角、實例化與隨機、屬性、材質、enum 表一致性）。 |
| [`build_asset.py`](build_asset.py) | 無頭 Blender 入口：每個 group 建自己的 asset 檔並標記 Asset（`--group`／`--asset` 可只建一個）。 |
| [`gn.py`](gn.py) | CLI：`build` / `inputs` / `list` / `apply` / `reload` / `stan-demo` / `box-demo`，透過 Blender Bridge 操作開著的 Blender（`--group stan | box`）。 |
| [`../../assets/geometry_nodes.blend`](../../assets/geometry_nodes.blend) | Stan Array 資產檔。任何 .blend 都能 Append / Link 這個 node group。 |
| [`../../assets/box_nodes.blend`](../../assets/box_nodes.blend) | Stan Box 資產檔（獨立，不與 Stan Array 放在一起）。任何 .blend 都能 Append / Link。 |
| [`../../demo/stan_array_demo.blend`](../../demo/stan_array_demo.blend) | 陣列示範場景（欄杆；host 上已套好 modifier 與參數）。 |
| [`../../demo/box_demo.blend`](../../demo/box_demo.blend) | 盒示範場景（solid；host 上已套好 modifier 與參數）。 |

## 節點圖分區（Stan Array）

| 分區 | 內容 |
|---|---|
| ① 單位與尺寸 | Unit selection（host / collection）＋ Bounding Box → 單元尺寸 |
| ② 間距 | 方向投影、Fit/Gap/Step 三個候選值 → Index Switch |
| ③ 排列 | A Linear、B Grid（XY / Hex / Tri / Brick / Herringbone / Chevron / Basket Weave）、C Radial、D Curve、E Mesh、F Collection；每個分支把 `arr_rot` / `arr_fwd` / `arr_nrm` 存成點屬性 |
| ④ 方向 | 讀回屬性 → Natural / Forward / Up → Rotation |
| ⑤ 實例化 | Instance on Points（可 Pick Instance） |
| ⑥ 變化 | Rotate / Scale / Set Position（Unit Scale、隨機、鏡像、漸變） |
| ⑦ 輸出 | 實例或 Realize |

## 節點圖分區（Stan Box）

| 分區 | 內容 |
|---|---|
| ① 尺寸 | `dims = Size XYZ × Scale Factor`（Vector Math MULTIPLY）；`offset = dims − floor(|dims|)` → 开口方向 |
| ② 外層盒 | `GeometryNodeMeshCube`（Size = dims，Vertices = `Vertices Per Side`） |
| ③ 空心 | 内塞尺寸 = `|dims| − 2×Wall Thickness`；`InputNormal` × `offset` → `DOT_PRODUCT > 0.001` = 挖穿面；`ScaleElements (FACE)` 收口 → `DeleteGeometry (FACE, ONLY_FACE)` 保留邊線框架 |
| ③ Plug | `MeshGrid` + `Transform` 放内塞平面，只塞 Z 轴开口側（z 位移 = `sign(offset.z) × 内塞.z/2`；4.5 限制） |
| ④ 實例化 | `MeshToPoints` → `InstanceOnPoints`；Jitter 用 `SetPosition` Offset，ID = `Index + Seed` → `RandomValue` |
| ⑤ 輸出 | Fill/Hollow 門閂（Switch / Index Switch）→ Corner Subdivide → Store Named Attribute → Realize → Set Material → Set Shade Smooth |

### Hollow / Fill / Corner 語意

- `offset = dims − floor(|dims|)`：某軸 offset > 0（小數）→ 挖 **+** 方向那面；
  offset < 0（負尺寸）→ 挖 **−** 方向那面；整數軸 offset = 0 → 不挖（關閉的盒）。
- `Fill Mode`：`0 None` 開放盒／`1 Plug` 内塞平面（僅 Z 轴开口）／`2 Cube` 實心。
- `Shrink Faces` + `Shrink Scale`：挖穿前把保留面往盒中心縮（0 = 收到中心）。
- `Corner Mode`：`0 None`／`1 Subdivide` — 4.5 沒有 `Bevel`／`MergePoints`，
  只有 Subdivide + Shade Smooth 的圓角近似。
- `Vertices Per Side` 4.5 要求 **≥ 2**（1 會退化成單點）。

### Grid 的七種晶格

`Grid Type`：

- `0` **XY**：`p = (i·sx, j·sy)`，`sx/sy` 由 Step/Gap/Fit 決定，Fit 會讓外緣對齊。
- `1` **Hex**：`R = Cell Size / 2`；
  pointy-top（`Flat Top = false`）`dx = √3·R`、`dy = 1.5·R`，奇數列 X 偏移 `dx/2`；
  flat-top（true）`dx = 1.5·R`、`dy = √3·R`，奇數行 Y 偏移 `dy/2`。
- `2` **Triangle**：真正的三角形貼磚。三角形**質心**排在蜂巢晶格上：
  `h = √3/2·a`、`x = a/2 + col·a/2 + (帶奇數 ? a/2 : 0)`、
  `y = band·h + (col 奇數 ? 2h/3 : h/3)`；col 奇數（down）自動轉 180°。
  `Count X` 是每帶三角形數、`Count Y` 是帶數。單元質心要在原點、頂點朝 +Y。
- `3` **Brick**：`x = col·stepX + (floor(row / Stagger Repeat) · Stagger · stepX mod stepX)`、
  `y = row·stepY`；`Stagger` 0 = 對齊、0.5 = 1/2、0.333 = 1/3、0.25 = 1/4。
  Brick 跟 XY 一樣吃 Step/Gap/Fit。
- `4` **Herringbone**：`Pattern W` 控制磚寬（L = 2W），4W × 4W cell，H 在 `(0,0)(3,1)(2,2)(1,3)`、V 在
  `(2,0)(1,1)(0,2)(3,3)`，每格 8 塊；磚要 2:1、中心在原點。
- `5` **Chevron**：長方形磚（原點置中）先被**斜切**成平行四邊形再實例化：
  `x' = sx·x`、`y' = sy·y + c·x`，`sx = (L/L0)/√2`、`sy = (W/W0)·√2`、`c = √2·W/L0`
  （`L0/W0` = 單元 bbox，`L/W` = `Pattern L/W`，0 = 從 bbox 推）。
  `A = L/√2`、`H = W·√2`，奇數欄 `scale.x = -1` 鏡像成 V；斜切後是 realized mesh，
  因此 Chevron 關閉 Pick Instance（instance index 固定 0），集合裡只放一塊磚。
- `6` **Basket Weave**：`Pattern W` 控制磚寬（L = 2W），2W × 2W block，
  偶數 block 兩塊橫磚、奇數 block 兩塊直磚。

Hex/Triangle 不使用 `Spacing Mode`；點數 = `Count X × Count Y`，直接用
`Index` 推 `col/row` 後算座標，所以不需要 Mesh Grid，也沒有頂點順序問題。

## 用法

### 1. 在 Blender 裡直接 Append

`File > Append` → `assets/geometry_nodes.blend` → `NodeTree` → `Stan Array`；
`File > Append` → `assets/box_nodes.blend` → `NodeTree` → `Stan Box`（兩個 group 各在自己
的資產檔裡）。之後對物件加 **Geometry Nodes** modifier 再選這個 group（Stan Box 的面板是
`① 尺寸`、`② 網格`、`③ 空心`、`④ 實例`、`⑤ 輸出`）。

### 2. 用 CLI 套到物件上

需要開著的 Blender + Blender Bridge（`tools/blender-bridge`）。

```bash
# 重建資產（無頭 Blender；每個 group 各存自己的 asset 檔）
python3 tools/gn/gn.py build
python3 tools/gn/gn.py build --group box    # 只重建 assets/box_nodes.blend

# 目前 Blender 裡有哪些工具 / 這個工具吃什麼參數
python3 tools/gn/gn.py list --group box
python3 tools/gn/gn.py inputs            # Stan Array
python3 tools/gn/gn.py inputs --group box # Stan Box

# 套用：Hex 蜂巢牆
python3 tools/gn/gn.py apply --object "Host" \
    --set mode=grid --set grid_type=hex --set cell=0.22 \
    --set count_x=12 --set count_y=10 --set flat_top=false

# 套用：線性 + Fit
python3 tools/gn/gn.py apply --object "Host" \
    --set mode=linear --set spacing_mode=fit --set length=4 --set count=9

# 套用：1/2 running bond 磚牆
python3 tools/gn/gn.py apply --object "Host" --set mode=grid --set grid_type=brick \
    --set count_x=10 --set count_y=17 --set spacing_mode=gap --set gap=0.008 \
    --set stagger=0.5 --set stagger_repeat=1

# 套用：空心盒 + Plug 内塞（Stan Box）
python3 tools/gn/gn.py apply --group box --object "Host" \
    --set hollow=1 --set wall=0.08 --set fill=plug --set vertices=3 \
    --set use_instances=1 --set jitter=0.45 --set seed=7

# 示範場景（十一個）+ contact sheet
python3 tools/gn/gn.py stan-demo

# 盒示範場景（五個）+ contact sheet
python3 tools/gn/gn.py box-demo --samples 24 --res 640
```

`apply` 的 Int 列舉可以用名字：`mode=grid`、`grid_type=hex`、`spacing_mode=fit`、
`align=up`、`mesh_mode=surface`、`mirror_axis=z`、`fill=plug`（`open` = `none`）、
`corner=subdivide`（`round` = `subdivide`）。`Curve` / `Surface` /
`Point Collection` / `Material` 是資料插槽、`Size XYZ` 是 Vector，`--set` 都不吃，
請在 modifier UI 設定。

### 3. 測試

```bash
blender -b --factory-startup --python tools/gn/test_stan_array.py    # 43 項
blender -b --factory-startup --python tools/gn/test_box_generator.py # 27 項
```

## 注意

- `Cell Size` 是六角外徑（頂點到頂點）；要留縫就把它調比實際 tile 大一點。
- Blender 的 6 邊柱體是 pointy-top，配 `Flat Top = false`。
- 陣列的奇數列／行會錯開半格，所以邊緣是鋸齒狀；用背板或框遮掉。
- `Collection Count` 必須等於 collection 內實際的 mesh 數量（CLI 會自動填）。
- `Mirror` 會讓鏡像份數的 scale 變負（normal 翻面），對稱零件可接受；
  要乾淨 normal 就 `Realize` 後接 Flip Faces。
- Stan Box 的 `Vertices Per Side` 要 **≥ 2**（4.5 的 `MeshCube` 給 1 會退化）。
- Stan Box 的开口看尺寸的小數部分：整數軸不挖、小數挖 + 方向、負值挖 − 方向。
- `Fill = Plug` 只塞 Z 轴开口；X/Y 开口用 `Fill = Cube` 或關掉 `Hollow`。
- 圓角是近似（4.5 無 Bevel／MergePoints）；`Rotation Range` 用弧度。
- 兩個 group 都以 **Blender 4.5** 建置與測試（不用的 5.2-only 節點：`MeshBevel`／`MergePoints`），
  5.2 可開啟與評估。
