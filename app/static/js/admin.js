(() => {
const { apiFetch, loadCurrentUser, showToast } = window.aiup;
const statsContainer = document.querySelector("#stats");
const logsContainer = document.querySelector("#logs");
const usersContainer = document.querySelector("#users");

const STAT_LABELS = {
  users: "Usuários", documents: "Documentos", documents_ready: "Prontos",
  documents_error: "Com erro", chats: "Conversas", messages: "Mensagens", ai_questions: "Perguntas",
};

function renderStats(stats) {
  statsContainer.replaceChildren();
  Object.entries(STAT_LABELS).forEach(([key, label]) => {
    const card = document.createElement("article");
    card.className = "stat-card";
    const value = document.createElement("strong");
    value.textContent = stats[key];
    const text = document.createElement("span");
    text.textContent = label;
    card.append(value, text);
    statsContainer.append(card);
  });
}

function renderLogs(logs) {
  logsContainer.replaceChildren();
  logs.forEach((log) => {
    const row = document.createElement("div");
    row.className = "log-row";
    const action = document.createElement("strong");
    action.textContent = log.action;
    const meta = document.createElement("small");
    meta.textContent = `${log.resource_type || "sistema"}${log.resource_id ? ` #${log.resource_id}` : ""} · ${new Date(log.created_at).toLocaleString("pt-BR")}`;
    row.append(action, meta);
    logsContainer.append(row);
  });
}

function userNode(user) {
  const row = document.createElement("div");
  row.className = "admin-user-row";
  const identity = document.createElement("div");
  const name = document.createElement("strong");
  name.textContent = user.name;
  const email = document.createElement("small");
  email.textContent = user.email;
  identity.append(name, email);
  const role = document.createElement("select");
  ["USER", "MANAGER", "IT_ADMIN"].forEach((value) => {
    const option = document.createElement("option");
    option.value = value; option.textContent = value; option.selected = value === user.role; role.append(option);
  });
  role.addEventListener("change", async () => {
    try { await apiFetch(`/api/users/${user.id}`, { method: "PATCH", body: JSON.stringify({ role: role.value }) }); showToast("Função atualizada.", "success"); }
    catch (reason) { showToast(reason.message, "error"); role.value = user.role; }
  });
  const active = document.createElement("button");
  active.className = `badge ${user.active ? "ready" : "error"}`;
  active.textContent = user.active ? "ATIVO" : "INATIVO";
  active.addEventListener("click", async () => {
    try { await apiFetch(`/api/users/${user.id}`, { method: "PATCH", body: JSON.stringify({ active: !user.active }) }); await loadUsers(); }
    catch (reason) { showToast(reason.message, "error"); }
  });
  row.append(identity, role, active);
  return row;
}

async function loadUsers() {
  const users = await apiFetch("/api/users");
  usersContainer.replaceChildren();
  users.forEach((user) => usersContainer.append(userNode(user)));
}

document.querySelector("#new-user")?.addEventListener("click", async () => {
  const name = window.prompt("Nome do usuário:");
  if (!name?.trim()) return;
  const email = window.prompt("E-mail do usuário:");
  if (!email?.trim()) return;
  const password = window.prompt("Senha inicial (mínimo 8 caracteres):");
  if (!password) return;
  try {
    await apiFetch("/api/users", { method: "POST", body: JSON.stringify({ name: name.trim(), email: email.trim(), password, role: "USER" }) });
    await loadUsers();
    showToast("Usuário criado.", "success");
  } catch (reason) { showToast(reason.message, "error"); }
});

(async () => {
  try {
    const user = await loadCurrentUser();
    if (!["MANAGER", "IT_ADMIN"].includes(user.role)) { window.location.href = "/"; return; }
    const [stats, logs] = await Promise.all([apiFetch("/api/admin/stats"), apiFetch("/api/admin/logs?page_size=20")]);
    renderStats(stats); renderLogs(logs.items);
    if (user.role === "IT_ADMIN") { document.querySelector("#users-panel").classList.remove("hidden"); await loadUsers(); }
  } catch (reason) { showToast(reason.message, "error"); }
})();
})();
