const form = document.querySelector("#login-form");
const error = document.querySelector("#login-error");

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
