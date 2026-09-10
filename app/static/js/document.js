(() => {
const {apiFetch,apiRequest,loadCurrentUser,showToast,downloadFile}=window.aiup;
const params=new URLSearchParams(location.search), id=Number(params.get("id"));
let page=Number(params.get("page"))||null, offset=0, file, objectUrl, totalPages=1;
const $=s=>document.querySelector(s);
async function load() {
  const result=await apiFetch("/api/documents/"+id+"/preview?offset="+offset+(page?"&page="+page:""));
  file=result.document;$("#document-title").textContent=file.original_filename;
  $("#document-meta").textContent="Versão "+file.version+" · "+file.category+(page?" · página "+page:"");
  $("#ask-document").href="/?document="+id;
  for(const section of result.sections) {
    const article=document.createElement("article");article.className="extracted-section";
    const title=document.createElement("h3");title.textContent=section.location||section.sheet||(section.page?"Página "+section.page:"Trecho "+(offset+1));
    const text=document.createElement("pre");text.textContent=section.text;article.append(title,text);$("#sections").append(article);offset++;
  }
  $("#more-sections").classList.toggle("hidden",offset>=result.total);
  if (!offset) $("#sections").textContent="Texto ainda indisponível. Confira o processamento na biblioteca.";
}
async function renderOriginal(){
  const response=await apiRequest("/api/documents/"+id+(file.file_type==="PDF"?"/pages/"+page:"/file"),{timeoutMs:60000});
  const blob=await response.blob();
  if(objectUrl)URL.revokeObjectURL(objectUrl);objectUrl=URL.createObjectURL(blob);
  const view=document.createElement("img");view.className="original-preview";view.alt=file.original_filename+(page?" — página "+page:"");view.src=objectUrl;
  $("#original-preview").replaceChildren();
  if(file.file_type==="PDF"){
    const nav=document.createElement("div");nav.className="card-actions";
    const previous=document.createElement("button"),next=document.createElement("button"),label=document.createElement("span");
    previous.textContent="← Página anterior";next.textContent="Próxima página →";label.textContent="Página "+page+" de "+totalPages;
    previous.className=next.className="button secondary";previous.disabled=page<=1;next.disabled=page>=totalPages;
    const change=async delta=>{page+=delta;history.replaceState(null,"","/document.html?id="+id+"&page="+page);offset=0;$("#sections").replaceChildren();await load();await renderOriginal();};
    previous.onclick=()=>change(-1).catch(e=>showToast(e.message,"error"));next.onclick=()=>change(1).catch(e=>showToast(e.message,"error"));
    nav.append(previous,label,next);$("#original-preview").append(nav);
  }
  $("#original-preview").append(view);
}
(async()=>{try{
  await loadCurrentUser();
  const initial=await apiFetch("/api/documents/"+id);file=initial;
  if(file.file_type==="PDF"){
    const overview=await apiFetch("/api/documents/"+id+"/preview?limit=1");
    totalPages=overview.total;page=page||1;
  }
  await load();
  if(["PDF","IMAGE"].includes(file.file_type))await renderOriginal();
}catch(e){showToast(e.message,"error");}})();
$("#more-sections").onclick=()=>load().catch(e=>showToast(e.message,"error"));
$("#download-original").onclick=()=>{if(file)downloadFile("/api/documents/"+id+"/file",file.original_filename).catch(e=>showToast(e.message,"error"));};
window.addEventListener("beforeunload",()=>{if(objectUrl)URL.revokeObjectURL(objectUrl);});
})();
