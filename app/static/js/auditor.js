(() => {
  const {apiFetch, loadCurrentUser, showToast, downloadFile} = window.aiup;
  const $ = selector => document.querySelector(selector);
  const base = "/api/auditor";
  const limit = 20;
  const kinds = {POSSIBLE_CONTRADICTION:"Possível contradição", RELEVANT_CHANGE:"Alteração relevante",
    POSSIBLE_OUTDATED:"Possível desatualização", NEEDS_CLARIFICATION:"Necessidade de esclarecimento"};
  const states = {PENDING_REVIEW:"Pendente de revisão", CONFIRMED:"Confirmado",
    FALSE_POSITIVE:"Falso positivo", RESOLVED:"Resolvido"};
  const outcomes = {NO_INCONSISTENCY_IDENTIFIED:"Sem inconsistência identificada no escopo",
    ALERTS_FOUND:"Alertas disponíveis", INSUFFICIENT_EVIDENCE:"Regras insuficientes para comparação",
    PARTIAL:"Análise parcial. Confira os limites registrados."};
  const running = run => ["queued", "running"].includes(run.status);
  const dialog = $("#audit-detail");
  const documentSelect = $("#audit-document");
  const previousSelect = $("#audit-previous");
  const dateText = value => new Date(value).toLocaleString("pt-BR");
  const showError = error => showToast(error.message, "error");
  let documents = new Map(), runs = [], offset = 0, total = 0, activeAlert = null;
  let filters = new URLSearchParams(), listRequest = 0, versionRequest = 0, detailRequest = 0;

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  function options(select, choices) {
    for (const [value, label] of Object.entries(choices)) select.add(new Option(label, value));
  }

  function button(text, click) {
    const item = element("button", text, "button secondary");
    item.type = "button";
    item.addEventListener("click", click);
    return item;
  }

  function setBusy(form, busy) {
    form.querySelector("button[type=submit], button:not([type])").disabled = busy;
    form.setAttribute("aria-busy", String(busy));
  }

  async function loadVersions() {
    const request = ++versionRequest, selected = documentSelect.value;
    const doc = documents.get(Number(selected));
    previousSelect.replaceChildren(new Option("Relacionados e versão anterior", ""));
    previousSelect.disabled = true;
    if (!doc || doc.version < 2) return;
    const versions = await apiFetch(`${base}/documents/${doc.id}/versions`);
    if (request !== versionRequest) return;
    for (const version of versions) previousSelect.add(new Option(`Apenas versão ${version.version} → ${doc.version}`, version.id));
    previousSelect.disabled = !versions.length;
  }

  function renderRuns() {
    const items = [];
    for (const run of runs.slice(0, 6)) {
      const doc = documents.get(run.document_id);
      const label = doc ? `${doc.original_filename} · v${doc.version}` : `Documento ${run.document_id}`;
      const card = element("article", undefined, "auditor-row");
      const body = element("div");
      body.append(element("strong", label), element("p", run.error || outcomes[run.outcome] || run.stage));
      if (running(run)) {
        const progress = element("progress");
        progress.max = 100;
        progress.value = run.progress;
        progress.setAttribute("aria-label", `Progresso de ${label}`);
        body.append(progress);
        card.append(body, button("Cancelar", async () => {
          try { await apiFetch(`${base}/runs/${run.id}/cancel`, {method:"POST"}); await loadRuns(); }
          catch (error) { showError(error); }
        }));
      } else card.append(body);
      items.push(card);
    }
    $("#audit-runs").replaceChildren(...items);
  }

  async function loadRuns() {
    const previous = runs;
    runs = await apiFetch(`${base}/runs`);
    const changed = JSON.stringify(previous) !== JSON.stringify(runs);
    if (changed) renderRuns();
    if (changed && runs.some(run => run.status === "done" && !previous.some(old => old.id === run.id && old.status === "done"))) {
      await loadAlerts();
    }
  }

  function alertCard(alert) {
    const card = element("article", undefined, "auditor-row");
    const body = element("div");
    const badges = element("div", undefined, "card-actions");
    badges.append(element("span", kinds[alert.kind], "badge processing"), element("span", states[alert.state], "badge"));
    if (alert.historical) badges.append(element("span", "Histórico", "badge"));
    body.append(badges, element("h3", alert.subject), element("p", alert.documents.map(doc => `${doc.name} · v${doc.version}`).join(" / ")),
      element("small", dateText(alert.detected_at)));
    card.append(body, button("Ver evidências", () => openAlert(alert.id).catch(showError)));
    return card;
  }

  async function loadAlerts() {
    const request = ++listRequest;
    const query = new URLSearchParams(filters);
    query.set("offset", offset);
    query.set("limit", limit);
    const result = await apiFetch(`${base}/alerts?${query}`);
    if (request !== listRequest) return;
    total = result.total;
    $("#audit-count").textContent = total ? `${offset + 1}–${offset + result.items.length} de ${total} alertas` : "Nenhum alerta neste filtro.";
    $("#audit-alerts").replaceChildren(...result.items.map(alertCard));
    $("#audit-back").disabled = offset === 0;
    $("#audit-next").disabled = offset + limit >= total;
  }

  function renderDetail(alert) {
    activeAlert = alert.id;
    $("#audit-detail-title").textContent = alert.subject;
    const blocks = [element("p", `${kinds[alert.kind]} · ${states[alert.state]}${alert.historical ? " · Histórico" : ""}`),
      element("p", alert.explanation)];
    for (const rule of alert.evidence) {
      const ref = rule.evidence;
      const doc = alert.documents.find(item => item.id === ref.document_id);
      const place = ref.location || ref.sheet || (ref.page ? `Página ${ref.page}` : `Trecho ${ref.section_index + 1}`);
      const block = element("article", undefined, "extracted-section auditor-source");
      const link = element("a", "Abrir fonte original", "button secondary");
      const query = new URLSearchParams({id:ref.document_id});
      if (ref.page) query.set("page", ref.page);
      else query.set("section", ref.section_index);
      link.href = `/document.html?${query}`;
      link.target = "_blank";
      link.rel = "noopener";
      block.append(element("h3", `${doc?.name || "Documento"} · v${ref.version} · ${place}`), element("pre", ref.excerpt));
      if (rule.uncertainty.length) block.append(element("small", rule.uncertainty.join(" · ")));
      block.append(link);
      blocks.push(block);
    }
    $("#audit-evidence").replaceChildren(...blocks);
    $("#review-state").value = alert.state;
    $("#review-reason").value = "";
    $("#audit-decisions").replaceChildren(...(alert.reviews.length ? alert.reviews.map(review =>
      element("li", `${states[review.state]} · ${dateText(review.created_at)}. ${review.justification}`)) : [element("li", "Sem decisões registradas.")]));
    if (!dialog.open) dialog.showModal();
  }

  async function openAlert(id) {
    const request = ++detailRequest;
    const alert = await apiFetch(`${base}/alerts/${id}`);
    if (request === detailRequest) renderDetail(alert);
  }

  options($("#audit-kind"), kinds);
  options($("#audit-state"), states);
  options($("#review-state"), states);
  documentSelect.addEventListener("change", () => loadVersions().catch(showError));
  $("#run-audit").addEventListener("submit", async event => {
    event.preventDefault();
    setBusy(event.target, true);
    try {
      const data = {document_id:Number(documentSelect.value), previous_document_id:Number(previousSelect.value) || null};
      const run = await apiFetch(`${base}/runs`, {method:"POST", body:JSON.stringify(data)});
      showToast(run.status === "done" ? "Esse escopo já foi analisado." : "Auditoria na fila.");
      await loadRuns();
    } catch (error) { showError(error); }
    finally { setBusy(event.target, false); }
  });
  $("#audit-filters").addEventListener("submit", event => {
    event.preventDefault();
    filters = new URLSearchParams({q:$("#audit-search").value.trim(), include_historical:$("#audit-historical").checked});
    for (const name of ["kind", "state"]) {
      const value = $(`#audit-${name}`).value;
      if (value) filters.set(name, value);
    }
    offset = 0;
    loadAlerts().catch(showError);
  });
  $("#audit-historical").addEventListener("change", () => $("#audit-filters").requestSubmit());
  $("#audit-back").onclick = () => { offset = Math.max(0, offset - limit); loadAlerts().catch(showError); };
  $("#audit-next").onclick = () => { if (offset + limit < total) { offset += limit; loadAlerts().catch(showError); } };
  $("#export-audit").onclick = () => downloadFile(`${base}/alerts/export?${filters}`, "ai-up-auditor.json").catch(showError);
  $("#close-audit").onclick = () => dialog.close();
  dialog.addEventListener("close", () => { detailRequest++; activeAlert = null; $("#audit-evidence").replaceChildren(); });
  $("#audit-review").addEventListener("submit", async event => {
    event.preventDefault();
    const id = activeAlert;
    if (!id) return;
    setBusy(event.target, true);
    try {
      const data = {state:$("#review-state").value, justification:$("#review-reason").value};
      const updated = await apiFetch(`${base}/alerts/${id}/reviews`, {method:"POST", body:JSON.stringify(data)});
      if (activeAlert === id) renderDetail(updated);
      await loadAlerts();
      showToast("Decisão registrada.");
    } catch (error) {
      if (error.status === 404 && dialog.open) dialog.close();
      showError(error);
    } finally { setBusy(event.target, false); }
  });

  (async () => {
    await loadCurrentUser();
    const rows = await apiFetch("/api/documents?document_status=READY&archived=false&limit=500");
    documents = new Map(rows.map(doc => [doc.id, doc]));
    for (const doc of rows) documentSelect.add(new Option(`${doc.original_filename} · v${doc.version}`, doc.id));
    await Promise.all([loadRuns(), loadAlerts()]);
    let polling = false;
    setInterval(async () => {
      if (polling || document.hidden) return;
      polling = true;
      try { await loadRuns(); } catch (error) { if (error.status !== 401) console.warn("Falha ao atualizar auditorias."); }
      finally { polling = false; }
    }, 3500);
  })().catch(showError);
})();
