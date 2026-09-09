const TOKEN_KEY = "ai_up_access_token";

async function apiFetch(path, options = {}) {
  const { timeoutMs, ...requestOptions } = options;
  const token = localStorage.getItem(TOKEN_KEY);
  const headers = new Headers(requestOptions.headers || {});
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (requestOptions.body && !(requestOptions.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const controller = timeoutMs ? new AbortController() : null;
  const timeout = controller ? window.setTimeout(() => controller.abort(), timeoutMs) : null;
  let response;
  try {
    response = await fetch(path, {
      ...requestOptions,
      headers,
      signal: controller?.signal || requestOptions.signal,
    });
  } catch (reason) {
    if (reason.name === "AbortError") {
      throw new Error("A resposta demorou mais que o esperado. Verifique o Ollama e tente novamente.");
    }
    throw new Error("Não foi possível conectar ao AI-Up. Confirme se o aplicativo está em execução.");
  } finally {
    if (timeout) window.clearTimeout(timeout);
  }
  if (response.status === 401) {
    localStorage.removeItem(TOKEN_KEY);
    window.location.href = "/login.html";
    throw new Error("Sessão expirada.");
  }
  if (!response.ok) {
    let detail = "Não foi possível concluir a operação.";
    try { detail = (await response.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  if (response.status === 204) return null;
  return response.json();
}

function showToast(message, type = "info") {
  const toast = document.querySelector("#toast");
  if (!toast) return;
  toast.textContent = message;
  toast.className = `toast visible ${type}`;
  window.setTimeout(() => toast.classList.remove("visible"), 3500);
}

async function loadCurrentUser() {
  const user = await apiFetch("/api/auth/me");
  const name = document.querySelector("#user-name");
  const role = document.querySelector("#user-role");
  const initial = document.querySelector("#user-initial");
  if (name) name.textContent = user.name;
  if (role) role.textContent = user.role.replace("IT_ADMIN", "IT Admin");
  if (initial) initial.textContent = user.name.charAt(0).toUpperCase();
  const adminLink = document.querySelector("#admin-link");
  if (adminLink && ["MANAGER", "IT_ADMIN"].includes(user.role)) adminLink.classList.remove("hidden");
  return user;
}

async function logout() {
  try { await apiFetch("/api/auth/logout", { method: "POST" }); } catch {}
  localStorage.removeItem(TOKEN_KEY);
  window.location.href = "/login.html";
}

document.querySelector("#logout")?.addEventListener("click", logout);
window.aiup = { apiFetch, loadCurrentUser, showToast, logout, TOKEN_KEY };
