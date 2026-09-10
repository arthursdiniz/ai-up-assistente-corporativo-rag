(() => {
const {apiFetch,loadCurrentUser,showToast} = window.aiup;
const $ = selector => document.querySelector(selector);
let items = [], offset = 0, timer, searchTimer, selected, revision = 0;
let currentUser = null, organization = null;
const node = (tag, text, cls="") => { const n=document.createElement(tag); n.textContent=text; n.className=cls; return n; };
const busy = item => ["UPLOADED","PROCESSING"].includes(item.status);
function action(text, callback) { const n=node("button",text,"button secondary"); n.onclick=()=>Promise.resolve().then(callback).catch(e=>showToast(e.message,"error")); return n; }
function scopeValue(item) { return item.visibility === "TEAM" ? `TEAM:${item.team_id}` : item.visibility; }
function scopePayload(value) {
  if (value.startsWith("TEAM:")) return {visibility:"TEAM",team_id:Number(value.split(":")[1])};
  return {visibility:value,team_id:null};
}
function teamName(teamId) { return organization?.teams.find(team=>team.id===teamId)?.name || "Equipe"; }
function sharingText(item) {
  if (item.visibility === "ORGANIZATION") return "Compartilhado com a empresa";
  if (item.visibility === "TEAM") return `Compartilhado com ${teamName(item.team_id)}`;
  return "Privado";
}
function populateScopeSelect(select) {
  const current = select.value;
  select.replaceChildren();
  [["PRIVATE","Somente comigo"],["ORGANIZATION","Toda a empresa"]].forEach(([value,label])=>{
    const option=node("option",label);option.value=value;select.append(option);
  });
  const allowedTeams=(organization?.teams||[]).filter(team=>currentUser.role==="IT_ADMIN"||currentUser.team_ids.includes(team.id));
  allowedTeams.forEach(team=>{const option=node("option",`Equipe: ${team.name}`);option.value=`TEAM:${team.id}`;select.append(option);});
  if ([...select.options].some(option=>option.value===current)) select.value=current;
}
function render() {
  $("#document-list").replaceChildren();
  const status=$("#status-filter").value, category=$("#category-filter").value.toLocaleLowerCase(), archive=$("#archive-filter").value;
  const filtered=items.filter(item=>(!status||item.status===status)&&item.category.toLocaleLowerCase().includes(category)&&(!archive||item.archived===(archive==="archived")));
  if (!filtered.length) $("#document-list").append(node("p","Nenhum documento nesta seleção. Envie arquivos ou ajuste os filtros.","table-empty"));
  filtered.forEach(item=>{
    const card=node("article","","document-card");
    const title=node("a",item.original_filename,"document-title"); title.href="/document.html?id="+item.id;
    card.append(title,node("small",item.file_type+" · "+(item.size_bytes/1024).toFixed(1)+" KB · "+item.category+" · v"+item.version+(item.archived?" · arquivada":"")));
    card.append(node("small",sharingText(item)+(item.is_owner?" · enviado por você":" · compartilhado com você"),"sharing-label"));
    card.append(node("span",({READY:"Pronto",ERROR:"Erro",PROCESSING:"Processando",UPLOADED:"Na fila"})[item.status],"badge "+item.status.toLowerCase()));
    if (busy(item)) { const p=node("progress",""); p.max=100;p.value=item.progress;p.setAttribute("aria-label","Progresso de "+item.original_filename);card.append(p,node("small",item.processing_stage+" · "+item.progress+"%")); }
    else card.append(node("small",item.chunk_count+" trechos · "+new Date(item.created_at).toLocaleString("pt-BR")));
    if (item.status_message) card.append(node("p",item.status_message,"error-text"));
    for (const warning of item.warnings) card.append(node("p",warning,"warning-text"));
    if (item.needs_reindex && !busy(item)) card.append(node("p","Índice anterior: reprocessar melhora a busca.","warning-text"));
    const controls=node("div","","card-actions");
    if (item.status==="READY") { const ask=node("a","Consultar com IA","button primary"); ask.href="/?document="+item.id;controls.append(ask); }
    if (item.is_owner) controls.append(action("Organizar",()=>{selected=item;$("#category-input").value=item.category;populateScopeSelect($("#document-scope"));$("#document-scope").value=scopeValue(item);$("#category-dialog").showModal();}));
    if (item.is_owner && !busy(item)) {
      controls.append(action(item.archived?"Reativar":"Arquivar",async()=>{await apiFetch("/api/documents/"+item.id,{method:"PATCH",body:JSON.stringify({archived:!item.archived})});await load();}));
      controls.append(action("Reprocessar",async()=>{await apiFetch("/api/documents/"+item.id+"/reprocess",{method:"POST"});await load();}));
      controls.append(action("Excluir",()=>{selected=item;$("#delete-document-copy").textContent=item.original_filename+": o arquivo e o índice serão excluídos. As conversas e os trechos já citados serão preservados.";$("#delete-document-dialog").showModal();}));
    }
    card.append(controls);$("#document-list").append(card);
  });
}
async function load(more=false) {
  const currentRevision=++revision, start=more?offset:0, limit=more?50:Math.max(50,offset);
  const filters=new URLSearchParams({q:$("#document-search").value,category:$("#category-filter").value,offset:start,limit:Math.min(limit,500)});
  if($("#status-filter").value)filters.set("document_status",$("#status-filter").value);
  if($("#archive-filter").value)filters.set("archived",String($("#archive-filter").value==="archived"));
  const results=await apiFetch("/api/documents?"+filters);
  if (currentRevision!==revision) return;
  items=more?items.concat(results):results;offset=items.length;render();
  $("#more-documents").classList.toggle("hidden",results.length<Math.min(limit,500));
  clearTimeout(timer);
  if (items.some(busy)) timer=setTimeout(()=>load().catch(e=>showToast(e.message,"error")),2000);
}
async function upload(files) {
  $("#upload-button").disabled=true;
  for (let i=0;i<files.length;i++) {
    $("#upload-progress").textContent="Enviando "+(i+1)+"/"+files.length+": "+files[i].name;
    const data=new FormData();data.append("file",files[i]);
    const sharing=scopePayload($("#upload-scope").value);
    data.append("visibility",sharing.visibility);
    if (sharing.team_id !== null) data.append("team_id",String(sharing.team_id));
    try {await apiFetch("/api/documents",{method:"POST",body:data,timeoutMs:60000});}
    catch(e){showToast(files[i].name+": "+e.message,"error");}
  }
  $("#upload-progress").textContent="Envio concluído. A preparação aparece em cada arquivo.";
  $("#upload-button").disabled=false;$("#file-input").value="";await load();
}
$("#upload-button").onclick=()=>$("#file-input").click();
$("#file-input").onchange=e=>upload([...e.target.files]).catch(e=>showToast(e.message,"error"));
const drop=$("#drop-zone");
["dragenter","dragover"].forEach(type=>drop.addEventListener(type,e=>{e.preventDefault();drop.classList.add("drag-over");}));
drop.addEventListener("dragleave",()=>drop.classList.remove("drag-over"));
drop.addEventListener("drop",e=>{e.preventDefault();drop.classList.remove("drag-over");upload([...e.dataTransfer.files]).catch(e=>showToast(e.message,"error"));});
$("#document-search").oninput=()=>{clearTimeout(searchTimer);offset=0;searchTimer=setTimeout(()=>load().catch(e=>showToast(e.message,"error")),250);};
["#status-filter","#category-filter","#archive-filter"].forEach(id=>$(id).addEventListener("input",()=>{clearTimeout(searchTimer);offset=0;searchTimer=setTimeout(()=>load().catch(e=>showToast(e.message,"error")),250);}));
$("#more-documents").onclick=()=>load(true).catch(e=>showToast(e.message,"error"));
$("#confirm-document-delete").onclick=async()=>{try{await apiFetch("/api/documents/"+selected.id,{method:"DELETE"});$("#delete-document-dialog").close();await load();showToast("Documento excluído. A recuperação exige um backup anterior.","success");}catch(e){showToast(e.message,"error");}};
$("#category-form").onsubmit=async e=>{e.preventDefault();try{await apiFetch("/api/documents/"+selected.id,{method:"PATCH",body:JSON.stringify({category:$("#category-input").value.trim(),...scopePayload($("#document-scope").value)})});$("#category-dialog").close();await load();showToast("Documento atualizado.","success");}catch(error){showToast(error.message,"error");}};
document.querySelectorAll("[data-close]").forEach(n=>n.onclick=()=>document.getElementById(n.dataset.close).close());
(async()=>{try{currentUser=await loadCurrentUser();organization=await apiFetch("/api/organizations/current");populateScopeSelect($("#upload-scope"));populateScopeSelect($("#document-scope"));await load();}catch(e){showToast(e.message,"error");}})();
})();
