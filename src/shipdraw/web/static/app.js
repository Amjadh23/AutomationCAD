"use strict";

// Plain-language form. Field names must match shipdraw/web/form.py.
const SECTIONS = [
  { title: "Wall shape", fields: [
    { name: "width", label: "Width", unit: "mm", hint: "Full width of the wall, side to side." },
    { name: "height", label: "Height", unit: "mm", hint: "From the bottom of the ship to the top of the wall." },
    { name: "corner_cut", label: "Corner cut", unit: "mm", hint: "The two bottom corners are cut off at 45°. Use 0 for square corners." },
  ] },
  { title: "Steel bars", subtitle: "stiffeners", fields: [
    { name: "profile", label: "Bar type", type: "text", list: "profiles", hint: "HP = bulb flat, FB = flat bar, L = angle. For example HP 160x8." },
    { name: "bar_spacing", label: "Every", unit: "mm", hint: "Distance between two bars." },
    { name: "first_at", label: "First bar at", unit: "mm", hint: "Distance from the middle line to the first bar. 0 puts a bar on the middle line." },
  ] },
  { title: "Corner triangles", subtitle: "brackets", fields: [
    { name: "brackets_bottom", label: "At the bottom", type: "checkbox" },
    { name: "brackets_top", label: "At the top", type: "checkbox" },
    { name: "bracket_size", label: "Size", unit: "mm", hint: "Length of each short side of the triangle." },
    { name: "bracket_thickness", label: "Thickness", unit: "mm" },
  ] },
  { title: "Wall plate", fields: [
    { name: "plate_thickness", label: "Thickness", unit: "mm" },
    { name: "plate_grade", label: "Steel grade", type: "text", hint: "For example AH36." },
  ] },
  { title: "Position in the ship", fields: [
    { name: "at_frame", label: "At frame", unit: "no.", hint: "Frames are the ship's ribs, numbered from the back. The wall sits on this one." },
    { name: "frame_first", label: "Show frames from", unit: "no." },
    { name: "frame_last", label: "Show frames to", unit: "no." },
    { name: "frame_spacing", label: "Frame spacing", unit: "mm", hint: "Distance between two frames." },
  ] },
  { title: "Title block", fields: [
    { name: "project_name", label: "Project", type: "text" },
    { name: "drawing_no", label: "Drawing no.", type: "text", hint: "Also used as the file name." },
    { name: "title", label: "Title", type: "text" },
    { name: "drawn_by", label: "Drawn by", type: "text" },
    { name: "revision", label: "Revision", type: "text" },
  ] },
];

const LABELS = Object.fromEntries(SECTIONS.flatMap((section) => section.fields.map((f) => [f.name, f.label])));
const PREVIEW_DELAY_MS = 350;
const MAX_ZOOM = 8;
const $ = (selector) => document.querySelector(selector);
const plural = (count, word, suffix = "s") => `${count} ${word}${count === 1 ? "" : suffix}`;
const capitalize = (text) => text.charAt(0).toUpperCase() + text.slice(1);
const formatNumber = (value, digits = 0) =>
  Number(value).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });

const state = { defaults: null, request: null, timer: null, hasDrawing: false, canExport: false, view: { scale: 1, x: 0, y: 0 } };

// ---------- form ----------

function buildForm() {
  const form = $("#form");
  for (const section of SECTIONS) {
    const fieldset = document.createElement("fieldset");
    const legend = document.createElement("legend");
    legend.textContent = section.title;
    if (section.subtitle) {
      const small = document.createElement("small");
      small.textContent = section.subtitle;
      legend.append(" ", small);
    }
    fieldset.append(legend, ...section.fields.map(buildField));
    form.append(fieldset);
  }
  form.addEventListener("input", () => schedulePreview());
  form.addEventListener("change", () => schedulePreview());
  form.addEventListener("submit", (event) => event.preventDefault());
}

