"use strict";

const root = document.getElementById("lcf-lab");
const field = name => root.querySelector("[data-" + name + "]");
const action = name => root.querySelector('[data-action="' + name + '"]');
const update = (name, text) => { field(name).textContent = text; };
const svgNamespace = "http://www.w3.org/2000/svg";
const elements = [
  ["Sc", "Scandium"], ["Ti", "Titanium"], ["V", "Vanadium"], ["Cr", "Chromium"],
  ["Mn", "Manganese"], ["Fe", "Iron"], ["Co", "Cobalt"], ["Ni", "Nickel"],
  ["Cu", "Copper"], ["Zn", "Zinc"],
];
const edgeLabels = { L1: "L₁", L2: "L₂", L3: "L₃", "L2,3": "L₂,₃" };
const detectionModes = [
  ["", "Unspecified"], ["TEY", "TEY · Total electron yield"],
  ["PEY", "PEY · Partial electron yield"], ["TFY", "TFY · Total fluorescence yield"],
  ["PFY", "PFY · Partial fluorescence yield"],
  ["IPFY", "IPFY · Inverse partial fluorescence yield"], ["Transmission", "Transmission"],
  ["Other", "Other"],
];
const referenceColors = ["var(--lcf-reference-a)", "var(--lcf-reference-b)", "var(--lcf-reference-c)"];
const state = {
  analysis: {
    element: "Fe",
    edge: "L2,3",
    settings: { fit_min: null, fit_max: null, max_shift: 0, shift_step: 0.02, sum_to_one: true },
    samples: [],
    standards: [],
  },
  selected: null,
  result: null,
  lastInput: null,
  tab: "standards",
  busy: false,
  synthetic: false,
  customWindow: false,
};
let nextId = 0;
let renderedStandards = null;
const libraryPacks = new Map();
let bundledLibraryLoaded = false;

function selectedSample() {
  return state.analysis.samples.find(sample => sample.id === state.selected);
}

function sampleResult(sampleId) {
  return state.result?.results.find(result => result.sample_id === sampleId);
}

function elementEdge() {
  return state.analysis.element + " " + edgeLabels[state.analysis.edge];
}

function setError(fieldName, message = "") {
  const target = field(fieldName);
  target.textContent = message;
  target.hidden = !message;
}

function reportChange(message = "Fit settings changed. Run Fit batch to refresh results.") {
  state.result = null;
  state.lastInput = null;
  setError("global-error");
  update("operation", message);
  render();
}

function setOptions(selector, options) {
  root.querySelectorAll(selector).forEach(select => {
    select.replaceChildren(...options.map(([value, label]) => new Option(label, value)));
  });
}

function button(label, cssClass, onClick, ariaLabel = "") {
  const control = document.createElement("button");
  control.type = "button";
  control.textContent = label;
  control.className = cssClass;
  if (ariaLabel) control.setAttribute("aria-label", ariaLabel);
  control.addEventListener("click", onClick);
  return control;
}

function numberCell(value) {
  const numericText = value.trim().replace(/([0-9.])[dD]([+-]?\d+)$/, "$1e$2");
  if (!/^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(numericText)) return NaN;
  return Number(numericText);
}

function splitRow(line, delimiter) {
  if (!delimiter) return line.trim().split(/\s+/);
  const cells = [];
  let value = "";
  let quoted = false;
  for (let index = 0; index < line.length; index++) {
    const char = line[index];
    if (char === '"') {
      if (quoted && line[index + 1] === '"') {
        value += '"';
        index++;
      } else {
        quoted = !quoted;
      }
    } else if (char === delimiter && !quoted) {
      cells.push(value.trim());
      value = "";
    } else {
      value += char;
    }
  }
  if (quoted) throw new Error("A quoted field was left open.");
  cells.push(value.trim());
  return cells;
}

