const state = {
  cases: [],
  selectedCase: null,
  latestResult: null,
};

const elements = {
  connectionStatus: document.querySelector("#connection-status"),
  moduleCount: document.querySelector("#module-count"),
  moduleGrid: document.querySelector("#module-grid"),
  workbench: document.querySelector("#workbench"),
  caseForm: document.querySelector("#case-form"),
  dynamicFields: document.querySelector("#dynamic-fields"),
  runCase: document.querySelector("#run-case"),
  resultPanel: document.querySelector("#result-panel"),
  globalError: document.querySelector("#global-error"),
  globalErrorMessage: document.querySelector("#global-error-message"),
  toast: document.querySelector("#toast"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatValue(value) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value);
}

function showToast(message) {
  elements.toast.textContent = message;
  elements.toast.classList.add("show");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => elements.toast.classList.remove("show"), 2800);
}

async function apiRequest(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) {
    const message = body?.error?.message || body?.detail || `请求失败（HTTP ${response.status}）`;
    const error = new Error(message);
    error.details = body?.error?.details;
    throw error;
  }
  return body;
}

function setConnectionStatus(mode, text) {
  elements.connectionStatus.classList.remove("online", "offline");
  elements.connectionStatus.classList.add(mode);
  elements.connectionStatus.querySelector("span:last-child").textContent = text;
}

async function checkHealth() {
  try {
    const health = await apiRequest("/health");
    setConnectionStatus("online", health.status === "ok" ? "后端在线" : "状态未知");
  } catch {
    setConnectionStatus("offline", "后端离线");
  }
}

async function loadCases() {
  elements.globalError.classList.add("is-hidden");
  elements.moduleGrid.innerHTML = `
    <article class="module-card skeleton-card" aria-hidden="true">
      <div class="skeleton line-short"></div>
      <div class="skeleton line-long"></div>
      <div class="skeleton block"></div>
    </article>`;
  try {
    const response = await apiRequest("/api/v1/cases");
    state.cases = response.items || [];
    elements.moduleCount.textContent = state.cases.length;
    renderCases();
    setConnectionStatus("online", "后端在线");

    const caseId = new URLSearchParams(window.location.hash.slice(1)).get("case");
    if (caseId && state.cases.some((item) => item.case_id === caseId)) {
      selectCase(caseId, false);
    }
  } catch (error) {
    state.cases = [];
    elements.moduleCount.textContent = "0";
    elements.moduleGrid.innerHTML = "";
    elements.globalErrorMessage.textContent = error.message;
    elements.globalError.classList.remove("is-hidden");
    setConnectionStatus("offline", "后端离线");
  }
}

function renderCases() {
  if (!state.cases.length) {
    elements.moduleGrid.innerHTML = `
      <div class="empty-catalog">
        <strong>还没有已注册模块</strong>
        <p>为案例包添加 register_cases(registry)，重启后端后入口会自动出现。</p>
      </div>`;
    return;
  }

  elements.moduleGrid.innerHTML = state.cases
    .map(
      (item, index) => `
        <article class="module-card" tabindex="0" role="button"
          data-case-id="${escapeHtml(item.case_id)}"
          aria-label="进入${escapeHtml(item.name)}">
          <div class="module-meta">
            <span>M-${String(index + 1).padStart(2, "0")}</span>
            <span>V${escapeHtml(item.version)}</span>
          </div>
          <h3>${escapeHtml(item.name)}</h3>
          <p>${escapeHtml(item.description || `${item.course}教学实验模块`)}</p>
          <span class="module-enter" aria-hidden="true">↗</span>
        </article>`,
    )
    .join("");

  elements.moduleGrid.querySelectorAll(".module-card[data-case-id]").forEach((card) => {
    card.addEventListener("click", () => selectCase(card.dataset.caseId));
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectCase(card.dataset.caseId);
      }
    });
  });
}

