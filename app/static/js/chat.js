(() => {
const {apiFetch, apiRequest, loadCurrentUser, showToast, downloadFile} = window.aiup;
const $ = selector => document.querySelector(selector);
const messages = $("#messages"), input = $("#message-input"), form = $("#message-form");
let user, current = null, selected = null, documents = [], chats = [], messageHistory = [];
let sequence = 0, busy = false, streamController = null, job = null, searchTimer, documentTimer;
let feedbackTarget = null, chatOffset = 0;
const storageKey = suffix => "aiup:" + user.id + ":" + suffix;
const draftKey = () => storageKey("draft:" + (current?.id || "new"));
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function button(text, action, className = "text-button") {
  const node = element("button", className, text);
  node.type = "button"; node.addEventListener("click", action); return node;
}
function inline(parent, text, sourcePrefix = "") {
  const regex = /(\*\*([^*]+)\*\*|\x60([^\x60]+)\x60|\[(\d+)\])/g;
  let position = 0;
  for (const match of text.matchAll(regex)) {
    parent.append(document.createTextNode(text.slice(position, match.index)));
    if (match[4] && sourcePrefix) {
      const link = element("a", "citation-link", "[" + match[4] + "]");
      link.href = "#" + sourcePrefix + match[4];
      link.addEventListener("click", event => {
        const target = document.getElementById(sourcePrefix + match[4]);
        if (target) { event.preventDefault(); target.open = true; target.scrollIntoView({block:"nearest", behavior:"smooth"}); target.querySelector("summary")?.focus(); }
      });
      parent.append(link);
    } else parent.append(element(match[2] ? "strong" : match[3] ? "code" : "span", "", match[2] || match[3] || match[0]));
    position = match.index + match[0].length;
  }
  parent.append(document.createTextNode(text.slice(position)));
}
function markdown(text, prefix = "") {
  const box = element("div", "message-content");
  const lines = String(text || "").replace(/\r\n/g,"\n").split("\n");
  for (let index = 0; index < lines.length;) {
    const line = lines[index].trim();
    if (!line) { index++; continue; }
    if (line.includes("|") && index + 1 < lines.length && /^\s*\|?[\s:|-]+\|[\s:|-]*$/.test(lines[index+1])) {
      const wrapper = element("div", "table-scroll");
      const table = element("table", "answer-table"), head = document.createElement("thead"), body = document.createElement("tbody");
      const cells = value => value.replace(/^\s*\||\|\s*$/g,"").split("|").map(cell => cell.trim());
      const header = document.createElement("tr");
      cells(line).forEach(value => { const cell = document.createElement("th"); inline(cell,value,prefix); header.append(cell); });
      head.append(header); index += 2;
      while (index < lines.length && lines[index].includes("|")) {
        const row = document.createElement("tr");
        cells(lines[index++]).forEach(value => { const cell = document.createElement("td"); inline(cell,value,prefix); row.append(cell); }); body.append(row);
      }
      table.append(head,body); wrapper.append(table); box.append(wrapper); continue;
    }
    const listMatch = line.match(/^(?:[-*]|\d+[.)])\s+(.+)/);
    if (listMatch) {
      const ordered = /^\d/.test(line), list = document.createElement(ordered ? "ol" : "ul");
      while (index < lines.length) {
        const match = lines[index].trim().match(ordered ? /^\d+[.)]\s+(.+)/ : /^[-*]\s+(.+)/);
        if (!match) break;
        const item = document.createElement("li"); inline(item,match[1],prefix); list.append(item); index++;
      }
      box.append(list); continue;
    }
    const heading = line.match(/^#{1,6}\s+(.+)/);
    const paragraph = document.createElement(heading ? "h4" : "p");
    inline(paragraph,heading ? heading[1] : line,prefix); box.append(paragraph); index++;
  }
  return box;
}
function sourceNode(source, index, messageId) {
  const details = element("details", "source-card");
  details.id = "source-" + messageId + "-" + (source.citation || index);
  const location = source.location || (source.page ? "página " + source.page : source.sheet || "documento");
  details.append(element("summary", "", "[" + (source.citation || index) + "] " + source.document + " — " + location));
  details.append(element("p", "", source.excerpt || "Excerto não registrado nesta resposta antiga."));
  if (source.document_id) {
    const link = element("a", "text-button source-open", "Abrir documento e conferir");
    link.href = "/document.html?id=" + source.document_id + (source.page ? "&page=" + source.page : "");
    link.target = "_blank"; link.rel = "noopener"; details.append(link);
  } else details.append(element("small", "", "Original removido; evidência histórica preservada."));
  return details;
}
function messageNode(message, previousQuestion, latest) {
  const article = element("article", "message " + message.role.toLowerCase());
  article.append(element("strong", "", message.role === "USER" ? "Você" : "AI-Up"));
  article.append(markdown(message.content, "source-" + message.id + "-"));
  if (message.metrics?.citation_warning) article.append(element("p","warning-text",message.metrics.citation_warning));
  if (message.metrics?.coverage === "retrieved_excerpts") article.append(element("small","warning-text","Síntese dos trechos encontrados; não é uma leitura integral de todos os arquivos."));
  if (message.sources?.length) {
    const sources = element("section", "source-section");
    sources.append(element("span", "source-label", "Trechos para conferência"));
    message.sources.forEach((source, index) => sources.append(sourceNode(source, index + 1, message.id)));
    article.append(sources);
  }
  if (message.role === "ASSISTANT" && message.id) {
    const actions = element("div", "message-actions");
    actions.append(button("Copiar", async () => {
      try { await navigator.clipboard.writeText(message.content); showToast("Resposta copiada.", "success"); }
      catch { showToast("Selecione a resposta e copie com Ctrl+C.", "error"); }
    }));
    if (latest && previousQuestion) actions.append(button("Refazer resposta", () => ask(previousQuestion, message.id)));
    actions.append(button("👍 Útil", () => rate(message.id, 1), message.feedback === 1 ? "active" : ""));
    actions.append(button("👎 Melhorar", () => { feedbackTarget = message.id; $("#feedback-comment").value = ""; $("#feedback-dialog").showModal(); }, message.feedback === -1 ? "active" : ""));
    article.append(actions);
  }
  return article;
}
function emptyState() {
  const box = element("div", "empty-state");
  box.append(element("div","brand-mark","A↑"), element("h2","","O que você precisa descobrir?"));
  const ready = documents.filter(item => item.status === "READY" && !item.archived);
  box.append(element("p","",ready.length ? "Selecione os documentos e faça sua pergunta. A conversa será criada ao enviar." : "Comece enviando um documento. Depois, peça uma resposta ou transforme as informações em algo útil."));
  box.append(button("＋ Enviar documentos", () => $("#chat-file-input").click(), "button secondary"));
  const suggestions = element("div","suggestion-list");
  ["Resuma em cinco tópicos.", "Liste os prazos e valores importantes.", "Monte um checklist das obrigações.", "Monte um plano de ação com responsáveis e prazos.", "Compare os documentos selecionados em uma tabela."].forEach(question => suggestions.append(button(question, () => { input.value = question; saveDraft(); input.focus(); resize(); }, "suggestion-chip")));
  box.append(suggestions); messages.append(box);
}
function renderMessages(restore = false) {
  const oldHeight = messages.scrollHeight, oldTop = messages.scrollTop;
  messages.replaceChildren();
  if (!messageHistory.length) emptyState();
  let previous = null;
  messageHistory.forEach((message,index) => {
    messages.append(messageNode(message,previous,index === messageHistory.length - 1));
    if (message.role === "USER") previous = message.content;
  });
  if (current && messageHistory.length < current.total_messages) messages.prepend(button("Carregar mensagens anteriores", loadOlder, "button secondary"));
  if (restore) messages.scrollTop = oldTop + messages.scrollHeight - oldHeight;
  else messages.scrollTop = messages.scrollHeight;
}
function updateScopeLabel() {
  const scope = current ? current.document_ids : selected;
  $("#select-scope").textContent = scope === null ? "Todos os documentos ativos" : scope.length + " documento(s) selecionado(s)";
}
function setBusy(value) {
  busy = value;
  form.querySelector('[type="submit"]').classList.toggle("hidden",value);
  $("#cancel-answer").classList.toggle("hidden",!value);
  input.disabled = value;
  $("#composer-hint").textContent = value ? "Geração local em andamento. Você pode parar a resposta ou mudar de conversa." : "Confira os trechos citados. Enter envia; Shift+Enter quebra a linha.";
}
function closeMobileMenu() {
  document.querySelector(".sidebar")?.classList.remove("mobile-open");
  document.querySelector(".mobile-menu")?.setAttribute("aria-expanded","false");
  document.querySelector(".mobile-menu")?.setAttribute("aria-label","Abrir navegação");
}
function saveDraft() { if (user) localStorage.setItem(draftKey(), input.value); }
function resize() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 160) + "px"; }
function restoreDraft() { input.value = localStorage.getItem(draftKey()) || ""; resize(); }
async function loadChats(append = false) {
  const offset = append ? chatOffset : 0;
  const result = await apiFetch("/api/chats?q=" + encodeURIComponent($("#chat-search").value) + "&offset=" + offset + "&limit=50");
  chats = append ? chats.concat(result) : result; chatOffset = chats.length;
  $("#more-chats").classList.toggle("hidden",result.length < 50);
  $("#chat-list").replaceChildren();
  for (const chat of chats) $("#chat-list").append(button((chat.pinned ? "★ " : "") + chat.title, () => selectChat(chat.id), "chat-item" + (chat.id === current?.id ? " active" : "")));
}
async function selectChat(id) {
  saveDraft(); sequence++; const mySequence = sequence;
  streamController?.abort(); job = null; setBusy(false);
  try {
    const result = await apiFetch("/api/chats/" + id);
    if (mySequence !== sequence) return;
    current = result; messageHistory = result.messages;
    localStorage.setItem(storageKey("last-chat"),String(id));
    $("#chat-title").textContent = current.title;
    $("#pin-chat").textContent = current.pinned ? "★" : "☆";
    $("#pin-chat").setAttribute("aria-pressed",String(current.pinned));
    updateScopeLabel(); renderMessages(); restoreDraft();
    $("#resume-answer").classList.add("hidden");
    closeMobileMenu();
    await loadChats();
    if (mySequence !== sequence) return;
    const active = await apiFetch("/api/chats/" + id + "/generations");
    if (mySequence === sequence && active.length) follow(active[0],mySequence);
    else if (mySequence === sequence) {
      const saved = sessionStorage.getItem(storageKey("request:" + id));
      if (saved) {
        try {
          const pending = JSON.parse(saved);
          const last = await apiFetch("/api/chats/" + id + "/generations/" + pending.request_id);
          if (mySequence !== sequence) return;
          if (["error","cancelled"].includes(last.status)) { input.value = last.question; saveDraft(); showToast(last.error || "Pergunta recuperada após interrupção.","info"); }
          sessionStorage.removeItem(storageKey("request:" + id));
        } catch { /* A POST with no acknowledgement can be retried with the same request ID. */ }
      }
    }
  } catch (error) { if (mySequence === sequence) showToast(error.message,"error"); }
}
function newChat() {
  closeMobileMenu();
  saveDraft(); sequence++; streamController?.abort(); current = null; job = null;
  messageHistory = []; selected = null; setBusy(false);
  $("#resume-answer").classList.add("hidden");
  localStorage.removeItem(storageKey("last-chat"));
  $("#chat-title").textContent = "Nova conversa"; $("#pin-chat").textContent = "☆";
  updateScopeLabel(); renderMessages(); restoreDraft(); input.focus();
}
async function loadOlder() {
  if (!current) return;
  const id = current.id, mySequence = sequence;
  const result = await apiFetch("/api/chats/" + id + "?offset=" + messageHistory.length + "&limit=100");
  if (mySequence !== sequence) return;
  messageHistory = result.messages.concat(messageHistory); renderMessages(true);
}
function pendingNode() {
  const article = element("article","message assistant pending-message");
  article.append(element("strong","","AI-Up"));
  const stage = element("p","thinking-row","Na fila"); stage.setAttribute("role","status");
  const content = element("div","stream-content");
  article.append(stage,content); messages.append(article); messages.scrollTop = messages.scrollHeight;
  return {article,stage,content};
}
async function ask(question, retryMessageId = null) {
  if (busy || question.trim().length < 2) return;
  question = question.trim(); saveDraft();
  setBusy(true);
  const submittedSequence = sequence;
  try {
    if (!current) {
      const created = await apiFetch("/api/chats", {method:"POST",body:JSON.stringify({title:"Nova conversa", document_ids:selected})});
      if (submittedSequence !== sequence) { await loadChats(); return; }
      current = created;
      localStorage.removeItem(storageKey("draft:new"));
      localStorage.setItem(storageKey("last-chat"), String(current.id));
    }
    const pendingKey = storageKey("request:" + current.id);
    let request; try { request = JSON.parse(sessionStorage.getItem(pendingKey)); } catch {}
    if (!request || request.message !== question || request.retry_message_id !== retryMessageId) {
      request = {message:question, request_id:crypto.randomUUID(), retry_message_id:retryMessageId};
      sessionStorage.setItem(pendingKey,JSON.stringify(request));
    }
    setBusy(true);
    const submittedChat = current.id, mySequence = sequence;
    const response = await apiFetch("/api/chats/" + submittedChat + "/generations",{method:"POST", body:JSON.stringify(request)});
    if (mySequence !== sequence) return;
    input.value = ""; localStorage.removeItem(draftKey()); resize();
    await follow(response,mySequence);
  } catch (error) {
    if (submittedSequence !== sequence) return;
    setBusy(false); input.value = question; saveDraft(); showToast(error.message,"error");
    $("#resume-answer").classList.remove("hidden");
  }
}
async function follow(generation,mySequence) {
  if (mySequence !== sequence || !current) return;
  job = generation; const chatId = current.id;
  setBusy(true); $("#resume-answer").classList.add("hidden"); renderMessages();
  messages.querySelector(".empty-state")?.remove();
  if (!generation.retry_message_id) messages.append(messageNode({role:"USER",content:generation.question}));
  const pending = pendingNode(); let text = "";
  const controller = new AbortController(); streamController = controller;
  try {
    const response = await apiRequest("/api/chats/" + chatId + "/generations/" + generation.id + "/events",{timeoutMs:0,signal:controller.signal});
    const reader = response.body.getReader(), decoder = new TextDecoder();
    let buffer = "", terminal = null;
    while (mySequence === sequence) {
      const {value,done} = await reader.read(); if (done) break;
      buffer += decoder.decode(value,{stream:true}); let boundary;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        const block = buffer.slice(0,boundary); buffer = buffer.slice(boundary+2);
        if (!block.startsWith("data: ")) continue;
        const event = JSON.parse(block.slice(6));
        if (mySequence !== sequence) { reader.cancel(); return; }
        if (event.type === "stage") pending.stage.textContent = event.data;
        if (event.type === "delta") {
          const nearEnd = messages.scrollHeight - messages.scrollTop - messages.clientHeight <= 8;
          text += event.data; pending.content.replaceChildren(markdown(text));
          if (nearEnd) messages.scrollTop = messages.scrollHeight;
        }
        if (["done","error","cancelled"].includes(event.type)) terminal = event;
      }
    }
    if (mySequence !== sequence) return;
    if (!terminal) throw new Error("Conexão interrompida. Use Retomar resposta para acompanhar o processamento.");
    sessionStorage.removeItem(storageKey("request:" + chatId)); job = null; setBusy(false);
    if (terminal.type !== "done") {
      input.value = generation.question; saveDraft();
      showToast(terminal.data.error || "Resposta cancelada. Sua pergunta foi preservada.",terminal.type === "error" ? "error" : "info");
    }
    const readingTop = messages.scrollTop, nearEnd = messages.scrollHeight - messages.scrollTop - messages.clientHeight <= 8;
    const result = await apiFetch("/api/chats/" + chatId); if (mySequence !== sequence) return;
    current = result; messageHistory = result.messages; renderMessages();
    if (!nearEnd) messages.scrollTop = readingTop;
    $("#chat-title").textContent = current.title; await loadChats();
  } catch (error) {
    if (mySequence !== sequence || controller.signal.aborted) return;
    pending.stage.textContent = "Conexão interrompida"; setBusy(false);
    $("#resume-answer").classList.remove("hidden"); input.value = generation.question; saveDraft(); showToast(error.message,"error");
  }
}
async function rate(id, value, reason = null) {
  if (!current) return;
  try {
    await apiFetch("/api/chats/" + current.id + "/messages/" + id + "/feedback",{method:"PATCH",body:JSON.stringify({feedback:value,reason})});
    const message = messageHistory.find(item => item.id === id);
    if (message) { message.feedback = value; message.feedback_reason = reason; }
    const scroll = messages.scrollTop; renderMessages(); messages.scrollTop = scroll; showToast("Avaliação registrada.","success");
  } catch (error) { showToast(error.message,"error"); }
}
async function loadDocuments() {
  documents = await apiFetch("/api/documents?limit=500");
  if (documents.some(item => ["UPLOADED","PROCESSING"].includes(item.status))) {
    clearTimeout(documentTimer); documentTimer = setTimeout(() => loadDocuments().catch(error => showToast(error.message,"error")),2000);
  }
}
async function uploadFiles(files) {
  for (const file of files) {
    try {
      const data = new FormData(); data.append("file",file);
      const uploaded = await apiFetch("/api/documents",{method:"POST",body:data,timeoutMs:60000});
      showToast(file.name + ": recebido. Acompanhe a preparação em Documentos.","success");
      if (current && current.document_ids !== null && !busy) {
        current = {...current,...await apiFetch("/api/chats/" + current.id,{method:"PATCH",body:JSON.stringify({document_ids:[...new Set(current.document_ids.concat(uploaded.id))]})})};
      } else if (!current && selected !== null) selected.push(uploaded.id);
    } catch (error) { showToast(file.name + ": " + error.message,"error"); }
  }
  await loadDocuments(); updateScopeLabel(); if (!messageHistory.length && !busy) renderMessages();
}
$("#new-chat").addEventListener("click",newChat);
$("#chat-search").addEventListener("input",() => { clearTimeout(searchTimer); searchTimer = setTimeout(() => loadChats().catch(error => showToast(error.message,"error")),250); });
$("#more-chats").addEventListener("click",() => loadChats(true).catch(error => showToast(error.message,"error")));
$("#pin-chat").addEventListener("click",async () => {
  if (!current) return;
  try { const updated = await apiFetch("/api/chats/" + current.id,{method:"PATCH",body:JSON.stringify({pinned:!current.pinned})}); current.pinned = updated.pinned; $("#pin-chat").textContent = updated.pinned ? "★" : "☆"; await loadChats(); }
  catch (error) { showToast(error.message,"error"); }
});
$("#select-scope").addEventListener("click",async () => {
  try {
    await loadDocuments(); const scope = current ? current.document_ids : selected;
    $("#scope-all").checked = scope === null; $("#scope-options").replaceChildren();
    documents.forEach(document => {
      const label = element("label","scope-option"), checkbox = window.document.createElement("input");
      checkbox.type = "checkbox"; checkbox.value = document.id; checkbox.checked = scope?.includes(document.id) || false;
      checkbox.disabled = document.status !== "READY"; checkbox.addEventListener("change",() => { $("#scope-all").checked = false; });
      label.append(checkbox,document.original_filename + " · v" + document.version + (document.archived ? " · arquivado" : "") + (document.status !== "READY" ? " · aguardando processamento" : "")); $("#scope-options").append(label);
    });
    $("#scope-dialog").showModal();
  } catch (error) { showToast(error.message,"error"); }
});
$("#scope-form").addEventListener("submit",async event => {
  event.preventDefault();
  const ids = $("#scope-all").checked ? null : [...document.querySelectorAll("#scope-options input:checked")].map(node => Number(node.value));
  if (ids !== null && !ids.length) { showToast("Selecione ao menos um documento ou marque todos.","error"); return; }
  try {
    if (current) { const result = await apiFetch("/api/chats/" + current.id,{method:"PATCH",body:JSON.stringify({document_ids:ids})}); current.document_ids = result.document_ids; }
    else selected = ids;
    updateScopeLabel(); $("#scope-dialog").close();
  } catch (error) { showToast(error.message,"error"); }
});
$("#attach-document").addEventListener("click",() => $("#chat-file-input").click());
$("#chat-file-input").addEventListener("change",async event => { await uploadFiles([...event.target.files]); event.target.value = ""; });
$("#cancel-answer").addEventListener("click",async () => {
  if (!job || !current) return;
  try { await apiFetch("/api/chats/" + current.id + "/generations/" + job.id + "/cancel",{method:"POST"}); }
  catch (error) { showToast(error.message,"error"); }
});
$("#resume-answer").addEventListener("click",() => { if (job) follow(job,sequence); else if (current) selectChat(current.id); });
$("#rename-chat").addEventListener("click",() => { if (!current) return; $("#rename-input").value = current.title; $("#rename-dialog").showModal(); $("#rename-input").focus(); });
$("#cancel-rename").addEventListener("click",() => $("#rename-dialog").close());
$("#rename-form").addEventListener("submit",async event => {
  event.preventDefault(); if (!current) return;
  try { const result = await apiFetch("/api/chats/" + current.id,{method:"PATCH",body:JSON.stringify({title:$("#rename-input").value.trim()})}); current.title = result.title; $("#chat-title").textContent = result.title; $("#rename-dialog").close(); await loadChats(); }
  catch (error) { showToast(error.message,"error"); }
});
$("#delete-chat").addEventListener("click",() => { if (current) $("#delete-dialog").showModal(); });
$("#cancel-delete").addEventListener("click",() => $("#delete-dialog").close());
$("#confirm-delete").addEventListener("click",async () => {
  if (!current) return;
  try { await apiFetch("/api/chats/" + current.id,{method:"DELETE"}); localStorage.removeItem(draftKey()); input.value = ""; newChat(); await loadChats(); $("#delete-dialog").close(); }
  catch (error) { showToast(error.message,"error"); }
});
$("#feedback-form").addEventListener("submit",async event => {
  event.preventDefault(); await rate(feedbackTarget,-1,$("#feedback-reason").value + ($("#feedback-comment").value.trim() ? ": " + $("#feedback-comment").value.trim() : "")); $("#feedback-dialog").close();
});
$("#export-chat").addEventListener("click",() => { if (current) $("#export-dialog").showModal(); });
document.querySelectorAll("[data-export]").forEach(node => node.addEventListener("click",async () => {
  if (!current) return;
  try { const format = node.dataset.export; await downloadFile("/api/chats/" + current.id + "/export?format=" + format,"ai-up-conversa." + (format === "markdown" ? "md" : format)); $("#export-dialog").close(); }
  catch (error) { showToast(error.message,"error"); }
}));
document.querySelectorAll("[data-close]").forEach(node => node.addEventListener("click",() => document.getElementById(node.dataset.close).close()));
form.addEventListener("submit",event => { event.preventDefault(); ask(input.value); });
input.addEventListener("input",() => { saveDraft(); resize(); });
input.addEventListener("keydown",event => { if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); if (input.value.trim().length >= 2) form.requestSubmit(); } });
messages.addEventListener("scroll",() => $("#jump-latest").classList.toggle("hidden",messages.scrollHeight-messages.scrollTop-messages.clientHeight < 160));
$("#jump-latest").addEventListener("click",() => messages.scrollTo({top:messages.scrollHeight,behavior:"smooth"}));
window.addEventListener("beforeunload",saveDraft);
(async () => {
  try {
    user = await loadCurrentUser(); await loadDocuments(); await loadChats();
    const params = new URLSearchParams(location.search), documentId = Number(params.get("document"));
    if (documentId && documents.some(item => item.id === documentId)) { newChat(); selected = [documentId]; updateScopeLabel(); }
    else { const last = Number(params.get("chat") || localStorage.getItem(storageKey("last-chat"))); if (last) await selectChat(last); else { renderMessages(); restoreDraft(); } }
  } catch (error) { showToast(error.message,"error"); }
})();
})();
