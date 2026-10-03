"use strict";

// Plain-language form. Field names must match shipdraw/web/form.py.
//   key  = the part of the measurement diagram this box describes
//   step = how much the arrow keys change the value (hold Shift for ten times as much)
const SECTIONS = [
  { title: "Wall shape", fields: [
    { name: "width", label: "Width", unit: "mm", step: 100, key: "width",
      hint: "Full width of the wall, from one side of the ship to the other." },
    { name: "height", label: "Height", unit: "mm", step: 100, key: "height",
      hint: "From the bottom of the ship (the baseline) up to the top of the wall." },
    { name: "corner_cut", label: "Corner cut", unit: "mm", step: 50, key: "corner",
      hint: "The two bottom corners are cut off at 45° to follow the hull. Use 0 for square corners." },
  ] },
  { title: "Steel bars", subtitle: "stiffeners", fields: [
    { name: "profile", label: "Bar type", type: "text", list: "profiles", key: "bars",
      hint: "The steel section welded to the wall: HP = bulb flat, FB = flat bar, L = angle. For example HP 160x8." },
    { name: "bar_spacing", label: "Every", unit: "mm", step: 50, key: "spacing",
      hint: "Distance between two neighbouring bars." },
    { name: "first_at", label: "First bar at", unit: "mm", step: 50, key: "first",
      hint: "Distance from the middle line to the first bar. 0 puts one bar exactly on the middle line." },
  ] },
  { title: "Corner triangles", subtitle: "brackets", fields: [
    { name: "brackets_bottom", label: "At the bottom", type: "checkbox", key: "brackets",
      hint: "Small steel triangles that join the bottom of each bar to the floor." },
    { name: "brackets_top", label: "At the top", type: "checkbox", key: "brackets",
      hint: "Small steel triangles that join the top of each bar to the deck." },
    { name: "bracket_size", label: "Size", unit: "mm", step: 10, key: "brackets",
      hint: "Length of each of the two short sides of a triangle." },
    { name: "bracket_thickness", label: "Thickness", unit: "mm", step: 1, key: "brackets",
      hint: "Steel thickness of the triangles." },
  ] },
  { title: "Wall plate", fields: [
    { name: "plate_thickness", label: "Thickness", unit: "mm", step: 1, key: "plate",
      hint: "Steel thickness of the wall itself." },
    { name: "plate_grade", label: "Steel grade", type: "text", key: "plate",
      hint: "The steel quality, as written on the drawing. For example AH36." },
  ] },
  { title: "Position in the ship", fields: [
    { name: "at_frame", label: "At frame", unit: "no.", step: 1,
      hint: "Frames are the ship's ribs, numbered from the back. The wall stands on this one." },
    { name: "frame_first", label: "Show frames from", unit: "no.", step: 1,
      hint: "First frame shown on the frame strip under the drawing." },
    { name: "frame_last", label: "Show frames to", unit: "no.", step: 1,
      hint: "Last frame shown on the frame strip under the drawing." },
    { name: "frame_spacing", label: "Frame spacing", unit: "mm", step: 50,
      hint: "Distance between two neighbouring frames." },
  ] },
  { title: "Title block", fields: [
    { name: "project_name", label: "Project", type: "text", wide: true, hint: "Ship or project name, shown in the title block." },
    { name: "title", label: "Title", type: "text", wide: true, hint: "Drawing title, shown in the title block." },
    { name: "drawing_no", label: "Drawing no.", type: "text", hint: "Drawing number. Also used as the file name." },
    { name: "drawn_by", label: "Drawn by", type: "text", hint: "Initials of the person who made the drawing." },
    { name: "revision", label: "Revision", type: "text", hint: "Revision letter, for example A." },
  ] },
];

