(() => {
const {apiFetch,loadCurrentUser,showToast,TOKEN_KEY}=window.aiup;
async function inspect() {
  const container=document.querySelector("#checks");container.textContent="Verificando serviços…";
  const result=await apiFetch("/api/health/details");container.replaceChildren();
  for(const check of result.checks){const card=document.createElement("article");card.className="document-card";const title=document.createElement("h2");title.textContent=check.name;const detail=document.createElement("p");detail.textContent=check.detail;const badge=document.createElement("span");badge.className="badge "+(check.status==="ok"?"ready":check.status==="error"?"error":"processing");badge.textContent={ok:"Disponível",error:"Requer atenção",warning:"Aviso"}[check.status];card.append(title,badge,detail);container.append(card);}
}
document.querySelector("#refresh-diagnostics").onclick=()=>inspect().catch(e=>showToast(e.message,"error"));
document.querySelector("#password-form").onsubmit=async e=>{
  e.preventDefault();const current=document.querySelector("#current-password"),password=document.querySelector("#new-password"),repeat=document.querySelector("#repeat-password");
  if(password.value!==repeat.value){showToast("As novas senhas não coincidem.","error");return;}
  try{await apiFetch("/api/auth/password",{method:"POST",body:JSON.stringify({current_password:current.value,new_password:password.value})});localStorage.removeItem(TOKEN_KEY);location.href="/login.html";}
  catch(error){showToast(error.message,"error");}
};
(async()=>{try{await loadCurrentUser();await inspect();}catch(e){showToast(e.message,"error");}})();
})();