function buildField(field) {
  const wrapper = document.createElement("div");
  wrapper.className = field.type === "checkbox" ? "field field-check" : "field";
  wrapper.dataset.field = field.name;
  const id = `f-${field.name}`;
  const input = document.createElement("input");
  input.id = id;
  input.name = field.name;
  const label = document.createElement("label");
  label.htmlFor = id;
  label.textContent = field.label;

  if (field.type === "checkbox") {
    input.type = "checkbox";
    wrapper.append(input, label);
    return wrapper;
  }

  input.type = "text";
  input.inputMode = field.type === "text" ? "text" : "decimal";
  input.spellcheck = false;
  if (field.list) input.setAttribute("list", field.list);
  const box = document.createElement("div");
  box.className = "input";
  box.append(input);
  if (field.unit) {
    const unit = document.createElement("span");
    unit.className = "unit";
    unit.textContent = field.unit;
    box.append(unit);
  }
  const message = document.createElement("p");
  message.className = "message";
  message.id = `${id}-msg`;
  input.setAttribute("aria-describedby", message.id);
  wrapper.append(label, box);
  if (field.hint) {
    const hint = document.createElement("p");
    hint.className = "hint";
    hint.textContent = field.hint;
    wrapper.append(hint);
  }
  wrapper.append(message);
  return wrapper;
}

function readValues() {
  const values = {};
  for (const input of $("#form").querySelectorAll("input")) {
    values[input.name] = input.type === "checkbox" ? input.checked : input.value;
  }
  return values;
}

function setValues(values) {
  const form = $("#form");
  for (const [name, value] of Object.entries(values)) {
    const input = form.elements.namedItem(name);
    if (!input) continue;
    if (input.type === "checkbox") input.checked = Boolean(value);
    else input.value = String(value);
  }
}

function focusField(name) {
  const input = $("#form").elements.namedItem(name);
  if (!input) return;
  input.scrollIntoView({ block: "center", behavior: "smooth" });
  input.focus({ preventScroll: true });
}

// ---------- preview requests ----------

function schedulePreview(delay = PREVIEW_DELAY_MS) {
  clearTimeout(state.timer);
  state.timer = setTimeout(runPreview, delay);
}

async function runPreview() {
  state.request?.abort();
  const request = new AbortController();
  state.request = request;
  setBusy(true);
  try {
    const response = await fetch("/api/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(readValues()),
      signal: request.signal,
    });
    if (!response.ok) throw new Error(`server answered ${response.status}`);
    showResult(await response.json());
  } catch (error) {
    if (error.name !== "AbortError") showOffline();
  } finally {
    if (state.request === request) {
      state.request = null;
      setBusy(false);
    }
  }
}

// ---------- results ----------

function showResult(result) {
  clearFieldMarks();
  for (const [name, text] of Object.entries(result.field_errors)) markField(name, "error", text);
  for (const issue of result.errors) if (issue.field) markField(issue.field, "error", issue.text);
  for (const issue of result.warnings) if (issue.field) markField(issue.field, "warning", issue.text);

  const badBoxes = Object.keys(result.field_errors).length;
  const details = {
    ok: ["Drawing ready", "Everything checks out."],
    warning: ["Drawing ready", `${plural(result.warnings.length, "note")} below.`],
    error: ["Can't draw this yet", `${plural(result.errors.length, "problem")} to fix below.`],
    invalid: ["Check the highlighted boxes", `${plural(badBoxes, "box", "es")} ${badBoxes === 1 ? "needs" : "need"} attention.`],
  };
  setStatus(result.status, ...details[result.status]);
  showIssues(result);
  showDrawing(result.svg);
  showSummary(result.summary);
  showBom(result.bom, result.summary);
  setExportsEnabled(result.status === "ok" || result.status === "warning");
}

function setStatus(kind, title, detail) {
  $("#status").dataset.state = kind;
  $("#status-title").textContent = title;
  $("#status-detail").textContent = detail;
}

function showOffline() {
  setStatus("offline", "Can't reach the drawing engine", "Is its black window still open? If you closed it, start the tool again.");
  setExportsEnabled(false);
}

