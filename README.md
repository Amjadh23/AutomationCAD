# shipdraw: bulkhead drawing engine (v1)

Generates a complete transverse-bulkhead drawing for AutoCAD from a small job file:
plate outline, stiffeners, brackets, frame layout, dimensions, BOM and title block,
with every entity on the company's layers.

## Setup (once)

```bash
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
```

## Make a drawing

```bash
.venv/Scripts/shipdraw build jobs/bhd-fr25.yaml
```

This writes to `out/`:

| File | What it is |
|---|---|
| `SY-101.dxf` | the drawing; open it in AutoCAD |
| `SY-101.png` | preview image |
| `SY-101-bom.csv` | bill of materials for Excel |
| `SY-101-report.txt` | rule-check results |

To make a new drawing, copy `jobs/bhd-fr25.yaml`, change the values and run the same command on your copy.

Exit codes: `0` = drawing written, `1` = rule errors (nothing written; see the report on screen), `2` = the job or config file is invalid.

## The drawing page (no commands needed)

Double-click **`Start drawing tool.bat`**. A black window opens; keep it open, and your browser shows the page.

1. Type the measurements on the left. The drawing on the right updates by itself.
2. Red boxes need fixing. Yellow notes are just for your attention.
3. Use the buttons at the top to download the AutoCAD file, the picture, the Excel list, or everything as a .zip.

Close the black window to stop the tool.

Tips: click a box and the diagram above the boxes shows what it measures. The arrow keys change a number (hold Shift for bigger steps). Measurements in the address bar pre-fill the page, so a set-up can be bookmarked, e.g. `http://127.0.0.1:8765/?width=12000&bar_spacing=500`.

## Company standard

- `config/standard.yaml` holds the sheet, layers, text sizes, dimension style, title block and rule limits. **All values are placeholders** until the client's standard is supplied. Change them there; no code changes are needed.
- `config/profiles.yaml` holds the HP bulb-flat weights. **These are placeholder estimates** (the report warns while they are in use). Replace them with the supplier's table.

## Tests

```bash
.venv/Scripts/python -m pytest
```
