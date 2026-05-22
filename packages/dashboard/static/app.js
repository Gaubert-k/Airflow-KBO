/**
 * Dashboard MS-09 — onglets + registre entreprises.
 */

const REFRESH_MS = 15000;
const STATE_LABELS = {
  NEW: "Nouveau",
  QUEUED_SCRAPE: "File scrape",
  SCRAPING: "Scrape en cours",
  RAW_STORED: "Brut stocké",
  QUEUED_PARSE: "File parse",
  PARSING: "Parse en cours",
  STRUCTURED: "Structuré",
  FAILED_SCRAPE: "Échec scrape",
  FAILED_PARSE: "Échec parse",
  FAILED_VALIDATE: "Échec validation",
};

let activeTab = "enterprises";
let entPage = 1;
const entPageSize = 50;
let entSearchTimer = null;
let refreshTimer = null;
/** BCE cochés pour DAG scrape (conservés entre pages tant que la session est ouverte). */
const selectedBce = new Set();

const SCRAPE_DAG_ID = "02_scrape_by_source";

function authHeaders() {
  const token = window.DASHBOARD_TOKEN || "";
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function apiErrorMessage(data, status) {
  const d = data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x.msg || JSON.stringify(x)).join("; ");
  return `Erreur HTTP ${status}`;
}

async function fetchJson(path) {
  const res = await fetch(path, { headers: authHeaders() });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data, res.status));
  return data;
}

function fmtDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("fr-BE");
  } catch {
    return iso;
  }
}

function labelState(state) {
  return STATE_LABELS[state] || state;
}

function showToast(msg, type = "info") {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = `toast toast-${type}`;
  el.hidden = false;
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => {
    el.hidden = true;
  }, 5000);
}

/* ——— Onglets ——— */
function switchTab(tabId) {
  activeTab = tabId;
  document.querySelectorAll(".tab").forEach((btn) => {
    const on = btn.dataset.tab === tabId;
    btn.classList.toggle("active", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    const on = panel.id === `panel-${tabId}`;
    panel.classList.toggle("active", on);
    panel.hidden = !on;
  });
  refreshActiveTab();
}

function setupTabs() {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });
}

/* ——— Vue globale ——— */
function renderKpis(snap) {
  const perf = snap.performance || {};
  const items = [
    { label: "En cours", value: (snap.in_flight ?? 0).toLocaleString("fr-BE"), cls: "" },
    { label: "En attente", value: (snap.pending ?? 0).toLocaleString("fr-BE"), cls: "warn" },
    { label: "Structurées", value: (snap.fully_structured ?? 0).toLocaleString("fr-BE"), cls: "ok" },
    { label: "Découvertes", value: snap.discovered_total ?? 0, cls: "" },
    { label: "Err. scrape", value: snap.scrape_errors ?? 0, cls: snap.scrape_errors ? "err" : "" },
    { label: "Err. parse", value: snap.parse_errors ?? 0, cls: snap.parse_errors ? "err" : "" },
    {
      label: "Taux scrape",
      value: perf.scrape_success_rate_pct != null ? `${perf.scrape_success_rate_pct}%` : "—",
      cls: "",
    },
  ];
  document.getElementById("kpi-grid").innerHTML = items
    .map(
      (k) =>
        `<article class="kpi ${k.cls}"><div class="label">${k.label}</div><div class="value">${k.value}</div></article>`
    )
    .join("");
}

function renderQueue(queue) {
  const entries = Object.entries(queue || {}).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, v]) => v));
  const chart = document.getElementById("queue-chart");
  if (!entries.length) {
    chart.innerHTML = '<p class="empty-msg">Aucune donnée.</p>';
  } else {
    chart.innerHTML = entries
      .map(([state, count]) => {
        const n = Number(count).toLocaleString("fr-BE");
        return `<div class="bar-row">
          <span class="bar-label">${escapeHtml(labelState(state))}</span>
          <div class="bar-track"><div class="bar-fill" style="width:${(100 * count) / max}%"></div></div>
          <span class="bar-count">${n}</span>
        </div>`;
      })
      .join("");
  }
  document.querySelector("#queue-table tbody").innerHTML = entries
    .map(
      ([state, count]) =>
        `<tr><td>${escapeHtml(labelState(state))}</td><td>${Number(count).toLocaleString("fr-BE")}</td></tr>`
    )
    .join("");
}