async function readSpectra(file, { single = false } = {}) {
  if (file.size > 5 * 1024 * 1024) throw new Error(file.name + " exceeds the 5 MB per-file limit.");
  const lines = (await file.text()).replace(/^\uFEFF/, "").split(/\r?\n/)
    .map((value, index) => ({ text: value.trim(), line: index + 1 }))
    .filter(row => row.text && !/^(#|!|\/\/)/.test(row.text));
  if (!lines.length) throw new Error(file.name + " has no data rows.");
  const first = lines[0].text;
  const delimiter = ["\t", ",", ";"].find(char => first.includes(char));
  let header;
  let rows;
  try {
    rows = lines.map(row => ({ cells: splitRow(row.text, delimiter), line: row.line }));
  } catch (error) {
    throw new Error(file.name + ". " + error.message);
  }
  if (!Number.isFinite(numberCell(rows[0].cells[0]))) header = rows.shift().cells;
  if (rows.length < 3) throw new Error(file.name + " needs at least three numeric rows.");
  const columns = rows[0].cells.length;
  if (columns < 2 || (single && columns !== 2)) {
    throw new Error(file.name + (single ? " needs one energy column and one signal column." : " needs an energy column and at least one signal column."));
  }
  if (header && header.length !== columns) throw new Error(file.name + " has a header that does not match its data columns.");
  const numericRows = rows.map(row => {
    const values = row.cells.map(numberCell);
    if (values.length !== columns || values.some(value => !Number.isFinite(value))) {
      throw new Error(file.name + ", line " + row.line + ". Expected " + columns + " finite numbers.");
    }
    return values;
  });
  numericRows.sort((firstRow, secondRow) => firstRow[0] - secondRow[0]);
  const energy = numericRows.map(row => row[0]);
  if (energy.some((value, index) => index > 0 && value === energy[index - 1])) {
    throw new Error(file.name + " contains repeated energies. Consolidate repeated readings before importing.");
  }
  const stem = file.name.replace(/\.[^.]+$/, "");
  return Array.from({ length: columns - 1 }, (_, index) => {
    const column = index + 1;
    return {
      id: "local-" + ++nextId,
      label: columns === 2 ? stem : header?.[column] || stem + " · Signal " + column,
      energy,
      signal: numericRows.map(row => row[column]),
      source_file: file.name,
    };
  });
}

function sharedRange(sample = selectedSample()) {
  if (!sample) return null;
  const shift = state.analysis.settings.max_shift || 0;
  let lower = sample.energy[0];
  let upper = sample.energy.at(-1);
  for (const reference of state.analysis.standards) {
    if (!reference.included) continue;
    lower = Math.max(lower, reference.energy[0] + shift);
    upper = Math.min(upper, reference.energy.at(-1) - shift);
  }
  if (lower >= upper) return null;
  return [lower, upper];
}

function applySharedRange(sample = selectedSample()) {
  const range = sharedRange(sample);
  if (range) [state.analysis.settings.fit_min, state.analysis.settings.fit_max] = range;
}

function resetProject(element, edge, samples, standards = [], settings = null, synthetic = false) {
  state.analysis = {
    element,
    edge,
    samples,
    standards,
    settings: settings || { fit_min: null, fit_max: null, max_shift: 0, shift_step: 0.02, sum_to_one: true },
  };
  state.selected = samples[0]?.id || null;
  state.synthetic = synthetic;
  state.customWindow = Boolean(settings);
  state.tab = "standards";
  if (!settings) applySharedRange();
}

async function getJson(response) {
  const payload = await response.json().catch(() => null);
  if (!response.ok || !payload || payload.error) {
    throw new Error(payload?.error || "LCF Lab returned an error (" + response.status + ").");
  }
  return payload;
}

function postJson(url, body) {
  return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}

async function perform(operation, callback, errorField = "global-error") {
  if (state.busy) return;
  state.busy = true;
  update("operation", operation);
  setError(errorField);
  render();
  try {
    await callback();
  } catch (error) {
    setError(errorField, error.message || "The operation could not be completed.");
    update("operation", "");
  } finally {
    state.busy = false;
    render();
  }
}

function openImport() {
  field("import-form").reset();
  field("import-element").value = state.analysis.element;
  field("import-edge").value = state.analysis.edge;
  field("replace-row").hidden = !state.analysis.samples.length;
  field("replace").checked = state.synthetic;
  setError("import-error");
  field("import-dialog").showModal();
}

function openReference() {
  field("reference-form").reset();
  field("reference-element").value = state.analysis.element;
  field("reference-edge").value = state.analysis.edge;
  setError("reference-error");
  field("reference-dialog").showModal();
}

function compatibleStandard(element, edge) {
  const project = state.analysis;
  return element === project.element && (
    edge === project.edge || (edge === "L2,3" && ["L2", "L3"].includes(project.edge))
  );
}

function registerLibraryPack(pack) {
  const hasText = value => typeof value === "string" && Boolean(value.trim());
  if (pack?.schema_version !== 1 || ![pack.id, pack.version, pack.label].every(hasText) ||
      !Array.isArray(pack.standards) || !pack.standards.length) {
    throw new Error("A reference pack needs a version 1 schema, ID, version, label, and standards.");
  }
  const ids = new Set();
  for (const item of pack.standards) {
    if (!item || ![item.id, item.label, item.provenance, item.license].every(hasText) ||
        !elements.some(([symbol]) => symbol === item.element) || !Object.hasOwn(edgeLabels, item.edge) ||
        ids.has(item.id) || (item.valence != null && !Number.isFinite(item.valence)) ||
        (item.mixed_nominal_valences != null &&
          (!Array.isArray(item.mixed_nominal_valences) || !item.mixed_nominal_valences.every(Number.isFinite))) ||
        !Array.isArray(item.energy) || !Array.isArray(item.signal) || item.energy.length < 3 ||
        item.signal.length !== item.energy.length || !item.signal.every(Number.isFinite) ||
        !item.energy.every((value, index) => Number.isFinite(value) && (index === 0 || value > item.energy[index - 1]))) {
      throw new Error("Invalid or duplicate reference in pack: " + (item?.label || pack.label) + ".");
    }
    ids.add(item.id);
  }
  libraryPacks.set(JSON.stringify([pack.id, pack.version]), pack);
}

function libraryTrace({ label, energy, signal }) {
  const svg = document.createElementNS(svgNamespace, "svg");
  const path = document.createElementNS(svgNamespace, "path");
  svg.setAttribute("viewBox", "0 0 94 38");
  svg.setAttribute("class", "lcf-library-trace");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", label + " spectrum preview");
  const low = signal.reduce((minimum, value) => Math.min(minimum, value), Infinity);
  const high = signal.reduce((maximum, value) => Math.max(maximum, value), -Infinity);
  const span = energy.at(-1) - energy[0];
  path.setAttribute("d", energy.map((value, index) => {
    const x = 2 + 90 * (value - energy[0]) / span;
    const y = 36 - 34 * (signal[index] - low) / (high - low || 1);
    return (index ? "L" : "M") + x.toFixed(2) + " " + y.toFixed(2);
  }).join(" "));
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "currentColor");
  path.setAttribute("stroke-width", "1.4");
  svg.append(path);
  return svg;
}

function syncLibraryAdd() {
  field("library-add").disabled = state.busy || !field("library-list").querySelector("input:checked:not(:disabled)");
}

function renderLibrary() {
  const sample = selectedSample();
  const mode = sample.detection_mode;
  const entries = field("library-list");
  const activeIds = new Set(state.analysis.standards.map(standard => standard.library?.key));
  const selectedIds = new Set([...entries.querySelectorAll("input:checked")].map(check => check.reference.library.key));
  let hidden = 0;
  entries.replaceChildren();
  update("library-context", [elementEdge(), mode || "Sample detection mode unspecified", "Use comparable normalization"].join(" · "));
  for (const [packKey, pack] of libraryPacks) {
    for (const item of pack.standards) {
      if (!compatibleStandard(item.element, item.edge)) continue;
      const differentMode = mode && item.detection_mode !== mode;
      if (differentMode && !field("library-other").checked) {
        hidden++;
        continue;
      }
      const key = JSON.stringify([packKey, item.id]);
      const alreadyAdded = activeIds.has(key);
      const card = document.createElement("div");
      card.className = "lcf-library-entry";
      const details = document.createElement("div");
      const label = document.createElement("label");
      label.className = "lcf-inline-check";
      const check = document.createElement("input");
      check.type = "checkbox";
      check.disabled = alreadyAdded;
      check.checked = !alreadyAdded && selectedIds.has(key);
      check.dataset.alreadyAdded = String(alreadyAdded);
      check.addEventListener("change", syncLibraryAdd);
      check.reference = { ...item, library: { key, pack_id: pack.id, version: pack.version, label: pack.label, spectrum_id: item.id } };
      label.append(check, item.label + (alreadyAdded ? " (added)" : ""));
      const notes = document.createElement("p");
      notes.className = "lcf-muted";
      const valence = item.mixed_nominal_valences?.length
        ? "Mixed nominal states " + item.mixed_nominal_valences.join(" / ")
        : item.valence != null ? "Nominal state " + item.valence : "";
      notes.textContent = [
        item.detection_mode || "Mode unspecified",
        item.energy[0].toFixed(2) + "–" + item.energy.at(-1).toFixed(2) + " eV",
        item.valence_label || valence,
        item.license, item.provenance,
      ].filter(Boolean).join(" · ");
      if (typeof item.source_url === "string" && item.source_url.startsWith("https://")) {
        const source = document.createElement("a");
        source.href = item.source_url;
        source.target = "_blank";
        source.rel = "noopener noreferrer";
        source.textContent = "Dataset";
        notes.append(" ", source);
      }
      details.append(label, notes);
      card.append(details, libraryTrace(item));
      entries.append(card);
    }
  }
  field("library-other-row").hidden = !mode || (!hidden && !field("library-other").checked);
  update("library-status", entries.childElementCount ? "" : "No references match the current element, edge, and mode.");
  syncLibraryAdd();
}

async function openLibrary() {
  setError("library-error");
  field("library-other").checked = false;
  field("library-list").replaceChildren();
  field("library-dialog").showModal();
  if (!bundledLibraryLoaded) {
    await perform("Opening reference library…", async () => {
      registerLibraryPack(await getJson(await fetch("/reference-library.json")));
      bundledLibraryLoaded = true;
    }, "library-error");
  }
  renderLibrary();
}

async function loadLibraryFile() {
  const input = field("library-file");
  const file = input.files[0];
  if (!file) return;
  await perform("Reading local reference pack…", async () => {
    if (file.size > 5 * 1024 * 1024) throw new Error("Reference packs must be 5 MB or smaller.");
    registerLibraryPack(JSON.parse((await file.text()).replace(/^\uFEFF/, "")));
  }, "library-error");
  input.value = "";
  renderLibrary();
}

function addLibraryStandards() {
  const checks = [...field("library-list").querySelectorAll("input:checked:not(:disabled)")];
  if (!checks.length) return;
  addStandards(checks.map(check => ({ ...check.reference, id: "local-" + ++nextId, included: true })), "library-dialog");
}

function addStandards(standards, dialog) {
  state.analysis.standards = [...state.analysis.standards, ...standards];
  if (!state.customWindow) applySharedRange(state.analysis.samples[0]);
  state.tab = "standards";
  field(dialog).close();
  reportChange(standards.length === 1 ? "Standard added." : standards.length + " standards added.");
}

function openExample() {
  update("example-detail", state.analysis.samples.length ? "Loading this synthetic example replaces the current workspace." : "Load synthetic spectra and standards to try a batch fit.");
  setError("example-error");
  field("example-dialog").showModal();
}

async function importSamples() {
  const element = field("import-element").value;
  const edge = field("import-edge").value;
  const files = Array.from(field("sample-files").files);
  const replace = !state.analysis.samples.length || field("replace").checked;
  const detection = field("sample-mode").value;
  const provenance = field("sample-provenance").value.trim();
  if (!replace && (state.synthetic || element !== state.analysis.element || edge !== state.analysis.edge)) {
    setError("import-error", "Select Replace the current project to start a separate analysis.");
    return;
  }
  await perform("Importing spectra…", async () => {
    const samples = [];
    for (const file of files) {
      const spectra = await readSpectra(file);
      for (const spectrum of spectra) samples.push({ ...spectrum, element, edge, detection_mode: detection, provenance });
    }
    if (replace) resetProject(element, edge, samples);
    else state.analysis.samples.push(...samples);
    field("import-dialog").close();
    reportChange(samples.length + (samples.length === 1 ? " spectrum imported." : " spectra imported."));
  }, "import-error");
}

async function importStandard() {
  const element = field("reference-element").value;
  const edge = field("reference-edge").value;
  const file = field("reference-file").files[0];
  const label = field("new-label").value.trim();
  const nominal = field("new-valence").valueAsNumber;
  const detection = field("reference-mode").value;
  const provenance = field("reference-provenance").value.trim();
  if (!compatibleStandard(element, edge)) {
    setError("reference-error", "Choose a standard at the project edge, " + elementEdge() + ".");
    return;
  }
  await perform("Importing standard…", async () => {
    const [spectrum] = await readSpectra(file, { single: true });
    const reference = {
      ...spectrum, element, edge, label: label || spectrum.label,
      valence: Number.isFinite(nominal) ? nominal : null, included: true,
      detection_mode: detection, provenance,
    };
    addStandards([reference], "reference-dialog");
  }, "reference-error");
}

async function loadExample() {
  const element = field("example-element").value;
  await perform("Loading synthetic example…", async () => {
    const example = await getJson(await fetch("/api/demo?element=" + encodeURIComponent(element)));
    resetProject(example.element, example.edge, example.samples, example.standards, example.settings, true);
    field("example-dialog").close();
    reportChange("Synthetic example loaded.");
  }, "example-error");
}

async function fitBatch() {
  const input = structuredClone(state.analysis);
  await perform("Fitting spectra…", async () => {
    const result = await getJson(await postJson("/api/fit", input));
    state.result = result;
    state.lastInput = input;
    const completed = result.results.filter(sample => sample.status === "ok").length;
    update("operation", completed + " of " + result.results.length + " spectra fitted.");
  });
}

async function exportZip() {
  await perform("Preparing ZIP…", async () => {
    const response = await postJson("/api/export", { analysis: state.lastInput, result: state.result });
    if (!response.ok) await getJson(response);
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = "lcf-lab-" + state.analysis.element.toLowerCase() + "-analysis.zip";
    root.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    update("operation", "ZIP downloaded.");
  });
}

function selectSample(id) {
  state.selected = id;
  render();
}

function removeSample(id) {
  state.analysis.samples = state.analysis.samples.filter(sample => sample.id !== id);
  if (state.selected === id) state.selected = state.analysis.samples[0]?.id || null;
  if (!state.analysis.samples.length) state.analysis.standards = [];
  reportChange("Sample removed from the workspace.");
}

function removeReference(id) {
  state.analysis.standards = state.analysis.standards.filter(reference => reference.id !== id);
  if (!state.customWindow) applySharedRange(state.analysis.samples[0]);
  reportChange("Standard removed from the workspace.");
}

function appendCells(row, values) {
  for (const value of values) row.insertCell().append(value);
}

function signed(value) {
  return (value >= 0 ? "+" : "−") + Math.abs(value).toFixed(3);
}

function weightText(weight) {
  if (!Number.isFinite(weight)) return "—";
  return state.analysis.settings.sum_to_one ? (weight * 100).toFixed(1) + "%" : weight.toFixed(4);
}

function renderTree() {
  const sampleList = field("sample-list");
  sampleList.replaceChildren();
  for (const sample of state.analysis.samples) {
    const row = document.createElement("div");
    row.className = "lcf-tree-entry";
    const entry = button(sample.label, "lcf-tree-row", () => selectSample(sample.id));
    entry.setAttribute("aria-pressed", String(state.selected === sample.id));
    const remove = button("×", "lcf-remove", () => removeSample(sample.id), "Remove " + sample.label);
    remove.disabled = state.busy;
    row.append(entry, remove);
    sampleList.append(row);
  }
  const references = field("ref-list");
  references.replaceChildren();
  state.analysis.standards.forEach((reference, index) => {
    const row = document.createElement("div");
    row.className = "lcf-ref-tree-row";
    row.setAttribute("aria-disabled", String(!reference.included));
    const swatch = document.createElement("i");
    swatch.className = "lcf-ref-swatch";
    swatch.style.setProperty("--lcf-ref-color", referenceColors[index % referenceColors.length]);
    swatch.setAttribute("aria-hidden", "true");
    row.append(swatch, reference.label);
    references.append(row);
  });
  update("count", state.analysis.samples.length);
  update("ref-count", state.analysis.standards.length);
}

function createReferenceRow(reference, index) {
  const row = document.createElement("tr");
  const include = document.createElement("input");
  include.type = "checkbox";
  include.checked = reference.included;
  include.setAttribute("aria-label", "Include reference " + (index + 1));
  include.addEventListener("change", () => { reference.included = include.checked; reportChange(); });
  const name = document.createElement("input");
  name.type = "text";
  name.maxLength = 100;
  name.value = reference.label;
  name.setAttribute("aria-label", "Reference " + (index + 1) + " label");
  name.title = [reference.source_file, reference.detection_mode, reference.provenance].filter(Boolean).join(" · ");
  name.addEventListener("change", () => {
    reference.label = name.value.trim() || reference.label;
    name.value = reference.label;
    reportChange();
  });
  const valence = document.createElement("input");
  valence.type = "number";
  valence.step = "any";
  valence.className = "lcf-reference-valence";
  valence.value = Number.isFinite(reference.valence) ? Number(reference.valence.toPrecision(5)) : "";
  valence.title = reference.valence == null ? "" : String(reference.valence);
  valence.setAttribute("aria-label", "Reference " + (index + 1) + " nominal oxidation state");
  valence.addEventListener("change", () => {
    reference.valence = Number.isFinite(valence.valueAsNumber) ? valence.valueAsNumber : null;
    valence.title = reference.valence == null ? "" : String(reference.valence);
    reportChange();
  });
  const remove = button("×", "lcf-remove", () => removeReference(reference.id), "Remove reference " + (index + 1));
  appendCells(row, [include, name, valence, "—", remove]);
  return row;
}

function renderReferences(result) {
  const table = field("reference-rows");
  if (renderedStandards !== state.analysis.standards) {
    renderedStandards = state.analysis.standards;
    table.replaceChildren(...renderedStandards.map(createReferenceRow));
  }
  table.querySelectorAll("input,button").forEach(control => { control.disabled = state.busy; });
  Array.from(table.rows).forEach((row, index) => {
    const reference = state.analysis.standards[index];
    row.cells[3].textContent = weightText(result?.weights?.find(item => item.id === reference.id)?.weight);
  });
  field("reference-empty").hidden = state.analysis.standards.length > 0;
  update("valence", Number.isFinite(result?.nominal_valence) ? result.nominal_valence.toFixed(2) : "—");
  update("offset", Number.isFinite(result?.energy_shift) ? signed(result.energy_shift) + " eV" : "—");
  update("rmse", Number.isFinite(result?.rmse) ? result.rmse.toPrecision(4) : "—");
}

function renderBatch() {
  const table = field("results");
  table.replaceChildren();
  for (const sample of state.analysis.samples) {
    const result = sampleResult(sample.id);
    const row = document.createElement("tr");
    row.dataset.selected = String(sample.id === state.selected);
    const select = button(sample.label, "lcf-sample-link", () => selectSample(sample.id), "View " + sample.label);
    const weights = result?.weights?.map(item => item.label + " " + weightText(item.weight)).join(" / ") || "—";
    let status = "Pending";
    if (result?.status === "ok") status = result.warnings?.length ? "Review" : "Fit complete";
    else if (result) status = /coverage|energy range/i.test(result.error || "") ? "Coverage" : "Fit failed";
    appendCells(row, [
      select, weights,
      Number.isFinite(result?.nominal_valence) ? result.nominal_valence.toFixed(2) : "—",
      Number.isFinite(result?.energy_shift) ? signed(result.energy_shift) : "—",
      Number.isFinite(result?.rmse) ? result.rmse.toPrecision(4) : "—",
      status,
    ]);
    table.append(row);
  }
  field("result-empty").hidden = state.analysis.samples.length > 0;
  const completed = state.result?.results.filter(item => item.status === "ok").length || 0;
  update("result-count", state.result ? completed + " of " + state.analysis.samples.length + " fitted" : "");
}

function drawPlot() {
  const box = field("chart");
  const sample = selectedSample();
  if (!sample) {
    const empty = document.createElement("p");
    empty.className = "lcf-chart-empty";
    empty.textContent = "Import normalized spectra or load a synthetic example to begin.";
    box.replaceChildren(empty);
    return;
  }
  const width = Math.floor(box.clientWidth);
  if (width < 180) return;
  const height = 344;
  const left = 95;
  const right = width - 13;
  const top = 15;
  const signalBottom = 207;
  const residualTop = 234;
  const residualBottom = 295;
  const axisLabelX = 18;
  const low = sample.energy[0];
  const high = sample.energy.at(-1);
  const result = sampleResult(sample.id);
  const showStandards = field("show-references").checked;
  const plottedStandards = showStandards ? state.analysis.standards.filter(reference => reference.included) : [];
  let minimum = Infinity;
  let maximum = -Infinity;
  function includeInDomain(energy, signal) {
    for (let index = 0; index < energy.length; index++) {
      if (energy[index] >= low && energy[index] <= high) {
        minimum = Math.min(minimum, signal[index]);
        maximum = Math.max(maximum, signal[index]);
      }
    }
  }
  includeInDomain(sample.energy, sample.signal);
  for (const standard of plottedStandards) includeInDomain(standard.energy, standard.signal);
  if (result?.status === "ok") includeInDomain(result.energy, result.fitted);
  const pad = Math.max((maximum - minimum) * 0.05, Math.max(Math.abs(minimum), Math.abs(maximum), 1) * 0.001);
  minimum -= pad;
  maximum += pad;
  const x = energy => left + (energy - low) / (high - low) * (right - left);
  const y = signal => signalBottom - (signal - minimum) / (maximum - minimum) * (signalBottom - top);
  const svg = document.createElementNS(svgNamespace, "svg");
  svg.setAttribute("width", width);
  svg.setAttribute("height", height);
  svg.setAttribute("viewBox", "0 0 " + width + " " + height);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", sample.label + " spectrum at " + elementEdge() + (result?.status === "ok" ? " with fitted signal and residual" : ""));
  function mark(type, attributes, parent = svg) {
    const shape = document.createElementNS(svgNamespace, type);
    Object.entries(attributes).forEach(([key, value]) => shape.setAttribute(key, value));
    parent.append(shape);
    return shape;
  }
  function text(value, xpos, ypos, anchor = "middle", size = 15.6) {
    const label = mark("text", { x: xpos, y: ypos, "text-anchor": anchor, fill: "var(--lcf-sub)", "font-size": size });
    label.textContent = value;
    return label;
  }
  function line(x1, y1, x2, y2, stroke = "var(--lcf-grid)") {
    mark("line", { x1, y1, x2, y2, stroke, "stroke-width": 1 });
  }
  function trace(energy, signal, mapper, stroke, strokeWidth, parent, dash = "") {
    // Keep both extrema of each small group to retain narrow peaks in dense display data.
    const stride = Math.max(1, Math.ceil(energy.length / 1200));
    const coordinates = [];
    for (let start = 0; start < energy.length; start += stride) {
      let minIndex = start;
      let maxIndex = start;
      for (let index = start + 1; index < Math.min(start + stride, energy.length); index++) {
        if (signal[index] < signal[minIndex]) minIndex = index;
        if (signal[index] > signal[maxIndex]) maxIndex = index;
      }
      const indexes = minIndex === maxIndex ? [minIndex] : [Math.min(minIndex, maxIndex), Math.max(minIndex, maxIndex)];
      for (const index of indexes) {
        coordinates.push((coordinates.length ? "L" : "M") + x(energy[index]).toFixed(2) + " " + mapper(signal[index]).toFixed(2));
      }
    }
    mark("path", { d: coordinates.join(" "), fill: "none", stroke, "stroke-width": strokeWidth, "stroke-dasharray": dash, "stroke-linejoin": "round" }, parent);
  }
  const definitions = mark("defs", {});
  const signalClip = mark("clipPath", { id: "lcf-signal-clip" }, definitions);
  const residualClip = mark("clipPath", { id: "lcf-residual-clip" }, definitions);
  mark("rect", { x: left, y: top, width: right - left, height: signalBottom - top }, signalClip);
  mark("rect", { x: left, y: residualTop, width: right - left, height: residualBottom - residualTop }, residualClip);
  const start = Math.max(low, state.analysis.settings.fit_min ?? low);
  const end = Math.min(high, state.analysis.settings.fit_max ?? high);
  if (start < end) {
    const highlight = { x: x(start), width: x(end) - x(start), fill: "var(--lcf-blue-wash)", opacity: 0.75 };
    mark("rect", { ...highlight, y: top, height: signalBottom - top });
    mark("rect", { ...highlight, y: residualTop, height: residualBottom - residualTop });
  }
  const digits = high - low < 8 ? 2 : 0;
  const labelWidth = Math.max(low.toFixed(digits).length, high.toFixed(digits).length) * 9;
  const tickCount = Math.min(width < 400 ? 3 : 6, Math.max(1, Math.floor((right - left) / (1.6 * labelWidth + 6))));
  for (let index = 0; index <= tickCount; index++) {
    const energy = low + (high - low) * index / tickCount;
    line(x(energy), top, x(energy), signalBottom);
    line(x(energy), residualTop, x(energy), residualBottom);
    text(energy.toFixed(digits), x(energy), residualBottom + 20, index === 0 ? "start" : index === tickCount ? "end" : "middle");
  }
  function axisNumber(value) {
    const magnitude = Math.abs(value);
    return magnitude !== 0 && (magnitude < 0.001 || magnitude >= 10000)
      ? value.toExponential(1) : Number(value.toPrecision(3)).toString();
  }
  for (let index = 0; index <= 4; index++) {
    const value = minimum + (maximum - minimum) * index / 4;
    line(left, y(value), right, y(value));
    text(axisNumber(value), left - 6, y(value) + 4, "end");
  }
  mark("rect", { x: left, y: top, width: right - left, height: signalBottom - top, fill: "none", stroke: "var(--lcf-line)" });
  mark("rect", { x: left, y: residualTop, width: right - left, height: residualBottom - residualTop, fill: "none", stroke: "var(--lcf-line)" });
  const signalLabelY = (top + signalBottom) / 2;
  const residualLabelY = (residualTop + residualBottom) / 2;
  const signalLabel = text("Normalized signal", axisLabelX, signalLabelY, "middle", 16.8);
  signalLabel.setAttribute("transform", "rotate(-90 " + axisLabelX + " " + signalLabelY + ")");
  const residualLabel = text("Residual", axisLabelX, residualLabelY, "middle", 16.8);
  residualLabel.setAttribute("transform", "rotate(-90 " + axisLabelX + " " + residualLabelY + ")");
  text("Energy (eV)", (left + right) / 2, height - 6, "middle", 16.8);
  const mainGroup = mark("g", { "clip-path": "url(#lcf-signal-clip)" });
  for (const reference of plottedStandards) {
    const index = state.analysis.standards.indexOf(reference);
    trace(reference.energy, reference.signal, y, referenceColors[index % referenceColors.length], 1.15, mainGroup, "4 3");
  }
  trace(sample.energy, sample.signal, y, "var(--lcf-observed)", 1.5, mainGroup);
  const zero = (residualTop + residualBottom) / 2;
  line(left, zero, right, zero, "var(--lcf-line)");
  text("0", left - 5, zero + 4, "end");
  if (result?.status === "ok") {
    trace(result.energy, result.fitted, y, "var(--lcf-blue)", 2, mainGroup);
    const limit = result.residual.reduce((largest, value) => Math.max(largest, Math.abs(value)), 0.00001) * 1.08;
    const residualGroup = mark("g", { "clip-path": "url(#lcf-residual-clip)" });
    trace(result.energy, result.residual, value => zero - value / limit * (zero - residualTop), "var(--lcf-residual)", 1.2, residualGroup);
    text("+" + axisNumber(limit), left - 6, residualTop + 8, "end");
    text("−" + axisNumber(limit), left - 6, residualBottom, "end");
  }
  box.replaceChildren(svg);
}

function renderWarnings(sample, result) {
  const warnings = field("fit-warnings");
  const messages = new Set(result?.warnings || []);
  if (sample?.detection_mode) {
    const mismatched = state.analysis.standards.filter(standard => standard.included && standard.detection_mode && standard.detection_mode !== sample.detection_mode);
    for (const standard of mismatched) {
      messages.add(standard.label + " uses " + standard.detection_mode + " while this sample uses " + sample.detection_mode + ". Check whether their line shapes are comparable.");
    }
  }
  warnings.replaceChildren(...Array.from(messages, message => {
    const item = document.createElement("li");
    item.textContent = message;
    return item;
  }));
  warnings.hidden = messages.size === 0;
}

function render() {
  const sample = selectedSample();
  const result = sampleResult(sample?.id);
  const coverage = sharedRange(sample);
  const settings = state.analysis.settings;
  const validWindow = Number.isFinite(settings.fit_min) && Number.isFinite(settings.fit_max) && settings.fit_min < settings.fit_max;
  const outside = validWindow && coverage && (settings.fit_min < coverage[0] || settings.fit_max > coverage[1]);
  const error = result?.error || (outside ? "The fit window exceeds the shared energy range for this sample and the included standards." : "");
  update("project-title", sample ? elementEdge() + " · " + (state.synthetic ? "Demo project" : "Analysis") : "New analysis");
  field("demo-tag").hidden = !state.synthetic;
  update("sample-title", sample?.label || "Spectrum");
  update("spectrum-detail", sample ? [elementEdge(), sample.detection_mode, "Normalized signal"].filter(Boolean).join(" · ") : "");
  update("project-edge", sample ? elementEdge() : "");
  update("file-status", state.synthetic ? "Synthetic demo spectra" : "Local analysis");
  update("coverage", coverage ? coverage.map(value => Number(value.toFixed(5))).join(" to ") + " eV" : "—");
  update("fit-message", result?.status === "ok" ? result.energy.length + " fitted points · " + (state.synthetic ? "Synthetic dataset" : "Selected fit") : "");
  update("error-text", error);
  field("error").hidden = !error;
  action("overlap").hidden = !outside;
  root.querySelectorAll("[data-setting]").forEach(control => {
    if (control.type === "checkbox") control.checked = settings[control.dataset.setting];
    else control.value = settings[control.dataset.setting] ?? "";
    control.disabled = state.busy;
  });
  const showReferences = state.tab === "standards";
  root.querySelector("#lcf-ref-tab").setAttribute("aria-selected", String(showReferences));
  root.querySelector("#lcf-settings-tab").setAttribute("aria-selected", String(!showReferences));
  root.querySelector("#lcf-ref-panel").hidden = !showReferences;
  root.querySelector("#lcf-settings-panel").hidden = showReferences;
  action("import").disabled = state.busy;
  action("example").disabled = state.busy;
  action("reference").disabled = state.busy || !sample;
  action("library").disabled = state.busy || !sample;
  action("fit").disabled = state.busy || !sample || !validWindow || !state.analysis.standards.some(standard => standard.included);
  action("export").disabled = state.busy || !state.result;
  action("overlap").disabled = state.busy;
  root.querySelectorAll("dialog input,dialog select,dialog button").forEach(control => {
    control.disabled = state.busy || control.dataset.alreadyAdded === "true";
  });
  syncLibraryAdd();
  renderTree();
  renderReferences(result);
  renderBatch();
  renderWarnings(sample, result);
  drawPlot();
}

setOptions("[data-elements]", elements.map(([symbol, name]) => [symbol, symbol + " · " + name]));
setOptions("[data-edges]", Object.entries(edgeLabels));
setOptions("[data-detection]", detectionModes);
action("import").addEventListener("click", openImport);
action("reference").addEventListener("click", openReference);
action("library").addEventListener("click", openLibrary);
field("library-file").addEventListener("change", loadLibraryFile);
field("library-other").addEventListener("change", renderLibrary);
action("example").addEventListener("click", openExample);
action("fit").addEventListener("click", fitBatch);
action("export").addEventListener("click", exportZip);
action("overlap").addEventListener("click", () => {
  applySharedRange();
  state.customWindow = true;
  state.tab = "settings";
  reportChange();
});
field("show-references").addEventListener("change", drawPlot);
root.querySelector("#lcf-ref-tab").addEventListener("click", () => { state.tab = "standards"; render(); });
root.querySelector("#lcf-settings-tab").addEventListener("click", () => { state.tab = "settings"; render(); });
root.querySelectorAll("[data-action=close-dialog]").forEach(control => {
  control.addEventListener("click", () => control.closest("dialog").close());
});
root.querySelectorAll("dialog").forEach(dialog => {
  dialog.addEventListener("cancel", event => { if (state.busy) event.preventDefault(); });
});
for (const [name, handler] of [["import-form", importSamples], ["reference-form", importStandard], ["library-form", addLibraryStandards], ["example-form", loadExample]]) {
  field(name).addEventListener("submit", event => { event.preventDefault(); if (!state.busy) handler(); });
}
root.querySelectorAll("[data-setting]").forEach(control => {
  control.addEventListener("change", () => {
    const key = control.dataset.setting;
    if (control.type === "checkbox") state.analysis.settings[key] = control.checked;
    else state.analysis.settings[key] = Number.isFinite(control.valueAsNumber) ? control.valueAsNumber : null;
    if (key === "fit_min" || key === "fit_max") state.customWindow = true;
    reportChange();
  });
});
render();
new ResizeObserver(drawPlot).observe(field("chart"));
