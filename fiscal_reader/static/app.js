const CSV_FIELDS = [
  "arquivo", "formato", "motor_ocr", "confianca_ocr_media", "data_emissao",
  "descricao", "quantidade", "valor_unitario", "valor_total_item",
  "observacoes", "status_revisao",
];
const SUPPORTED = new Set(["jpg", "jpeg", "png", "tif", "tiff", "pdf", "xml"]);
const MAX_FILE_BYTES = 20_000_000;
const state = { files: [], rows: [], selectedId: null, processing: false, nextId: 1, service: null };
const $ = (id) => document.getElementById(id);

function formatSize(bytes) {
  if (bytes < 1_000) return "<1 KB";
  return bytes < 1_000_000 ? `${(bytes / 1_000).toFixed(0)} KB` : `${(bytes / 1_000_000).toFixed(1)} MB`;
}

function fileExtension(name) {
  return name.split(".").at(-1)?.toLowerCase() || "";
}

function setMessage(message, error = false) {
  const element = $("processStatus");
  element.textContent = message;
  element.classList.toggle("error", error);
}

function addFiles(fileList) {
  let rejected = 0;
  for (const file of Array.from(fileList)) {
    if (!SUPPORTED.has(fileExtension(file.name)) || file.size === 0 || file.size > MAX_FILE_BYTES) {
      rejected += 1;
      continue;
    }
    const alreadyAdded = state.files.some((entry) =>
      entry.file.name === file.name && entry.file.size === file.size && entry.file.lastModified === file.lastModified
    );
    if (alreadyAdded) continue;
    state.files.push({
      id: state.nextId++, file, status: "pending", message: "Aguardando processamento",
      result: null, previewUrl: null,
    });
  }
  if (rejected) setMessage(`${rejected} arquivo(s) ignorado(s): formato inválido, vazio ou acima de 20 MB.`, true);
  else if (state.files.length) setMessage("Arquivos prontos para processar.");
  if (!state.selectedId && state.files.length) state.selectedId = state.files[0].id;
  renderFiles();
  renderPreview();
  renderControls();
}

function renderControls() {
  const count = state.files.length;
  $("fileCounter").textContent = `${count} ${count === 1 ? "arquivo" : "arquivos"}`;
  const pending = state.files.filter((entry) => entry.status === "pending" || entry.status === "error").length;
  $("processButton").disabled = state.processing || pending === 0;
  $("processLabel").textContent = state.processing ? "Processando…" : pending > 0 ? `Processar ${pending} ${pending === 1 ? "arquivo" : "arquivos"}` : "Processar arquivos";
  $("exportButton").disabled = state.rows.length === 0 || state.processing;
  $("addRowButton").disabled = !state.files.some((entry) => entry.status === "done");
  $("clearButton").disabled = state.files.length === 0;
}

function renderFiles() {
  const list = $("fileList");
  list.replaceChildren();
  if (!state.files.length) {
    const empty = document.createElement("p");
    empty.className = "file-list-empty";
    empty.textContent = "Os arquivos adicionados aparecem aqui.";
    list.append(empty);
    return;
  }
  for (const entry of state.files) {
    const card = document.createElement("div");
    card.className = `file-card${entry.id === state.selectedId ? " selected" : ""}`;
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.setAttribute("aria-label", `Selecionar ${entry.file.name}`);
    card.addEventListener("click", () => selectFile(entry.id));
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectFile(entry.id);
      }
    });

    const kind = document.createElement("span");
    const ext = fileExtension(entry.file.name);
    kind.className = `file-kind ${ext === "xml" || ext === "pdf" ? ext : ""}`;
    kind.textContent = ext === "jpeg" ? "JPG" : ext.toUpperCase();
    const info = document.createElement("span");
    info.className = "file-info";
    const name = document.createElement("span");
    name.className = "file-name";
    name.title = entry.file.name;
    name.textContent = entry.file.name;
    const status = document.createElement("span");
    status.className = `file-state ${entry.status}`;
    status.textContent = entry.message || formatSize(entry.file.size);
    info.append(name, status);
    const remove = document.createElement("button");
    remove.className = "remove-file";
    remove.type = "button";
    remove.title = `Remover ${entry.file.name}`;
    remove.setAttribute("aria-label", `Remover ${entry.file.name}`);
    remove.textContent = "×";
    remove.disabled = state.processing;
    remove.addEventListener("click", (event) => { event.stopPropagation(); removeFile(entry.id); });
    card.append(kind, info, remove);
    list.append(card);
  }
}

