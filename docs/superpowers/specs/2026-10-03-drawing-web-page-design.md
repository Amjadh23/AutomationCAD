# Drawing Web Page — Design

**Date:** 2026-10-03
**Status:** Approved in chat
**Builds on:** `2026-09-28-bulkhead-drawing-engine-design.md` (engine v1)

## 1. Goal

Give people who have never used AutoCAD a way to use the engine. The page has four parts:

- **Measurement boxes**, in plain words.
- **A live preview** of the real drawing, updated as they type.
- **Messages in plain words**, with the material list underneath.
- **Export buttons** for the AutoCAD file, the picture, the Excel list, or all three.

It runs on this computer only. Phase 1 delivers working, tested functionality. Phase 2 is a visual design pass ("visually stunning, not AI slop"), with animations and a proper theme. Functionality has priority, and Phase 2 must not break it.

## 2. Decisions

| Decision | Choice | Reason |
|---|---|---|
| Where it runs | Local server bound to `127.0.0.1`, opened in the browser | Drawings stay on the computer; nothing to host; nothing new to install |
| Server | Python standard library `http.server` (`ThreadingHTTPServer`) | No new dependencies; the page has one user at a time |
| Preview fidelity | The preview is the engine's own DXF rendered to SVG by ezdxf | What you see is exactly what gets exported |
| Preview look | AutoCAD layer colours on a dark sheet (`ColorPolicy.COLOR`, custom dark background) | Looks like real CAD; shows the layers are right |
| Wall shape input | Width, height and corner cut (a 45° bottom corner; 0 gives square corners) | Plain words; covers normal bulkheads. Job files still accept any polygon |
| Frontend | One HTML file, one CSS file and one JS file, written in plain JavaScript with no build step and no CDN | Works offline and stays simple to run |
| Fonts | System fonts (Segoe UI Variable, Cascadia Mono / Consolas) | Offline; no downloads |
| Start | Double-click `Start drawing tool.bat`; `shipdraw serve` underneath | Usable by non-programmers |

## 3. Components

**Engine refactor**

- `pipeline.render_drawing(job, standard, profiles) -> Rendered`, where `Rendered` holds the report, parts, plan, BOM and the ezdxf document. The document is `None` when the checks failed.
- `build()` is rebuilt on top of `render_drawing()`, with unchanged behaviour.

**Rendering helpers** (inside `render/`, the only place allowed to import ezdxf)

- `render_svg(doc, w_mm, h_mm) -> str` in `preview.py`.
- `dxf_bytes(doc)` and `png_bytes(doc, w_mm, h_mm)` in the new `files.py`. PNG rendering is serialised with a lock, because pyplot is not thread-safe.

**`shipdraw/web/form.py`** (pure)

- `DEFAULT_VALUES` reproduces the example job.
- `form_to_job(values) -> Job` raises `FormError(field_errors)` with a plain-language message per field. Engine validation locations are mapped back to form fields.
- `outline_half(width, height, corner_cut)`.
- `split_message(engine_message) -> (field, text)` maps rule-check messages to fields.

**`shipdraw/web/api.py`**: `DrawingService(standard, profiles)`, with no HTTP of its own:

- `defaults() -> {values, profiles}`
- `preview(values)` returns `{status, field_errors, errors[], warnings[], summary, bom, svg}`, where `status` is one of `ok`, `warning`, `error` or `invalid`
- `export(values, kind) -> Export(filename, content_type, data)`, where `kind` is `dxf`, `png`, `csv` or `zip`. It raises `ExportRefused` when the input is invalid or a rule fails.

**`shipdraw/web/server.py`**

| Route | Returns |
|---|---|
| `GET /` and `GET /static/<file>` | Files from the static folder only. No subfolders and no path traversal |
| `GET /api/defaults` | The default values and the profile list |
| `POST /api/preview` | The preview response |
| `POST /api/export/<kind>` | A download, or **422** with `{error}` |

Guards:

- the request body is limited to 100 kB (**413** above that);
- a request that isn't a JSON object gets **400**;
- a `Host` header other than `127.0.0.1` or `localhost` gets **403** (DNS-rebinding guard).

If the requested port is busy, the server falls back to a free port.

**CLI**: `shipdraw serve [--port 8765] [--no-browser] [--config DIR]`. It prints the URL and opens the browser.

**Static page**

- Form fields are generated from a section list in `app.js`. The sections are:
  1. Wall shape
  2. Steel bars
  3. Corner triangles
  4. Wall plate
  5. Position in the ship
  6. Title block
- Preview requests are debounced (350 ms) and stale requests are aborted.
- Errors and warnings appear inline on their fields and in an issue list; clicking an issue focuses its field.
- A status line shows the overall result, followed by a summary (scale, bars, triangles, weight) and the BOM table.
- Exports are enabled only for `ok` or `warning`. A download shows a toast message.
- The preview supports zoom (wheel and buttons) and pan (drag), and double-click fits it back.
- "Reset to example" restores the defaults.
- If the server can't be reached, the page shows an "offline" message.

## 4. Phase 2: design direction

- **Theme:** a "drafting room" theme. A deep ink-navy background with a faint blueprint grid, and the drawing as the hero. Cyan and amber engineering accents.
- **Typography:** tabular monospaced figures for numbers.
- **Restraint:** no gradient-soup, no emoji icons, no generic card spam, and no purple-to-pink AI defaults.
- **Animations:**
  - a "plotter" draw-on of the sheet on first load (stroke-dashoffset over the SVG paths);
  - a soft cross-fade on updates;
  - a scanning indicator while computing;
  - status and number transitions;
  - button micro-interactions.
- **Reduced motion:** honour `prefers-reduced-motion` by turning the animations off.
- **Accessibility:** visible focus states and good contrast.
- **Layout:** works from 1280 px laptop widths up to large monitors, and stays usable at tablet width.

## 5. Testing

- **pytest:**
  - form mapping and plain-language errors;
  - the API service: preview statuses, summary numbers, a clean DXF audit on export, PNG and CSV contents, the ZIP file list, refused exports;
  - the HTTP server: routes, static-file confinement, 400/403/404/413/422 responses, and the busy-port fallback;
  - CLI `serve` wiring;
  - `render_drawing()`.
- **Browser check (Claude's built-in browser):**
  1. the page loads and shows the example drawing;
  2. editing a box updates the drawing;
  3. a bad value highlights its box;
  4. a rule error blocks export;
  5. every export downloads;
  6. zoom and pan work.

  After Phase 2, repeat the browser check and take screenshots.
