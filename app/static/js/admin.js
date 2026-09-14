(() => {
const { apiFetch, loadCurrentUser, showToast } = window.aiup;
const statsContainer = document.querySelector("#stats");
const logsContainer = document.querySelector("#logs");
const usersContainer = document.querySelector("#users");
const teamsContainer = document.querySelector("#teams");
const invitationsContainer = document.querySelector("#invitations");
let currentUsers = [];
let currentOrganization = null;
let currentAdmin = null;
let selectedUser = null;
const ACTION_LABELS = {
  BOOTSTRAP_ADMIN: "Administrador inicial criado",
  CHANGE_PASSWORD: "Senha alterada",
  ACCEPT_INVITATION: "Convite aceito",
  CREATE_INVITATION: "Convite criado",
  DELETE_TEAM: "Equipe excluída",
  REVOKE_INVITATION: "Convite revogado",
  TRANSFER_DOCUMENTS: "Documentos transferidos",
  UPDATE_TEAM: "Equipe renomeada",
  UPDATE_TEAM_MEMBERS: "Integrantes atualizados",
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
  active.disabled = user.id === currentAdmin?.id;
  active.addEventListener("click", async () => {
    if (user.active) {
      selectedUser = user;
      const target = document.querySelector("#transfer-target");
      target.replaceChildren();
      currentUsers.filter(item=>item.active&&item.id!==user.id).forEach(item=>{
        const option=document.createElement("option");option.value=item.id;option.textContent=`${item.name} · ${item.email}`;target.append(option);
      });
      if (!target.options.length) { showToast("Não existe outro usuário ativo para receber os documentos.", "error"); return; }
      document.querySelector("#transfer-copy").textContent=`Os documentos de ${user.name} passarão para o usuário escolhido antes do bloqueio.`;
      document.querySelector("#transfer-dialog").showModal();
      return;
    }
    try { await apiFetch(`/api/users/${user.id}`, { method: "PATCH", body: JSON.stringify({ active: true }) }); await loadUsers(); }
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
    const nameRow = document.createElement("div");
    nameRow.className = "team-card-name";
    const nameInput = document.createElement("input");
    nameInput.value = team.name;
    nameInput.maxLength = 120;
    nameInput.setAttribute("aria-label", `Nome da equipe ${team.name}`);
    const saveName = document.createElement("button");
    saveName.className = "button secondary";
    saveName.textContent = "Renomear";
    saveName.addEventListener("click", async()=>{
      try { await apiFetch(`/api/organizations/teams/${team.id}`,{method:"PATCH",body:JSON.stringify({name:nameInput.value.trim()})});await loadOrganization();await loadInvitations();showToast("Equipe renomeada.","success"); }
      catch(reason){showToast(reason.message,"error");nameInput.value=team.name;}
    });
    nameRow.append(nameInput,saveName);
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
    const remove = document.createElement("button");
    remove.className = "button danger";
    remove.textContent = "Excluir equipe";
    remove.addEventListener("click",async()=>{
      if(!confirm(`Excluir a equipe ${team.name}? Os documentos compartilhados com ela ficarão privados.`))return;
      try{await apiFetch(`/api/organizations/teams/${team.id}`,{method:"DELETE"});await loadOrganization();await loadInvitations();showToast("Equipe excluída; documentos preservados como privados.","success");}
      catch(reason){showToast(reason.message,"error");}
    });
    const actions=document.createElement("div");actions.className="card-actions";actions.append(save,remove);
    card.append(nameRow, description, members, actions);
    teamsContainer.append(card);
  });
}

async function loadOrganization() {
  currentOrganization = await apiFetch("/api/organizations/current");
  document.querySelector("#organization-name").value = currentOrganization.name;
  renderTeams();
}

function renderInvitations(invitations) {
  invitationsContainer.replaceChildren();
  if (!invitations.length) {
    const empty=document.createElement("p");empty.className="table-empty";empty.textContent="Nenhum convite criado.";invitationsContainer.append(empty);return;
  }
  const statuses={PENDING:"Pendente",ACCEPTED:"Aceito",REVOKED:"Revogado",EXPIRED:"Expirado"};
  const roles={USER:"Usuário",MANAGER:"Gestor",IT_ADMIN:"Administrador"};
  invitations.forEach(invitation=>{
    const row=document.createElement("div");row.className="log-row invitation-row";
    const content=document.createElement("div");
    const email=document.createElement("strong");email.textContent=invitation.email;
    const teamNames=invitation.team_ids.map(id=>currentOrganization.teams.find(team=>team.id===id)?.name).filter(Boolean);
    const meta=document.createElement("small");meta.textContent=`${roles[invitation.role]} · ${statuses[invitation.status]}${teamNames.length?` · ${teamNames.join(", ")}`:""} · expira ${new Date(invitation.expires_at).toLocaleString("pt-BR")}`;
    content.append(email,meta);row.append(content);
    if(invitation.status==="PENDING"){
      const revoke=document.createElement("button");revoke.className="text-button";revoke.textContent="Revogar";
      revoke.onclick=async()=>{try{await apiFetch(`/api/organizations/invitations/${invitation.id}`,{method:"DELETE"});await loadInvitations();showToast("Convite revogado.","success");}catch(reason){showToast(reason.message,"error");}};
      row.append(revoke);
    }
    invitationsContainer.append(row);
  });
}

async function loadInvitations(){renderInvitations(await apiFetch("/api/organizations/invitations"));}

function populateInvitationTeams(){
  const container=document.querySelector("#invitation-teams");container.replaceChildren();
  if(!currentOrganization.teams.length){const empty=document.createElement("small");empty.textContent="Nenhuma equipe disponível.";container.append(empty);return;}
  currentOrganization.teams.forEach(team=>{const label=document.createElement("label"),checkbox=document.createElement("input");checkbox.type="checkbox";checkbox.value=team.id;label.append(checkbox,document.createTextNode(team.name));container.append(label);});
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
document.querySelector("#new-invitation").onclick=()=>{populateInvitationTeams();document.querySelector("#invitation-dialog").showModal();};
document.querySelector("#invitation-form").onsubmit=async event=>{
  event.preventDefault();const form=event.target;
  const teamIds=[...document.querySelectorAll("#invitation-teams input:checked")].map(input=>Number(input.value));
  try{
    const result=await apiFetch("/api/organizations/invitations",{method:"POST",body:JSON.stringify({email:form.email.value,role:form.role.value,team_ids:teamIds})});
    form.reset();document.querySelector("#invitation-dialog").close();
    document.querySelector("#invitation-link").value=location.origin+result.accept_path;
    document.querySelector("#invitation-link-dialog").showModal();await loadInvitations();
  }catch(reason){showToast(reason.message,"error");}
};
document.querySelector("#copy-invitation-link").onclick=async()=>{
  const input=document.querySelector("#invitation-link");
  try{await navigator.clipboard.writeText(input.value);showToast("Link copiado.","success");}
  catch(_){input.select();document.execCommand("copy");showToast("Link copiado.","success");}
};
document.querySelector("#transfer-form").onsubmit=async event=>{
  event.preventDefault();
  try{await apiFetch(`/api/users/${selectedUser.id}/deactivate`,{method:"POST",body:JSON.stringify({transfer_document_owner_id:Number(document.querySelector("#transfer-target").value)})});document.querySelector("#transfer-dialog").close();await loadUsers();showToast("Documentos transferidos e conta desativada.","success");}
  catch(reason){showToast(reason.message,"error");}
};
document.querySelectorAll("[data-close]").forEach(button=>button.onclick=()=>document.getElementById(button.dataset.close).close());
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
    currentAdmin = user;
    if (!["MANAGER", "IT_ADMIN"].includes(user.role)) { window.location.href = "/"; return; }
    const [stats, logs] = await Promise.all([apiFetch("/api/admin/stats"), apiFetch("/api/admin/logs?page_size=20")]);
    renderStats(stats); renderLogs(logs.items); await loadLogs(); await loadQuality();
    if (user.role === "IT_ADMIN") {
      document.querySelector("#users-panel").classList.remove("hidden");
      document.querySelector("#organization-panel").classList.remove("hidden");
      document.querySelector("#invitation-panel").classList.remove("hidden");
      await loadUsers();
      await loadOrganization();
      await loadInvitations();
    }
  } catch (reason) { showToast(reason.message, "error"); }
})();
})();
