const token = decodeURIComponent(location.hash.slice(1));
const form = document.querySelector("#invite-form");
const title = document.querySelector("#invite-title");
const description = document.querySelector("#invite-description");
const error = document.querySelector("#invite-error");
const back = document.querySelector("#invite-back");

async function request(path, body) {
  const response = await fetch(path, {
    method: "POST",
    credentials: "same-origin",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.message || result.detail || "Não foi possível validar o convite.");
  return result;
}

async function inspect() {
  if (!token || token.length < 32) throw new Error("O link do convite está incompleto.");
  const invitation = await request("/api/auth/invitations/inspect", {token});
  const roles = {USER:"Usuário",MANAGER:"Gestor",IT_ADMIN:"Administrador"};
  title.textContent = `Entrar em ${invitation.organization_name}`;
  description.textContent = `Acesso como ${roles[invitation.role] || invitation.role}. O convite expira em ${new Date(invitation.expires_at).toLocaleString("pt-BR")}.`;
  document.querySelector("#invite-email").value = invitation.email;
  form.classList.remove("hidden");
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  error.textContent = "";
  const button = form.querySelector("button");
  button.disabled = true;
  button.textContent = "Criando…";
  try {
    const result = await request("/api/auth/invitations/accept", {
      token,
      name: document.querySelector("#invite-name").value,
      password: document.querySelector("#invite-password").value,
    });
    sessionStorage.setItem("ai_up_access_token", result.access_token);
    history.replaceState(null, "", "/invite.html");
    location.href = "/";
  } catch (reason) {
    error.textContent = reason.message;
  } finally {
    button.disabled = false;
    button.textContent = "Criar conta e entrar";
  }
});

inspect().catch(reason => {
  title.textContent = "Convite indisponível";
  description.textContent = reason.message;
  back.classList.remove("hidden");
});