const FIELDS = Object.fromEntries(SECTIONS.flatMap((section) => section.fields.map((field) => [field.name, field])));
const LABELS = Object.fromEntries(Object.values(FIELDS).map((field) => [field.name, field.label]));
const DEFAULT_CAPTION = "Click any box to see what it measures. Tip: the arrow keys change a number, Shift makes bigger steps.";
const STATUS_ICONS = { idle: "i-dot", ok: "i-check", warning: "i-alert", error: "i-x", invalid: "i-x", offline: "i-x" };
const PREVIEW_DELAY_MS = 350;
const PLOT_STAGGER_MS = 2.6;  // keep in step with .sheet-layer.plotting in app.css
const PLOT_DURATION_MS = 1100;
const MAX_ZOOM = 8;
const REDUCED_MOTION = window.matchMedia("(prefers-reduced-motion: reduce)");

const $ = (selector) => document.querySelector(selector);
const plural = (count, word, suffix = "s") => `${count} ${word}${count === 1 ? "" : suffix}`;
const capitalize = (text) => text.charAt(0).toUpperCase() + text.slice(1);
const formatNumber = (value, digits = 0) =>
  Number(value).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });

const state = { defaults: null, request: null, timer: null, hasDrawing: false, canExport: false, view: { scale: 1, x: 0, y: 0 } };

// ---------- form ----------

function buildForm() {
  const form = $("#form");
  SECTIONS.forEach((section, index) => {
    const group = document.createElement("div");
    group.className = "group";
    group.setAttribute("role", "group");
    const title = document.createElement("h3");
    title.className = "group-title";
    title.id = `group-${index}`;
    title.append(section.title);
    if (section.subtitle) {
      const small = document.createElement("small");
      small.textContent = section.subtitle;
      title.append(small);
    }
    group.setAttribute("aria-labelledby", title.id);
    group.append(title, ...section.fields.map(buildField));
    form.append(group);
  });
  form.addEventListener("input", () => schedulePreview());
  form.addEventListener("change", () => schedulePreview());
  form.addEventListener("submit", (event) => event.preventDefault());
  form.addEventListener("keydown", stepWithArrows);
  form.addEventListener("focusin", (event) => explain(FIELDS[event.target.name]));
  form.addEventListener("focusout", (event) => {
    if (!form.contains(event.relatedTarget)) explain(null);
  });
}

function buildField(field) {
  const wrapper = document.createElement("div");
  wrapper.className = field.type === "checkbox" ? "field field-check" : field.wide ? "field field-wide" : "field";
  wrapper.dataset.field = field.name;
  const id = `f-${field.name}`;
  const input = document.createElement("input");
  input.id = id;
  input.name = field.name;
  const label = document.createElement("label");
  label.htmlFor = id;
  label.textContent = field.label;
  const hint = document.createElement("p");
  hint.className = "hint";
  hint.id = `${id}-hint`;
  hint.textContent = field.hint;
  const message = document.createElement("p");
  message.className = "message";
  message.id = `${id}-msg`;
  input.setAttribute("aria-describedby", `${hint.id} ${message.id}`);

  if (field.type === "checkbox") {
    input.type = "checkbox";
    wrapper.append(label, input, hint);
    return wrapper;
  }

  input.type = "text";
  input.inputMode = field.type === "text" ? "text" : "decimal";
  input.spellcheck = false;
  if (field.list) input.setAttribute("list", field.list);
  const box = document.createElement("div");
  box.className = field.type === "text" ? "input input-text" : "input";
  box.append(input);
  if (field.unit) {
    const unit = document.createElement("span");
    unit.className = "unit";
    unit.textContent = field.unit;
    box.append(unit);
  }
  wrapper.append(label, box, hint, message);
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
  revealField(input.closest(".field"));
  input.focus({ preventScroll: true });
}