function renderPerf(snap) {
  const p = snap.performance || {};
  document.getElementById("perf-list").innerHTML = `
    <li><span>Tentatives scrape</span><strong>${p.scrape_attempts ?? 0}</strong></li>
    <li><span>Succès scrape</span><strong>${p.scrape_successes ?? 0}</strong></li>
    <li><span>Échecs scrape</span><strong>${p.scrape_failures ?? 0}</strong></li>
    <li><span>Échecs proxy</span><strong>${p.proxy_failures ?? 0}</strong></li>
    <li><span>Parse OK</span><strong>${p.parse_successes ?? 0}</strong></li>
    <li><span>Parse KO</span><strong>${p.parse_failures ?? 0}</strong></li>
  `;
  document.getElementById("acq-metrics").textContent = JSON.stringify(
    snap.acquisition_metrics || {},
    null,
    2
  );
}

function renderDiscoveries(rows) {
  const tbody = document.querySelector("#discoveries-table tbody");
  if (!rows?.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty-msg">Aucune découverte.</td></tr>';
    return;
  }
  tbody.innerHTML = rows
    .map(
      (d) => `<tr>
        <td class="mono">${escapeHtml(d.source_enterprise_number)}</td>
        <td class="mono">${escapeHtml(d.discovered_enterprise_number)}</td>
        <td>${escapeHtml(d.reason_code || d.reason || "")}</td>
        <td>${fmtDate(d.discovered_at)}</td>
      </tr>`
    )
    .join("");
}

function renderEvents(rows) {
  const tbody = document.querySelector("#events-table tbody");
  if (!rows?.length) {
    tbody.innerHTML = '<tr><td colspan="3" class="empty-msg">Aucun événement.</td></tr>';
    return;
  }
  tbody.innerHTML = rows
    .map((e) => {
      const detail = JSON.stringify(e.payload || {});
      const short = detail.length > 60 ? detail.slice(0, 57) + "…" : detail;
      return `<tr>
        <td><code>${escapeHtml(e.event_type)}</code></td>
        <td title="${escapeHtml(detail)}">${escapeHtml(short)}</td>
        <td>${fmtDate(e.created_at)}</td>
      </tr>`;
    })
    .join("");
}

function fmtPct(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return `${Number(value).toLocaleString("fr-BE", { maximumFractionDigits: 1 })} %`;
}

function renderAnalytics(data) {
  const hint = document.getElementById("analytics-hint");
  const help = document.getElementById("analytics-help");
  const kpis = document.getElementById("analytics-kpis");

  if (data.empty) {
    hint.textContent = "Aucune donnée — lancez d’abord l’extraction puis le DAG 07_analytics_refresh.";
    hint.className = "status-line warn";
    if (help) help.textContent = "";
    if (kpis) kpis.innerHTML = "";
    document.querySelector("#postal-table tbody").innerHTML =
      '<tr><td colspan="3" class="empty-msg">—</td></tr>';
    document.querySelector("#state-table tbody").innerHTML =
      '<tr><td colspan="3" class="empty-msg">—</td></tr>';
    document.querySelector("#activity-table tbody").innerHTML =
      '<tr><td colspan="4" class="empty-msg">—</td></tr>';
    return;
  }

  hint.textContent = data.refreshed_at
    ? `Dernière mise à jour : ${fmtDate(data.refreshed_at)}`
    : "";
  hint.className = "status-line ok";
  if (help) help.textContent = data.help || "";

  const total = Number(data.total_enterprises) || 0;
  const nPostal = (data.postal || []).length;
  const nStates = (data.states || []).length;
  const nActs = (data.activities || []).length;
  if (kpis) {
    kpis.innerHTML = `
      <div class="kpi-card"><span class="kpi-value">${total.toLocaleString("fr-BE")}</span><span class="kpi-label">Entreprises analysées</span></div>
      <div class="kpi-card"><span class="kpi-value">${nPostal}</span><span class="kpi-label">Codes postaux</span></div>
      <div class="kpi-card"><span class="kpi-value">${nStates}</span><span class="kpi-label">Catégories de statut</span></div>
      <div class="kpi-card"><span class="kpi-value">${nActs}</span><span class="kpi-label">Activités NACE (top)</span></div>`;
  }

  document.querySelector("#postal-table tbody").innerHTML = (data.postal || [])
    .map(
      (r) =>
        `<tr><td><strong>${escapeHtml(r.postal_code)}</strong></td><td>${Number(r.enterprise_count).toLocaleString("fr-BE")}</td><td>${fmtPct(r.share_pct)}</td></tr>`
    )
    .join("") || '<tr><td colspan="3" class="empty-msg">—</td></tr>';

  document.querySelector("#state-table tbody").innerHTML = (data.states || [])
    .map(
      (r) =>
        `<tr><td>${escapeHtml(r.status_label_fr || r.business_status)}</td><td>${Number(r.enterprise_count).toLocaleString("fr-BE")}</td><td>${fmtPct(r.share_pct)}</td></tr>`
    )
    .join("") || '<tr><td colspan="3" class="empty-msg">—</td></tr>';

  document.querySelector("#activity-table tbody").innerHTML = (data.activities || [])
    .map(
      (r) =>
        `<tr><td><code title="${escapeHtml(r.nace_code)}">${escapeHtml(r.nace_display || r.nace_code)}</code></td><td>${escapeHtml(r.activity_label || "Libellé non disponible")}</td><td>${Number(r.enterprise_count).toLocaleString("fr-BE")}</td><td>${fmtPct(r.share_pct)}</td></tr>`
    )
    .join("") || '<tr><td colspan="4" class="empty-msg">—</td></tr>';
}