function setBusy(busy) {
  $("#busy").hidden = !busy;
  $(".preview").classList.toggle("is-busy", busy);
}

function markField(name, kind, text) {
  const field = document.querySelector(`.field[data-field="${name}"]`);
  if (!field || field.dataset.state === "error" || (field.dataset.state === "warning" && kind === "warning")) return;
  field.dataset.state = kind;
  const message = field.querySelector(".message");
  if (message) message.textContent = text;
  field.querySelector("input")?.setAttribute("aria-invalid", String(kind === "error"));
}

function clearFieldMarks() {
  for (const field of document.querySelectorAll(".field[data-state]")) {
    delete field.dataset.state;
    const message = field.querySelector(".message");
    if (message) message.textContent = "";
    field.querySelector("input")?.removeAttribute("aria-invalid");
  }
}

function showIssues(result) {
  const list = $("#issues");
  list.replaceChildren();
  const items = [
    ...Object.entries(result.field_errors).filter(([name]) => !LABELS[name]).map(([, text]) => ({ kind: "error", text })),
    ...result.errors.map((issue) => ({ kind: "error", ...issue })),
    ...result.warnings.map((issue) => ({ kind: "warning", ...issue })),
  ];
  for (const item of items) {
    const li = document.createElement("li");
    li.className = `issue issue-${item.kind}`;
    if (item.field && LABELS[item.field]) {
      const where = document.createElement("button");
      where.type = "button";
      where.className = "issue-field";
      where.textContent = LABELS[item.field];
      where.addEventListener("click", () => focusField(item.field));
      li.append(where, " ");
    }
    li.append(item.text);
    list.append(li);
  }
}

function showDrawing(svg) {
  const sheet = $("#sheet");
  const placeholder = $("#placeholder");
  if (svg) {
    sheet.innerHTML = svg;
    sheet.classList.remove("stale");
    placeholder.hidden = true;
    if (!state.hasDrawing) {
      state.hasDrawing = true;
      fitView();
    }
    return;
  }
  sheet.classList.add("stale");
  if (!state.hasDrawing) {
    placeholder.hidden = false;
    placeholder.textContent = "The drawing appears here once the measurements are valid.";
  }
}

function showSummary(summary) {
  const box = $("#summary");
  box.replaceChildren();
  if (!summary) return;
  const items = [
    ["Scale", `1:${summary.scale}`],
    ["Steel bars", summary.stiffeners],
    ["Corner triangles", summary.brackets],
    ["Total weight", `${formatNumber(summary.total_weight_kg, 1)} kg`],
  ];
  for (const [term, value] of items) {
    const item = document.createElement("div");
    const dt = document.createElement("dt");
    dt.textContent = term;
    const dd = document.createElement("dd");
    dd.textContent = value;
    item.append(dt, dd);
    box.append(item);
  }
}

function showBom(rows, summary) {
  const table = $("#bom");
  if (!rows) {
    table.hidden = true;
    return;
  }
  const body = table.tBodies[0];
  body.replaceChildren();
  for (const row of rows) {
    const tr = document.createElement("tr");
    const cells = [
      [row.item, false],
      [row.description, false],
      [row.qty, true],
      [row.length_mm == null ? "–" : formatNumber(row.length_mm), true],
      [formatNumber(row.weight_kg, 1), true],
    ];
    for (const [value, numeric] of cells) {
      const td = document.createElement("td");
      td.textContent = value;
      if (numeric) td.className = "num";
      tr.append(td);
    }
    body.append(tr);
  }
  $("#bom-total").textContent = formatNumber(summary.total_weight_kg, 1);
  table.hidden = false;
}

// ---------- exports ----------

function setExportsEnabled(enabled) {
  state.canExport = enabled;
  for (const button of document.querySelectorAll("[data-export]")) {
    if (!button.classList.contains("working")) button.disabled = !enabled;
  }
}

