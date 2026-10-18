const state = {
  cases: [],
  selectedCase: null,
  latestResult: null,
  uploadedFile: null,
  history: [],
  historySubmitterFilter: "",
  expandedHistoryCase: null,
  assistantMessages: [],
  assistantCaseId: null,
  assistantBusy: false,
  moduleIntroductionRequest: 0,
  codeReviewRequest: 0,
};

function isCodeGraderCase(caseId) {
  const item = state.cases.find((candidate) => candidate.case_id === caseId);
  return item?.input_schema?.["x-ui-mode"] === "python-file";
}

function courseLabel(caseId, oneBasedIndex) {
  const declaredNumber = caseById(caseId)?.course_number;
  const number = Number.isInteger(declaredNumber)
    ? String(declaredNumber).padStart(2, "0")
    : String(oneBasedIndex).padStart(2, "0");
  return `课程 ${number}`;
}

function caseById(caseId) {
  return state.cases.find((item) => item.case_id === caseId) || null;
}

function historyForCase(caseId) {
  return filteredSubmissionHistory().filter((item) => item.case_id === caseId);
}

function submitterFilterValue(item) {
  return item.submitter ? String(item.submitter) : "__unassigned__";
}

function filteredSubmissionHistory() {
  if (!state.historySubmitterFilter) return state.history;
  return state.history.filter(
    (item) => submitterFilterValue(item) === state.historySubmitterFilter,
  );
}
const HISTORY_DB_NAME = "ai-tutor-lab";
const HISTORY_STORE_NAME = "submissions";
const ASSISTANT_STORE_NAME = "assistant_chat";
const ASSISTANT_CONTEXT_KEY = "course-assistant-main";
const STUDENT_ID_STORAGE_KEY = "ai-tutor-student-id";
const SUBMITTER_STORAGE_KEY = "ai-tutor-submitter";

function getOrCreateStudentId() {
  try {
    const existing = window.localStorage.getItem(STUDENT_ID_STORAGE_KEY);
    if (existing) return existing;
    const generated = window.crypto?.randomUUID?.() || `student-${Date.now()}-${Math.random()}`;
    window.localStorage.setItem(STUDENT_ID_STORAGE_KEY, generated);
    return generated;
  } catch {
    return `student-session-${Date.now()}-${Math.random()}`;
  }
}

const studentId = getOrCreateStudentId();