/* ——— Entreprises ——— */
function statePillClass(state) {
  if (state === "STRUCTURED") return "ok";
  if (state.startsWith("FAILED")) return "err";
  if (state === "SCRAPING" || state === "PARSING") return "warn";
  return "";
}

async function loadEnterprises() {
  const status = document.getElementById("ent-status");
  const q = document.getElementById("ent-search").value.trim();
  const state = document.getElementById("ent-state-filter").value;
  const sort = document.getElementById("ent-sort").value;

  const params = new URLSearchParams({
    page: String(entPage),
    page_size: String(entPageSize),
    sort: state === "QUEUED_SCRAPE" && !q ? "number" : sort,
  });
  if (state) params.set("state", state);
  if (state === "QUEUED_SCRAPE" && !q) params.set("light", "1");
  if (q.length >= 4) params.set("q", q);
  else if (q.length > 0) {
    status.textContent = "Saisissez au moins 4 caractères pour la recherche.";
    status.className = "status-line warn";
    return;
  }

  status.textContent = "Chargement…";
  status.className = "status-line";
  try {
    const data = await fetchJson(`/api/enterprises?${params}`);
    renderEnterprisesTable(data);
    renderPagination(data);
    let msg = `${Number(data.total).toLocaleString("fr-BE")} résultats · page ${data.page}/${data.total_pages}`;
    if (data.light_mode) msg += " · mode liste rapide";
    if (data.default_filter_applied) msg += " (structurées)";
    status.textContent = msg;
    status.className = "status-line ok";
  } catch (err) {
    status.textContent = err.message;
    status.className = "status-line err";
    document.getElementById("enterprises-tbody").innerHTML =
      `<tr><td colspan="7" class="empty-msg">${escapeHtml(err.message)}</td></tr>`;
  }
}

function updateSelectionUi() {
  const bar = document.getElementById("ent-selection-bar");
  const countEl = document.getElementById("ent-selection-count");
  const n = selectedBce.size;
  if (bar) bar.hidden = n === 0;
  if (countEl) countEl.textContent = String(n);
}

function toggleBceSelection(num, checked) {
  if (checked) selectedBce.add(num);
  else selectedBce.delete(num);
  updateSelectionUi();
}