function selectFile(id) {
  state.selectedId = id;
  renderFiles();
  renderPreview();
  document.querySelectorAll("#resultsBody tr").forEach((row) => {
    row.classList.toggle("selected", Number(row.dataset.fileId) === id);
  });
}

function removeFile(id) {
  const entry = state.files.find((item) => item.id === id);
  if (!entry) return;
  if (entry.previewUrl) URL.revokeObjectURL(entry.previewUrl);
  state.files = state.files.filter((item) => item.id !== id);
  state.rows = state.rows.filter((item) => item.fileId !== id);
  if (state.selectedId === id) state.selectedId = state.files[0]?.id ?? null;
  renderFiles();
  renderResults();
  renderPreview();
  renderControls();
}

function renderPreview() {
  const entry = state.files.find((item) => item.id === state.selectedId);
  const pane = $("previewPane");
  pane.replaceChildren();
  pane.classList.remove("ocr-content");
  $("selectedFilename").textContent = entry?.file.name || "Selecione um arquivo";
  $("ocrText").textContent = entry?.result?.ocr_text || (entry?.result?.format === "xml_nfe"
    ? "XML lido diretamente. O OCR não foi usado."
    : "O texto reconhecido aparecerá após o processamento.");
  if (!entry) {
    const placeholder = document.createElement("div");
    placeholder.className = "source-placeholder";
    placeholder.textContent = "Selecione um arquivo na lista ou uma linha da tabela para conferir a origem.";
    pane.append(placeholder);
    return;
  }
  const ext = fileExtension(entry.file.name);
  if (ext === "xml") {
    pane.classList.add("ocr-content");
    const pre = document.createElement("pre");
    pre.textContent = "Carregando XML…";
    pane.append(pre);
    entry.file.text().then((content) => {
      if (state.selectedId === entry.id) pre.textContent = content.slice(0, 30_000);
    });
    return;
  }
  if (!entry.previewUrl) entry.previewUrl = URL.createObjectURL(entry.file);
  if (ext === "pdf") {
    const frame = document.createElement("iframe");
    frame.src = entry.previewUrl;
    frame.title = `Prévia de ${entry.file.name}`;
    pane.append(frame);
  } else {
    const image = document.createElement("img");
    image.src = entry.previewUrl;
    image.alt = `Imagem de ${entry.file.name}`;
    pane.append(image);
  }
}

function switchSourceTab(tab) {
  const preview = tab === "preview";
  $("previewPane").hidden = !preview;
  $("ocrPane").hidden = preview;
  $("previewTab").classList.toggle("active", preview);
  $("ocrTab").classList.toggle("active", !preview);
  $("previewTab").setAttribute("aria-selected", String(preview));
  $("ocrTab").setAttribute("aria-selected", String(!preview));
}

function makeInput(row, field, className, placeholder) {
  const input = document.createElement("input");
  input.type = "text";
  input.className = className;
  input.value = row.data[field] ?? "";
  input.placeholder = placeholder;
  input.setAttribute("aria-label", `${field.replaceAll("_", " ")} de ${row.data.arquivo}`);
  const required = field === "descricao" || field === "quantidade" || field === "valor_total_item";
  input.classList.toggle("missing", required && !input.value.trim());
  input.addEventListener("input", () => {
    row.data[field] = input.value;
    input.classList.toggle("missing", required && !input.value.trim());
    if (row.data.status_revisao !== "revisar_extracao") {
      row.data.status_revisao = "revisar_extracao";
      const select = input.closest("tr").querySelector("select");
      select.value = "revisar_extracao";
      select.classList.remove("reviewed");
      updateSummary();
    }
  });
  return input;
}

