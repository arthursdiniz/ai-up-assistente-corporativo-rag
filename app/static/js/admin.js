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
  usersContainer.replaceChildren();
  users.forEach((user) => usersContainer.append(userNode(user)));
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
    if (user.role === "IT_ADMIN") { document.querySelector("#users-panel").classList.remove("hidden"); await loadUsers(); }
  } catch (reason) { showToast(reason.message, "error"); }
})();
})();