function renderEnterprisesTable(data) {
  const tbody = document.getElementById("enterprises-tbody");
  const items = data.items || [];
  const selectAll = document.getElementById("ent-select-all");
  if (selectAll) {
    const pageNums = items.map((r) => r.enterprise_number);
    selectAll.checked =
      pageNums.length > 0 && pageNums.every((n) => selectedBce.has(n));
    selectAll.indeterminate =
      pageNums.some((n) => selectedBce.has(n)) &&
      !pageNums.every((n) => selectedBce.has(n));
  }
  if (!items.length) {
    tbody.innerHTML =
      '<tr><td colspan="7" class="empty-msg">Aucun résultat pour ce filtre.</td></tr>';
    return;
  }
  tbody.innerHTML = items
    .map((row) => {
      const pill = statePillClass(row.state);
      const registry = row.has_registry
        ? `Oui (${row.snapshot_count})`
        : '<span class="muted">Non</span>';
      const num = escapeHtml(row.enterprise_number);
      const checked = selectedBce.has(row.enterprise_number) ? "checked" : "";
      return `<tr>
        <td class="col-check"><input type="checkbox" class="ent-row-check" data-num="${num}" ${checked} aria-label="Sélectionner ${num}"/></td>
        <td class="mono"><strong>${num}</strong></td>
        <td><span class="state-pill ${pill}">${escapeHtml(labelState(row.state))}</span></td>
        <td>${fmtDate(row.last_scrape_at)}</td>
        <td>${row.raw_doc_count}</td>
        <td>${registry}</td>
        <td class="actions">
          <button type="button" class="btn btn-sm btn-secondary" data-action="detail" data-num="${num}">Détail</button>
          <button type="button" class="btn btn-sm" data-action="parse" data-num="${num}">Parser</button>
        </td>
      </tr>`;
    })
    .join("");

  tbody.querySelectorAll("button[data-action]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.dataset.action === "detail") openDetailModal(btn.dataset.num);
      else onEnterpriseAction(btn);
    });
  });
  tbody.querySelectorAll(".ent-row-check").forEach((cb) => {
    cb.addEventListener("change", () => toggleBceSelection(cb.dataset.num, cb.checked));
  });
  updateSelectionUi();
}

/* ——— Détail entreprise (modal) ——— */
function closeDetailModal() {
  document.getElementById("detail-modal").hidden = true;
}

function renderKvRows(rows) {
  if (!rows?.length) return '<p class="empty-msg">Non renseigné</p>';
  return `<dl class="detail-kv">${rows
    .map((r) => `<dt>${escapeHtml(r.label)}</dt><dd>${escapeHtml(r.value)}</dd>`)
    .join("")}</dl>`;
}

function renderManagers(list) {
  if (!list?.length) return '<p class="empty-msg">Aucun dirigeant extrait</p>';
  return `<ul class="detail-list">${list
    .map(
      (m) =>
        `<li><span class="detail-role">${escapeHtml(m.role || "—")}</span> ${escapeHtml(m.name || "")}</li>`
    )
    .join("")}</ul>`;
}

function renderActivities(list) {
  if (!list?.length) return '<p class="empty-msg">Aucune activité NACE</p>';
  return `<ul class="detail-list">${list
    .map(
      (a) =>
        `<li><code>${escapeHtml(a.code || "")}</code> ${escapeHtml(a.label || "")}</li>`
    )
    .join("")}</ul>`;
}

function renderMoniteur(mon) {
  if (!mon) return '<p class="empty-msg">Pas de données Moniteur</p>';
  const previews = mon.publications_preview || [];
  const hint =
    mon.result_link_count != null
      ? `<p class="muted">${mon.result_link_count} lien(s) détecté(s)${mon.partial ? " · extrait partiel" : ""}</p>`
      : "";
  if (!previews.length) return `${hint}<p class="empty-msg">Aucune publication listée</p>`;
  return `${hint}<ul class="detail-list pub-list">${previews
    .map((p) => `<li>${escapeHtml(p)}</li>`)
    .join("")}</ul>`;
}

function renderOtherSources(sources) {
  if (!sources?.length) return "";
  return `<section class="detail-section">
    <h3>Autres sources</h3>
    <ul class="detail-list">${sources
      .map(
        (s) =>
          `<li><strong>${escapeHtml(s.label || s.source)}</strong>
           ${s.partial ? '<span class="badge-partial">partiel</span>' : ""}
           <span class="muted">${escapeHtml(s.summary || "")}</span></li>`
      )
      .join("")}</ul>
  </section>`;
}

