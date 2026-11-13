# Stan Array 工具庫（GN）

`Stan Array` 是一個通用陣列 Geometry Nodes group：Linear／Grid（XY・Hex・
Triangle）／Radial／Curve／Mesh／Collection，間距支援 Step／Gap／Fit，
可隨機、鏡像、漸變。完整參數表在[根目錄 README](../../README.md#stan-array)。

## 檔案

| 路徑 | 說明 |
|---|---|
| [`stan_array.py`](stan_array.py) | `Stan Array` node group 的產生器（純 bpy，可重跑、可版控）。 |
| [`stan_array_demo.py`](stan_array_demo.py) | 八個示範場景與 Cycles 算圖（headless）。 |
| [`contact_sheet.py`](contact_sheet.py) | 把 `demo/stan_*.png` 拼成 `demo/stan_contact.png`（需要 Pillow）。 |
| [`test_stan_array.py`](test_stan_array.py) | 無頭煙霧測試（19 項：每個模式、三種晶格、間距、方向、鏡像、漸變、Realize）。 |
| [`build_asset.py`](build_asset.py) | 無頭 Blender 入口：建 group、標記 Asset、存 `assets/geometry_nodes.blend`。 |
| [`gn.py`](gn.py) | CLI：`build` / `inputs` / `list` / `apply` / `reload` / `stan-demo`，透過 Blender Bridge 操作開著的 Blender。 |
| [`../../assets/geometry_nodes.blend`](../../assets/geometry_nodes.blend) | 資產庫。任何 .blend 都能 Append / Link 這個 node group。 |
| [`../../demo/stan_array_demo.blend`](../../demo/stan_array_demo.blend) | 示範場景（欄杆；host 上已套好 modifier 與參數）。 |

## 節點圖分區

| 分區 | 內容 |
|---|---|
| ① 單位與尺寸 | Unit selection（host / collection）＋ Bounding Box → 單元尺寸 |
| ② 間距 | 方向投影、Fit/Gap/Step 三個候選值 → Index Switch |
| ③ 排列 | A Linear、B Grid（XY / Hex / Tri）、C Radial、D Curve、E Mesh、F Collection；每個分支把 `arr_rot` / `arr_fwd` / `arr_nrm` 存成點屬性 |
| ④ 方向 | 讀回屬性 → Natural / Forward / Up → Rotation |
| ⑤ 實例化 | Instance on Points（可 Pick Instance） |
| ⑥ 變化 | Rotate / Scale / Set Position（Unit Scale、隨機、鏡像、漸變） |
| ⑦ 輸出 | 實例或 Realize |

### Grid 的三種晶格

`Grid Type`：

- `0` **XY**：`p = (i·sx, j·sy)`，`sx/sy` 由 Step/Gap/Fit 決定，Fit 會讓外緣對齊。
- `1` **Hex**：`R = Cell Size / 2`；
  pointy-top（`Flat Top = false`）`dx = √3·R`、`dy = 1.5·R`，奇數列 X 偏移 `dx/2`；
  flat-top（true）`dx = 1.5·R`、`dy = √3·R`，奇數行 Y 偏移 `dy/2`。
- `2` **Triangle**：`dx = Step`（邊長）、`dy = √3/2·Step`，奇數列 X 偏移 `dx/2`。

Hex/Triangle 不使用 `Spacing Mode`；點數 = `Count X × Count Y`，直接用
`Index` 推 `col/row` 後算座標，所以不需要 Mesh Grid，也沒有頂點順序問題。

## 用法

### 1. 在 Blender 裡直接 Append

`File > Append` → `assets/geometry_nodes.blend` → `NodeTree` → `Stan Array`。
之後對物件加 **Geometry Nodes** modifier 再選這個 group。

### 2. 用 CLI 套到物件上

需要開著的 Blender + Blender Bridge（`tools/blender-bridge`）。

```bash
# 重建資產（無頭 Blender）
python3 tools/gn/gn.py build

# 目前 Blender 裡有哪些工具 / 這個工具吃什麼參數
python3 tools/gn/gn.py list
python3 tools/gn/gn.py inputs

# 套用：Hex 蜂巢牆
python3 tools/gn/gn.py apply --object "Host" \
    --set mode=grid --set grid_type=hex --set cell=0.22 \
    --set count_x=12 --set count_y=10 --set flat_top=false

# 套用：線性 + Fit
python3 tools/gn/gn.py apply --object "Host" \
    --set mode=linear --set spacing_mode=fit --set length=4 --set count=9

# 示範場景（八個）+ contact sheet
python3 tools/gn/gn.py stan-demo
```

`apply` 的 Int 列舉可以用名字：`mode=grid`、`grid_type=hex`、`spacing_mode=fit`、
`align=up`、`mesh_mode=surface`、`mirror_axis=z`。`Curve` / `Surface` /
`Point Collection` 是資料插槽，請在 modifier UI 設定。

### 3. 測試

```bash
blender -b --factory-startup --python tools/gn/test_stan_array.py
```

## 注意

- `Cell Size` 是六角外徑（頂點到頂點）；要留縫就把它調比實際 tile 大一點。
- Blender 的 6 邊柱體是 pointy-top，配 `Flat Top = false`。
- 陣列的奇數列／行會錯開半格，所以邊緣是鋸齒狀；用背板或框遮掉。
- `Collection Count` 必須等於 collection 內實際的 mesh 數量（CLI 會自動填）。
- `Mirror` 會讓鏡像份數的 scale 變負（normal 翻面），對稱零件可接受；
  要乾淨 normal 就 `Realize` 後接 Flip Faces。