async function exportFile(kind, button) {
  button.disabled = true;
  button.classList.add("working");
  try {
    const response = await fetch(`/api/export/${kind}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(readValues()),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      toast(data.error ? `${capitalize(data.error)}.` : "Export failed.", "error");
      return;
    }
    const blob = await response.blob();
    const name = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") || "")?.[1] || `drawing.${kind}`;
    const url = URL.createObjectURL(blob);
    const link = Object.assign(document.createElement("a"), { href: url, download: name });
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
    toast(`Saved ${name} to your Downloads folder.`, "ok");
  } catch {
    toast("Can't reach the drawing engine. Is its black window still open?", "error");
  } finally {
    button.classList.remove("working");
    button.disabled = !state.canExport;
  }
}

function toast(text, kind) {
  const element = $("#toast");
  element.textContent = text;
  element.dataset.kind = kind;
  element.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { element.hidden = true; }, 4000);
}

// ---------- zoom and pan ----------

function applyView() {
  const stage = $("#stage").getBoundingClientRect();
  const view = state.view;
  view.x = Math.min(0, Math.max(stage.width - stage.width * view.scale, view.x));
  view.y = Math.min(0, Math.max(stage.height - stage.height * view.scale, view.y));
  $("#sheet").style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.scale})`;
  $("#stage").classList.toggle("zoomed", view.scale > 1);
}

function fitView() {
  state.view = { scale: 1, x: 0, y: 0 };
  applyView();
}

function zoomAt(factor, cx, cy) {
  const view = state.view;
  const scale = Math.min(MAX_ZOOM, Math.max(1, view.scale * factor));
  const k = scale / view.scale;
  view.x = cx - (cx - view.x) * k;
  view.y = cy - (cy - view.y) * k;
  view.scale = scale;
  applyView();
}

function zoomAtCentre(factor) {
  const stage = $("#stage").getBoundingClientRect();
  zoomAt(factor, stage.width / 2, stage.height / 2);
}

function setupViewer() {
  const stage = $("#stage");
  stage.addEventListener("wheel", (event) => {
    event.preventDefault();
    const box = stage.getBoundingClientRect();
    zoomAt(event.deltaY < 0 ? 1.15 : 1 / 1.15, event.clientX - box.left, event.clientY - box.top);
  }, { passive: false });

  let drag = null;
  stage.addEventListener("pointerdown", (event) => {
    if (state.view.scale === 1) return;
    drag = { x: event.clientX - state.view.x, y: event.clientY - state.view.y };
    stage.setPointerCapture(event.pointerId);
    stage.classList.add("dragging");
  });
  stage.addEventListener("pointermove", (event) => {
    if (!drag) return;
    state.view.x = event.clientX - drag.x;
    state.view.y = event.clientY - drag.y;
    applyView();
  });
  const endDrag = () => {
    drag = null;
    stage.classList.remove("dragging");
  };
  stage.addEventListener("pointerup", endDrag);
  stage.addEventListener("pointercancel", endDrag);
  stage.addEventListener("dblclick", fitView);
  $("#zoom-in").addEventListener("click", () => zoomAtCentre(1.25));
  $("#zoom-out").addEventListener("click", () => zoomAtCentre(0.8));
  $("#zoom-fit").addEventListener("click", fitView);
  window.addEventListener("resize", applyView);
}

// ---------- start ----------

async function init() {
  buildForm();
  setupViewer();
  for (const button of document.querySelectorAll("[data-export]")) {
    button.addEventListener("click", () => exportFile(button.dataset.export, button));
  }
  $("#reset").addEventListener("click", () => {
    if (!state.defaults) return;
    setValues(state.defaults);
    schedulePreview(0);
  });
  try {
    const response = await fetch("/api/defaults");
    const data = await response.json();
    state.defaults = data.values;
    $("#profiles").replaceChildren(...data.profiles.map((name) => Object.assign(document.createElement("option"), { value: name })));
    setValues(data.values);
    schedulePreview(0);
  } catch {
    showOffline();
  }
}

document.addEventListener("DOMContentLoaded", init);