function renderStructuredRegistry(summary, detail) {
  const raw = detail?.raw_documents || [];
  const successRaw = raw.filter((r) => r.download_status === "SUCCESS");

  if (!summary) {
    if (successRaw.length) {
      const labels = [...new Set(successRaw.map((r) => `${r.source}/${r.doc_type}`))].join(
        ", "
      );
      return `<p class="detail-meta warn">Documents bruts prêts (${successRaw.length}) — ${escapeHtml(labels)}.</p>
        <p class="empty-msg">Registre non généré — cliquez <strong>Parser</strong> ou lancez le DAG <code>04_extract_batch</code>.</p>`;
    }
    return '<p class="empty-msg">Pas encore de registre — scrape puis Parser ou DAG 04.</p>';
  }
  if (summary.pending_parse) {
    const srcs = (summary.raw_sources || [])
      .map((s) => escapeHtml(s.label || `${s.source}/${s.doc_type}`))
      .join(", ");
    const hint =
      detail?.registry_inconsistent
        ? "État « Structuré » sans snapshot valide — "
        : "";
    return `<p class="detail-meta warn">${hint}${summary.raw_doc_count || successRaw.length} document(s) brut(s) prêt(s)${srcs ? ` : ${srcs}` : ""}.</p>
      <p class="empty-msg">Registre à construire — cliquez <strong>Parser</strong> ou DAG <code>04_extract_batch</code>.</p>`;
  }
  if (summary.empty) {
    if (successRaw.length) {
      return `<p class="detail-meta warn">Snapshot obsolète ou vide.</p>
        <p class="empty-msg">Re-parser (${successRaw.length} document(s) brut(s) SUCCESS).</p>`;
    }
    return '<p class="empty-msg">Pas encore de registre — Parser ou DAG 04.</p>';
  }
  if (!summary.has_data) {
    return `<p class="empty-msg">Snapshot présent mais identité KBO incomplète.
      ${summary.legacy_snapshot ? " Re-parser après scrape KBO." : ""}</p>`;
  }
  const hq = summary.headquarters || {};
  const hqRows = [];
  if (hq.address) hqRows.push({ label: "Adresse du siège", value: hq.address });
  if (hq.postal_code) hqRows.push({ label: "Code postal", value: hq.postal_code });
  const meta = summary.registry_complete
    ? `<p class="detail-meta ok">Registre complet · MAJ ${fmtDate(summary.snapshot_at)}</p>`
    : `<p class="detail-meta warn">Registre partiel · MAJ ${fmtDate(summary.snapshot_at)}</p>`;
  return `${meta}
    <section class="detail-section">
      <h3>Identité</h3>
      ${renderKvRows(summary.identity)}
    </section>
    <section class="detail-section">
      <h3>Siège</h3>
      ${renderKvRows(hqRows)}
    </section>
    <section class="detail-section">
      <h3>Dirigeants</h3>
      ${renderManagers(summary.managers)}
    </section>
    <section class="detail-section">
      <h3>Activités NACE</h3>
      ${renderActivities(summary.activities)}
    </section>
    <section class="detail-section">
      <h3>Moniteur belge</h3>
      ${renderMoniteur(summary.moniteur)}
    </section>
    ${renderOtherSources(summary.other_sources)}
    <details class="detail-raw">
      <summary>Sources brutes (JSON parse)</summary>
      <pre class="json-block">${escapeHtml(
        JSON.stringify(summary.raw_documents_parsed || [], null, 2)
      )}</pre>
    </details>`;
}

async function openDetailModal(num) {
  const modal = document.getElementById("detail-modal");
  const body = document.getElementById("detail-body");
  const footer = document.getElementById("detail-footer");
  document.getElementById("detail-title").textContent = `Entreprise ${num}`;
  body.textContent = "Chargement…";
  footer.innerHTML = "";
  modal.hidden = false;

  try {
    const d = await fetchJson(`/api/enterprises/${encodeURIComponent(num)}`);
    const proc = d.processing || {};
    const summary = d.structured_summary;
    const titleName =
      summary?.identity?.find((r) => r.label === "Dénomination")?.value || num;
    document.getElementById("detail-title").textContent = titleName
      ? `${titleName} (${num})`
      : `Entreprise ${num}`;
    body.innerHTML = `
      <section class="detail-section">
        <h3>État pipeline</h3>
        <dl class="detail-kv">
          <dt>État</dt><dd>${escapeHtml(labelState(proc.state || "—"))}</dd>
          <dt>Depuis</dt><dd>${fmtDate(proc.state_since)}</dd>
          <dt>Source seed</dt><dd>${escapeHtml(d.seed_source)}</dd>
          <dt>Créée</dt><dd>${fmtDate(d.created_at)}</dd>
        </dl>
      </section>
      <section class="detail-section detail-registry">
        <h3>Registre entreprise</h3>
        ${renderStructuredRegistry(summary, d)}
      </section>
      <section class="detail-section">
        <h3>Documents bruts (${(d.raw_documents || []).length})</h3>
        ${
          (d.raw_documents || []).length
            ? `<table class="data-table"><thead><tr><th>Source</th><th>Type</th><th>Date</th><th>Statut</th></tr></thead><tbody>
            ${d.raw_documents
              .map(
                (r) => `<tr><td>${escapeHtml(r.source)}</td><td>${escapeHtml(r.doc_type)}</td>
                <td>${fmtDate(r.scraped_at)}</td><td>${escapeHtml(r.download_status)}</td></tr>`
              )
              .join("")}</tbody></table>`
            : '<p class="empty-msg">Aucun — lancez le DAG <code>02_scrape_by_source</code> (onglet DAGs).</p>'
        }
      </section>
    `;
    footer.innerHTML = `
      <button type="button" class="btn" data-action="parse" data-num="${escapeHtml(num)}">Parser</button>
      <button type="button" class="btn btn-secondary" data-close="1">Fermer</button>
    `;
    footer.querySelectorAll("button[data-action]").forEach((btn) => {
      btn.addEventListener("click", () => onEnterpriseAction(btn));
    });
  } catch (err) {
    body.innerHTML = `<p class="empty-msg">${escapeHtml(err.message)}</p>`;
  }
}