function renderResults() {
  const body = $("resultsBody");
  body.replaceChildren();
  $("emptyResults").hidden = state.rows.length > 0;
  $("tableWrap").hidden = state.rows.length === 0;
  for (const row of state.rows) {
    const tr = document.createElement("tr");
    tr.dataset.fileId = String(row.fileId);
    tr.classList.toggle("selected", row.fileId === state.selectedId);
    tr.addEventListener("click", () => selectFile(row.fileId));
    const fileCell = document.createElement("td");
    const fileName = document.createElement("span");
    fileName.className = "filename-cell";
    fileName.textContent = row.data.arquivo || "";
    fileName.title = row.data.arquivo || "";
    fileCell.append(fileName);
    tr.append(fileCell);
    for (const [field, className, placeholder] of [
      ["data_emissao", "date", "AAAA-MM-DD"],
      ["descricao", "description", "Nome do item"],
      ["quantidade", "", "Qtd."],
      ["valor_unitario", "price", "Opcional"],
      ["valor_total_item", "price", "Preço"],
    ]) {
      const cell = document.createElement("td");
      cell.append(makeInput(row, field, className, placeholder));
      tr.append(cell);
    }
    const reviewCell = document.createElement("td");
    const select = document.createElement("select");
    select.setAttribute("aria-label", `Revisão de ${row.data.descricao || row.data.arquivo}`);
    for (const [value, label] of [
      ["revisar_extracao", "Revisar"], ["conferido", "Conferido"], ["extraido_xml", "XML"],
    ]) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      select.append(option);
    }
    select.value = row.data.status_revisao || "revisar_extracao";
    select.classList.toggle("reviewed", select.value === "conferido" || select.value === "extraido_xml");
    select.addEventListener("change", () => {
      row.data.status_revisao = select.value;
      select.classList.toggle("reviewed", select.value !== "revisar_extracao");
      updateSummary();
    });
    reviewCell.append(select);
    tr.append(reviewCell);
    const deleteCell = document.createElement("td");
    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "delete-row";
    deleteButton.textContent = "×";
    deleteButton.title = "Remover item";
    deleteButton.setAttribute("aria-label", `Remover item ${row.data.descricao || "sem descrição"}`);
    deleteButton.addEventListener("click", (event) => {
      event.stopPropagation();
      state.rows = state.rows.filter((item) => item.id !== row.id);
      renderResults();
      renderControls();
    });
    deleteCell.append(deleteButton);
    tr.append(deleteCell);
    body.append(tr);
  }
  updateSummary();
  renderControls();
}

function updateSummary() {
  $("itemCount").textContent = String(state.rows.length);
  $("reviewCount").textContent = String(state.rows.filter((row) => row.data.status_revisao === "revisar_extracao").length);
  $("doneCount").textContent = String(state.rows.filter((row) => row.data.status_revisao === "conferido" || row.data.status_revisao === "extraido_xml").length);
}

function readBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",", 2)[1]);
    reader.onerror = () => reject(new Error("Não foi possível ler o arquivo"));
    reader.readAsDataURL(file);
  });
}

async function processFiles() {
  if (state.processing) return;
  const files = state.files.filter((entry) => entry.status === "pending" || entry.status === "error");
  if (!files.length) return;
  state.processing = true;
  renderControls();
  let successful = 0;
  let failed = 0;
  for (const [index, entry] of files.entries()) {
    selectFile(entry.id);
    entry.status = "processing";
    entry.message = "Lendo arquivo…";
    renderFiles();
    setMessage(`Processando ${index + 1} de ${files.length}: ${entry.file.name}`);
    try {
      const content = await readBase64(entry.file);
      entry.message = "OCR e interpretação em andamento…";
      renderFiles();
      const response = await fetch("/api/process", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: entry.file.name,
          content_base64: content,
          ocr: $("ocrSelect").value,
          provider: $("providerSelect").value,
          model: $("modelInput").value.trim() || null,
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || `Erro HTTP ${response.status}`);
      entry.result = payload;
      entry.status = "done";
      entry.message = `${payload.item_count} ${payload.item_count === 1 ? "item encontrado" : "itens encontrados"} · ${formatSize(entry.file.size)}`;
      for (const data of payload.rows) state.rows.push({ id: state.nextId++, fileId: entry.id, data });
      successful += 1;
      renderResults();
      renderPreview();
    } catch (error) {
      entry.status = "error";
      entry.message = error instanceof Error ? error.message : "Falha no processamento";
      failed += 1;
    }
    renderFiles();
  }
  state.processing = false;
  setMessage(failed ? `${successful} arquivo(s) processado(s), ${failed} com erro. Clique no arquivo para ver o motivo.` : `${successful} arquivo(s) processado(s). Revise os itens antes de baixar.`, failed > 0);
  renderControls();
  renderFiles();
}

