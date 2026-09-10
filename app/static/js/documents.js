(() => {
const {apiFetch,loadCurrentUser,showToast} = window.aiup;
const $ = selector => document.querySelector(selector);
let items = [], offset = 0, timer, searchTimer, selected, revision = 0;
const node = (tag, text, cls="") => { const n=document.createElement(tag); n.textContent=text; n.className=cls; return n; };
const busy = item => ["UPLOADED","PROCESSING"].includes(item.status);
function action(text, callback) { const n=node("button",text,"button secondary"); n.onclick=()=>Promise.resolve().then(callback).catch(e=>showToast(e.message,"error")); return n; }
function render() {
  $("#document-list").replaceChildren();
  const status=$("#status-filter").value, category=$("#category-filter").value.toLocaleLowerCase(), archive=$("#archive-filter").value;
  const filtered=items.filter(item=>(!status||item.status===status)&&item.category.toLocaleLowerCase().includes(category)&&(!archive||item.archived===(archive==="archived")));
  if (!filtered.length) $("#document-list").append(node("p","Nenhum documento nesta seleção. Envie arquivos ou ajuste os filtros.","table-empty"));
  filtered.forEach(item=>{
    const card=node("article","","document-card");
    const title=node("a",item.original_filename,"document-title"); title.href="/document.html?id="+item.id;
    card.append(title,node("small",item.file_type+" · "+(item.size_bytes/1024).toFixed(1)+" KB · "+item.category+" · v"+item.version+(item.archived?" · arquivada":"")));
    card.append(node("span",({READY:"Pronto",ERROR:"Erro",PROCESSING:"Processando",UPLOADED:"Na fila"})[item.status],"badge "+item.status.toLowerCase()));
    if (busy(item)) { const p=node("progress",""); p.max=100;p.value=item.progress;p.setAttribute("aria-label","Progresso de "+item.original_filename);card.append(p,node("small",item.processing_stage+" · "+item.progress+"%")); }
    else card.append(node("small",item.chunk_count+" trechos · "+new Date(item.created_at).toLocaleString("pt-BR")));
    if (item.status_message) card.append(node("p",item.status_message,"error-text"));
    for (const warning of item.warnings) card.append(node("p",warning,"warning-text"));
    if (item.needs_reindex && !busy(item)) card.append(node("p","Índice anterior: reprocessar melhora a busca.","warning-text"));
    const controls=node("div","","card-actions");
    if (item.status==="READY") { const ask=node("a","Consultar com IA","button primary"); ask.href="/?document="+item.id;controls.append(ask); }
    controls.append(action("Categoria",()=>{selected=item;$("#category-input").value=item.category;$("#category-dialog").showModal();}));
    if (!busy(item)) {
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
$("#category-form").onsubmit=async e=>{e.preventDefault();try{await apiFetch("/api/documents/"+selected.id,{method:"PATCH",body:JSON.stringify({category:$("#category-input").value.trim()})});$("#category-dialog").close();await load();}catch(error){showToast(error.message,"error");}};
document.querySelectorAll("[data-close]").forEach(n=>n.onclick=()=>document.getElementById(n.dataset.close).close());
(async()=>{try{await loadCurrentUser();await load();}catch(e){showToast(e.message,"error");}})();
})();
