# Stan Geometry Nodes

Two scriptable **Geometry Nodes** groups for Blender, built from pure `bpy`
generators. Each group ships as **its own asset file** (Stan Box is not bundled
with Stan Array):

- **Stan Array** — a general-purpose array modifier: one node group with six
  layouts, three lattice types inside Grid, and three spacing rules:
  `Linear` · `Grid (XY / Hex / Triangle / Brick / Herringbone / Chevron / Basket)` · `Radial` · `Curve` · `Mesh` ·
  `Collection` — with `Step` / `Gap` / `Fit` spacing, orientation control, random
  variation, alternating mirror, and gradient.
- **Stan Box** — a parametric box generator: `Size XYZ` × `Scale Factor`, hollow
  cut-outs driven by fractional sizes, plug/cube fills, face shrink, corner
  rounding, and vertex-grid instancing with jitter / rotation / scale randomness.

![Stan Array demo scenes](demo/stan_contact.png)

![Stan Box demo scenes](demo/box_contact.png)

Built and tested on **Blender 4.5** (both assets also open and evaluate in 5.2).
The groups are marked as **Assets**, so they work in any `.blend` once you
Append / Link them.

> **Migrating from Hex Array:** the old standalone `Hex Array` group is now
> **`Mode = Grid` + `Grid Type = Hex`**. The old group (and its demo) still live in
> the [`v1.0.0`](https://github.com/stansu/stan-array/releases/tag/v1.0.0) release
> and in git history.

---

## Quick start

1. **File → Append…** — each group lives in its own asset file:
   `assets/geometry_nodes.blend` → **NodeTree** → `Stan Array`, or
   `assets/box_nodes.blend` → **NodeTree** → `Stan Box`.
2. Add a **Geometry Nodes** modifier to a mesh object and pick the group.
3. Fill the panel inputs. The modifier UI is grouped:
   Stan Array — `① 排列`, `② 環狀`, `③ 曲線與網格`, `④ 方向`, `⑤ 變化`, `⑥ 輸出`;
   Stan Box — `① 尺寸`, `② 網格`, `③ 空心`, `④ 實例`, `⑤ 輸出`.

> **Mode is an integer.** Blender 4.5 has no Python API for creating the items of a
> menu socket on a node-group interface, so a real dropdown cannot be scripted into
> the asset. The mapping is in the socket's tooltip:
> `0 Linear · 1 Grid · 2 Radial · 3 Curve · 4 Mesh · 5 Collection`.
> The same applies to `Grid Type`, `Spacing Mode`, `Align` and the axis inputs.

## Layouts (`Mode`)

| Mode | Layout | Point source | Main inputs |
|---|---|---|---|
| `0` | **Linear** | a line along `Direction` | `Count`, `Direction`, `Step`/`Gap`/`Length` |
| `1` | **Grid** | XY grid, hex lattice, triangle tiling or brick bond | `Count X`, `Count Y`, `Grid Type`, `Cell Size`, `Flat Top`, `Stagger` |
| `2` | **Radial** | a circle / arc | `Count`, `Radius`, `Arc`, `Start Angle` |
| `3` | **Curve** | points along a Curve object | `Curve`, `Count`, `Step`/`Gap` |
| `4` | **Mesh** | vertices / edge midpoints / face centres / random surface | `Surface`, `Mesh Mode`, `Density` |
| `5` | **Collection** | the **origin + rotation** of every mesh object in `Point Collection` | `Point Collection` |

`Surface` empty means "use the host object's own geometry". `Curve` and
`Point Collection` are only evaluated in their mode.

### Grid types

| `Grid Type` | Lattice | Pitch | Stagger |
|---|---|---|---|
| `0` **XY** | square | `Step` per axis, or Gap / Fit | none |
| `1` **Hex** | honeycomb | `Cell Size` (hex diameter) | `Flat Top` = false: odd **rows** shift `dx/2`; true: odd **columns** shift `dy/2` |
| `2` **Triangle** | triangular **tiling** — triangle centroids on a honeycomb | `Step` = triangle side | every other cell rotated 180° (up/down) |
| `3` **Brick** | staggered brick courses | `Step`/`Gap`/`Fit` per axis | `Stagger` × brick length, advanced every `Stagger Repeat` courses |
| `4` **Herringbone** | 2:1 brick herringbone | `Count X`/`Count Y` = 4W cells, 8 bricks per cell | `Pattern W` (L = 2W), centred |
| `5` **Chevron** | chevron / herringbone-V | `Count X`/`Count Y` = planks | `Pattern L`/`Pattern W`; **plain rectangular brick** — the node group shears it into a parallelogram |
| `6` **Basket Weave** | 2×2 blocks of H/V pairs | `Count X`/`Count Y` = blocks, 2 bricks per block | `Pattern W` (L = 2W), centred |

Hex math (`R = Cell Size / 2`):

| Hex orientation | dx | dy |
|---|---|---|
| pointy-top (`Flat Top` = false) | `√3·R` | `1.5·R` |
| flat-top (`Flat Top` = true) | `1.5·R` | `√3·R` |

`Cell Size` is the hex **diameter** (vertex to vertex) — make it slightly larger
than the tile to leave grout lines. Blender's 6-sided cylinder is pointy-top, so
use `Flat Top = false` with it. Hex and Triangle ignore `Spacing Mode`; the
lattice pitch comes from `Cell Size` / `Step`.

**Hex and Triangle are no longer the same lattice.** Hex places units at honeycomb
cell centres (for hex tiles). Triangle places equilateral-triangle **centroids** on
the dual honeycomb and rotates every other cell 180°, so triangle tiles actually
tessellate. `Count X` is the number of triangles per band and `Count Y` the number
of bands. The unit triangle must have its **centroid at the origin** and its apex
pointing **+Y** (Blender's 3-sided cylinder is already like this); down cells are
flipped automatically.

If you used Triangle as a plain point lattice in **v2.0.0**, reproduce it with
`Grid Type = Hex` and `Cell Size = Step / 0.866`.

Brick positions:

```
x = col·stepX + (floor(row / Stagger Repeat) · Stagger · stepX  mod  stepX)
y = row·stepY
```

`Stagger = 0` is stack bond, `0.5` running bond, `0.333` a 1/3 bond, `0.25` a
1/4 bond. `Stagger Repeat` keeps the same offset for N courses before advancing
(1 = every course). Brick uses the same `Step` / `Gap` / `Fit` as XY.

## Spacing (`Spacing Mode`)

| Value | Rule | Formula |
|---|---|---|
| `0` **Step** | fixed centre-to-centre distance | `step = Step` |
| `1` **Gap** | fit the unit's bounding box plus a gap | `step = extent + Gap` |
| `2` **Fit** | keep the count, fit the total length | `step = (Length − extent) / (Count − 1)` |

- `extent` for Linear is the unit bounding box projected on `Direction`:
  `|sx·dx| + |sy·dy| + |sz·dz|`.
- XY Grid applies the rule per axis (`extent.x`, `extent.y`, `Length`, `Length Y`).
- Fit makes the **outer edges flush**: the first unit's near edge starts at `0`,
  the last unit's far edge ends at `Length`. Step/Gap start at the origin.
- Curve `Step`/`Gap` resamples the curve by length; `Fit` distributes `Count`
  points across the whole curve (centres at the ends). Curve `Gap` uses the unit's
  XY diagonal as its footprint.
- Radial, Hex and Triangle ignore `Spacing Mode`.

## Orientation (`Align`)

| Value | Result |
|---|---|
| `0` **Natural** | Linear/Grid: as authored · Radial: rotated by the point angle · Curve: the curve frame (`Curve to Points`) · Mesh: **Z aligned to the surface normal** · Collection: the locator object's rotation |
| `1` **Forward** | align `Forward Axis` of the unit to the forward vector: `Direction` (Linear), curve tangent (Curve), edge direction (Mesh edges), radial tangent, or the locator's local X |
| `2` **Up** | align `Up Axis` to the up vector: surface normal (Mesh), radial outward, curve normal, or the locator's local Z |

Defaults: `Forward Axis = Y`, `Up Axis = Z` (Blender conventions).

## Variation

Applied **after** instancing, so it composes with each unit's own orientation:

| Input | Effect |
|---|---|
| `Unit Scale` | uniform scale multiplier for every unit (1 = as authored) |
| `Random Offset` | per-copy translation, `±Random Offset` on each axis |
| `Random Rotate` | per-copy random Euler rotation, degrees, `±` per axis |
| `Random Scale` | per-copy uniform scale, `1 ± Random Scale` |
| `Seed` | seed for all of the above |
| `Mirror` + `Mirror Axis` | every odd copy gets a negative scale on X / Y / Z |
| `Gradient Scale` | copy 0 is `1.0`, last copy is `Gradient Scale` |
| `Gradient Rotate` | last copy is twisted by this many degrees around Z |

## Unit source

- **Host** (default): the modifier object's own geometry is the unit.
- **Collection** (`Unit From Collection`): the unit is picked from `Collection`,
  randomly per copy using `Collection Count`. `Collection Info` uses *Separate
  Children* + *Reset Children*, so the unit objects' own transforms are ignored —
  apply scale, keep the meshes at the origin.
- **Collection locators** (`Mode = 5`): `Point Collection` is read for each mesh
  object's **origin and rotation** (via `Sample Index` on the instance domain) and
  the host geometry is placed there. Empties are invisible to Geometry Nodes, so
  use small mesh objects as locators. Locator **scale is ignored**.

## Parameters

**① Arrangement**

| Input | Type | Default | Notes |
|---|---|---|---|
| `Mode` | Int | 0 | 0 Linear · 1 Grid · 2 Radial · 3 Curve · 4 Mesh · 5 Collection |
| `Unit From Collection` | Bool | false | unit from `Collection` instead of the host |
| `Collection` | Collection | – | unit source (random pick when several) |
| `Collection Count` | Int | 1 | number of mesh objects, for the random pick |
| `Direction` | Vector | (1, 0, 0) | Linear direction, object space |
| `Count` | Int | 5 | Linear / Radial / Curve(Fit) |
| `Count X` `Count Y` | Int | 5 | Grid (Triangle: triangles per band × bands) |
| `Grid Type` | Int | 0 | 0 XY · 1 Hex · 2 Triangle · 3 Brick · 4 Herringbone · 5 Chevron · 6 Basket Weave |
| `Cell Size` | Float | 0.25 | hex diameter |
| `Flat Top` | Bool | false | hex orientation |
| `Stagger` | Float | 0.5 | Brick offset as a fraction of `stepX` (0 = stack, 0.5 = 1/2, 0.333 = 1/3) |
| `Stagger Repeat` | Int | 1 | courses per offset step (1 = every course, 2 = every two) |
| `Pattern L` | Float | 0.0 | Herringbone / Chevron / Basket brick length; 0 = derive from the unit (Herringbone / Basket use 2×`Pattern W`) |
| `Pattern W` | Float | 0.0 | brick width; 0 = derive from the unit |
| `Spacing Mode` | Int | 0 | 0 Step · 1 Gap · 2 Fit |
| `Step` | Float | 1.0 | metres (also Triangle side) |
| `Gap` | Float | 0.1 | metres |
| `Length` `Length Y` | Float | 5.0 | Fit totals |

**② Radial** — `Radius` (1.0), `Arc` (360°, degrees), `Start Angle` (0°).

**③ Curve & Mesh** — `Curve` (Object), `Surface` (Object), `Mesh Mode`
(0 vertices · 1 edges · 2 faces · 3 surface), `Density` (10 pts/m²), `Point
Collection`.

**④ Orientation** — `Align` (0 Natural · 1 Forward · 2 Up), `Forward Axis`
(0 X · 1 Y · 2 Z), `Up Axis`.

**⑤ Variation** — `Random Offset`, `Random Rotate`, `Unit Scale`, `Random Scale`,
`Seed`, `Mirror`, `Mirror Axis`, `Gradient Scale`, `Gradient Rotate`.

**⑥ Output** — `Realize` (false = instances, fast; true = real mesh for booleans,
export, or shading that needs unique geometry).

## Demo scenes

`demo/stan_*.png` (eleven scenes) are rendered by `tools/gn/stan_array_demo.py`:

| Scene | Shows |
|---|---|
| [fence](demo/stan_fence.png) | Linear + Gap (posts + rails) |
| [tiles](demo/stan_tiles.png) | Grid XY + Gap on a wall |
| [hex](demo/stan_hex.png) | Grid Type = Hex, three tiles picked at random |
| [tri](demo/stan_tri.png) | Grid Type = Triangle — a real triangular tiling with alternating up/down cells |
| [brick](demo/stan_brick.png) | Grid Type = Brick — 1/2 running bond with mortar and mixed brick colours |
| [patterns](demo/stan_patterns.png) | Herringbone, Basket Weave and Chevron side by side |
| [chevron](demo/stan_chevron.png) | Grid Type = Chevron top view: rectangular bricks sheared into planks, odd columns mirrored → 90° V |
| [lamp](demo/stan_lamp.png) | Radial with a unit offset from its origin |
| [bracelet](demo/stan_bracelet.png) | Curve with a cyclic path |
| [scatter](demo/stan_scatter.png) | Mesh → Surface, normals + random variation |
| [locators](demo/stan_locators.png) | Collection mode: origin + rotation of locator objects |

Open [`demo/stan_array_demo.blend`](demo/stan_array_demo.blend) to inspect the
fence scene: the host carries the `Stan Array` modifier with its inputs already
set.

## Herringbone, Chevron, Basket Weave

These three are 2D **patterns**, not simple course offsets:

- **Herringbone** (`4`): a 4W × 4W cell holds 8 bricks — four horizontal at
  `(0,0) (3,1) (2,2) (1,3)` and four vertical at `(2,0) (1,1) (0,2) (3,3)`,
  in units of `W`. Bricks cross cell edges, which is what makes the bond
  continuous. `Pattern W` sets the brick width, `L = 2W`; leave it at 0 to use the
  unit's own width, or set it to scale any unit (even a cube) into the right brick.
- **Basket Weave** (`6`): a 2W × 2W block holds two bricks, `Pattern W`
  controls the width (`L = 2W`). Blocks alternate
  orientation like a checkerboard: even blocks are two stacked horizontal bricks,
  odd blocks are two side-by-side vertical bricks. Requires a 2:1 brick.
- **Chevron** (`5`): a **plain rectangular brick**, centred at the origin — the
  node group shears it into a parallelogram before instancing:
  `x' = sx·x`, `y' = sy·y + c·x` with `sx = (L/L0)/√2`, `sy = (W/W0)·√2`,
  `c = √2·W/L0` (`L0`/`W0` = unit bbox, `L`/`W` = `Pattern L`/`Pattern W`).
  Planks sit at ±45° in a square lattice (`A = L/√2`, `H = W·√2`), with odd
  columns mirrored (`scale.x = -1`) to make the V; the slanted edges of
  neighbouring rows meet flush (gap = overlap = 0). The V angle is
  `2·atan(2W/L)` — 90° when `L = 2W`. Because the sheared unit is realized
  geometry, Chevron does **not** random-pick from the collection: keep one
  brick in it (`Pick Instance` is off, instance index is clamped to 0).
  `Pattern L` / `Pattern W` set the plank size; when both are 0 the size is
  derived from the unit's own bbox.

`Count X` / `Count Y` mean cells for Herringbone and Basket Weave (8 and 2 bricks
per cell), and planks for Chevron. All three are unit-size driven: author the
brick/parallelogram at its real size and keep it centred at the origin.

## Common brick & tile patterns

`Grid Type = Brick` covers every pattern that is a **repeating course offset**.
The value of `Stagger` is a fraction of one brick/tile length:

| Pattern | `Grid Type` | `Stagger` | `Stagger Repeat` | Typical use |
|---|---|---|---|---|
| Stack bond | Brick | `0` | `1` | modern tiles, stack bond feature walls |
| Running bond 1/2 | Brick | `0.5` | `1` | brick walls, subway tile |
| 1/3 bond | Brick | `0.333` | `1` | 300×600 large-format tiles |
| 1/4 bond | Brick | `0.25` | `1` | 600×1200 tiles, plank tile |
| 1/5 / 1/6 bond | Brick | `0.2` / `0.167` | `1` | long planks, minimal lippage |
| Offset every 2 courses | Brick | `0.5` | `2` | decorative block work |
| Hexagon | Hex | – | – | honeycomb tile, 200 mm across flats |
| Triangle | Triangle | – | – | triangle tiling, `Step` = side |
| Penny round / mosaic | XY | – | – | circles in a square grid, use `Gap` |
| Diagonal / 45° | XY or Brick | – | – | rotate the **host object** 45° |

Patterns that are **not** a single course offset use the pattern grid types:

- **Herringbone / chevron** — bricks alternate 90°: use `Grid Type = 4`
  (Herringbone) or `5` (Chevron, a rectangular brick sheared into planks).
- **Basket weave** — 2×2 blocks alternate orientation: `Grid Type = 6`.
- **English / Flemish bond** — header and stretcher courses alternate; use two
  arrays (or a Collection with two brick lengths) rather than `Stagger`.

Typical real-world sizes (use metres in Blender; joints are the `Gap`):

| Material | Unit size | Joint |
|---|---|---|
| UK brick | 215 × 65 × 102.5 mm | 10 mm |
| US modular brick | 194 × 57 × 92 mm | 10 mm |
| Subway tile | 75 × 150 mm | 2–3 mm |
| Large-format tile | 300 × 600 mm | 2–3 mm, 1/3 bond |
| Plank tile | 150 × 900 mm | 2 mm, 1/3 or random |
| Hex tile | 200 mm across flats | 3 mm |
| Mosaic | 25 × 25 mm | 2 mm |

For brick, author the brick mesh at its real size and use `Gap` = joint; the
`Gap` mode measures the unit bounding box, so the pitch becomes
`brick + joint` automatically.

## Stan Box parameters

**Stan Box** is a **generator**, not an array: the cube is built inside the node
group from the inputs below, and the host object's geometry is replaced by the
box (or by boxes instanced onto the cube's vertices).

**① Size**

| Input | Type | Default | Notes |
|---|---|---|---|
| `Size XYZ` | Vector | (1, 1, 1) | box size, metres |
| `Scale Factor` | Float | 1.0 | uniform multiplier applied to `Size XYZ` |

**② Grid**

| Input | Type | Default | Notes |
|---|---|---|---|
| `Vertices Per Side` | Int | 2 | cube vertices per side; 2 = plain box, 3 → 3×3×3 = 27 instance points |
| `Subdivide` | Int | 0 | subdivision passes (0–6), used by `Corner Mode = Subdivide` |

**③ Hollow**

| Input | Type | Default | Notes |
|---|---|---|---|
| `Hollow` | Bool | false | punch through the faces the size fraction opens, keeping the edge frame |
| `Wall Thickness` | Float | 0.1 | inner insert size = \|size\| − 2 × thickness |
| `Fill Mode` | Int | 0 | 0 None · 1 Plug · 2 Cube |
| `Shrink Faces` | Bool | false | pull the kept faces toward the centre (closed chevron-ish bricks) |
| `Shrink Scale` | Float | 0.5 | 0 = collapse to centre, 1 = no shrink |
| `Corner Mode` | Int | 0 | 0 None · 1 Subdivide |

**④ Instances**

| Input | Type | Default | Notes |
|---|---|---|---|
| `Use Instances` | Bool | false | instance the box onto the cube's vertices |
| `Jitter` | Float | 0.0 | random translation radius per instance |
| `Rotation Range` | Float | 0.0 | random Euler amplitude, **radians** |
| `Scale Random` | Float | 0.0 | per-instance uniform scale, `1 ± Scale Random` |
| `Seed` | Int | 0 | seed for all randomness (instance index + seed) |

**⑤ Output**

| Input | Type | Default | Notes |
|---|---|---|---|
| `Realize Instances` | Bool | true | expand instances into a real mesh (no effect when `Use Instances` is off) |
| `Store Attributes` | Bool | false | store `box_index` / `box_seed` / `box_random` / `box_scale` on the instance domain |
| `Shade Smooth` | Bool | false | smooth shading on the result |
| `Material` | Material | – | material slot applied to the generated geometry |

### How the hollow cut-outs work

The opening is derived from the size itself, so no extra "open axis" input is
needed:

```
dims   = Size XYZ × Scale Factor
offset = dims − floor(|dims|)
cut    = dot(face normal, offset) > 0.001
```

- **integer** axis (`offset = 0`) → nothing is cut → a closed box
- **fractional** axis (`offset > 0`) → the face on the **+** side is cut
- **negative** axis (`offset < 0`) → the face on the **−** side is cut

Cut faces are deleted (`DeleteGeometry` = `ONLY_FACE`), so the shell keeps the
edge frame — an open carton. `Hollow = false` keeps every face. `Fill Mode = 1
(Plug)` adds an inner plane at `|size| − 2 × Wall Thickness` on each **Z**
opening (`MeshGrid` + `Transform`, with the plug z-shifted by
`sign(offset.z) × inner.z / 2`); `Fill Mode = 2 (Cube)` returns a solid box.
`Shrink Faces` scales the surviving faces toward the box centre
(`ScaleElements` = FACE) before the delete, which closes the opening into a
chevron-ish brick.

### Fill Mode / Corner Mode values

| Value | `Fill Mode` | `Corner Mode` |
|---|---|---|
| `0` | `None` — open box | `None` — sharp corners |
| `1` | `Plug` — inner insert plane, Z openings only | `Subdivide` — rounded approximation |
| `2` | `Cube` — solid box | – |

CLI aliases: `fill=none|open|plug|cube`, `corner=none|subdivide|round`
(`open` ≡ `none`, `round` ≡ `subdivide`). The values are integers; the mapping is
written in the socket tooltip.

### Box demo scenes

`demo/box_*.png` (five scenes) are rendered by `tools/gn/box_demo.py`:

| Scene | Shows |
|---|---|
| [solid](demo/box_solid.png) | Cardboard, crate and flat ink boxes — `Size XYZ` + `Scale Factor` |
| [hollow](demo/box_hollow.png) | Fractional size opens the top; an integer size stays closed |
| [plug](demo/box_plug.png) | Hollow + `Fill Mode = Plug` insert, plus a foam pad |
| [scatter](demo/box_scatter.png) | `Use Instances` on a 3×3×3 vertex grid with jitter / rotation / scale |
| [corner](demo/box_corner.png) | `Corner Mode = Subdivide` + `Shade Smooth` rounded clay box |

Open [`demo/box_demo.blend`](demo/box_demo.blend) to inspect the solid scene: the
host carries the `Stan Box` modifier with its inputs already set.

## Limits / gotchas

- `Gap` measures the unit's **bounding box**, not the silhouette. Rotated or
  irregular units can still touch; add a little extra gap.
- `Fit` keeps the count and changes the spacing. If the unit is larger than
  `Length`, the step clamps to 0.
- Hex and Triangle build a ragged staggered edge by design. A backing panel hides
  it; use `Flat Top` to choose which edge is ragged for Hex.
- Triangle expects a unit triangle whose centroid sits at the origin and whose apex
  points +Y; the down cells are rotated 180°, so an off-centre triangle will show
  seams.
- For `Unit From Collection`, the bounding box used by `Gap`/`Fit` comes from the
  realised collection. Keep unit meshes at the origin.
- `Collection Count` must match the real number of mesh objects, or the random
  pick can go out of range (the CLI fills it in).
- `Mirror` produces negative scales (flipped normals) on the mirrored copies. That
  is expected for symmetric parts; use `Realize` + *Flip Faces* if you need clean
  normals.
- The host object's original geometry is replaced by the array.

Stan Box:

- `Vertices Per Side` must be **≥ 2** — on Blender 4.5 `MeshCube` with 1 vertex
  collapses to a single point and poisons the whole group.
- Cut-outs are keyed to the **size fraction**, so an axis that is an integer is
  always closed. Use a fractional size (e.g. `0.75`) to open that axis, and a
  negative size to open the opposite side.
- `Fill Mode = Plug` caps **Z openings only**. An X or Y opening needs
  `Fill Mode = Cube` (or `Hollow = false`) — 4.5 has no generic cap node to plug
  an arbitrary axis.
- Corner rounding is an **approximation**: 4.5 has no `Bevel` node and no
  `MergePoints`, so `Corner Mode = Subdivide` + `Shade Smooth` only softens the
  silhouette; it does not produce a real bevel radius.
- `Rotation Range` is in **radians** (`0`–`2π`), unlike Stan Array's
  `Random Rotate`, which is in degrees.
- `Realize Instances = false` keeps instances, which are cheap but cannot be
  booleaned or exported.
- `Store Attributes` names are fixed: `box_index`, `box_seed`, `box_random`,
  `box_scale` (instance domain; moved to the point domain after realize).
- The host object's original geometry is replaced by the box.

---

## CLI, build and tests

```bash
# rebuild both asset files (each group → its own .blend, headless)
python3 tools/gn/gn.py build
python3 tools/gn/gn.py build --group box    # only assets/box_nodes.blend

# list / inspect a group (needs a running Blender + Blender Bridge)
python3 tools/gn/gn.py inputs
python3 tools/gn/gn.py inputs --group box
python3 tools/gn/gn.py apply --object "Host" \
    --set mode=grid --set grid_type=hex --set cell=0.22 --set count_x=12
python3 tools/gn/gn.py apply --group stan --object "Host" \
    --set mode=linear --set spacing_mode=fit --set length=4 --set count=9
python3 tools/gn/gn.py apply --group box --object "Host" \
    --set hollow=1 --set wall=0.08 --set fill=plug --set vertices=3 \
    --set use_instances=1 --set jitter=0.45 --set seed=7

# render the eleven demo scenes + contact sheet
python3 tools/gn/gn.py stan-demo --samples 32 --res 760

# render the five box demo scenes + contact sheet
python3 tools/gn/gn.py box-demo --samples 24 --res 640

# smoke tests (43 checks: every mode, lattice, brick bond, patterns, chevron shear, spacing, align, mirror, gradient, realize, fit guard, enum wiring)
blender -b --factory-startup --python tools/gn/test_stan_array.py

# smoke tests (27 checks: size, grid floor, hollow cut direction, plug/cube fill, shrink, corner, instancing + randomness, attributes, material, enum wiring)
blender -b --factory-startup --python tools/gn/test_box_generator.py
```

`apply` accepts enum names (`mode=grid`, `grid_type=hex`, `spacing_mode=fit`,
`align=up`, `mesh_mode=surface`, `mirror_axis=z`, `fill=plug`,
`corner=subdivide`, …) as well as numbers. Data-block sockets (`Curve`,
`Surface`, `Point Collection`, `Material`) and the unit `Collection` are not set
through `--set`; use `--collection` for the unit collection and the modifier UI
for the object/material sockets. `--set` also does not convert **Vector** inputs,
so `Size XYZ` is set in the modifier UI.

The CLI spawns Blender 4.5 when present (`BLENDER_BIN` overrides it); the asset
itself works in 4.5 and 5.2. The bridge is optional — only `inputs`, `apply`,
`list` and `reload` need a live Blender; building and demo renders are headless.

### Repository layout

```
assets/geometry_nodes.blend    Stan Array node group (asset)
assets/box_nodes.blend         Stan Box node group (asset — separate file)
demo/                          demo scenes, renders, contact sheets
tools/gn/                      generators (stan_array.py, box_generator.py), build, CLI, tests, demos, contact sheet
tools/blender-bridge/          optional localhost bridge add-on for the CLI
```

### License

MIT — see [LICENSE](LICENSE).

---

## 中文說明

**Stan Array** 是一個 Geometry Nodes modifier group：`File → Append` →
`assets/geometry_nodes.blend` → `NodeTree` → `Stan Array`，加到物件上，選 **Mode**：

- `0` 線性（Direction 方向）
- `1` 網格（**Grid Type**：`0` XY、`1` Hex、`2` Triangle、`3` Brick、`4` Herringbone、`5` Chevron、`6` Basket Weave）
- `2` 環狀（Radius、Arc、Start Angle）
- `3` 曲線（指定 Curve 物件）
- `4` Mesh（頂點／邊中點／面中心／表面隨機；Surface 留空用自己）
- `5` Collection（讀 `Point Collection` 裡每個物件的**原點＋旋轉**）

**Grid Type = Hex** 就是原本的 Hex Array：`Cell Size` 是六角外徑，
`Flat Top` 切 pointy/flat，`Count X/Y` 是格數。Blender 的 6 邊柱體是 pointy-top，
所以配 `Flat Top = false`。

**Grid Type = Triangle** 是真正的三角形貼磚：三角形質心排在蜂巢晶格上，
每隔一格自動轉 180°（up/down 交錯），所以三角形會密合。`Step` 是三角形邊長，
`Count X` 是每帶的三角形數、`Count Y` 是帶數。單元的**質心要在原點、頂點朝 +Y**
（Blender 的 3 邊柱體本來就是這樣）。

**Grid Type = Brick**：`Stagger` 是磚長的錯位比例（`0` 對齊、`0.5` 1/2、`0.333` 1/3、
`0.25` 1/4），`Stagger Repeat` 是每幾列推進一次（1 = 每列）。Brick 跟 XY 一樣吃
`Step` / `Gap` / `Fit`；用 `Gap` 當灰縫最方便，pitch 會自動是「磚 + 縫」。

**Herringbone（4）／Basket Weave（6）** 需要 2:1 的磚（長 = 2×寬、原點在中心）；
`Count X/Y` 是 4W 格／2W 區塊，每格分別 8／2 塊。**Chevron（5）** 給一塊**長方形磚**
（原點置中）即可：node group 會先斜切（shear）成平行四邊形再實例化——
`x' = sx·x、y' = sy·y + c·x`，`sx = (L/L0)/√2、sy = (W/W0)·√2、c = √2·W/L0`
（`L0/W0` 是單元 bbox，`L/W` 是 `Pattern L/W`）。每隔一欄 `scale.x = -1` 鏡像成 V，
斜邊互相貼合（gap/overlap = 0），`L = 2W` 時 V 為 90°。斜切後的單元是 realized
mesh，所以 Chevron 不會從 Collection 隨機挑款：集合裡只放一塊磚。

Hex/Triangle 不受 `Spacing Mode` 影響，間距由 `Cell Size` / `Step` 決定。

`Spacing Mode`：`0` Step（中心距固定）、`1` Gap（用 bounding box 貼齊留縫）、
`2` Fit（數量不變，外緣對齊 `Length`；Grid 另有 `Length Y`）。

`Align`：`0` Natural（各模式預設方向）、`1` Forward（前方軸對齊方向／切線）、
`2` Up（上方軸對齊法線）。`Forward Axis` 預設 Y、`Up Axis` 預設 Z。

`Unit From Collection` 打開時，單元從 `Collection` 隨機挑（`Collection Count` 要填對，
CLI 會自動填）。Collection 模式用的是 locator 物件的原點與旋轉，**不吃 scale**；
Empty 物件 GN 看不到，請用小 mesh 當 locator。

變化：`Unit Scale`（整體倍率）、`Random Offset`／`Random Rotate`／`Random Scale`／
`Seed`、`Mirror`＋`Mirror Axis`（每隔一份鏡像）、`Gradient Scale`／`Gradient Rotate`
（沿順序漸變）。`Realize` 打開會輸出實際 mesh（布林、匯出用）。

**Mode / Grid Type 是整數**：Blender 4.5 的 node group menu socket 沒辦法用 Python
建選項，所以沒做成下拉選單；對照寫在 tooltip 與上面的表。

`Gap` 是用 bounding box 量的，不是精確外型；`Fit` 在單元比 `Length` 大時間距會變 0。
Unit collection 的物件請把 scale 套用、留在原點（`Reset Children` 會忽略物件變換）。

**Stan Box** 是**盒生成器**（不是陣列）：`File → Append` →
`assets/box_nodes.blend` → `NodeTree` → `Stan Box`（Stan Box 有自己的資產檔，不與 Stan Array 放在一起）。
立方體在 node group 裡用輸入參數建出來，
 host 物件原本的 geometry 會被盒（或盒實例）取代。

**① 尺寸**：`Size XYZ`（盒尺寸，公尺）、`Scale Factor`（整體倍率）。
**② 網格**：`Vertices Per Side`（每邊頂點數，2 = 基本盒；3 → 3×3×3 = 27 個實例點）、
`Subdivide`（細分层數 0–6，給圓角用）。
**③ 空心**：`Hollow`（挖穿面、保留邊線框架）、`Wall Thickness`（内塞尺寸 =
 |尺寸| − 2×壁厚）、`Fill Mode`、`Shrink Faces`／`Shrink Scale`、`Corner Mode`。
**④ 實例**：`Use Instances`（把盒實例化到立方體頂點）、`Jitter`（随机位移半徑）、
`Rotation Range`（随机旋轉幅度，**弧度**）、`Scale Random`（`1 ± 幅度`）、`Seed`。
**⑤ 輸出**：`Realize Instances`（展開成真實 mesh）、`Store Attributes`（存
 `box_index`/`box_seed`/`box_random`/`box_scale`）、`Shade Smooth`、`Material`。

开口由**尺寸本身**決定，不需要額外「开口軸」輸入：

```
dims   = Size XYZ × Scale Factor
offset = dims − floor(|dims|)
cut    = dot(面法線, offset) > 0.001
```

- 某軸是**整數**（`offset = 0`）→ 不挖 = 關閉的盒
- 某軸是**小數**（`offset > 0`）→ 挖掉 **+** 方向那面
- 某軸是**負值**（`offset < 0`）→ 挖掉 **−** 方向那面

被挖的面用 `DeleteGeometry (ONLY_FACE)` 移除，所以殼會留下邊線框架（像開口紙箱）。
`Hollow = false` 則保留所有面。`Fill Mode = 1 (Plug)` 在**每個 Z 轴开口**放一块
内塞平面（尺寸 = |尺寸| − 2×壁厚，用 `MeshGrid` + `Transform`，z 依
`sign(offset.z) × 内塞.z / 2` 位移）；`Fill Mode = 2 (Cube)` 退回實心盒。
`Shrink Faces` 在挖穿前把保留面往盒中心縮（`ScaleElements` = FACE），
把开口收成 chevron 磚。

| 值 | `Fill Mode` | `Corner Mode` |
|---|---|---|
| `0` | `None` 開放盒 | `None` 尖角 |
| `1` | `Plug` 内塞平面（只塞 Z 轴开口） | `Subdivide` 圓角近似 |
| `2` | `Cube` 實心 | – |

CLI 別名：`fill=none|open|plug|cube`、`corner=none|subdivide|round`
（`open` = `none`、`round` = `subdivide`）。這些值是整數，對照寫在 tooltip。

Stan Box 注意：`Vertices Per Side` 要 **≥ 2**（4.5 的 `MeshCube` 給 1 會退化成
單點，整個 group 都壞掉）。开口看尺寸的小數部分，所以整數軸永遠關閉——要开口
就用小數尺寸（例如 `0.75`），負尺寸開 opposite 側。`Fill = Plug` 只塞 **Z**，
X/Y 开口請改用 `Fill = Cube` 或關掉 `Hollow`。圓角是**近似**：4.5 沒有 `Bevel`
也沒有 `MergePoints`，`Corner = Subdivide` + `Shade Smooth` 只把邊線柔和，沒有真實
bevel 半徑。`Rotation Range` 是**弧度**（跟 Stan Array 的 `Random Rotate` 用角度不同）。
`--set` 不支援 **Vector** 輸入，`Size XYZ` 與 `Material` 要在 modifier UI 裡填。

**Stan Box 示範場景**（`demo/box_*.png`，五個，由 `tools/gn/box_demo.py` 渲染）：

| 場景 | 內容 |
|---|---|
| [solid](demo/box_solid.png) | 紙箱、木板箱、扁盒 — `Size XYZ` + `Scale Factor` |
| [hollow](demo/box_hollow.png) | 小數尺寸挖開頂面；整數尺寸保持關閉 |
| [plug](demo/box_plug.png) | Hollow + `Fill Mode = Plug` 内塞，另加一塊泡棉 |
| [scatter](demo/box_scatter.png) | `Use Instances` 排在 3×3×3 頂點上，加 jitter／旋轉／大小隨機 |
| [corner](demo/box_corner.png) | `Corner Mode = Subdivide` + `Shade Smooth` 的圓角黏土盒 |

`demo/box_demo.blend` 裡是 solid 場景，host 上已經帶著填好參數的 `Stan Box` modifier。

### 建置與測試

```bash
python3 tools/gn/gn.py build                       # 重建兩個 asset 檔（各自一個：geometry_nodes.blend = Stan Array、box_nodes.blend = Stan Box）
python3 tools/gn/gn.py build --group box           # 只重建 assets/box_nodes.blend
blender -b --factory-startup --python tools/gn/test_stan_array.py   # 43 項檢查
blender -b --factory-startup --python tools/gn/test_box_generator.py # 27 項檢查
python3 tools/gn/gn.py stan-demo                   # 十一個陣列示範場景 + contact sheet
python3 tools/gn/gn.py box-demo                    # 五個盒示範場景 + contact sheet
python3 tools/gn/gn.py inputs --group box          # 列出 Stan Box 參數
python3 tools/gn/gn.py apply --group box --object "Host" --set hollow=1 --set fill=plug
```

Asset 以 Blender 4.5 建置／測試，5.2 可正常開啟與評估（CLI 會優先找 4.5）。
