(() => {
const { apiFetch, loadCurrentUser, showToast } = window.aiup;
let currentChatId = null;
let isBusy = false;
let suggestionQuestions = [
  "Resuma os pontos mais importantes.",
  "Quais prazos e valores aparecem?",
  "Há riscos ou obrigações relevantes?",
];

const list = document.querySelector("#chat-list");
const messages = document.querySelector("#messages");
const title = document.querySelector("#chat-title");
const form = document.querySelector("#message-form");
const input = document.querySelector("#message-input");
const composerHint = document.querySelector("#composer-hint");
const renameDialog = document.querySelector("#rename-dialog");
const renameForm = document.querySelector("#rename-form");
const renameInput = document.querySelector("#rename-input");
const deleteDialog = document.querySelector("#delete-dialog");

function appendInlineMarkdown(parent, text) {
  const pattern = /(\*\*([^*]+)\*\*|`([^`]+)`)/g;
  let position = 0;
  for (const match of text.matchAll(pattern)) {
    if (match.index > position) parent.append(document.createTextNode(text.slice(position, match.index)));
    const element = document.createElement(match[2] ? "strong" : "code");
    element.textContent = match[2] || match[3];
    parent.append(element);
    position = match.index + match[0].length;
  }
  if (position < text.length) parent.append(document.createTextNode(text.slice(position)));
}

function markdownNode(text) {
  const container = document.createElement("div");
  container.className = "message-content";
  const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
  let index = 0;
  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) { index += 1; continue; }
    const unordered = line.match(/^[-*]\s+(.+)/);
    const ordered = line.match(/^\d+[.)]\s+(.+)/);
    if (unordered || ordered) {
      const orderedList = Boolean(ordered);
      const listNode = document.createElement(orderedList ? "ol" : "ul");
      while (index < lines.length) {
        const candidate = lines[index].trim();
        const itemMatch = candidate.match(orderedList ? /^\d+[.)]\s+(.+)/ : /^[-*]\s+(.+)/);
        if (!itemMatch) break;
        const item = document.createElement("li");
        appendInlineMarkdown(item, itemMatch[1]);
        listNode.append(item);
        index += 1;
      }
      container.append(listNode);
      continue;
    }
    const heading = line.match(/^(#{1,3})\s+(.+)/);
    if (heading) {
      const headingNode = document.createElement("h4");
      appendInlineMarkdown(headingNode, heading[2]);
      container.append(headingNode);
      index += 1;
      continue;
    }
    const paragraphLines = [line];
    index += 1;
    while (index < lines.length) {
      const candidate = lines[index].trim();
      if (!candidate || /^[-*]\s+/.test(candidate) || /^\d+[.)]\s+/.test(candidate) || /^#{1,3}\s+/.test(candidate)) break;
      paragraphLines.push(candidate);
      index += 1;
    }
    const paragraph = document.createElement("p");
    appendInlineMarkdown(paragraph, paragraphLines.join(" "));
    container.append(paragraph);
  }
  return container;
}

function appendHighlightedEvidence(parent, text, answer) {
  const stopwords = new Set(["como", "com", "das", "dos", "esta", "este", "isso", "mais", "para", "pela", "pelo", "qual", "que", "uma"]);
  const words = String(answer || "").match(/[\p{L}\p{N}][\p{L}\p{N}.,%-]*/gu) || [];
  const terms = [...new Set(words.map((word) => word.replace(/[.,]$/, "")).filter((word) => word.length >= 4 && !stopwords.has(word.toLocaleLowerCase("pt-BR"))))]
    .filter((word) => String(text).toLocaleLowerCase("pt-BR").includes(word.toLocaleLowerCase("pt-BR")))
    .sort((left, right) => right.length - left.length)
    .slice(0, 10);
  if (!terms.length) { parent.textContent = text; return; }
  const escaped = terms.map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const pattern = new RegExp(`(${escaped.join("|")})`, "giu");
  let position = 0;
  for (const match of String(text).matchAll(pattern)) {
    if (match.index > position) parent.append(document.createTextNode(text.slice(position, match.index)));
    const mark = document.createElement("mark");
    mark.textContent = match[0];
    parent.append(mark);
    position = match.index + match[0].length;
  }
  if (position < text.length) parent.append(document.createTextNode(text.slice(position)));
}

function suggestionButton(question) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "suggestion-chip";
  button.textContent = question;
  button.addEventListener("click", () => {
    input.value = question;
    input.focus();
  });
  return button;
}

function emptyState(text = "Crie uma conversa e envie documentos para começar.") {
  messages.replaceChildren();
  const box = document.createElement("div");
  box.className = "empty-state";
  const mark = document.createElement("div");
  mark.className = "brand-mark";
  mark.textContent = "A↑";
  const heading = document.createElement("h2");
  heading.textContent = "Converse com seus documentos.";
  const copy = document.createElement("p");
  copy.textContent = text;
  const suggestions = document.createElement("div");
  suggestions.className = "suggestion-list";
  suggestionQuestions.forEach((question) => suggestions.append(suggestionButton(question)));
  box.append(mark, heading, copy, suggestions);
  messages.append(box);
}

function sourceNode(source, answer) {
  const details = document.createElement("details");
  details.className = "source-card";
  const summary = document.createElement("summary");
  const location = source.page
    ? `página ${source.page}`
    : (source.sheet ? `planilha ${source.sheet}` : "documento");
  summary.textContent = `${source.document} — ${location}`;
  details.append(summary);
  if (source.excerpt) {
    const label = document.createElement("small");
    label.textContent = "EVIDÊNCIA UTILIZADA";
    const excerpt = document.createElement("p");
    appendHighlightedEvidence(excerpt, source.excerpt, answer);
    details.append(label, excerpt);
  }
  return details;
}

async function copyAnswer(content, button) {
  try {
    await navigator.clipboard.writeText(content);
    button.textContent = "Copiado";
    window.setTimeout(() => { button.textContent = "Copiar"; }, 1600);
  } catch {
    showToast("Não foi possível copiar automaticamente.", "error");
  }
}

async function rateAnswer(messageId, feedback, button, actions) {
  try {
    await apiFetch(`/api/chats/${currentChatId}/messages/${messageId}/feedback`, {
      method: "PATCH",
      body: JSON.stringify({ feedback }),
    });
    actions.querySelectorAll("[data-feedback]").forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    showToast("Obrigado pelo feedback.", "success");
  } catch (reason) { showToast(reason.message, "error"); }
}

function messageNode(message, previousUserQuestion = null) {
  const article = document.createElement("article");
  article.className = `message ${message.role.toLowerCase()}`;
  const label = document.createElement("strong");
  label.textContent = message.role === "USER" ? "Você" : "AI-Up";
  article.append(label, markdownNode(message.content));

  if (message.sources?.length) {
    const sourceSection = document.createElement("section");
    sourceSection.className = "source-section";
    const sourceLabel = document.createElement("span");
    sourceLabel.className = "source-label";
    sourceLabel.textContent = message.sources.length === 1 ? "1 fonte verificável" : `${message.sources.length} fontes verificáveis`;
    const sourceList = document.createElement("div");
    sourceList.className = "source-list";
    message.sources.forEach((source) => sourceList.append(sourceNode(source, message.content)));
    sourceSection.append(sourceLabel, sourceList);
    article.append(sourceSection);
  }

  if (message.role === "ASSISTANT" && message.id) {
    const actions = document.createElement("div");
    actions.className = "message-actions";
    const copy = document.createElement("button");
    copy.type = "button";
    copy.textContent = "Copiar";
    copy.addEventListener("click", () => copyAnswer(message.content, copy));
    actions.append(copy);
    if (previousUserQuestion) {
      const retry = document.createElement("button");
      retry.type = "button";
      retry.textContent = "Tentar novamente";
      retry.addEventListener("click", () => askQuestion(previousUserQuestion));
      actions.append(retry);
    }
    [[1, "Útil", "👍"], [-1, "Não foi útil", "👎"]].forEach(([value, name, icon]) => {
      const rate = document.createElement("button");
      rate.type = "button";
      rate.dataset.feedback = String(value);
      rate.textContent = icon;
      rate.title = name;
      rate.setAttribute("aria-label", name);
      if (message.feedback === value) rate.classList.add("active");
      rate.addEventListener("click", () => rateAnswer(message.id, value, rate, actions));
      actions.append(rate);
    });
    article.append(actions);
  }
  return article;
}

function pendingNode() {
  const article = document.createElement("article");
  article.className = "message assistant pending-message";
  const label = document.createElement("strong");
  label.textContent = "AI-Up";
  const row = document.createElement("div");
  row.className = "thinking-row";
  const spinner = document.createElement("span");
  spinner.className = "thinking-spinner";
  const status = document.createElement("span");
  status.textContent = "Interpretando sua pergunta…";
  row.append(spinner, status);
  article.append(label, row);
  return { article, status };
}

function setBusy(value) {
  isBusy = value;
  input.disabled = value;
  form.querySelector("button[type='submit']").disabled = value;
  composerHint.textContent = value
    ? "Processamento local em andamento — seus documentos não saem desta máquina."
    : "O AI-Up responde somente com base nos trechos recuperados.";
}

async function loadSuggestionQuestions() {
  try {
    const documents = await apiFetch("/api/documents");
    const ready = documents.find((document) => document.status === "READY");
    if (!ready) return;
    const result = await apiFetch(`/api/documents/${ready.id}/suggestions`);
    if (Array.isArray(result.suggestions) && result.suggestions.length) suggestionQuestions = result.suggestions.slice(0, 3);
  } catch {
    // Sugestões genéricas continuam disponíveis se a lista de documentos falhar.
  }
}

function isNearConversationEnd() {
  return messages.scrollHeight - messages.scrollTop - messages.clientHeight < 120;
}

async function loadChats(preferredId = currentChatId, scrollToEnd = true, restoreScrollTop = null) {
  const chats = await apiFetch("/api/chats");
  list.replaceChildren();
  chats.forEach((chat) => {
    const button = document.createElement("button");
    button.className = `chat-item ${chat.id === preferredId ? "active" : ""}`;
    button.dataset.chatId = String(chat.id);
    button.textContent = chat.title;
    button.addEventListener("click", () => { if (!isBusy) selectChat(chat.id); });
    list.append(button);
  });
  if (preferredId && chats.some((chat) => chat.id === preferredId)) await selectChat(preferredId, false, scrollToEnd, restoreScrollTop);
  else if (chats.length) await selectChat(chats[0].id, false, scrollToEnd, restoreScrollTop);
  else { currentChatId = null; title.textContent = "Selecione uma conversa"; emptyState(); }
}

async function selectChat(chatId, refreshList = true, scrollToEnd = true, restoreScrollTop = null) {
  currentChatId = chatId;
  const chat = await apiFetch(`/api/chats/${chatId}`);
  title.textContent = chat.title;
  messages.replaceChildren();
  if (!chat.messages.length) emptyState("Faça uma pergunta direta, peça um resumo ou explore riscos e prazos.");
  else {
    let previousUserQuestion = null;
    chat.messages.forEach((message) => {
      messages.append(messageNode(message, previousUserQuestion));
      if (message.role === "USER") previousUserQuestion = message.content;
    });
  }
  if (scrollToEnd) messages.scrollTop = messages.scrollHeight;
  else if (restoreScrollTop !== null) messages.scrollTop = restoreScrollTop;
  if (refreshList) document.querySelectorAll(".chat-item").forEach((item) => item.classList.toggle("active", item.dataset.chatId === String(chatId)));
}

async function askQuestion(question) {
  if (!currentChatId) { showToast("Crie uma conversa primeiro.", "error"); return; }
  if (!question || isBusy) return;
  const requestedChatId = currentChatId;
  messages.querySelector(".empty-state")?.remove();
  messages.append(messageNode({ role: "USER", content: question }));
  const pending = pendingNode();
  messages.append(pending.article);
  messages.scrollTop = messages.scrollHeight;
  setBusy(true);
  const states = ["Buscando evidências nos documentos…", "Selecionando os trechos mais relevantes…", "Redigindo uma resposta verificável…"];
  let stateIndex = 0;
  const progressTimer = window.setInterval(() => {
    pending.status.textContent = states[Math.min(stateIndex, states.length - 1)];
    stateIndex += 1;
  }, 4500);
  try {
    await apiFetch(`/api/chats/${requestedChatId}/messages`, {
      method: "POST",
      body: JSON.stringify({ message: question }),
      timeoutMs: 180000,
    });
    const keepReadingPosition = !isNearConversationEnd();
    const readingPosition = messages.scrollTop;
    await loadChats(requestedChatId, !keepReadingPosition, readingPosition);
  } catch (reason) {
    pending.article.remove();
    showToast(reason.message, "error");
    input.value = question;
  } finally {
    window.clearInterval(progressTimer);
    setBusy(false);
    input.focus();
  }
}

document.querySelector("#new-chat").addEventListener("click", async () => {
  if (isBusy) return;
  try {
    const chat = await apiFetch("/api/chats", { method: "POST", body: JSON.stringify({ title: "Nova conversa" }) });
    await loadChats(chat.id);
    input.focus();
  } catch (reason) { showToast(reason.message, "error"); }
});

document.querySelector("#rename-chat").addEventListener("click", () => {
  if (!currentChatId || isBusy) return;
  renameInput.value = title.textContent;
  renameDialog.showModal();
  renameInput.focus();
  renameInput.select();
});

document.querySelector("#cancel-rename").addEventListener("click", () => renameDialog.close());
renameForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const newTitle = renameInput.value.trim();
  if (!currentChatId || !newTitle) return;
  try { await apiFetch(`/api/chats/${currentChatId}`, { method: "PATCH", body: JSON.stringify({ title: newTitle }) }); renameDialog.close(); await loadChats(currentChatId); }
  catch (reason) { showToast(reason.message, "error"); }
});

document.querySelector("#delete-chat").addEventListener("click", () => {
  if (currentChatId && !isBusy) deleteDialog.showModal();
});
document.querySelector("#cancel-delete").addEventListener("click", () => deleteDialog.close());
document.querySelector("#confirm-delete").addEventListener("click", async () => {
  if (!currentChatId) return;
  try { await apiFetch(`/api/chats/${currentChatId}`, { method: "DELETE" }); currentChatId = null; await loadChats(); }
  catch (reason) { showToast(reason.message, "error"); }
  finally { deleteDialog.close(); }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const question = input.value.trim();
  if (!question) return;
  input.value = "";
  await askQuestion(question);
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

(async () => { try { await loadCurrentUser(); await loadSuggestionQuestions(); await loadChats(); } catch (reason) { showToast(reason.message, "error"); } })();
})();
