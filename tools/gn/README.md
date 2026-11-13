# Geometry Nodes 工具庫（GN）

可重複使用的 Geometry Nodes 工具：

- **Array** — 通用陣列：線性／網格／環狀／曲線／Mesh 頂點邊面／Collection 物件軸心，
  間距支援固定（Step）、貼齊留縫（Gap）、總長均分（Fit），可隨機、鏡像、漸變。
  完整參數表在[根目錄 README](../../README.md#array)。
- **Hex Array** — 蜂巢狀陣列，每格放 Collection 裡的一個物件，可亂數挑選、亂數大小、亂數間距。

用 `python3 tools/gn/gn.py demo` 會生出示範場景（[`demo/hex_array_demo.blend`](../demo/hex_array_demo.blend)）。

![俯視](../demo/hex_top.png)

![示範](../demo/hex_demo.png)

## 檔案

| 路徑 | 說明 |
|---|---|
| [`array_gn.py`](array_gn.py) | `Array` node group 的產生器（純 bpy，可重跑、可版控）。 |
| [`array_demo.py`](array_demo.py) | `Array` 示範場景與算圖（headless，六個場景 + contact sheet）。 |
| [`test_array.py`](test_array.py) | `Array` 的無頭煙霧測試（16 項：每個模式、間距、方向、鏡像、漸變、Realize）。 |
| [`hex_array.py`](hex_array.py) | `Hex Array` node group 的產生器（純 bpy，可重跑、可版控）。 |
| [`build_asset.py`](build_asset.py) | 無頭 Blender 入口：建 group、標記 Asset、存 `assets/geometry_nodes.blend`。 |
| [`gn.py`](gn.py) | CLI：`build` / `inputs` / `list` / `apply` / `reload` / `demo` / `array-demo`，可加 `--group array`；透過 Blender Bridge 操作開著的 Blender。 |
| [`../../assets/geometry_nodes.blend`](../../assets/geometry_nodes.blend) | 資產庫。任何 .blend 都能 Append / Link 這個 node group。 |
| [`../../demo/hex_array_demo.blend`](../../demo/hex_array_demo.blend) | Hex Array 示範場景（3 種 tile、材質、燈光、相機、算好的圖）。 |
| [`../../demo/array_demo.blend`](../../demo/array_demo.blend) | Array 示範場景（欄杆；host 上已套好 modifier 與參數）。 |

## 參數

| 參數 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `Collection` | Collection | – | 六角單元的物件來源；多個物件時隨機挑選 |
| `Count Long` | Int | 12 | 長邊方向（X）的格數 |
| `Count Short` | Int | 8 | 短邊方向（Y）的列數 |
| `Cell Size` | Float | 0.25 | 六角單元外徑（頂點到頂點，公尺）→ 決定格距 |
| `Spacing` | Float | 1.0 | 中心距倍率：1.0 = 六角緊貼，>1 拉開 |
| `Stagger Columns` | Bool | False | False = pointy-top（行沿 X 錯開，Blender 預設 6 邊柱體）；True = flat-top（列沿 Y 錯開） |
| `Size Random` | Float | 0.0 | 單元大小隨機幅度（± 比例，0…1） |
| `Spacing Random` | Float | 0.0 | 格點位置抖動（相對間距的比例） |
| `Yaw Random` | Float | 0.0 | 每格繞 Z 隨機旋轉（1 = 一整圈） |
| `Collection Count` | Int | 1 | Collection 裡的物件數，用於隨機挑選（CLI 會自動填） |
| `Scale` | Float | 1.0 | 單元大小倍率（1 = 物件原始大小）；`Size Random` 再乘上隨機量 |
| `Seed` | Int | 0 | 亂數種子 |

## 節點圖分區

![節點圖](../assets/hex_array_nodes.png)

> 這張是自動產生的結構圖（`assets/hex_array_nodes.png`），實際 node group 的分區與連線一致。
> 對話框標題就是 Blender 裡的 frame 名稱，節點上的文字是節點 label。


node group 內用 9 個 frame 分區（顏色也不同），從左到右、由下到上是資料流：

| 分區 | 內容 | 輸出 |
|---|---|---|
| ① 格距 | `窄邊 0.75·D` / `寬邊 0.866·D` → pointy/flat 切換 → `dx`、`dy`（乘 Spacing） | dx, dy |
| ② 格點 | `N−1`、格點寬高 → `Grid` → `只留頂點` | 點雲（每個六角中心） |
| ③ 錯位 | 用座標 `round(Y/dy)`、`round(X/dx)` 推列／行 → 奇偶 → 錯開半格 | 錯位 X / Y |
| ④ 抖動 | `抖動幅度 = dx/2 × Spacing Random` → 兩個 Random Value | 抖動 X / Y |
| ⑤ 定位 | 錯位 + 抖動 → `位移向量` → `Set Position` | 排好的點雲 |
| ⑥ 單元 | `Collection` → `Collection Info`；`最大 index` → `隨機 index` | 實例來源 + index |
| ⑦ 大小 | `1 ± Size Random` → 隨機倍率；`Scale × 隨機` → 向量 | Scale 向量 |
| ⑧ 旋轉 | `亂數 0…1 × 2π × Yaw Random` → Euler → Rotation | Rotation |
| ⑨ 實例化 | `Instance on Points`（Pick Instance + index + Rotation + Scale）→ 輸出 | 幾何 |

每個節點都有中文 label（例如 `列 = round(Y/dy)`、`錯開 dx/2`），frame 標題也寫了它在做什麼。

## Array 節點圖分區

| 分區 | 內容 |
|---|---|
| ① 單位與尺寸 | Unit selection（host / collection）＋ Bounding Box → 單元尺寸 |
| ② 間距 | 方向投影、Fit/Gap/Step 三個候選值 → Index Switch |
| ③ 排列 | A Linear、B Grid、C Radial、D Curve、E Mesh、F Collection；每個分支把 `arr_rot` / `arr_fwd` / `arr_nrm` 存成點屬性 |
| ④ 方向 | 讀回屬性 → Natural / Forward / Up → Rotation |
| ⑤ 實例化 | Instance on Points（可 Pick Instance） |
| ⑥ 變化 | Rotate / Scale / Set Position（隨機、鏡像、漸變） |
| ⑦ 輸出 | 實例或 Realize |

Collection 模式用 `Instances to Points` 的替代方案：`Sample Index`（INSTANCE 域）
取每個 locator 的 Position 與 Instance Rotation，再餵給 `Points` 與 `Instance on Points`。
`Sample Nearest Surface` 的 Value 是純量，所以邊中點的法線是分 X/Y/Z 三次取樣再組合。

## 用法

### 1. 在 Blender 裡直接 Append（最單純）

`File > Append` → 選 `assets/geometry_nodes.blend` → `NodeTree` → `Hex Array`。
之後在 Geometry Nodes 編輯器用它，或對物件加 **Geometry Nodes** modifier 再選這個 group。

想讓它出現在 **Asset Browser**：把 group 標記為 asset，存進自己的 asset library 資料夾即可
（這份檔案裡它已經是 asset）。

### 2. 用 CLI 套到物件上

需要開著的 Blender + Blender Bridge（`tools/blender-bridge`）。

```bash
# 重建資產（無頭 Blender，會寫 assets/geometry_nodes.blend）
python3 tools/gn/gn.py build

# 目前 Blender 裡有哪些工具 / 這個工具吃什麼參數
python3 tools/gn/gn.py list
python3 tools/gn/gn.py inputs

# Array：線性 + Fit（Curve / Surface / Point Collection 等資料插槽請在 modifier UI 設定）
python3 tools/gn/gn.py apply --group array --object "Host" \
    --set mode=linear --set spacing=fit --set length=5 --set count=9

# 六個示範場景
python3 tools/gn/gn.py array-demo

# 把 Hex Array 套到 "Hex Array Demo"，單元來自 collection "Hex Tiles"
python3 tools/gn/gn.py apply --object "Hex Array Demo" --collection "Hex Tiles" \
    --set count_long=16 --set count_short=10 \
    --set cell=0.2 --set spacing=1.05 \
    --set size_random=0.15 --set spacing_random=0.1 --set seed=7

# 少了新版 group 時加上 --reload，會丟掉 session 裡的舊版重載
python3 tools/gn/gn.py apply ... --reload

# 示範場景 + Cycles 算圖 + 視口截圖
python3 tools/gn/gn.py demo
```

`apply` 沒給 `--set collection_count` 時，會自動用 collection 內的 mesh 物件數量填入。

### 3. 直接用 bridge 呼叫

```bash
python3 tools/blender-bridge/bb '{"op":"session"}'
```

## 幾何怎麼算

平面六角（circumradius `R = Cell Size / 2`）：

| 擺法 | dx（X 中心距） | dy（Y 中心距） | 錯位 |
|---|---|---|---|
| pointy-top（預設） | `√3·R` | `1.5·R` | 奇數行 X 偏移 `dx/2` |
| flat-top（`Stagger Columns` = True） | `1.5·R` | `√3·R` | 奇數列 Y 偏移 `dy/2` |

兩者都再乘 `Spacing`。`Cell Size` 只決定格距，**不會**縮放單元物件；要縮放用 `Scale`
（或把 tile 直接做成正確尺寸，`Scale` 保持 1）。

節點圖用 Mesh Grid → Mesh to Points（只留頂點）→ Set Position（錯位＋抖動）→
Instance on Points（Collection Info + Pick Instance + 亂數 index）。

## 為什麼要「對齊方向」

- 單元物件的**網格本身**方向要對應 `Stagger Columns`：Blender 預設 6 邊柱體是 pointy-top
  （頂點朝上），所以預設 `False`。如果你的六角是 flat-top（平頂邊朝上），把它設成 `True`。
- `Collection Info` 勾了 `Reset Children`，會忽略子物件的**位置、旋轉、縮放**——所以不要用
  「物件旋轉 30°」來轉六角，要轉 mesh 本身（或先 Apply Rotation）。
- 格點的列／行是用**座標**推出來的（`round(Y/dy)`、`round(X/dx)`），不是用頂點 index；
  這樣不管 Mesh Grid 的頂點順序怎麼排都不會錯位。

## 注意

- `Size Random` 讓單元大於格距時會互相重疊；要留縫就把 `Spacing` 拉到 1.05–1.2，
  或把 `Size Random` 壓在 0.1 以下。
- `Collection Count` 必須等於 collection 內實際的 mesh 數量，亂數 index 才不會超範圍
  （CLI 會自動處理；手動加 modifier 時要自己填，或設成 1 只用第一個物件）。
- 單元物件建議原點在中心、尺寸一致；`Collection Info` 的 `Reset Children` 會忽略
  子物件的位置/旋轉，所以 collection 裡的物件可以擺在旁邊當模板（示範檔就是這樣做，
  模板 collection 也設成 hide_render）。
- 換版本後 session 裡的舊 node group 不會自動更新，`apply` / `demo` 加 `--reload`。
