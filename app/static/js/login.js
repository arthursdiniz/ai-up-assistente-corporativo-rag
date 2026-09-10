const form = document.querySelector("#login-form");
const error = document.querySelector("#login-error");
const bootstrapEntry = document.querySelector("#bootstrap-entry");
const bootstrapMessage = document.querySelector("#bootstrap-message");
const bootstrapOpen = document.querySelector("#bootstrap-open");
const bootstrapDialog = document.querySelector("#bootstrap-dialog");
const bootstrapForm = document.querySelector("#bootstrap-form");
const bootstrapError = document.querySelector("#bootstrap-error");
const bootstrapTokenField = document.querySelector("#bootstrap-token-field");

localStorage.removeItem("ai_up_access_token");
if (sessionStorage.getItem("ai_up_access_token")) window.location.href = "/";

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  error.textContent = "";
  const button = form.querySelector("button");
  button.disabled = true;
  button.textContent = "Entrando…";
  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: form.email.value, password: form.password.value }),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "Não foi possível entrar.");
    sessionStorage.setItem("ai_up_access_token", body.access_token);
    window.location.href = "/";
  } catch (reason) {
    error.textContent = reason.message;
  } finally {
    button.disabled = false;
    button.textContent = "Entrar";
  }
});

async function checkBootstrap() {
  try {
    const response = await fetch("/api/auth/bootstrap", { credentials: "same-origin" });
    if (!response.ok) return;
    const state = await response.json();
    if (!state.required) return;
    bootstrapEntry.classList.remove("hidden");
    bootstrapTokenField.classList.toggle("hidden", !state.token_required);
    if (!state.available) {
      bootstrapMessage.textContent = "A instalação está vazia. Defina BOOTSTRAP_TOKEN no servidor para liberar a configuração inicial.";
      bootstrapOpen.classList.add("hidden");
    }
  } catch (_) {
    // O login continua disponível mesmo se o diagnóstico inicial falhar.
  }
}

bootstrapOpen.addEventListener("click", () => {
  bootstrapError.textContent = "";
  bootstrapDialog.showModal();
  bootstrapForm.elements.namedItem("name").focus();
});

document.querySelector("#bootstrap-cancel").addEventListener("click", () => bootstrapDialog.close());

bootstrapForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  bootstrapError.textContent = "";
  const button = bootstrapForm.querySelector("button[type='submit']");
  button.disabled = true;
  button.textContent = "Criando…";
  const headers = { "Content-Type": "application/json" };
  const configuredToken = bootstrapForm.elements.namedItem("bootstrap_token").value.trim();
  if (configuredToken) headers["X-Bootstrap-Token"] = configuredToken;
  try {
    const response = await fetch("/api/auth/register", {
      method: "POST",
      credentials: "same-origin",
      headers,
      body: JSON.stringify({
        name: bootstrapForm.elements.namedItem("name").value,
        email: bootstrapForm.elements.namedItem("email").value,
        password: bootstrapForm.elements.namedItem("password").value,
      }),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "Não foi possível criar o administrador.");
    sessionStorage.setItem("ai_up_access_token", body.access_token);
    window.location.href = "/";
  } catch (reason) {
    bootstrapError.textContent = reason.message;
  } finally {
    button.disabled = false;
    button.textContent = "Criar e entrar";
  }
});

checkBootstrap();