function revealField(field) {
  // Scroll only the measurements list (never the page), centring the box below the sticky diagram.
  const list = $(".inputs-scroll");
  const behavior = REDUCED_MOTION.matches ? "auto" : "smooth";
  if (list.scrollHeight <= list.clientHeight) {
    field.scrollIntoView({ block: "center", behavior });  // small screens: the page itself scrolls
    return;
  }
  const area = list.getBoundingClientRect();
  const visibleTop = area.top + $("#key").offsetHeight;
  const box = field.getBoundingClientRect();
  list.scrollBy({ top: box.top + box.height / 2 - (visibleTop + area.bottom) / 2, behavior });
}

function stepWithArrows(event) {
  if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
  const input = event.target;
  const field = FIELDS[input.name];
  if (!field?.step) return;
  const current = Number(String(input.value).replace(/,/g, "").trim());
  if (!Number.isFinite(current)) return;
  event.preventDefault();
  const delta = field.step * (event.shiftKey ? 10 : 1) * (event.key === "ArrowUp" ? 1 : -1);
  input.value = String(Math.round((current + delta) * 1000) / 1000);
  schedulePreview();
}

// ---------- measurement diagram ----------

function explain(field) {
  const key = $("#key");
  key.classList.toggle("has-focus", Boolean(field?.key));
  for (const group of key.querySelectorAll("[data-key]")) {
    group.classList.toggle("on", Boolean(field?.key) && group.dataset.key === field.key);
  }
  const caption = $("#key-caption");
  if (!field) {
    caption.textContent = DEFAULT_CAPTION;
    return;
  }
  const name = document.createElement("b");
  name.textContent = field.label;
  caption.replaceChildren(name, ` — ${field.hint}`);
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
    ok: ["Drawing ready", "Everything checks out. Ready to export."],
    warning: ["Drawing ready", `${plural(result.warnings.length, "note")} to look at below.`],
    error: ["Can't draw this yet", `${plural(result.errors.length, "problem")} to fix below.`],
    invalid: ["Check the highlighted boxes", `${plural(badBoxes, "box", "es")} ${badBoxes === 1 ? "needs" : "need"} attention.`],
  };
  setStatus(result.status, ...details[result.status]);
  showIssues(result);
  showDrawing(result.svg);
  showSummary(result.summary);
  showBom(result.bom, result.summary);
  updateDocChip(result.summary);
  setExportsEnabled(result.status === "ok" || result.status === "warning");
}

function setStatus(kind, title, detail) {
  const status = $("#status");
  const changed = status.dataset.state !== kind;
  status.dataset.state = kind;
  $("#status-use").setAttribute("href", `#${STATUS_ICONS[kind] ?? "i-dot"}`);
  $("#status-title").textContent = title;
  $("#status-detail").textContent = detail;
  if (changed) {
    status.classList.remove("changed");
    void status.offsetWidth;  // restart the icon animation
    status.classList.add("changed");
  }
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
  items.forEach((item, index) => {
    const li = document.createElement("li");
    li.className = `issue issue-${item.kind}`;
    li.style.animationDelay = `${index * 40}ms`;
    if (item.field && LABELS[item.field]) {
      const where = document.createElement("button");
      where.type = "button";
      where.className = "issue-field";
      where.textContent = LABELS[item.field];
      where.title = "Go to this box";
      where.addEventListener("click", () => focusField(item.field));
      li.append(where);
    }
    li.append(item.text);
    list.append(li);
  });
}

function showDrawing(svg) {
  const sheet = $("#sheet");
  const placeholder = $("#placeholder");
  if (!svg) {
    sheet.classList.add("stale");
    if (!state.hasDrawing) placeholder.textContent = "The drawing appears here once the measurements are valid.";
    return;
  }
  sheet.classList.remove("stale");
  placeholder.hidden = true;
  const layer = document.createElement("div");
  layer.className = "sheet-layer";
  layer.innerHTML = svg;
  const previous = [...sheet.children];

  if (!state.hasDrawing) {
    state.hasDrawing = true;
    if (!REDUCED_MOTION.matches) plot(layer);
    sheet.append(layer);
    fitView();
    return;
  }
  // Cross-fade: the new sheet fades in on top, then the old one is removed.
  layer.classList.add("entering");
  sheet.append(layer);
  void layer.offsetWidth;
  layer.classList.remove("entering");
  setTimeout(() => previous.forEach((old) => old.remove()), 320);
}