function setupDetailModal() {
  document.querySelectorAll("[data-close]").forEach((el) => {
    el.addEventListener("click", closeDetailModal);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeDetailModal();
  });
}

/* ——— DAGs Airflow ——— */
async function triggerDagFromUi(dagId, conf) {
  const res = await fetch(`/api/dags/${encodeURIComponent(dagId)}/trigger`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ conf }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(apiErrorMessage(data, res.status));
  return data;
}

function renderDagsCatalog(catalog) {
  const root = document.getElementById("dags-catalog");
  root.innerHTML = catalog
    .map((dag) => {
      const conf = dag.default_conf || {};
      const fields = (dag.conf_fields || [])
        .map((f) => {
          if (f.type === "boolean") {
            const checked = conf[f.name] !== false ? "checked" : "";
            return `<label class="check-row"><input type="checkbox" data-dag="${dag.dag_id}" data-field="${f.name}" ${checked}/> ${f.name}</label>`;
          }
          if (f.type === "string") {
            const val = conf[f.name] ?? "";
            return `<label>${f.name}</label><input type="text" data-dag="${dag.dag_id}" data-field="${f.name}" value="${escapeHtml(String(val))}"/>`;
          }
          const val = conf[f.name] ?? "";
          return `<label>${f.name}</label><input type="number" data-dag="${dag.dag_id}" data-field="${f.name}" value="${val}" min="${f.min || 1}" max="${f.max || 500}"/>`;
        })
        .join("");
      return `<article class="dag-card" data-dag-id="${dag.dag_id}">
        <h3>${escapeHtml(dag.label)}</h3>
        <p><code>${escapeHtml(dag.dag_id)}</code> — ${escapeHtml(dag.description)}</p>
        ${fields}
        <button type="button" class="btn btn-trigger" data-trigger-dag="${dag.dag_id}">Lancer</button>
      </article>`;
    })
    .join("");

  root.querySelectorAll(".btn-trigger").forEach((btn) => {
    btn.addEventListener("click", () => onDagTriggerClick(btn.dataset.triggerDag));
  });
}

function collectDagConf(dagId) {
  const conf = {};
  document.querySelectorAll(`[data-dag="${dagId}"][data-field]`).forEach((el) => {
    const name = el.dataset.field;
    if (el.type === "checkbox") conf[name] = el.checked;
    else if (el.type === "text") conf[name] = el.value.trim();
    else conf[name] = parseInt(el.value, 10) || 0;
  });
  if (dagId === SCRAPE_DAG_ID && selectedBce.size > 0) {
    // Airflow Param schema: string | null (CSV), pas un tableau JSON
    conf.enterprise_numbers = [...selectedBce].join(",");
    if (conf.limit === undefined || conf.limit > selectedBce.size) {
      conf.limit = selectedBce.size;
    }
  }
  return conf;
}

