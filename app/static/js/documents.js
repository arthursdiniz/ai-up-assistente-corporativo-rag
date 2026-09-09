(() => {
const { apiFetch, loadCurrentUser, showToast } = window.aiup;
const list = document.querySelector("#document-list");
const fileInput = document.querySelector("#file-input");
const progress = document.querySelector("#upload-progress");
const deleteDialog = document.querySelector("#delete-document-dialog");
const deleteCopy = document.querySelector("#delete-document-copy");
let pendingDelete = null;

function formatDate(value) {
  return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}

function rowNode(item) {
  const row = document.createElement("div");
  row.className = "table-row";
  const name = document.createElement("strong");
  name.textContent = item.original_filename;
  const type = document.createElement("span");
  type.textContent = item.file_type;
  const date = document.createElement("span");
  date.textContent = formatDate(item.created_at);
  const status = document.createElement("span");
  status.className = `badge ${item.status.toLowerCase()}`;
  status.textContent = item.status;
  const remove = document.createElement("button");
  remove.className = "icon-button danger";
  remove.textContent = "⌫";
  remove.title = "Excluir documento";
  remove.setAttribute("aria-label", `Excluir ${item.original_filename}`);
  remove.addEventListener("click", () => {
    pendingDelete = item;
    deleteCopy.textContent = `${item.original_filename} e seu índice de busca serão removidos. As conversas existentes serão preservadas.`;
    deleteDialog.showModal();
  });
  row.append(name, type, date, status, remove);
  return row;
}

async function loadDocuments() {
  const documents = await apiFetch("/api/documents");
  list.replaceChildren();
  if (!documents.length) {
    const empty = document.createElement("p");
    empty.className = "table-empty";
    empty.textContent = "Nenhum documento enviado ainda.";
    list.append(empty);
    return;
  }
  documents.forEach((item) => list.append(rowNode(item)));
}

fileInput.addEventListener("change", async () => {
  const file = fileInput.files[0];
  if (!file) return;
  const data = new FormData();
  data.append("file", file);
  progress.classList.remove("hidden");
  try {
    const result = await apiFetch("/api/documents", { method: "POST", body: data });
    showToast(result.status === "READY" ? "Documento pronto para consulta." : (result.status_message || "Processamento concluído."), result.status === "READY" ? "success" : "error");
    await loadDocuments();
  } catch (reason) { showToast(reason.message, "error"); }
  finally { progress.classList.add("hidden"); fileInput.value = ""; }
});

document.querySelector("#cancel-document-delete").addEventListener("click", () => {
  pendingDelete = null;
  deleteDialog.close();
});
document.querySelector("#confirm-document-delete").addEventListener("click", async () => {
  if (!pendingDelete) return;
  try {
    await apiFetch(`/api/documents/${pendingDelete.id}`, { method: "DELETE" });
    await loadDocuments();
    showToast("Documento excluído.", "success");
  } catch (reason) { showToast(reason.message, "error"); }
  finally { pendingDelete = null; deleteDialog.close(); }
});

(async () => { try { await loadCurrentUser(); await loadDocuments(); } catch (reason) { showToast(reason.message, "error"); } })();
})();