function plot(layer) {
  // Draw every line like a pen plotter: each path's dash runs from empty to full.
  const paths = layer.querySelectorAll("path");
  paths.forEach((path, index) => {
    path.setAttribute("pathLength", "1");
    path.style.setProperty("--i", index);
  });
  layer.classList.add("plotting");
  setTimeout(() => layer.classList.remove("plotting"), paths.length * PLOT_STAGGER_MS + PLOT_DURATION_MS + 100);
}

function showSummary(summary) {
  const box = $("#summary");
  box.classList.toggle("is-empty", !summary);
  if (!summary) return;
  countTo(box.querySelector('[data-readout="scale"]'), summary.scale, 0, "1:");
  countTo(box.querySelector('[data-readout="stiffeners"]'), summary.stiffeners);
  countTo(box.querySelector('[data-readout="brackets"]'), summary.brackets);
  countTo(box.querySelector('[data-readout="total_weight_kg"]'), summary.total_weight_kg, 1);
}

function countTo(element, target, digits = 0, prefix = "") {
  const from = Number(element.dataset.value ?? target);
  element.dataset.value = target;
  cancelAnimationFrame(element.frame);
  clearTimeout(element.settle);
  const show = (value) => { element.textContent = prefix + formatNumber(value, digits); };
  if (REDUCED_MOTION.matches || document.hidden || from === target) {
    show(target);
    return;
  }
  const start = performance.now();
  const duration = 600;
  const step = (now) => {
    const t = Math.min(1, (now - start) / duration);
    show(from + (target - from) * (1 - Math.pow(1 - t, 3)));
    if (t < 1) element.frame = requestAnimationFrame(step);
  };
  element.frame = requestAnimationFrame(step);
  // Animation frames pause in background tabs; make sure the true value always lands.
  element.settle = setTimeout(() => {
    cancelAnimationFrame(element.frame);
    show(target);
  }, duration + 50);
}

function showBom(rows, summary) {
  const table = $("#bom");
  $("#bom-empty").hidden = Boolean(rows);
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

function updateDocChip(summary) {
  const values = readValues();
  $("#doc-no").textContent = values.drawing_no.trim() || "—";
  const parts = [];
  if (values.revision.trim()) parts.push(`Rev ${values.revision.trim()}`);
  if (summary) parts.push(`1:${summary.scale}`);
  $("#doc-meta").textContent = parts.join(" · ");
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
  element.hidden = true;
  void element.offsetWidth;  // restart the slide-in animation
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
  $("#zoom-level").textContent = `${Math.round(view.scale * 100)}%`;
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
  new ResizeObserver(applyView).observe(stage);
}

// ---------- address bar ----------

// Measurements in the address bar pre-fill the page, e.g. /?width=12000&bar_spacing=500,
// so a set-up can be bookmarked or shared. ?focus=<field> puts the cursor in that box.
function applyAddressBar() {
  const params = new URLSearchParams(window.location.search);
  const values = {};
  for (const [name, value] of params) {
    if (!FIELDS[name]) continue;
    values[name] = FIELDS[name].type === "checkbox" ? !["0", "false", "no", "off"].includes(value.toLowerCase()) : value;
  }
  setValues(values);
  const focus = params.get("focus");
  if (focus && FIELDS[focus]) focusField(focus);
}

// ---------- start ----------

async function init() {
  buildForm();
  explain(null);
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
    applyAddressBar();
    schedulePreview(0);
  } catch {
    showOffline();
  }
}

document.addEventListener("DOMContentLoaded", init);