function renderDagRunsTable(runs) {
  const tbody = document.getElementById("dag-runs-tbody");
  if (!tbody) return;
  if (!runs?.length) {
    tbody.innerHTML =
      '<tr><td colspan="6" class="empty-msg">Aucun run — cliquez Lancer sur une carte DAG.</td></tr>';
    return;
  }
  tbody.innerHTML = runs
    .map((r) => {
      const conf = JSON.stringify(r.conf || {});
      const short = conf.length > 40 ? conf.slice(0, 37) + "…" : conf;
      const link = r.run_url
        ? `<a href="${escapeHtml(r.run_url)}" target="_blank" rel="noopener" class="link-btn">Ouvrir dans Airflow ↗</a>`
        : "—";
      return `<tr>
        <td><code>${escapeHtml(r.dag_id)}</code></td>
        <td class="mono" title="${escapeHtml(r.dag_run_id)}">${escapeHtml((r.dag_run_id || "").slice(0, 28))}…</td>
        <td><span class="state-pill ${r.state === "success" ? "ok" : r.state === "failed" ? "err" : "warn"}">${escapeHtml(r.state || "—")}</span></td>
        <td>${fmtDate(r.start_date)}</td>
        <td title="${escapeHtml(conf)}">${escapeHtml(short)}</td>
        <td>${link}</td>
      </tr>`;
    })
    .join("");
}

async function onDagTriggerClick(dagId) {
  const status = document.getElementById("dag-trigger-status");
  const btn = document.querySelector(`[data-trigger-dag="${dagId}"]`);
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Lancement…";
  }
  status.textContent = `Lancement ${dagId}…`;
  status.className = "status-line";
  try {
    const conf = collectDagConf(dagId);
    const result = await triggerDagFromUi(dagId, conf);
    status.innerHTML = `DAG lancé : <code>${escapeHtml(result.dag_run_id || "")}</code>`;
    if (result.run_url) {
      status.innerHTML += ` — <a href="${escapeHtml(result.run_url)}" target="_blank" rel="noopener"><strong>Ouvrir dans Airflow ↗</strong></a>`;
      window.open(result.run_url, "_blank", "noopener");
    }
    status.className = "status-line ok";
    const n = (result.conf && result.conf.enterprise_numbers) || [];
    const extra =
      Array.isArray(n) && n.length
        ? ` — ${n.length} BCE`
        : "";
    showToast(`DAG ${dagId} visible dans Airflow${extra}`, "ok");
    await refreshDagRunsList();
  } catch (err) {
    status.textContent = err.message;
    status.className = "status-line err";
    showToast(err.message, "err");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Lancer";
    }
  }
}

