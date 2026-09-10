const TOKEN_KEY = "ai_up_access_token";
let refreshPromise = null;

async function refreshSession() {
  if (!refreshPromise) {
    refreshPromise = fetch("/api/auth/refresh", {
      method: "POST",
      credentials: "same-origin",
    }).then(async response => {
      if (!response.ok) return false;
      const body = await response.json();
      sessionStorage.setItem(TOKEN_KEY, body.access_token);
      return true;
    }).catch(() => false);
  }
  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}

async function apiRequest(path, options = {}, allowRefresh = true) {
  const {timeoutMs = 20000, ...requestOptions} = options;
  const headers = new Headers(requestOptions.headers || {});
  const token = sessionStorage.getItem(TOKEN_KEY);
  if (token) headers.set("Authorization", "Bearer " + token);
  if (requestOptions.body && !(requestOptions.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const controller = new AbortController();
  const externalAbort = () => controller.abort();
  requestOptions.signal?.addEventListener("abort", externalAbort, {once:true});
  if (requestOptions.signal?.aborted) controller.abort();
  const timeout = timeoutMs ? setTimeout(() => controller.abort(), timeoutMs) : null;
  try {
    const response = await fetch(path, {...requestOptions, headers, signal:timeoutMs === 0 && requestOptions.signal ? requestOptions.signal : controller.signal});
    if (response.status === 401) {
      if (allowRefresh && path !== "/api/auth/refresh" && await refreshSession()) {
        return apiRequest(path, options, false);
      }
      sessionStorage.removeItem(TOKEN_KEY);
      location.href = "/login.html";
      throw new Error("Sua sessão terminou. Entre novamente.");
    }
    if (!response.ok) {
      let detail = "Não foi possível concluir a operação.";
      let body = null;
      try {
        body = await response.json();
        detail = typeof body.message === "string" ? body.message : (typeof body.detail === "string" ? body.detail : detail);
        if (body.errors?.length) detail += " " + body.errors.map(item => item.field + ": " + item.message).join("; ");
      } catch {}
      const error = new Error(detail);
      error.status = response.status;
      error.code = body?.error;
      error.requestId = body?.request_id || response.headers.get("X-Request-ID");
      throw error;
    }
    return response;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("A conexão foi interrompida. Sua solicitação pode continuar em processamento; reabra a conversa para retomar.");
    if (error instanceof TypeError) throw new Error("Não foi possível conectar. Confira se o AI-Up está aberto e tente novamente.");
    throw error;
  } finally {
    if (timeout) clearTimeout(timeout);
    requestOptions.signal?.removeEventListener("abort", externalAbort);
  }
}

async function apiFetch(path, options = {}) {
  const response = await apiRequest(path, options);
  return response.status === 204 ? null : response.json();
}

let toastTimer;
function showToast(message, type = "info") {
  const toast = document.querySelector("#toast");
  if (!toast) return;
  clearTimeout(toastTimer);
  toast.textContent = message;
  toast.setAttribute("role", type === "error" ? "alert" : "status");
  toast.className = "toast visible " + type;
  toastTimer = setTimeout(() => toast.classList.remove("visible"), type === "error" ? 9000 : 4500);
  toast.onclick = () => toast.classList.remove("visible");
}

async function loadCurrentUser() {
  const user = await apiFetch("/api/auth/me");
  const labels = {USER:"Usuário", MANAGER:"Gestor", IT_ADMIN:"Administrador"};
  const name = document.querySelector("#user-name");
  const role = document.querySelector("#user-role");
  const initial = document.querySelector("#user-initial");
  if (name) name.textContent = user.name;
  if (role) role.textContent = labels[user.role] || user.role;
  if (initial) initial.textContent = user.name.charAt(0).toUpperCase();
  if (["MANAGER","IT_ADMIN"].includes(user.role)) document.querySelector("#admin-link")?.classList.remove("hidden");
  return user;
}

async function logout() {
  try { await apiFetch("/api/auth/logout", {method:"POST"}); }
  catch (error) { showToast(error.message, "error"); return; }
  sessionStorage.removeItem(TOKEN_KEY);
  location.href = "/login.html";
}

async function downloadFile(path, name) {
  const response = await apiRequest(path, {timeoutMs:60000});
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

function setupShell() {
  const sidebar = document.querySelector(".sidebar");
  if (!sidebar) return;
  sidebar.id = "app-sidebar";
  const toggle = document.createElement("button");
  toggle.className = "mobile-menu icon-button";
  toggle.textContent = "☰";
  toggle.setAttribute("aria-label", "Abrir navegação");
  toggle.setAttribute("aria-expanded", "false");
  toggle.setAttribute("aria-controls", sidebar.id);
  toggle.addEventListener("click", () => {
    const opened = sidebar.classList.toggle("mobile-open");
    toggle.setAttribute("aria-expanded", String(opened));
    toggle.setAttribute("aria-label", opened ? "Fechar navegação" : "Abrir navegação");
  });
  document.body.prepend(toggle);
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") { sidebar.classList.remove("mobile-open"); toggle.setAttribute("aria-expanded","false"); }
  });
  const navigation = sidebar.querySelector(".nav-links");
  if (navigation && !navigation.querySelector('[href="/settings.html"]')) {
    const link = document.createElement("a");
    link.href = "/settings.html";
    link.textContent = "Diagnóstico e conta";
    navigation.append(link);
  }
  document.querySelector("#logout")?.setAttribute("aria-label","Sair de todas as sessões");
}

// Keep native scrolling inside lists, fields and dialogs. Only redirect input
// from fixed chat chrome, where there is otherwise no scrollable ancestor.
function canScrollVertically(node, delta) {
  return node && node.scrollHeight > node.clientHeight + 1 &&
    (delta < 0 ? node.scrollTop > 0 : node.scrollTop + node.clientHeight < node.scrollHeight - 1);
}

function scrollDestination(target, delta) {
  if (!(target instanceof Element)) return null;
  const dialog = target.closest("dialog[open]");
  if (document.querySelector("dialog[open]") && !dialog) return null;
  for (let node = target; node; node = node.parentElement) {
    if (/(auto|scroll)/.test(getComputedStyle(node).overflowY) && canScrollVertically(node, delta)) return null;
    if (node === dialog) return null;
  }
  if (target.closest(".sidebar") || target.closest("select, input, [contenteditable=true]")) return null;
  const history = document.querySelector("#messages");
  return target.closest(".workspace") && canScrollVertically(history, delta) ? history : null;
}

function setupScrollNavigation() {
  if (document.querySelector(".content-page")) document.body.classList.add("document-page");
  document.addEventListener("wheel", event => {
    if (event.defaultPrevented || event.ctrlKey || event.shiftKey || Math.abs(event.deltaX) > Math.abs(event.deltaY) || !event.deltaY) return;
    const destination = scrollDestination(event.target, event.deltaY);
    if (!destination) return;
    const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? destination.clientHeight : 1;
    destination.scrollTop += event.deltaY * unit;
    event.preventDefault();
  }, {passive:false});
  document.addEventListener("keydown", event => {
    if (event.defaultPrevented || event.ctrlKey || event.altKey || event.metaKey ||
        !(event.target instanceof Element) || event.target.closest("input,textarea,select,[contenteditable=true],dialog[open]")) return;
    if (!["PageUp","PageDown","Home","End"].includes(event.key)) return;
    const history = document.querySelector("#messages");
    if (!history || event.target.closest(".sidebar")) return;
    const direction = ["PageUp","Home"].includes(event.key) ? -1 : 1;
    if (!canScrollVertically(history, direction)) return;
    if (event.key === "Home") history.scrollTop = 0;
    else if (event.key === "End") history.scrollTop = history.scrollHeight;
    else history.scrollTop += direction * history.clientHeight * 0.85;
    event.preventDefault();
  });
}

document.querySelector("#logout")?.addEventListener("click", logout);
setupShell();
setupScrollNavigation();
window.aiup = {apiFetch, apiRequest, loadCurrentUser, showToast, logout, downloadFile, TOKEN_KEY};
