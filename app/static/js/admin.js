(() => {
const { apiFetch, loadCurrentUser, showToast } = window.aiup;
const statsContainer = document.querySelector("#stats");
const logsContainer = document.querySelector("#logs");
const usersContainer = document.querySelector("#users");
const teamsContainer = document.querySelector("#teams");
let currentUsers = [];
let currentOrganization = null;
const ACTION_LABELS = {
  BOOTSTRAP_ADMIN: "Administrador inicial criado",
  CHANGE_PASSWORD: "Senha alterada",
  CREATE_USER: "Usuário criado",
  LOGIN: "Login realizado",
  LOGIN_FAILED: "Tentativa de login recusada",
  LOGOUT: "Sessões encerradas",
  USER_BLOCKED: "Usuário bloqueado",
  USER_ROLE_CHANGED: "Perfil de acesso alterado",
  USER_UNBLOCKED: "Usuário desbloqueado",
};

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
    action.textContent = ACTION_LABELS[log.action] || log.action;
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
    option.value = value; option.textContent = {USER:"Usuário",MANAGER:"Gestor",IT_ADMIN:"Administrador"}[value]; option.selected = value === user.role; role.append(option);
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
  currentUsers = users;
  usersContainer.replaceChildren();
  users.forEach((user) => usersContainer.append(userNode(user)));
  if (currentOrganization) renderTeams();
}

function renderTeams() {
  teamsContainer.replaceChildren();
  if (!currentOrganization.teams.length) {
    const empty = document.createElement("p");
    empty.className = "table-empty";
    empty.textContent = "Nenhuma equipe criada. Crie uma para compartilhar documentos com um grupo específico.";
    teamsContainer.append(empty);
    return;
  }
  currentOrganization.teams.forEach((team) => {
    const card = document.createElement("article");
    card.className = "team-card";
    const heading = document.createElement("h3");
    heading.textContent = team.name;
    const description = document.createElement("p");
    description.textContent = `${team.member_ids.length} integrante${team.member_ids.length === 1 ? "" : "s"}`;
    const members = document.createElement("div");
    members.className = "team-members";
    currentUsers.forEach((user) => {
      const label = document.createElement("label");
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = user.id;
      checkbox.checked = team.member_ids.includes(user.id);
      const identity = document.createElement("span");
      identity.textContent = `${user.name} · ${user.email}`;
      label.append(checkbox, identity);
      members.append(label);
    });
    const save = document.createElement("button");
    save.className = "button secondary";
    save.textContent = "Salvar integrantes";
    save.addEventListener("click", async () => {
      save.disabled = true;
      const memberIds = [...members.querySelectorAll("input:checked")].map((input) => Number(input.value));
      try {
        await apiFetch(`/api/organizations/teams/${team.id}/members`, {
          method: "PUT",
          body: JSON.stringify({ user_ids: memberIds }),
        });
        await loadOrganization();
        showToast("Integrantes da equipe atualizados.", "success");
      } catch (reason) {
        showToast(reason.message, "error");
      } finally {
        save.disabled = false;
      }
    });
    card.append(heading, description, members, save);
    teamsContainer.append(card);
  });
}

async function loadOrganization() {
  currentOrganization = await apiFetch("/api/organizations/current");
  document.querySelector("#organization-name").value = currentOrganization.name;
  renderTeams();
}

let logPage=1;
async function loadLogs(){const result=await apiFetch("/api/admin/logs?page="+logPage+"&page_size=20");renderLogs(result.items);document.querySelector("#log-page").textContent="Página "+logPage;document.querySelector("#previous-logs").disabled=logPage===1;document.querySelector("#next-logs").disabled=logPage*20>=result.total;}
document.querySelector("#previous-logs").onclick=()=>{logPage--;loadLogs().catch(e=>showToast(e.message,"error"));};
document.querySelector("#next-logs").onclick=()=>{logPage++;loadLogs().catch(e=>showToast(e.message,"error"));};
document.querySelector("#new-user").onclick=()=>document.querySelector("#user-dialog").showModal();
document.querySelector("#cancel-user").onclick=()=>document.querySelector("#user-dialog").close();
document.querySelector("#user-form").onsubmit=async event=>{
  event.preventDefault();const form=event.target;const values=Object.fromEntries(new FormData(form));
  try{await apiFetch("/api/users",{method:"POST",body:JSON.stringify({...values,role:"USER"})});form.reset();document.querySelector("#user-dialog").close();await loadUsers();showToast("Usuário criado.","success");}
  catch(error){showToast(error.message,"error");}
};
document.querySelector("#organization-form").onsubmit = async (event) => {
  event.preventDefault();
  try {
    await apiFetch("/api/organizations/current", {
      method: "PATCH",
      body: JSON.stringify({ name: document.querySelector("#organization-name").value.trim() }),
    });
    await loadOrganization();
    showToast("Nome da empresa atualizado.", "success");
  } catch (reason) { showToast(reason.message, "error"); }
};
document.querySelector("#team-form").onsubmit = async (event) => {
  event.preventDefault();
  const input = document.querySelector("#team-name");
  try {
    await apiFetch("/api/organizations/teams", {
      method: "POST",
      body: JSON.stringify({ name: input.value.trim() }),
    });
    event.target.reset();
    await loadOrganization();
    showToast("Equipe criada.", "success");
  } catch (reason) { showToast(reason.message, "error"); }
};
async function loadQuality(){
 const result=await apiFetch("/api/admin/quality"),container=document.querySelector("#quality");container.replaceChildren();
 const grid=document.createElement("div");grid.className="quality-grid";
 for(const [label,value]of [["Respostas",result.sample_size],["Úteis",result.positive],["Precisam melhorar",result.negative],["Sem evidência",result.insufficient],["Tempo médio",result.average_seconds===null?"—":result.average_seconds+" s"]]){
  const card=document.createElement("p");card.textContent=label+": "+value;grid.append(card);
 }
 container.append(grid);
 for(const item of result.recent_feedback){const line=document.createElement("p");line.textContent="Resposta #"+item.message_id+" · "+item.reason;container.append(line);}
}
(async () => {
  try {
    const user = await loadCurrentUser();
    if (!["MANAGER", "IT_ADMIN"].includes(user.role)) { window.location.href = "/"; return; }
    const [stats, logs] = await Promise.all([apiFetch("/api/admin/stats"), apiFetch("/api/admin/logs?page_size=20")]);
    renderStats(stats); renderLogs(logs.items); await loadLogs(); await loadQuality();
    if (user.role === "IT_ADMIN") {
      document.querySelector("#users-panel").classList.remove("hidden");
      document.querySelector("#organization-panel").classList.remove("hidden");
      await loadUsers();
      await loadOrganization();
    }
  } catch (reason) { showToast(reason.message, "error"); }
})();
})();