function addManualRow() {
  const entry = state.files.find((item) => item.id === state.selectedId && item.status === "done")
    || state.files.find((item) => item.status === "done");
  if (!entry) return;
  selectFile(entry.id);
  const sample = entry.result.rows[0] || {};
  state.rows.push({
    id: state.nextId++, fileId: entry.id,
    data: {
      arquivo: entry.file.name,
      formato: entry.result.format,
      motor_ocr: sample.motor_ocr || "",
      confianca_ocr_media: sample.confianca_ocr_media || "",
      data_emissao: sample.data_emissao || "",
      descricao: "", quantidade: "", valor_unitario: "", valor_total_item: "",
      observacoes: "Adicionado manualmente", status_revisao: "revisar_extracao",
    },
  });
  renderResults();
  $("tableWrap").scrollTop = $("tableWrap").scrollHeight;
}

function escapeCsv(value) {
  const text = String(value ?? "");
  return /[;"\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function downloadCsv() {
  if (!state.rows.length) return;
  const lines = [CSV_FIELDS.map(escapeCsv).join(";")];
  for (const row of state.rows) lines.push(CSV_FIELDS.map((field) => escapeCsv(row.data[field])).join(";"));
  const blob = new Blob(["\ufeff", lines.join("\r\n"), "\r\n"], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  const today = new Date();
  const localDate = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  link.download = `itens-revisados-${localDate}.csv`;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5_000);
  setMessage(`${state.rows.length} item(ns) exportado(s) para CSV.`);
}

function clearAll() {
  for (const entry of state.files) if (entry.previewUrl) URL.revokeObjectURL(entry.previewUrl);
  state.files = [];
  state.rows = [];
  state.selectedId = null;
  renderFiles();
  renderResults();
  renderPreview();
  setMessage("");
}

async function refreshService() {
  try {
    const response = await fetch("/api/status");
    state.service = await response.json();
  } catch {
    state.service = { ollama_online: false, ollama_models: [], gemini_configured: false };
  }
  const badge = $("ollamaBadge");
  badge.classList.toggle("ready", state.service.ollama_online);
  badge.classList.toggle("offline", !state.service.ollama_online);
  badge.textContent = state.service.ollama_online ? "Ollama conectado" : "Ollama indisponível";
  updateProviderHint();
}

function updateProviderHint() {
  const local = $("providerSelect").value === "ollama";
  $("modelInput").placeholder = local ? "qwen3:4b-instruct" : "gemini-3.1-flash-lite";
  $("providerHint").textContent = local
    ? (state.service?.ollama_online ? "O texto reconhecido permanece no computador." : "Inicie o Ollama para processar imagens e PDFs localmente.")
    : (state.service?.gemini_configured ? "O texto reconhecido será enviado à API Gemini." : "Defina GEMINI_API_KEY antes de usar o Gemini.");
}

$("dropZone").addEventListener("click", () => $("fileInput").click());
$("dropZone").addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") { event.preventDefault(); $("fileInput").click(); }
});
$("fileInput").addEventListener("change", (event) => { addFiles(event.target.files); event.target.value = ""; });
for (const eventName of ["dragenter", "dragover"]) {
  $("dropZone").addEventListener(eventName, (event) => { event.preventDefault(); $("dropZone").classList.add("dragging"); });
}
for (const eventName of ["dragleave", "drop"]) {
  $("dropZone").addEventListener(eventName, (event) => { event.preventDefault(); $("dropZone").classList.remove("dragging"); });
}
$("dropZone").addEventListener("drop", (event) => addFiles(event.dataTransfer.files));
$("providerSelect").addEventListener("change", () => { $("modelInput").value = ""; updateProviderHint(); });
$("processButton").addEventListener("click", processFiles);
$("addRowButton").addEventListener("click", addManualRow);
$("exportButton").addEventListener("click", downloadCsv);
$("clearButton").addEventListener("click", clearAll);
$("previewTab").addEventListener("click", () => switchSourceTab("preview"));
$("ocrTab").addEventListener("click", () => switchSourceTab("ocr"));
renderControls();
refreshService();