function selectCase(caseId, shouldScroll = true) {
  const selected = state.cases.find((item) => item.case_id === caseId);
  if (!selected) return;
  state.selectedCase = selected;
  state.latestResult = null;
  const index = state.cases.findIndex((item) => item.case_id === caseId) + 1;

  document.querySelector("#case-index").textContent = `M-${String(index).padStart(2, "0")}`;
  document.querySelector("#case-course").textContent = selected.course;
  document.querySelector("#case-name").textContent = selected.name;
  document.querySelector("#case-description").textContent =
    selected.description || "该模块暂未提供详细说明。";
  document.querySelector("#case-version").textContent = `v${selected.version}`;
  document.querySelector("#case-datasets").innerHTML = selected.output_datasets.length
    ? selected.output_datasets
        .map((name) => `<span class="dataset-chip">${escapeHtml(name)}</span>`)
        .join("")
    : '<span class="dataset-chip">动态输出</span>';

  renderInputForm(selected.input_schema || {});
  elements.resultPanel.classList.add("is-hidden");
  elements.workbench.classList.remove("is-hidden");
  window.history.replaceState(null, "", `#case=${encodeURIComponent(caseId)}`);
  if (shouldScroll) elements.workbench.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderInputForm(schema) {
  const properties = schema.properties || {};
  const required = new Set(schema.required || []);
  const entries = Object.entries(properties);

  if (!entries.length) {
    elements.dynamicFields.innerHTML = `
      <div class="field-group full-width">
        <label class="field-label" for="raw-input">输入 JSON <span class="required-mark">必填</span></label>
        <textarea id="raw-input" name="__raw_input" data-kind="object" required>{}</textarea>
        <p class="field-help">此模块未声明字段级 schema，请直接输入 JSON 对象。</p>
      </div>`;
    return;
  }

  elements.dynamicFields.innerHTML = entries
    .map(([name, definition]) => createField(name, definition, required.has(name)))
    .join("");
}

function createField(name, definition, isRequired) {
  const type = Array.isArray(definition.type)
    ? definition.type.find((item) => item !== "null")
    : definition.type || "string";
  const title = definition.title || name;
  const description = definition.description || buildConstraintHint(definition);
  const requiredLabel = isRequired ? '<span class="required-mark">必填</span>' : "";
  const common = `id="field-${escapeHtml(name)}" name="${escapeHtml(name)}" data-kind="${escapeHtml(type)}" ${isRequired ? "required" : ""}`;
  let control = "";
  let groupClass = "field-group";

  if (definition.enum) {
    control = `<select ${common}>
      ${isRequired ? "" : '<option value="">— 不设置 —</option>'}
      ${definition.enum.map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`).join("")}
    </select>`;
  } else if (type === "boolean") {
    return `<label class="field-group checkbox-field" for="field-${escapeHtml(name)}">
      <input ${common} type="checkbox" ${definition.default === true ? "checked" : ""} />
      <span>${escapeHtml(title)}</span>${requiredLabel}
    </label>`;
  } else if (type === "integer" || type === "number") {
    control = `<input ${common} type="number" ${type === "integer" ? 'step="1"' : 'step="any"'}
      ${definition.minimum !== undefined ? `min="${definition.minimum}"` : ""}
      ${definition.maximum !== undefined ? `max="${definition.maximum}"` : ""}
      ${definition.default !== undefined ? `value="${escapeHtml(definition.default)}"` : ""} />`;
  } else if (type === "array" || type === "object") {
    groupClass += " full-width";
    const defaultValue = definition.default ?? (type === "array" ? [] : {});
    control = `<textarea ${common}>${escapeHtml(JSON.stringify(defaultValue, null, 2))}</textarea>`;
  } else {
    const longText = definition.maxLength > 120 || definition.format === "multiline";
    if (longText) groupClass += " full-width";
    control = longText
      ? `<textarea ${common} maxlength="${definition.maxLength || ""}">${escapeHtml(definition.default ?? "")}</textarea>`
      : `<input ${common} type="text" ${definition.minLength ? `minlength="${definition.minLength}"` : ""}
          ${definition.maxLength ? `maxlength="${definition.maxLength}"` : ""}
          value="${escapeHtml(definition.default ?? "")}" />`;
  }

  return `<div class="${groupClass}">
    <label class="field-label" for="field-${escapeHtml(name)}">
      <span>${escapeHtml(title)}</span>${requiredLabel}
    </label>
    ${control}
    ${description ? `<p class="field-help">${escapeHtml(description)}</p>` : ""}
  </div>`;
}

function buildConstraintHint(definition) {
  const hints = [];
  if (definition.minimum !== undefined) hints.push(`最小值 ${definition.minimum}`);
  if (definition.maximum !== undefined) hints.push(`最大值 ${definition.maximum}`);
  if (definition.minLength !== undefined) hints.push(`至少 ${definition.minLength} 个字符`);
  if (definition.maxLength !== undefined) hints.push(`最多 ${definition.maxLength} 个字符`);
  return hints.join("，");
}

function collectInput() {
  const rawField = elements.caseForm.elements.namedItem("__raw_input");
  if (rawField) {
    const parsed = JSON.parse(rawField.value);
    if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
      throw new Error("输入必须是 JSON 对象");
    }
    return parsed;
  }

  const input = {};
  elements.dynamicFields.querySelectorAll("[name]").forEach((field) => {
    const kind = field.dataset.kind;
    if (kind === "boolean") {
      input[field.name] = field.checked;
      return;
    }
    if (field.value === "" && !field.required) return;
    if (kind === "integer") input[field.name] = Number.parseInt(field.value, 10);
    else if (kind === "number") input[field.name] = Number.parseFloat(field.value);
    else if (kind === "array" || kind === "object") input[field.name] = JSON.parse(field.value);
    else input[field.name] = field.value;
  });
  return input;
}

async function executeSelectedCase(event) {
  event.preventDefault();
  if (!state.selectedCase) return;
  let input;
  try {
    input = collectInput();
  } catch (error) {
    showToast(`输入解析失败：${error.message}`);
    return;
  }

  elements.runCase.disabled = true;
  elements.runCase.querySelector("span:first-child").textContent = "正在运行…";
  try {
    const result = await apiRequest("/api/v1/executions", {
      method: "POST",
      body: JSON.stringify({ case_id: state.selectedCase.case_id, input }),
    });
    state.latestResult = result;
    renderResult(result);
    showToast("模块运行完成");
  } catch (error) {
    const firstDetail = error.details?.errors?.[0]?.msg;
    showToast(firstDetail ? `${error.message}：${firstDetail}` : error.message);
  } finally {
    elements.runCase.disabled = false;
    elements.runCase.querySelector("span:first-child").textContent = "运行模块";
  }
}

function renderResult(result) {
  const payload = result.payload || {};
  document.querySelector("#request-id").textContent = result.request_id;
  document.querySelector("#request-id").title = result.request_id;
  document.querySelector("#download-csv").href =
    `/api/v1/results/${encodeURIComponent(result.request_id)}?format=csv`;
  document.querySelector("#result-summary").textContent = payload.summary || "执行完成";
  document.querySelector("#raw-json").textContent = JSON.stringify(result, null, 2);

  const metrics = Object.entries(payload.metrics || {});
  document.querySelector("#metric-grid").innerHTML = metrics.length
    ? metrics
        .map(
          ([key, value]) => `<article class="metric-card">
            <span>${escapeHtml(key)}</span>
            <strong>${escapeHtml(formatValue(value))}</strong>
          </article>`,
        )
        .join("")
    : "";

  document.querySelector("#dataset-results").innerHTML = (payload.datasets || [])
    .map(renderDataset)
    .join("");
  document.querySelector("#diagnostic-list").innerHTML = (payload.diagnostics || [])
    .map(
      (item) => `<div class="diagnostic-item ${escapeHtml(item.level)}">
        <span class="diagnostic-code">${escapeHtml(item.code)}</span>
        <span>${escapeHtml(item.message)}</span>
      </div>`,
    )
    .join("");

  elements.resultPanel.classList.remove("is-hidden");
  elements.resultPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderDataset(dataset) {
  const columns = dataset.columns || [];
  const rows = dataset.rows || [];
  return `<section class="dataset-block">
    <div class="dataset-title">
      <h4>${escapeHtml(dataset.title)}</h4>
      <span>${escapeHtml(dataset.name)} · ${rows.length} ROWS</span>
    </div>
    <div class="table-scroll">
      <table class="result-table">
        <thead><tr>${columns
          .map(
            (column) =>
              `<th>${escapeHtml(column.title)}${column.unit ? ` / ${escapeHtml(column.unit)}` : ""}</th>`,
          )
          .join("")}</tr></thead>
        <tbody>${
          rows.length
            ? rows
                .map(
                  (row) => `<tr>${columns
                    .map((column) => {
                      const value = row[column.key];
                      const rendered = escapeHtml(formatValue(value));
                      return `<td>${typeof value === "object" && value !== null ? `<code>${rendered}</code>` : rendered}</td>`;
                    })
                    .join("")}</tr>`,
                )
                .join("")
            : `<tr><td colspan="${Math.max(columns.length, 1)}">该数据集没有记录</td></tr>`
        }</tbody>
      </table>
    </div>
  </section>`;
}

document.querySelector("#refresh-cases").addEventListener("click", () => {
  loadCases();
  document.querySelector("#module-catalog").scrollIntoView({ behavior: "smooth" });
});
document.querySelector("#retry-load").addEventListener("click", loadCases);
elements.connectionStatus.addEventListener("click", checkHealth);
elements.caseForm.addEventListener("submit", executeSelectedCase);
document.querySelector("#close-workbench").addEventListener("click", () => {
  elements.workbench.classList.add("is-hidden");
  window.history.replaceState(null, "", window.location.pathname);
  document.querySelector("#module-catalog").scrollIntoView({ behavior: "smooth" });
});

checkHealth();
loadCases();
