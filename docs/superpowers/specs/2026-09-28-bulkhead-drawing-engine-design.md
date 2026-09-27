# Bulkhead Drawing Engine — v1 Design

**Date:** 2026-09-28
**Status:** Approved in brainstorming, pending spec review
**Project:** AutoCAD Automation for Shipyard (build #1 of 3)

## 1. Context

Draftsmen at the shipyard client spend ~4 hours per ship drawing, much of it on
repetitive work: title block, layers, dimensions, standard details (stiffeners,
brackets, frames), and re-checking the same things every time. The target is
~1 hour. (The 4 h → 1 h figure is an estimate; it has not been measured yet.)

The overall project is three separate builds:

1. **Automation engine** (this spec) — rule-based: parameters → complete drawing.
2. **AI assistant** — an MCP server that lets Claude call the engine's tools from
   plain-language instructions and review drawings. Depends on build #1.
3. **Building-drawing rule pack** — reuses the engine for building drawings
   (government / JKR route). Later.

**Guiding principle:** the AI never draws coordinates. Code draws; the AI (build
#2) only picks tools and fills in parameters.

## 2. Goal and scope

v1 produces one drawing type end to end: a **transverse bulkhead with its frame
layout**, from a small job file, as a DXF that opens in AutoCAD.

### In scope

- Bulkhead elevation (looking forward) from a straight-line polygon outline.
- Vertical stiffeners at a set spacing, clipped exactly to the outline.
- End brackets at stiffener ends (top and/or bottom).
- Frame layout strip with frame numbers and spacing dimensions.
- BOM (plate, stiffeners, brackets) with weights.
- Title block with editable attributes; all entities on standard layers.
- Deterministic rule checks (errors block generation; warnings are reported).
- PNG preview, BOM CSV, and a text check report alongside the DXF.

### Out of scope for v1

Manholes and openings, horizontal stringers/girders, curved hulls from offset
tables, paper-space layouts/viewports, weld symbols, non-uniform frame spacing,
drawing live inside an AutoCAD session, and the AI layer.

## 3. Key decisions

| Decision | Choice | Reason |
|---|---|---|
| Output mechanism | Python + `ezdxf` writing DXF files | No AutoCAD or .NET SDK on the dev machine; DXF is fully testable here and opens in any AutoCAD version including LT; build #2 can wrap Python functions directly. |
| Company standard | Placeholder standard in `config/standard.yaml` | Client's real standard not yet available; swapping it later changes config only, not code. |
| Outline input | Straight-line polygon, half outline mirrored about CL | Covers flat-bottom, chine and chamfered-bilge bulkheads; guarantees symmetry; halves the input. |
| Sheet space | Model space, border and annotations scaled by the sheet scale | Simplest, viewable in every DXF viewer, and common shipyard practice. Paper space can come later. |
| Sheet scale | One scale per sheet, picked automatically | The largest scale (smallest denominator) from the allowed list at which every view fits its zone. |
| Input format | YAML job file + CLI | Plain text, diff-able, easy for build #2 to generate. |

## 4. Inputs

### 4.1 Job file (`jobs/<name>.yaml`)

```yaml
project:
  name: "OSV 60m"
  drawing_no: "SY-101"
  title: "TRANSVERSE BULKHEAD AT FR25"
  drawn_by: "AH"
  revision: "A"
  date: 2026-09-28          # optional; defaults to today
frames:
  first: 20
  last: 30
  spacing: 600              # mm, uniform
bulkhead:
  at_frame: 25
  outline_half:             # (y from CL, z from baseline), mm, starboard half
    - [0, 0]
    - [3600, 0]
    - [4500, 900]            # 900 x 900 bilge chamfer
    - [4500, 3500]
    - [0, 3500]
  plate:      { thickness: 8, grade: "AH36" }
  stiffeners: { profile: "HP 160x8", spacing: 600, first_at: 300 }
  brackets:   { top: true, bottom: true, size: 250, thickness: 8 }
```

Validation (via pydantic; failures report the field path and reason, exit code 2,
no files written):

- All lengths > 0 except `first_at`, which is ≥ 0.
- `frames.last` > `frames.first`.
- `outline_half`: at least 3 points; every point has y ≥ 0 and z ≥ 0; the
  first and last points lie on the centreline (y = 0).
- `stiffeners.profile` must parse as `FB bxt`, `L axbxt` or `HP hxt`.

### 4.2 Company standard (`config/standard.yaml`)

It holds everything that is "company style", with placeholder values for now:

- **Sheet:** size (A1, 841 × 594 mm), margins, view zones, and the allowed scale
  denominators `[20, 25, 50, 100]`.
- **Layers:** name, ACI colour, linetype and lineweight for `BORDER`, `TITLE`,
  `PLATE`, `STIFFENER`, `BRACKET`, `CENTRELINE` (CENTER linetype), `FRAME`,
  `DIM`, `TEXT` and `BOM`. Layer names are looked up through role keys, so
  renaming a layer is a config-only change.
- **Text heights** in paper mm; model heights are paper height × scale.
- **Dimension style:** arrow size, text height and offsets in paper mm, with
  DIMSCALE = sheet scale.
- **Title block:** field list (`PROJECT`, `DWG_NO`, `TITLE`, `SCALE`, `DRAWN`,
  `DATE`, `REV`), plus the block geometry.
- **Rule limits:** `max_stiffener_spacing` (placeholder 700 mm).

### 4.3 Profile library (`config/profiles.yaml`)

- **FB** (flat bar, b × t): kg/m = b · t · 7.85e-3. Calculated, exact.
- **L** (angle, a × b × t): kg/m = (a + b − t) · t · 7.85e-3. Calculated; root
  radius ignored, so it is marked "approx." in the BOM.
- **HP** (bulb flat): kg/m must come from an explicit library entry. v1 ships
  entries flagged `placeholder: true`, and using one raises a warning. An HP size
  that is missing from the library is an error.
- Steel density: 7850 kg/m³.

## 5. Geometry and rules

**Coordinates.** Bulkhead elevation looking forward: +y is to starboard (drawn to
the right) and +z is up from the baseline. The frame strip uses x = frame_no ×
spacing, with FR0 at x = 0.

**Outline.** Full polygon = `outline_half` + its mirror image (y → −y), traversed
in reverse without duplicating the centreline points. Collinear vertices (e.g. the
centreline points in the middle of a straight top or bottom edge) are then removed.
Rule errors: fewer than 3 distinct vertices, self-intersection, zero area.

**Stiffener positions.** y_k = first_at + k · spacing for k = 0, 1, 2, … while
y_k < the maximum half-breadth of the outline. Each position is mirrored to −y_k.
If first_at = 0, the y = 0 stiffener appears once and is not mirrored.

**Clipping.** Each vertical line y = y_k is intersected with the polygon. Every
interior segment of non-zero length becomes one stiffener, running from its
bottom end to its top end. Convex outlines give one segment per line; stepped
outlines may give several.

**Brackets.** Brackets go at the bottom end if `brackets.bottom`, and at the top
end if `brackets.top`. Each bracket is a triangle with vertices:

- P: the stiffener end point, which lies on the outline;
- P moved `size` along the stiffener into the plate;
- P moved `size` along the outline edge that leaves P towards the centreline
  (towards +y for a stiffener on y = 0). If P is on a vertex, use the edge whose
  far end has the smaller |y|.

Rule errors:

- `size` ≥ stiffener length / (number of bracketed ends);
- the outline edge from P towards the centreline is shorter than `size`.

**Rule checks** (`checks.py`):

| Rule | Severity |
|---|---|
| Invalid outline (fewer than 3 vertices, self-intersecting, zero area) | error |
| `at_frame` outside `[first, last]` | error |
| No stiffener positions intersect the outline | error |
| Bracket too large for its stiffener, or doesn't fit on the boundary edge | error |
| Unknown profile | error |
| Drawing doesn't fit the sheet at any allowed scale | error |
| `stiffeners.spacing` > `max_stiffener_spacing` | warning |
| HP profile weight taken from a placeholder entry | warning |

## 6. Output

The command `shipdraw build <job.yaml> [-o OUT_DIR] [--no-preview]` writes the
following files to `OUT_DIR` (default `out/`), each named by `drawing_no`:

1. **`<dwg>.dxf`**: one A1 sheet, in DXF version R2018.
   - **Bulkhead elevation** (top-left zone): plate outline (`PLATE`),
     centreline and baseline (`CENTRELINE`), stiffeners (`STIFFENER`), brackets
     (`BRACKET`). Labels (`TEXT`): `PL 8 AH36`, `HP 160x8 @ 600 TYP.`,
     `BKT 250x250x8 TYP.`, `CL`, `BL`, and a view title
     `BULKHEAD AT FR25 (LOOKING FWD)`. Dimensions (`DIM`, real DIMENSION
     entities): the stiffener spacing chain along the bottom, the overall
     breadth, and the overall height.
   - **Frame layout strip** (bottom-left zone): frame ticks FR*first*–FR*last*
     (`FRAME`), frame numbers, a spacing dimension chain, and the bulkhead frame
     highlighted on `PLATE` with the label `BHD`.
   - **BOM table** (right zone, above the title block, on `BOM`), with columns
     ITEM, DESCRIPTION, QTY, LENGTH (mm), WEIGHT (kg). Rows:
     - the plate;
     - stiffeners, one row per distinct cut length (rounded to the nearest mm);
     - brackets;
     - a TOTAL row.
   - **Title block**: a block definition with ATTDEFs, inserted bottom-right and
     scaled by the sheet scale, with its attributes filled from the job file.
     The border is drawn on `BORDER`.
2. **`<dwg>.png`**: preview rendered through ezdxf's drawing add-on and matplotlib.
   Skipped with `--no-preview`.
3. **`<dwg>-bom.csv`**: the same rows as the BOM table.
4. **`<dwg>-report.txt`**: rule-check results and a summary (stiffener count,
   total weight, scale, generation time). The same summary is printed to stdout.

**BOM weights.**

- Plate: polygon area (shoelace formula) × thickness × 7.85e-6 kg/mm³.
- Stiffeners: total length in metres × kg/m.
- Brackets: the sum of the actual triangle areas × thickness × density.

**Atomic writes.** Each file is written to a temporary name in `OUT_DIR` and then
moved into place with `os.replace`. If the run fails before writing, no output
files are created.

**Exit codes:** 0 = success (with or without warnings); 1 = rule errors, nothing
written; 2 = invalid job file or bad usage.

## 7. Architecture

The core rule is that geometry and rules never import `ezdxf`. Only `render/`
knows about DXF.

```
jobs/*.yaml → job.py → structure.py → checks.py → render/ → .dxf / .png
                            └──→ bom.py → .csv + BOM table
```

| Unit | Responsibility | Depends on |
|---|---|---|
| `config/standard.yaml` | Company standard (section 4.2) | (none) |
| `config/profiles.yaml` | Profile library (section 4.3) | (none) |
| `shipdraw/job.py` | Load and validate a job file into typed models | pydantic, PyYAML |
| `shipdraw/standard.py` | Load `standard.yaml` and `profiles.yaml` into typed models | pydantic, PyYAML |
| `shipdraw/geometry.py` | Mirroring, polygon validity and area, vertical-line clipping, bracket triangles | (none) |
| `shipdraw/structure.py` | Job → parts (frame positions, plate, stiffeners, brackets) | geometry |
| `shipdraw/bom.py` | Parts → BOM rows | standard (profiles) |
| `shipdraw/checks.py` | Parts + job → list of errors and warnings | structure, standard |
| `shipdraw/render/sheet.py` | Layers, linetypes, dim style, border, title block, scale selection | ezdxf, standard |
| `shipdraw/render/bulkhead_view.py` | Draws the elevation | ezdxf |
| `shipdraw/render/frame_view.py` | Draws the frame strip | ezdxf |
| `shipdraw/render/bom_table.py` | Draws the BOM table | ezdxf |
| `shipdraw/render/preview.py` | DXF → PNG | ezdxf, matplotlib |
| `shipdraw/cli.py` | `shipdraw build`: runs the pipeline and writes the outputs | all of the above |

**Project layout:**

- `pyproject.toml`
- `src/shipdraw/…`
- `tests/…`
- `config/…`
- `jobs/bhd-fr25.yaml` (the example job from section 4.1)
- `.gitignore` (excludes `.venv/` and `out/`)

**Stack:** Python 3.13 in a local `.venv`, with `ezdxf`, `pydantic`, `PyYAML`,
`matplotlib` and `pytest`.

**Link to build #2:** the MCP server will import `structure`, `checks`, `bom`
and the CLI's pipeline function directly. The pipeline must therefore be
callable as a function, `build(job, standard, out_dir) -> BuildResult`, and not
only through the CLI.

## 8. Testing

Development is test-first (TDD). Tests are layered:

1. **Geometry unit tests.** Mirroring produces a symmetric polygon; the shoelace
   area is correct; clipping at y = 3900 on the example outline (on the bilge
   chamfer) gives z ∈ [300, 3500]; collinear centreline vertices are removed; every bracket triangle lies inside the plate polygon;
   self-intersection is detected.
2. **Structure, rule and BOM tests.** The example job gives 14 stiffeners at
   ±300, ±900, …, ±3900; the bottom brackets of the ±3900 stiffeners lie
   along the sloped chamfer. Frame x-positions are correct. Each rule in section 5
   gets one passing and one failing case. BOM weights match hand calculations.
3. **DXF round-trip tests.** Generate the file, reopen it with ezdxf, and run
   `audit()` expecting zero errors. Also check that every standard layer exists,
   every entity is on a standard layer, the title-block attributes match the job,
   and the DIMENSION count is as expected.
4. **Visual check.** Render the PNG preview of the example job and inspect it
   before calling v1 complete.
5. **User acceptance (manual, in AutoCAD).** Open `SY-101.dxf` in real AutoCAD
   and check that:
   - it opens with no errors or recovery prompt;
   - the layers match `standard.yaml`;
   - the dimensions are editable;
   - the title block edits with `ATTEDIT`.

   Until this passes, v1 is reported as "verified in ezdxf, pending AutoCAD
   check".

## 9. Success criteria

- `shipdraw build jobs/bhd-fr25.yaml` exits 0 and writes the DXF, PNG, CSV and
  report. The only expected warning is the HP placeholder-weight warning.
- The whole pytest suite passes, and ezdxf `audit()` reports zero errors.
- The visual check shows all four sheet elements (elevation, frame strip, BOM,
  title block) laid out without overlaps.
- The user's AutoCAD acceptance check passes.
- Generation takes a few seconds or less for the example job.

(Measuring the real draftsman time saving (4 h → 1 h) is a separate exercise
with the client and is not a software criterion.)