async function refreshDagRunsList() {
  try {
    const runs = await fetchJson("/api/dags/runs/recent");
    renderDagRunsTable(runs);
  } catch (err) {
    const tbody = document.getElementById("dag-runs-tbody");
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="6" class="empty-msg">${escapeHtml(err.message)}</td></tr>`;
    }
  }
}

async function refreshDagsTab() {
  const catalog = await fetchJson("/api/dags");
  renderDagsCatalog(catalog);
  await refreshDagRunsList();
}

async function quickScrapeDag() {
  const dagId = "02_scrape_by_source";
  if (selectedBce.size === 0) {
    const ok = confirm(
      "Aucune entreprise cochée.\n\nLancer le DAG sur la file (limit du paramètre) ?"
    );
    if (!ok) return;
  }
  switchTab("dags");
  let limit = selectedBce.size || 25;
  if (!selectedBce.size) {
    limit = parseInt(prompt("Taille du lot (file QUEUED_SCRAPE) ?", "25"), 10) || 25;
  }
  const card = document.querySelector(`[data-dag-id="${dagId}"]`);
  const limitInput = card?.querySelector('[data-field="limit"]');
  const wireInput = card?.querySelector('[data-field="wire_bridge"]');
  if (limitInput) limitInput.value = String(limit);
  if (wireInput) wireInput.checked = true;
  await onDagTriggerClick(dagId);
}

function renderPagination(data) {
  const nav = document.getElementById("ent-pagination");
  const prev = entPage > 1;
  const next = entPage < data.total_pages;
  nav.innerHTML = `
    <button type="button" data-nav="prev" ${prev ? "" : "disabled"}>← Préc.</button>
    <span class="page-info">Page ${data.page} / ${data.total_pages}</span>
    <button type="button" data-nav="next" ${next ? "" : "disabled"}>Suiv. →</button>
  `;
  nav.querySelector('[data-nav="prev"]')?.addEventListener("click", () => {
    entPage -= 1;
    loadEnterprises();
  });
  nav.querySelector('[data-nav="next"]')?.addEventListener("click", () => {
    entPage += 1;
    loadEnterprises();
  });
}

async function postAction(path, timeoutMs) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(path, {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ wire_bridge: true }),
      signal: ctrl.signal,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(apiErrorMessage(data, res.status));
    return data;
  } finally {
    clearTimeout(t);
  }
}

async function onEnterpriseAction(btn) {
  const num = btn.dataset.num;
  const action = btn.dataset.action;
  const row = btn.closest("tr");
  row?.querySelectorAll("button").forEach((b) => (b.disabled = true));

  showToast(`Parse ${num} en cours…`, "info");

  try {
    const path = `/api/enterprises/${encodeURIComponent(num)}/parse?sync=true`;
    const result = await postAction(path, 90000);
    showToast(result.message || "Terminé", result.success ? "ok" : "warn");
    await loadEnterprises();
    if (activeTab !== "overview") {
      await refreshOverview();
    }
  } catch (err) {
    showToast(err.message, "err");
  } finally {
    row?.querySelectorAll("button").forEach((b) => (b.disabled = false));
  }
}

function setupEnterprisesUi() {
  document.getElementById("ent-select-all")?.addEventListener("change", (e) => {
    const checked = e.target.checked;
    document.querySelectorAll(".ent-row-check").forEach((cb) => {
      cb.checked = checked;
      toggleBceSelection(cb.dataset.num, checked);
    });
  });
  document.getElementById("ent-clear-selection")?.addEventListener("click", () => {
    selectedBce.clear();
    document.querySelectorAll(".ent-row-check").forEach((cb) => (cb.checked = false));
    const sa = document.getElementById("ent-select-all");
    if (sa) {
      sa.checked = false;
      sa.indeterminate = false;
    }
    updateSelectionUi();
  });
  document.getElementById("ent-refresh").addEventListener("click", loadEnterprises);
  document.getElementById("ent-state-filter").addEventListener("change", () => {
    entPage = 1;
    loadEnterprises();
  });
  document.getElementById("ent-sort").addEventListener("change", () => {
    entPage = 1;
    loadEnterprises();
  });
  document.getElementById("ent-search").addEventListener("input", () => {
    clearTimeout(entSearchTimer);
    entSearchTimer = setTimeout(() => {
      entPage = 1;
      loadEnterprises();
    }, 450);
  });
}

/* ——— Refresh par onglet ——— */
async function refreshOverview() {
  const [snap, config] = await Promise.all([
    fetchJson("/api/supervision"),
    fetchJson("/api/config"),
  ]);
  if (config.airflow_ui_url) {
    document.getElementById("airflow-link").href = config.airflow_ui_url;
  }
  renderKpis(snap);
  renderQueue(snap.queue_by_state);
  renderPerf(snap);
  document.getElementById("generated-at").textContent =
    `Généré : ${fmtDate(snap.generated_at)}`;
  return snap;
}

async function refreshAnalyticsTab() {
  const data = await fetchJson("/api/analytics");
  renderAnalytics(data);
}

async function refreshJournalTab() {
  const snap = await fetchJson("/api/supervision");
  renderDiscoveries(snap.recent_discoveries);
  renderEvents(snap.recent_events);
}

async function refreshActiveTab() {
  const badge = document.getElementById("refresh-badge");
  try {
    if (activeTab === "enterprises") {
      await loadEnterprises();
    } else if (activeTab === "overview") {
      await refreshOverview();
    } else if (activeTab === "analytics") {
      await refreshAnalyticsTab();
    } else if (activeTab === "dags") {
      await refreshDagsTab();
    } else if (activeTab === "journal") {
      await refreshJournalTab();
    }
    badge.textContent = `OK · ${new Date().toLocaleTimeString("fr-BE")}`;
    badge.style.color = "var(--ok)";
  } catch (err) {
    badge.textContent = err.message;
    badge.style.color = "var(--err)";
    console.error(err);
  }
}

function startAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(refreshActiveTab, REFRESH_MS);
}

/* ——— Init ——— */
function init() {
  setupTabs();
  setupEnterprisesUi();
  setupDetailModal();
  document.getElementById("ent-dag-scrape")?.addEventListener("click", quickScrapeDag);
  document.getElementById("ent-dag-scrape-selection")?.addEventListener("click", quickScrapeDag);
  switchTab("enterprises");
  startAutoRefresh();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