function getSavedSubmitter() {
  try {
    return window.localStorage.getItem(SUBMITTER_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

function saveSubmitter(value) {
  try {
    window.localStorage.setItem(SUBMITTER_STORAGE_KEY, value);
  } catch {
    // The backend request still carries the value when browser storage is unavailable.
  }
}

const API_BASE_URL = String(window.AI_TUTOR_API_BASE_URL || "").replace(/\/$/, "");

function apiUrl(path) {
  return `${API_BASE_URL}${path}`;
}

const elements = {
  connectionStatus: document.querySelector("#connection-status"),
  moduleCount: document.querySelector("#module-count"),
  moduleGrid: document.querySelector("#module-grid"),
  workbench: document.querySelector("#workbench"),
  caseForm: document.querySelector("#case-form"),
  dynamicFields: document.querySelector("#dynamic-fields"),
  runCase: document.querySelector("#run-case"),
  resultPanel: document.querySelector("#result-panel"),
  historyPanel: document.querySelector("#submission-history"),
  historySubmitterFilter: document.querySelector("#history-submitter-filter"),
  submissionTimeline: document.querySelector("#submission-timeline"),
  codeDiff: document.querySelector("#code-diff"),
  globalError: document.querySelector("#global-error"),
  globalErrorMessage: document.querySelector("#global-error-message"),
  toast: document.querySelector("#toast"),
  assistantMessages: document.querySelector("#assistant-messages"),
  assistantForm: document.querySelector("#assistant-form"),
  assistantInput: document.querySelector("#assistant-input"),
  assistantSend: document.querySelector("#assistant-send"),
  assistantStatus: document.querySelector("#assistant-model-status"),
  assistantContext: document.querySelector("#assistant-context"),
  clearAssistantChat: document.querySelector("#clear-assistant-chat"),
  moduleIntroduction: document.querySelector("#module-introduction"),
  moduleIntroductionName: document.querySelector("#module-introduction-name"),
  moduleIntroductionContent: document.querySelector("#module-introduction-content"),
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
  const response = await fetch(apiUrl(path), {
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
  const description = `${text}，点击重新检查`;
  elements.connectionStatus.title = description;
  elements.connectionStatus.setAttribute("aria-label", description);
}

async function checkHealth() {
  try {
    const health = await apiRequest("/health");
    setConnectionStatus("online", health.status === "ok" ? "可以提交" : "状态未知");
  } catch {
    setConnectionStatus("offline", "暂不可用");
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
    state.cases = (response.items || [])
      .filter((item) => item.catalog_visible !== false)
      .sort(
        (left, right) =>
          Number(left.course_number ?? Number.MAX_SAFE_INTEGER) -
          Number(right.course_number ?? Number.MAX_SAFE_INTEGER),
      );
    if (elements.moduleCount) elements.moduleCount.textContent = state.cases.length;
    renderCases();
    setConnectionStatus("online", "可以提交");

    const caseId = new URLSearchParams(window.location.hash.slice(1)).get("case");
    if (caseId && state.cases.some((item) => item.case_id === caseId)) {
      selectCase(caseId, false);
    }
  } catch (error) {
    state.cases = [];
    if (elements.moduleCount) elements.moduleCount.textContent = "0";
    elements.moduleGrid.innerHTML = "";
    elements.globalErrorMessage.textContent = error.message;
    elements.globalError.classList.remove("is-hidden");
    setConnectionStatus("offline", "暂不可用");
  }
}

function renderCases() {
  if (!state.cases.length) {
    elements.moduleGrid.innerHTML = `
      <div class="empty-catalog">
        <strong>项目暂未开放</strong>
        <p>请稍后刷新页面，或联系课程教师。</p>
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
            <span>${courseLabel(item.case_id, index + 1)}</span>
            <span>${escapeHtml(item.course)}</span>
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
  state.uploadedFile = null;
  const index = state.cases.findIndex((item) => item.case_id === caseId) + 1;

  document.querySelector("#case-index").textContent = courseLabel(caseId, index);
  document.querySelector("#case-course").textContent = selected.course;
  document.querySelector("#case-name").textContent = selected.name;
  document.querySelector("#case-description").textContent =
    selected.description || "该模块暂未提供详细说明。";
  const datasetLabels = {
    functional_tests: "功能完成度",
    runtime_tests: "隔离运行测试",
    runtime_packets: "基座返回报文",
    runtime_curve: "运行复杂度曲线",
    runtime_observations: "运行输出数据",
    quality_scores: "代码质量",
    code_issues: "问题与建议",
    benchmark_curve: "时间-规模关系",
    fitted_curve: "拟合复杂度曲线",
    complexity_analysis: "复杂度拟合分析",
  };
  document.querySelector("#case-datasets").innerHTML = selected.output_datasets.length
    ? selected.output_datasets
        .map((name) => `<span class="dataset-chip">${escapeHtml(datasetLabels[name] || name)}</span>`)
        .join("")
    : '<span class="dataset-chip">动态输出</span>';

  renderInputForm(selected.input_schema || {});
  elements.resultPanel.classList.add("is-hidden");
  elements.historyPanel.classList.toggle("is-hidden", !isCodeGraderCase(caseId));
  if (isCodeGraderCase(caseId)) {
    loadSubmissionHistory();
  }
  elements.workbench.classList.remove("is-hidden");
  window.history.replaceState(null, "", `#case=${encodeURIComponent(caseId)}`);
  introduceSelectedModule(selected);
  if (shouldScroll) {
    elements.moduleIntroduction.scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

function renderInputForm(schema) {
  document.querySelector("#input-panel-title").textContent = "设置实验输入";
  document.querySelector(".schema-note").textContent = "按项目要求填写";
  elements.runCase.querySelector("span:first-child").textContent = "运行模块";
  if (schema["x-ui-mode"] === "python-file") {
    renderPythonFileUploader(schema);
    return;
  }
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

function renderPythonFileUploader(schema) {
  const maxBytes = Number(schema["x-max-file-bytes"] || 500000);
  document.querySelector("#input-panel-title").textContent = "提交 Python 代码";
  document.querySelector(".schema-note").textContent = "仅接受单个 .py 文件";
  elements.runCase.querySelector("span:first-child").textContent = "提交并评测";
  elements.dynamicFields.innerHTML = `
    <div class="field-group full-width">
      <label class="field-label" for="submission-author">
        <span>提交人</span><span class="required-mark">必填</span>
      </label>
      <input id="submission-author" type="text" maxlength="128" required
        autocomplete="name" value="${escapeHtml(getSavedSubmitter())}"
        placeholder="请输入姓名或学号" />
      <p class="field-help">同一提交人的历史版本会保存，但不会互相触发查重扣分。</p>
    </div>
    <div class="python-upload full-width">
      <input id="python-file" type="file" accept=".py,text/x-python" hidden />
      <button class="drop-zone" id="python-drop-zone" type="button">
        <span class="drop-icon">PY</span>
        <strong>选择或拖入 Python 文件</strong>
        <small>只读取 .py 文件，最大 ${Math.round(maxBytes / 1000)} KB</small>
      </button>
      <div class="selected-file is-hidden" id="selected-file">
        <div><strong id="selected-file-name"></strong><span id="selected-file-meta"></span></div>
        <button type="button" id="replace-file">重新选择</button>
      </div>
      <details class="source-preview is-hidden" id="source-preview">
        <summary>预览待评测源码</summary>
        <pre id="source-preview-code"></pre>
      </details>
      <p class="upload-safety">代码将在隔离运行环境中评测，不会访问服务器真实网卡。</p>
    </div>`;

  const input = document.querySelector("#python-file");
  const zone = document.querySelector("#python-drop-zone");
  const openPicker = () => input.click();
  zone.addEventListener("click", openPicker);
  document.querySelector("#replace-file").addEventListener("click", openPicker);
  input.addEventListener("change", () => acceptPythonFile(input.files?.[0], maxBytes));
  zone.addEventListener("dragover", (event) => {
    event.preventDefault();
    zone.classList.add("dragging");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragging"));
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("dragging");
    acceptPythonFile(event.dataTransfer?.files?.[0], maxBytes);
  });
}

async function acceptPythonFile(file, maxBytes) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".py")) {
    showToast("仅允许提交扩展名为 .py 的文件");
    return;
  }
  if (file.size > maxBytes) {
    showToast(`文件不能超过 ${Math.round(maxBytes / 1000)} KB`);
    return;
  }
  try {
    const source = await file.text();
    if (!source.trim()) throw new Error("文件内容为空");
    state.uploadedFile = {
      name: file.name,
      size: file.size,
      lastModified: file.lastModified,
      source,
    };
    document.querySelector("#selected-file-name").textContent = file.name;
    document.querySelector("#selected-file-meta").textContent =
      `${formatBytes(file.size)} · ${source.split(/\r?\n/).length} 行`;
    document.querySelector("#selected-file").classList.remove("is-hidden");
    document.querySelector("#source-preview").classList.remove("is-hidden");
    document.querySelector("#source-preview-code").textContent = source;
    showToast("文件已读取，可以提交评测");
  } catch (error) {
    showToast(`无法读取文件：${error.message}`);
  }
}

function formatBytes(bytes) {
  if (bytes < 1000) return `${bytes} B`;
  return `${(bytes / 1000).toFixed(1)} KB`;
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
  } else if (type === "array" && definition.items?.enum) {
    groupClass += " full-width";
    const selected = new Set(definition.default || []);
    const labels = definition["x-enum-labels"] || {};
    control = `<div class="checkbox-grid" id="field-${escapeHtml(name)}">${definition.items.enum
      .map(
        (item) => `<label class="checkbox-option">
          <input type="checkbox" name="${escapeHtml(name)}" value="${escapeHtml(item)}" data-kind="array-enum" ${selected.has(item) ? "checked" : ""} />
          <span>${escapeHtml(labels[item] || item)}</span>
        </label>`,
      )
      .join("")}</div>`;
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
  if (state.selectedCase?.input_schema?.["x-ui-mode"] === "python-file") {
    if (!state.uploadedFile) throw new Error("请先选择一个 .py 文件");
    return {
      filename: state.uploadedFile.name,
      source_code: state.uploadedFile.source,
    };
  }
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
    if (kind === "array-enum") {
      if (!Array.isArray(input[field.name])) input[field.name] = [];
      if (field.checked) input[field.name].push(field.value);
      return;
    }
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

function collectExecutionMetadata() {
  if (!isCodeGraderCase(state.selectedCase?.case_id)) {
    return { student_id: studentId };
  }
  const submitter = document.querySelector("#submission-author")?.value.trim() || "";
  if (!submitter) throw new Error("请填写提交人");
  saveSubmitter(submitter);
  return { submitter };
}

async function executeSelectedCase(event) {
  event.preventDefault();
  if (!state.selectedCase) return;
  let input;
  let metadata;
  try {
    input = collectInput();
    metadata = collectExecutionMetadata();
  } catch (error) {
    showToast(`输入解析失败：${error.message}`);
    return;
  }

  elements.runCase.disabled = true;
  elements.runCase.querySelector("span:first-child").textContent = "正在运行…";
  try {
    const result = await apiRequest("/api/v1/executions", {
      method: "POST",
      body: JSON.stringify({
        case_id: state.selectedCase.case_id,
        input,
        metadata,
      }),
    });
    state.latestResult = result;
    renderResult(result);
    if (isCodeGraderCase(state.selectedCase.case_id)) {
      await saveSubmissionToBrowser(result, input, metadata.submitter);
      await loadSubmissionHistory();
    }
    showToast("评测完成");
  } catch (error) {
    const firstDetail = error.details?.errors?.[0]?.msg;
    showToast(firstDetail ? `${error.message}：${firstDetail}` : error.message);
  } finally {
    elements.runCase.disabled = false;
    elements.runCase.querySelector("span:first-child").textContent =
      isCodeGraderCase(state.selectedCase?.case_id) ? "提交并评测" : "运行模块";
  }
}

function renderResult(result) {
  const payload = result.payload || {};
  document.querySelector("#download-csv").href =
    apiUrl(`/api/v1/results/${encodeURIComponent(result.request_id)}?format=csv`);
  document.querySelector("#result-summary").textContent = payload.summary || "执行完成";

  const metrics = isCodeGraderCase(result.case_id)
    ? studentMetrics(payload.metrics || {})
    : Object.entries(payload.metrics || {});
  document.querySelector("#metric-grid").innerHTML = metrics.length
    ? metrics
        .map(([key, value]) => {
          const display = Array.isArray(value)
            ? value.map((item) => escapeHtml(formatValue(item))).join("<br>")
            : escapeHtml(formatValue(value));
          return `<article class="metric-card">
            <span>${escapeHtml(key)}</span>
            <strong>${display}</strong>
          </article>`;
        })
        .join("")
    : "";

  const datasetResults = document.querySelector("#dataset-results");
  if (isCodeGraderCase(result.case_id)) {
    datasetResults.innerHTML = renderCodeEvaluation(payload);
  } else {
    const algorithmColors = buildAlgorithmColorMap(payload.datasets || []);
    datasetResults.innerHTML = (payload.datasets || [])
      .map((dataset) => renderDataset(dataset, { algorithmColors }))
      .join("");
  }
  if (isCodeGraderCase(result.case_id)) {
    loadAiCodeReview(result.request_id);
  }
  document.querySelector("#diagnostic-list").innerHTML = (payload.diagnostics || [])
    .map(
      (item) => `<div class="diagnostic-item ${escapeHtml(item.level)}">
        ${isCodeGraderCase(result.case_id) ? "" : `<span class="diagnostic-code">${escapeHtml(item.code)}</span>`}
        <span>${escapeHtml(item.message)}</span>
      </div>`,
    )
    .join("");

  elements.resultPanel.classList.remove("is-hidden");
  elements.resultPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function studentMetrics(metrics) {
  const items = [
    ["项目总分", `${metrics.overall_score ?? 0} / 100`],
    ["功能通过率", `${metrics.test_pass_rate ?? 0}%`],
    ["已通过检查", `${metrics.tests_passed ?? 0} / ${metrics.tests_total ?? 0}`],
    ["功能得分", `${metrics.functionality_score ?? 0} / 80`],
    ["代码规范", `${metrics.pep8_score ?? 0} / 10`],
    ["模块化程度", `${metrics.modularity_score ?? 0} / 10`],
  ];
  if (metrics.runtime_status !== undefined) {
    const runtimeLabels = {
      succeeded: "运行成功",
      compile_error: "编译失败",
      runtime_error: "运行失败",
      timed_out: "运行超时",
      unavailable: "沙箱不可用",
      internal_error: "运行器异常",
    };
    items.push(
      ["代码运行状态", runtimeLabels[metrics.runtime_status] || metrics.runtime_status],
      ["运行测试通过率", `${metrics.runtime_pass_rate ?? 0}%`],
      ["运行测试", `${metrics.runtime_tests_passed ?? 0} / ${metrics.runtime_tests_total ?? 0}`],
      ["运行耗时", `${metrics.runtime_duration_ms ?? 0} ms`],
    );
  }
  if (metrics.similarity_checked_submissions !== undefined) {
    items.push(
      ["同案例查重范围", `${metrics.similarity_checked_submissions} 份历史代码`],
      ["最高代码相似度", `${metrics.similarity_score ?? 0}%`],
      ["查重扣分", `-${metrics.similarity_penalty ?? 0}`],
    );
  }
  return items;
}

const CHART_COLORS = [
  "#ee5b32",
  "#176f68",
  "#c99a1f",
  "#7a5cff",
  "#2f9e44",
  "#c83d1e",
  "#0b7285",
  "#e8590c",
];

function isCurveDataset(dataset) {
  return /curve$/i.test(dataset.name || "");
}

function buildAlgorithmColorMap(datasets) {
  const names = [];
  for (const dataset of datasets) {
    const column = (dataset.columns || []).find(
      (item) => item.key === "algorithm_name",
    );
    if (!column) continue;
    for (const row of dataset.rows || []) {
      const name = row[column.key];
      if (name && !names.includes(name)) names.push(name);
    }
  }
  const colors = new Map();
  names.forEach((name, index) => {
    colors.set(name, CHART_COLORS[index % CHART_COLORS.length]);
  });
  return colors;
}

function trimNumber(value, digits = 2) {
  return String(Number(value.toFixed(digits)));
}

function formatTimeValue(seconds) {
  const abs = Math.abs(seconds);
  if (abs === 0) return "0";
  if (abs >= 1) return `${trimNumber(seconds, 2)}s`;
  if (abs >= 1e-3) return `${trimNumber(seconds * 1e3, 2)}ms`;
  if (abs >= 1e-6) return `${trimNumber(seconds * 1e6, 2)}µs`;
  return `${trimNumber(seconds * 1e9, 1)}ns`;
}

function formatCountValue(value) {
  const abs = Math.abs(value);
  if (abs === 0) return "0";
  if (abs >= 1e6) return `${trimNumber(value / 1e6, 1)}M`;
  if (abs >= 1e3) return `${trimNumber(value / 1e3, 1)}k`;
  if (abs >= 1) return String(Math.round(value));
  return trimNumber(value, 3);
}

function formatSizeValue(value) {
  const abs = Math.abs(value);
  if (abs >= 1e6) return `${trimNumber(value / 1e6, 1)}M`;
  if (abs >= 1e3) return `${trimNumber(value / 1e3, 1)}k`;
  return String(Math.round(value));
}

function renderCurveChart(dataset, algorithmColors) {
  const columns = dataset.columns || [];
  const rows = dataset.rows || [];
  if (!rows.length) return "";
  const xColumn =
    columns.find((column) => column.key === "size") ||
    columns.find((column) => column.data_type === "integer");
  const yColumn = columns.find((column) => column.data_type === "number");
  const groupColumn =
    columns.find((column) => column.key === "algorithm_name") ||
    columns.find((column) => column.key === "algorithm");
  if (!xColumn || !yColumn) return "";

  const isTime = yColumn.key === "time_seconds" || yColumn.unit === "s";
  const yFormat = isTime ? formatTimeValue : formatCountValue;

  const seriesMap = new Map();
  for (const row of rows) {
    const x = Number(row[xColumn.key]);
    const y = Number(row[yColumn.key]);
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    const key = groupColumn ? String(row[groupColumn.key]) : yColumn.title;
    if (!seriesMap.has(key)) seriesMap.set(key, []);
    seriesMap.get(key).push({ x, y });
  }
  const series = [...seriesMap.entries()]
    .map(([name, points]) => ({ name, points: points.sort((a, b) => a.x - b.x) }))
    .filter((item) => item.points.length);
  if (!series.length) return "";

  const width = 760;
  const height = 360;
  const pad = { top: 24, right: 24, bottom: 54, left: 82 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;

  const allX = series.flatMap((item) => item.points.map((point) => point.x));
  const allY = series.flatMap((item) => item.points.map((point) => point.y));
  let minX = Math.min(...allX);
  let maxX = Math.max(...allX);
  if (minX === maxX) {
    minX -= 1;
    maxX += 1;
  }

  const positiveY = allY.filter((value) => value > 0);
  const useLogY =
    positiveY.length >= 2 && Math.max(...positiveY) / Math.min(...positiveY) > 30;

  let axisMinY;
  let axisMaxY;
  const yTickValues = [];
  if (useLogY) {
    axisMinY = 10 ** Math.floor(Math.log10(Math.min(...positiveY)));
    axisMaxY = 10 ** Math.ceil(Math.log10(Math.max(...allY)));
    for (let exp = Math.round(Math.log10(axisMinY)); 10 ** exp <= axisMaxY * 1.0001; exp += 1) {
      yTickValues.push(10 ** exp);
    }
  } else {
    axisMinY = Math.min(...allY, 0);
    axisMaxY = Math.max(...allY);
    if (axisMinY === axisMaxY) axisMaxY = axisMinY + 1;
    for (let i = 0; i <= 5; i += 1) {
      yTickValues.push(axisMinY + ((axisMaxY - axisMinY) * i) / 5);
    }
  }

  const log = (value) => Math.log10(Math.max(value, axisMinY));
  const sx = (x) => pad.left + ((x - minX) / (maxX - minX)) * innerW;
  const sy = (y) => {
    if (useLogY) {
      const ratio =
        (log(y) - log(axisMinY)) / (log(axisMaxY) - log(axisMinY) || 1);
      return pad.top + innerH - ratio * innerH;
    }
    return pad.top + innerH - ((y - axisMinY) / (axisMaxY - axisMinY || 1)) * innerH;
  };

  let grid = "";
  let yLabels = "";
  for (const value of yTickValues) {
    const y = sy(value);
    grid += `<line x1="${pad.left}" y1="${y.toFixed(1)}" x2="${width - pad.right}" y2="${y.toFixed(1)}" stroke="#e2ddd2" stroke-width="1" />`;
    yLabels += `<text x="${pad.left - 10}" y="${(y + 4).toFixed(1)}" text-anchor="end" font-size="11" fill="#4f5c62">${escapeHtml(yFormat(value))}</text>`;
  }
  let xLabels = "";
  for (let i = 0; i <= 5; i += 1) {
    const value = minX + ((maxX - minX) * i) / 5;
    const x = sx(value);
    xLabels += `<text x="${x.toFixed(1)}" y="${height - pad.bottom + 20}" text-anchor="middle" font-size="11" fill="#4f5c62">${escapeHtml(formatSizeValue(value))}</text>`;
  }

  const colorFor = (name, index) =>
    (algorithmColors && algorithmColors.get(name)) || CHART_COLORS[index % CHART_COLORS.length];

  const lines = series
    .map((item, index) => {
      const color = colorFor(item.name, index);
      const points = item.points
        .map((point) => `${sx(point.x).toFixed(1)},${sy(point.y).toFixed(1)}`)
        .join(" ");
      const dots = item.points
        .map(
          (point) =>
            `<circle cx="${sx(point.x).toFixed(1)}" cy="${sy(point.y).toFixed(1)}" r="3" fill="${color}" />`,
        )
        .join("");
      return `<polyline fill="none" stroke="${color}" stroke-width="2.5" points="${points}" />${dots}`;
    })
    .join("");

  const legend = series
    .map((item, index) => {
      const color = colorFor(item.name, index);
      return `<span class="chart-legend-item"><i style="background:${color}"></i>${escapeHtml(item.name)}</span>`;
    })
    .join("");

  let scaleNote;
  if (useLogY) {
    scaleNote = isTime
      ? "纵轴为对数刻度（每格约 ×10）。不同算法耗时可能相差几个数量级，靠近底部、接近水平的线表示该算法太快、增长极小（如二分查找），属正常现象。"
      : "纵轴为对数刻度（每格约 ×10）。比较次数是判断复杂度的可靠依据；贴近底部的线表示增长极慢（如二分查找的 O(log n)）。";
  } else {
    scaleNote = "纵轴为线性刻度。";
  }
  const svg = `<svg class="curve-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(dataset.title)}">
    ${grid}
    <line x1="${pad.left}" y1="${pad.top}" x2="${pad.left}" y2="${height - pad.bottom}" stroke="#172026" stroke-width="1.5" />
    <line x1="${pad.left}" y1="${height - pad.bottom}" x2="${width - pad.right}" y2="${height - pad.bottom}" stroke="#172026" stroke-width="1.5" />
    ${lines}
    ${xLabels}
    ${yLabels}
    <text x="${pad.left + innerW / 2}" y="${height - 8}" text-anchor="middle" font-size="12" fill="#172026" font-weight="700">${escapeHtml(xColumn.title)}</text>
    <text x="16" y="${pad.top + innerH / 2}" text-anchor="middle" font-size="12" fill="#172026" font-weight="700" transform="rotate(-90 16 ${pad.top + innerH / 2})">${escapeHtml(yColumn.title)}</text>
  </svg>`;

  return `<div class="curve-chart-wrap">
    <div class="chart-legend">${legend}</div>
    ${svg}
    <p class="chart-caption">横轴：${escapeHtml(xColumn.title)}；纵轴：${escapeHtml(yColumn.title)}。${scaleNote}</p>
  </div>`;
}

function renderDataset(dataset, options = {}) {
  const columns = dataset.columns || [];
  const rows = dataset.rows || [];
  const chart = isCurveDataset(dataset)
    ? renderCurveChart(dataset, options.algorithmColors)
    : "";
  const table = `<div class="table-scroll">
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
                      let rendered = escapeHtml(formatValue(value));
                      if (column.key === "algorithm_name" && options.algorithmColors) {
                        const color = options.algorithmColors.get(value);
                        if (color) {
                          rendered = `<span class="algo-name"><i class="algo-dot" style="background:${color}"></i><span style="color:${color}">${rendered}</span></span>`;
                        }
                      }
                      return `<td>${typeof value === "object" && value !== null ? `<code>${rendered}</code>` : rendered}</td>`;
                    })
                    .join("")}</tr>`,
                )
                .join("")
            : `<tr><td colspan="${Math.max(columns.length, 1)}">该数据集没有记录</td></tr>`
        }</tbody>
      </table>
    </div>`;
  const tableBlock = chart
    ? `<details class="dataset-table-toggle"><summary>查看数据表（${rows.length} 行）</summary>${table}</details>`
    : table;
  return `<section class="dataset-block">
    ${
      options.hideTitle
        ? ""
        : `<div class="dataset-title">
            <h4>${escapeHtml(dataset.title)}</h4>
            <span>${rows.length} 行</span>
          </div>`
    }
    ${chart}
    ${tableBlock}
  </section>`;
}

function findDataset(payload, name) {
  return (payload.datasets || []).find((dataset) => dataset.name === name) || { rows: [] };
}

function renderCodeEvaluation(payload) {
  const tests = findDataset(payload, "functional_tests").rows;
  const runtimeTests = findDataset(payload, "runtime_tests").rows;
  const runtimePackets = findDataset(payload, "runtime_packets");
  const runtimeObservations = findDataset(payload, "runtime_observations");
  const algorithmColors = buildAlgorithmColorMap(payload.datasets || []);
  const curveBlocks = (payload.datasets || [])
    .filter((dataset) => isCurveDataset(dataset) && (dataset.rows || []).length)
    .map((dataset) => renderDataset(dataset, { algorithmColors }))
    .join("");
  const quality = findDataset(payload, "quality_scores").rows.filter(
    (item) => item.dimension !== "重复代码",
  );
  const issues = findDataset(payload, "code_issues");
  const testDetails = tests
    .map(
      (item) => `<details class="evaluation-detail ${item.passed ? "passed" : "failed"}">
        <summary>
          <span class="check-state">${item.passed ? "通过" : "待完善"}</span>
          <strong>${escapeHtml(item.title)}</strong>
          <b>${escapeHtml(item.earned)} / ${escapeHtml(item.weight)}</b>
        </summary>
        <div class="evaluation-body">
          <p><span>判定证据</span>${escapeHtml(item.evidence)}</p>
          <p><span>改进建议</span>${escapeHtml(item.suggestion)}</p>
        </div>
      </details>`,
    )
    .join("");
  const qualityCards = quality
    .map(
      (item) => `<details class="quality-card">
        <summary>
          <span>${escapeHtml(item.dimension)}</span>
          <strong>${escapeHtml(item.score)}<small>/${escapeHtml(item.max_score)}</small></strong>
        </summary>
        <p>${escapeHtml(item.summary)}</p>
        <div class="quality-bar"><i style="width:${Math.max(0, Math.min(100, item.max_score ? item.score / item.max_score * 100 : 0))}%"></i></div>
        <small>${escapeHtml(item.details)}</small>
      </details>`,
    )
    .join("");
  const runtimeDetails = runtimeTests
    .map(
      (item) => `<details class="evaluation-detail ${item.passed ? "passed" : "failed"}">
        <summary>
          <span class="check-state">${item.passed ? "通过" : "未通过"}</span>
          <strong>${escapeHtml(item.title)}</strong>
        </summary>
        <div class="evaluation-body">
          <p><span>运行证据</span>${escapeHtml(item.evidence)}</p>
        </div>
      </details>`,
    )
    .join("");
  const staticFunctionSection = tests.length
    ? `<section class="evaluation-section">
        <div class="dataset-title"><h4>功能检查</h4><span>${tests.filter((item) => item.passed).length} / ${tests.length} PASSED</span></div>
        <div class="evaluation-list">${testDetails}</div>
      </section>`
    : "";
  return `
    ${staticFunctionSection}
    <section class="evaluation-section">
      <div class="dataset-title"><h4>隔离运行测试</h4><span>${runtimeTests.filter((item) => item.passed).length} / ${runtimeTests.length} PASSED</span></div>
      <div class="evaluation-list">${runtimeDetails}</div>
      ${runtimePackets.rows.length ? renderDataset(runtimePackets) : ""}
      ${runtimeObservations.rows.length ? renderDataset(runtimeObservations) : ""}
    </section>
    ${
      curveBlocks
        ? `<section class="evaluation-section">
      <div class="dataset-title"><h4>运行复杂度曲线</h4><span>基于沙箱实跑计时</span></div>
      ${curveBlocks}
    </section>`
        : ""
    }
    <section class="evaluation-section">
      <div class="dataset-title"><h4>代码质量</h4><span>点击展开评分依据</span></div>
      <div class="quality-grid">${qualityCards}</div>
    </section>
    ${renderStudentIssues(issues)}`;
}

function renderStudentIssues(dataset) {
  const severityLabels = { error: "错误", warning: "注意", style: "规范", quality: "质量" };
  const studentDataset = {
    ...dataset,
    columns: (dataset.columns || []).filter((column) => column.key !== "code"),
    rows: (dataset.rows || [])
      .filter((row) => row.code !== "DUP001")
      .map((row) => ({
        severity: severityLabels[row.severity] || row.severity,
        line: row.line,
        message: row.message,
        suggestion: row.suggestion,
      })),
  };
  return `<section class="evaluation-section student-issues-section">
    <div class="dataset-title">
      <h4>问题与改进建议</h4>
      <span>${studentDataset.rows.length} 项待查看</span>
    </div>
    <div class="ai-code-review is-loading" id="ai-code-review">
      <span>AI 点评</span>
      <p>正在结合本次评测结果整理建议……</p>
    </div>
    ${renderDataset(studentDataset, { hideTitle: true })}
  </section>`;
}

async function loadAiCodeReview(requestId) {
  state.codeReviewRequest += 1;
  const reviewRequest = state.codeReviewRequest;
  const container = document.querySelector("#ai-code-review");
  if (!container) return;
  try {
    const response = await apiRequest("/api/v1/assistant/code-review", {
      method: "POST",
      body: JSON.stringify({ request_id: requestId }),
    });
    if (reviewRequest !== state.codeReviewRequest) return;
    container.querySelector("p").textContent = response.reply;
    container.classList.remove("is-loading", "is-unavailable");
  } catch (error) {
    if (reviewRequest !== state.codeReviewRequest) return;
    container.querySelector("p").textContent = `AI 点评暂不可用：${error.message}`;
    container.classList.remove("is-loading");
    container.classList.add("is-unavailable");
  }
}

function openHistoryDb() {
  return new Promise((resolve, reject) => {
    if (!window.indexedDB) {
      reject(new Error("当前浏览器不支持 IndexedDB"));
      return;
    }
    const request = window.indexedDB.open(HISTORY_DB_NAME, 2);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(HISTORY_STORE_NAME)) {
        const store = db.createObjectStore(HISTORY_STORE_NAME, { keyPath: "id" });
        store.createIndex("case_id", "case_id", { unique: false });
        store.createIndex("created_at", "created_at", { unique: false });
      }
      if (!db.objectStoreNames.contains(ASSISTANT_STORE_NAME)) {
        db.createObjectStore(ASSISTANT_STORE_NAME, { keyPath: "id" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("无法打开浏览器历史数据库"));
  });
}

function renderAssistantMessages() {
  if (!state.assistantMessages.length && !state.assistantBusy) {
    elements.assistantMessages.innerHTML = `
      <div class="assistant-empty">
        <strong>今天想学点什么？</strong>
        <p>可以先说说你正在学习的课程、遇到的困难，或者选择下方项目开始实践。</p>
      </div>`;
    return;
  }
  const messages = state.assistantMessages
    .map(
      (message) => `
        <article class="assistant-message ${message.role}">
          <span>${message.role === "user" ? "我" : "课程助手"}</span>
          <p>${escapeHtml(message.content)}</p>
        </article>`,
    )
    .join("");
  const pending = state.assistantBusy
    ? `<article class="assistant-message assistant is-pending">
        <span>课程助手</span><p>正在整理思路，请稍候……</p>
      </article>`
    : "";
  elements.assistantMessages.innerHTML = messages + pending;
  elements.assistantMessages.scrollTop = elements.assistantMessages.scrollHeight;
}

function setAssistantBusy(isBusy) {
  state.assistantBusy = isBusy;
  elements.assistantInput.disabled = isBusy;
  elements.assistantSend.disabled = isBusy;
  elements.clearAssistantChat.disabled = isBusy;
  renderAssistantMessages();
}

function setAssistantStatus(mode, text) {
  const dot = document.querySelector(".assistant-status-dot");
  dot.classList.remove("online", "offline");
  if (mode) dot.classList.add(mode);
  elements.assistantStatus.textContent = text;
}

async function checkAssistantStatus() {
  try {
    const response = await apiRequest("/api/v1/assistant/status");
    setAssistantStatus(
      response.configured ? "online" : "offline",
      response.configured ? "课程助手在线" : "课程助手待配置",
    );
  } catch {
    setAssistantStatus("offline", "课程助手暂不可用");
  }
}

async function saveAssistantContext() {
  const db = await openHistoryDb();
  await new Promise((resolve, reject) => {
    const transaction = db.transaction(ASSISTANT_STORE_NAME, "readwrite");
    transaction.objectStore(ASSISTANT_STORE_NAME).put({
      id: ASSISTANT_CONTEXT_KEY,
      messages: state.assistantMessages.slice(-30),
      case_id: state.assistantCaseId,
      updated_at: new Date().toISOString(),
    });
    transaction.oncomplete = resolve;
    transaction.onerror = () => reject(transaction.error);
  });
  db.close();
}

async function loadAssistantContext() {
  try {
    const db = await openHistoryDb();
    const record = await new Promise((resolve, reject) => {
      const request = db
        .transaction(ASSISTANT_STORE_NAME, "readonly")
        .objectStore(ASSISTANT_STORE_NAME)
        .get(ASSISTANT_CONTEXT_KEY);
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(request.error);
    });
    db.close();
    state.assistantMessages = Array.isArray(record?.messages)
      ? record.messages
          .filter(
            (item) =>
              (item?.role === "user" || item?.role === "assistant") &&
              typeof item?.content === "string",
          )
          .slice(-30)
      : [];
    state.assistantCaseId = record?.case_id || null;
  } catch (error) {
    state.assistantMessages = [];
    state.assistantCaseId = null;
    showToast(`无法读取本机聊天记录：${error.message}`);
  }
  renderAssistantMessages();
}

async function clearAssistantContext() {
  if (state.assistantBusy) return;
  try {
    const db = await openHistoryDb();
    await new Promise((resolve, reject) => {
      const transaction = db.transaction(ASSISTANT_STORE_NAME, "readwrite");
      transaction.objectStore(ASSISTANT_STORE_NAME).delete(ASSISTANT_CONTEXT_KEY);
      transaction.oncomplete = resolve;
      transaction.onerror = () => reject(transaction.error);
    });
    db.close();
    state.assistantMessages = [];
    state.assistantCaseId = null;
    renderAssistantMessages();
    showToast("聊天记录已从当前浏览器删除");
  } catch (error) {
    showToast(`删除失败：${error.message}`);
  }
}

async function askAssistant(question) {
  const content = String(question || "").trim();
  if (!content || state.assistantBusy) return;
  state.assistantMessages.push({ role: "user", content });
  elements.assistantInput.value = "";
  setAssistantBusy(true);
  try {
    await saveAssistantContext();
    const response = await apiRequest("/api/v1/assistant/chat", {
      method: "POST",
      body: JSON.stringify({
        messages: state.assistantMessages
          .slice(-20)
          .map(({ role, content: messageContent }) => ({ role, content: messageContent })),
        case_id: state.selectedCase?.case_id || null,
      }),
    });
    state.assistantMessages.push({ role: "assistant", content: response.reply });
    setAssistantStatus("online", "课程助手在线");
    await saveAssistantContext();
  } catch (error) {
    state.assistantMessages.push({
      role: "assistant",
      content: `这次没有成功连接到课程助手。${error.message}`,
    });
    setAssistantStatus("offline", "课程助手暂不可用");
    await saveAssistantContext().catch(() => {});
  } finally {
    setAssistantBusy(false);
    elements.assistantInput.focus();
  }
}

async function introduceSelectedModule(selected) {
  elements.assistantContext.textContent = `正在学习 · ${selected.name}`;
  state.assistantCaseId = selected.case_id;
  state.moduleIntroductionRequest += 1;
  const requestId = state.moduleIntroductionRequest;
  elements.moduleIntroductionName.textContent = selected.name;
  elements.moduleIntroductionContent.textContent = "AI 正在整理这个模块的核心知识点……";
  elements.moduleIntroduction.classList.remove("is-hidden");
  saveAssistantContext().catch(() => {});
  try {
    const response = await apiRequest("/api/v1/assistant/module-introduction", {
      method: "POST",
      body: JSON.stringify({ case_id: selected.case_id }),
    });
    if (requestId !== state.moduleIntroductionRequest) return;
    elements.moduleIntroductionContent.textContent = response.reply;
    setAssistantStatus("online", "课程助手在线");
  } catch (error) {
    if (requestId !== state.moduleIntroductionRequest) return;
    elements.moduleIntroductionContent.textContent = `知识导览暂未生成：${error.message}`;
    setAssistantStatus("offline", "课程助手暂不可用");
  }
}

async function saveSubmissionToBrowser(result, input, submitter) {
  try {
    const db = await openHistoryDb();
    await new Promise((resolve, reject) => {
      const transaction = db.transaction(HISTORY_STORE_NAME, "readwrite");
      transaction.objectStore(HISTORY_STORE_NAME).put({
        id: result.request_id,
        case_id: result.case_id,
        created_at: result.created_at || new Date().toISOString(),
        filename: input.filename,
        source_code: input.source_code,
        submitter,
        result,
      });
      transaction.oncomplete = resolve;
      transaction.onerror = () => reject(transaction.error);
    });
    db.close();
  } catch (error) {
    showToast(`评测已完成，但本机历史保存失败：${error.message}`);
  }
}

async function loadSubmissionHistory() {
  if (!isCodeGraderCase(state.selectedCase?.case_id)) return;
  try {
    const db = await openHistoryDb();
    const all = await new Promise((resolve, reject) => {
      const request = db
        .transaction(HISTORY_STORE_NAME, "readonly")
        .objectStore(HISTORY_STORE_NAME)
        .getAll();
      request.onsuccess = () => resolve(request.result || []);
      request.onerror = () => reject(request.error);
    });
    db.close();
    state.history = all
      .filter((item) => isCodeGraderCase(item.case_id))
      .sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
    state.expandedHistoryCase = state.selectedCase?.case_id || null;
    updateHistorySubmitterFilter();
    renderSubmissionHistory();
  } catch (error) {
    state.history = [];
    updateHistorySubmitterFilter();
    elements.submissionTimeline.innerHTML = `<p class="history-empty">无法读取本机历史：${escapeHtml(error.message)}</p>`;
  }
}

function updateHistorySubmitterFilter() {
  const submitters = [...new Set(state.history.map(submitterFilterValue))].sort((left, right) =>
    left.localeCompare(right, "zh-CN"),
  );
  if (
    state.historySubmitterFilter &&
    !submitters.includes(state.historySubmitterFilter)
  ) {
    state.historySubmitterFilter = "";
  }
  elements.historySubmitterFilter.innerHTML = [
    '<option value="">全部提交人</option>',
    ...submitters.map((submitter) => {
      const label = submitter === "__unassigned__" ? "旧记录（未标注）" : submitter;
      return `<option value="${escapeHtml(submitter)}">${escapeHtml(label)}</option>`;
    }),
  ].join("");
  elements.historySubmitterFilter.value = state.historySubmitterFilter;
}

function renderSubmissionHistory() {
  if (!state.history.length) {
    elements.submissionTimeline.innerHTML =
      '<p class="history-empty">尚无本机提交。完成第一次评测后，这里会出现版本记录。</p>';
    updateDiffSelectors();
    return;
  }
  const visibleHistory = filteredSubmissionHistory();
  if (!visibleHistory.length) {
    elements.submissionTimeline.innerHTML =
      '<p class="history-empty">当前提交人没有本机提交记录。</p>';
    updateDiffSelectors();
    return;
  }
  const groups = [];
  visibleHistory.forEach((item) => {
    let group = groups.find((entry) => entry.caseId === item.case_id);
    if (!group) {
      group = { caseId: item.case_id, items: [] };
      groups.push(group);
    }
    group.items.push(item);
  });
  elements.submissionTimeline.innerHTML = groups
    .map((group) => {
      const meta = caseById(group.caseId);
      const index = state.cases.findIndex((entry) => entry.case_id === group.caseId) + 1;
      const isOpen = state.expandedHistoryCase === group.caseId;
      const latest = group.items[0]?.result?.payload?.metrics?.overall_score;
      const rows = group.items
        .map((item, itemIndex) => {
          const metrics = item.result?.payload?.metrics || {};
          const time = new Date(item.created_at).toLocaleString("zh-CN", { hour12: false });
          const submitter = item.submitter || "旧记录（未标注）";
          return `<button class="timeline-item" type="button" data-history-id="${escapeHtml(item.id)}">
            <span class="timeline-dot"></span>
            <span><b>第 ${group.items.length - itemIndex} 次提交</b><strong>${escapeHtml(item.filename)}</strong><small>提交人：${escapeHtml(submitter)} · ${escapeHtml(time)}</small></span>
            <em>${escapeHtml(metrics.overall_score ?? "—")}<small>总分</small></em>
          </button>`;
        })
        .join("");
      return `<div class="history-group ${isOpen ? "is-open" : ""}" data-case-id="${escapeHtml(group.caseId)}">
        <button class="history-group-head" type="button" data-history-toggle="${escapeHtml(group.caseId)}" aria-expanded="${isOpen ? "true" : "false"}">
          <span class="history-group-title">
            <b>${escapeHtml(courseLabel(group.caseId, index < 1 ? 1 : index))} · ${escapeHtml(meta?.name || group.caseId)}</b>
            <small>${group.items.length} 次提交${latest === undefined ? "" : ` · 最新 ${escapeHtml(String(latest))} 分`}</small>
          </span>
          <span class="history-group-caret">▾</span>
        </button>
        <div class="history-group-body">${rows}</div>
      </div>`;
    })
    .join("");
  elements.submissionTimeline.querySelectorAll("[data-history-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const caseId = button.dataset.historyToggle;
      state.expandedHistoryCase = state.expandedHistoryCase === caseId ? null : caseId;
      renderSubmissionHistory();
    });
  });
  elements.submissionTimeline.querySelectorAll("[data-history-id]").forEach((button) => {
    button.addEventListener("click", () => {
      const record = state.history.find((item) => item.id === button.dataset.historyId);
      if (record?.result) renderResult(record.result);
    });
  });
  updateDiffSelectors();
}

function updateDiffSelectors() {
  const items = historyForCase(state.selectedCase?.case_id);
  const options = items
    .map((item, index) => `<option value="${escapeHtml(item.id)}">第 ${items.length - index} 次 · ${escapeHtml(item.filename)}</option>`)
    .join("");
  const from = document.querySelector("#diff-from");
  const to = document.querySelector("#diff-to");
  from.innerHTML = options || '<option value="">暂无版本</option>';
  to.innerHTML = options || '<option value="">暂无版本</option>';
  if (items.length >= 2) {
    from.value = items[1].id;
    to.value = items[0].id;
    renderVersionDiff();
  } else {
    elements.codeDiff.textContent = "当前项目至少提交两次后可进行比较。";
  }
}

function renderVersionDiff() {
  const scope = historyForCase(state.selectedCase?.case_id);
  const oldRecord = scope.find((item) => item.id === document.querySelector("#diff-from").value);
  const newRecord = scope.find((item) => item.id === document.querySelector("#diff-to").value);
  if (!oldRecord || !newRecord) {
    showToast("请选择两次可比较的提交");
    return;
  }
  const lines = lineDiff(oldRecord.source_code || "", newRecord.source_code || "");
  elements.codeDiff.innerHTML = lines
    .map(({ type, text }) => `<span class="diff-${type}">${type === "add" ? "+" : type === "remove" ? "−" : " "} ${escapeHtml(text)}</span>`)
    .join("\n");
}

function lineDiff(before, after) {
  const left = before.split(/\r?\n/).slice(0, 400);
  const right = after.split(/\r?\n/).slice(0, 400);
  const matrix = Array.from({ length: left.length + 1 }, () => new Uint16Array(right.length + 1));
  for (let i = left.length - 1; i >= 0; i -= 1) {
    for (let j = right.length - 1; j >= 0; j -= 1) {
      matrix[i][j] = left[i] === right[j] ? matrix[i + 1][j + 1] + 1 : Math.max(matrix[i + 1][j], matrix[i][j + 1]);
    }
  }
  const result = [];
  let i = 0;
  let j = 0;
  while (i < left.length || j < right.length) {
    if (i < left.length && j < right.length && left[i] === right[j]) {
      result.push({ type: "same", text: left[i] }); i += 1; j += 1;
    } else if (j < right.length && (i === left.length || matrix[i][j + 1] >= matrix[i + 1][j])) {
      result.push({ type: "add", text: right[j] }); j += 1;
    } else {
      result.push({ type: "remove", text: left[i] }); i += 1;
    }
  }
  return result;
}

document.querySelector("#refresh-cases").addEventListener("click", () => {
  loadCases();
  document.querySelector("#module-catalog").scrollIntoView({ behavior: "smooth" });
});
document.querySelector("#retry-load").addEventListener("click", loadCases);
document.querySelector("#compare-versions").addEventListener("click", renderVersionDiff);
elements.historySubmitterFilter.addEventListener("change", (event) => {
  state.historySubmitterFilter = event.target.value;
  renderSubmissionHistory();
});
elements.connectionStatus.addEventListener("click", checkHealth);
elements.caseForm.addEventListener("submit", executeSelectedCase);
elements.assistantForm.addEventListener("submit", (event) => {
  event.preventDefault();
  askAssistant(elements.assistantInput.value);
});
elements.assistantInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    elements.assistantForm.requestSubmit();
  }
});
elements.clearAssistantChat.addEventListener("click", clearAssistantContext);
document.querySelector("#close-workbench").addEventListener("click", () => {
  elements.workbench.classList.add("is-hidden");
  window.history.replaceState(null, "", window.location.pathname);
  document.querySelector("#module-catalog").scrollIntoView({ behavior: "smooth" });
});

async function initializePage() {
  checkHealth();
  await loadAssistantContext();
  await Promise.all([checkAssistantStatus(), loadCases()]);
}

initializePage();
