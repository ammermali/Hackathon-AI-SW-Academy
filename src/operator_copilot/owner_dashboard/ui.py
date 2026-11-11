"""Self-contained Owner Dashboard – Learning Analytics UI served by FastAPI (/owner)."""

from __future__ import annotations


def render_owner_dashboard_html() -> str:
    """Return HTML5/CSS3/ES6 single-page dashboard wired live to /api/v1/owner/* endpoints."""
    return """<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Owner Dashboard — Learning Analytics | Operator Copilot</title>
  <style>
    :root {
      --bg: #0f172a;
      --surface: #1e293b;
      --surface-alt: #263348;
      --border: #334155;
      --text: #f1f5f9;
      --muted: #94a3b8;
      --accent: #38bdf8;
      --accent-dark: #0284c7;
      --critical: #ef4444;
      --high: #f97316;
      --medium: #eab308;
      --low: #22c55e;
      --info: #60a5fa;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
    }
    header {
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 14px 24px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    .brand h1 { margin: 0; font-size: 1.15rem; font-weight: 700; color: var(--accent); }
    .brand p { margin: 2px 0 0; font-size: 0.82rem; color: var(--muted); }
    .auth-bar {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }
    input, select, button {
      background: var(--bg);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 7px 10px;
      font-size: 0.85rem;
    }
    button {
      background: var(--accent-dark);
      border-color: var(--accent);
      cursor: pointer;
      font-weight: 600;
    }
    button:hover { opacity: 0.92; }
    button.secondary { background: var(--surface-alt); border-color: var(--border); }
    .layout { display: grid; grid-template-columns: 230px 1fr; min-height: calc(100vh - 68px); }
    nav {
      background: var(--surface);
      border-right: 1px solid var(--border);
      padding: 16px 12px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    nav button {
      width: 100%;
      text-align: left;
      background: transparent;
      border: 1px solid transparent;
      padding: 10px 12px;
      font-weight: 500;
      color: var(--muted);
    }
    nav button.active {
      background: var(--surface-alt);
      border-color: var(--accent-dark);
      color: var(--text);
      font-weight: 600;
    }
    main { padding: 20px 26px; max-width: 1440px; }
    .filters-bar {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 12px 16px;
      margin-bottom: 18px;
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: flex-end;
    }
    .field { display: flex; flex-direction: column; gap: 4px; }
    .field label { font-size: 0.75rem; color: var(--muted); }
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
      gap: 14px;
      margin-bottom: 20px;
    }
    .kpi {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 14px 16px;
    }
    .kpi .label { font-size: 0.78rem; color: var(--muted); }
    .kpi .value { font-size: 1.65rem; font-weight: 700; margin-top: 4px; color: var(--accent); }
    .kpi .sub { font-size: 0.76rem; color: var(--muted); margin-top: 4px; }
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px 18px;
      margin-bottom: 18px;
    }
    .card h2 { margin: 0 0 12px; font-size: 1.02rem; }
    table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
    th, td { padding: 9px 10px; border-bottom: 1px solid var(--border); text-align: left; }
    th { color: var(--muted); font-weight: 600; font-size: 0.78rem; text-transform: uppercase; }
    tr.clickable:hover { background: var(--surface-alt); cursor: pointer; }
    .badge {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 0.72rem;
      font-weight: 700;
    }
    .b-CRITICAL { background: rgba(239,68,68,.2); color: #fca5a5; border: 1px solid var(--critical); }
    .b-HIGH { background: rgba(249,115,22,.2); color: #fdba74; border: 1px solid var(--high); }
    .b-MEDIUM { background: rgba(234,179,8,.18); color: #fde047; border: 1px solid var(--medium); }
    .b-LOW, .b-RESOLVED, .b-COMPETENTE { background: rgba(34,197,94,.18); color: #86efac; border: 1px solid var(--low); }
    .b-INFO, .b-IMPROVING, .b-IN_MIGLIORAMENTO { background: rgba(96,165,250,.18); color: #93c5fd; border: 1px solid var(--info); }
    .b-OPEN, .b-ATTENZIONE_CRITICA { background: rgba(239,68,68,.2); color: #fca5a5; }
    .hidden { display: none !important; }
    .error-banner {
      background: rgba(239,68,68,.15);
      border: 1px solid var(--critical);
      color: #fecaca;
      padding: 10px 14px;
      border-radius: 8px;
      margin-bottom: 14px;
      font-size: 0.88rem;
    }
    .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .insight-item {
      border-left: 3px solid var(--accent);
      background: var(--surface-alt);
      padding: 10px 14px;
      border-radius: 6px;
      margin-bottom: 10px;
    }
    .pagination { display: flex; justify-content: flex-end; gap: 8px; align-items: center; margin-top: 12px; }
    svg.chart { width: 100%; height: 190px; background: var(--bg); border-radius: 8px; border: 1px solid var(--border); }
    @media (max-width: 900px) {
      .layout { grid-template-columns: 1fr; }
      .two-col { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <h1>Owner Dashboard — Learning Analytics</h1>
      <p>Governance multi-tenant dell'apprendimento, Topic Critici ed Efficacia Custom Quiz</p>
    </div>
    <div class="auth-bar">
      <input id="authTenant" placeholder="Tenant ID" value="default" title="X-Tenant-ID" />
      <input id="authOwnerId" placeholder="Owner User ID" value="owner_admin" title="X-User-ID" />
      <input id="authOwnerKey" type="password" placeholder="X-Owner-Key" title="X-Owner-Key" />
      <input id="authScope" placeholder="Scope Amministrazioni (csv opz.)" title="X-Owner-Scope" />
      <button onclick="connectOwner()">Accedi / Aggiorna</button>
    </div>
  </header>

  <div class="layout">
    <nav>
      <button id="nav-overview" class="active" onclick="switchTab('overview')">Overview</button>
      <button id="nav-users" onclick="switchTab('users')">Utenti</button>
      <button id="nav-topics" onclick="switchTab('topics')">Topic da ripassare</button>
      <button id="nav-analytics" onclick="switchTab('analytics')">Learning Analytics</button>
      <button id="nav-customquiz" onclick="switchTab('customquiz')">Custom Quiz Performance</button>
    </nav>

    <main>
      <div id="statusError" class="error-banner hidden"></div>

      <div class="filters-bar">
        <div class="field"><label>Da data</label><input id="fDateFrom" type="date" /></div>
        <div class="field"><label>A data</label><input id="fDateTo" type="date" /></div>
        <div class="field"><label>Amministrazione</label><input id="fAdmin" placeholder="Tutte" /></div>
        <div class="field"><label>Software</label><input id="fSoftware" placeholder="Tutti (es. CWOL, OTRS)" /></div>
        <div class="field"><label>Modulo</label><input id="fModule" placeholder="Tutti" /></div>
        <button onclick="refreshAll(true)">Applica Filtri</button>
        <button class="secondary" onclick="resetFilters()">Reset</button>
      </div>

      <!-- TAB 1: OVERVIEW -->
      <section id="tab-overview">
        <div class="kpi-grid" id="overviewKpis"></div>
        <div class="card">
          <h2>Andamento Punteggi & Risoluzione Lacune nel Tempo</h2>
          <svg id="overviewChart" class="chart" viewBox="0 0 720 180"></svg>
        </div>
      </section>

      <!-- TAB 2: UTENTI + SCHEDA DETTAGLIO -->
      <section id="tab-users" class="hidden">
        <div class="card">
          <h2>User Learning Overview</h2>
          <div style="display:flex; gap:10px; flex-wrap:wrap; margin-bottom:12px;">
            <input id="uSearch" placeholder="Cerca nome, ID o amministrazione..." />
            <select id="uStatus">
              <option value="">Tutti gli stati</option>
              <option value="ATTENZIONE_CRITICA">ATTENZIONE_CRITICA</option>
              <option value="SUPPORTO_NECESSARIO">SUPPORTO_NECESSARIO</option>
              <option value="IN_MIGLIORAMENTO">IN_MIGLIORAMENTO</option>
              <option value="COMPETENTE">COMPETENTE</option>
              <option value="NESSUNA_ATTIVITA">NESSUNA_ATTIVITA</option>
            </select>
            <select id="uSort">
              <option value="open_gaps_count">Ordina per Lacune Aperte</option>
              <option value="quiz_success_rate">Ordina per Successo Quiz</option>
              <option value="courses_completed">Ordina per Corsi Completati</option>
              <option value="last_activity_at">Ordina per Ultima Attività</option>
              <option value="display_name">Ordina per Nome</option>
            </select>
            <button onclick="loadUsers(1)">Filtra Utenti</button>
          </div>
          <table>
            <thead>
              <tr>
                <th>Utente</th><th>Amministrazione</th><th>Software</th><th>Corsi</th>
                <th>Media Quiz</th><th>Custom Quiz</th><th>Improvement</th>
                <th>Lacune Aperte</th><th>Ultima Attività</th><th>Stato</th>
              </tr>
            </thead>
            <tbody id="usersTableBody"></tbody>
          </table>
          <div class="pagination">
            <button class="secondary" onclick="changeUserPage(-1)">Precedente</button>
            <span id="usersPageInfo">Pagina 1</span>
            <button class="secondary" onclick="changeUserPage(1)">Successiva</button>
          </div>
        </div>

        <div id="userDetailCard" class="card hidden">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <h2 id="userDetailTitle">Dettaglio Utente</h2>
            <button class="secondary" onclick="document.getElementById('userDetailCard').classList.add('hidden')">Chiudi Scheda</button>
          </div>
          <div id="userDetailContent"></div>
        </div>
      </section>

      <!-- TAB 3: TOPIC DA RIPASSARE -->
      <section id="tab-topics" class="hidden">
        <div class="card">
          <h2>Topic to Review — Argomenti Critici da Ripassare</h2>
          <table>
            <thead>
              <tr>
                <th>Topic</th><th>Software / Modulo</th><th>Utenti Coinvolti</th>
                <th>Lacune (Aperte/Tot)</th><th>% Errori Media</th><th>Evoluzione</th><th>Criticità</th>
              </tr>
            </thead>
            <tbody id="topicsTableBody"></tbody>
          </table>
        </div>
        <div id="topicDrilldownCard" class="card hidden">
          <h2 id="topicDrillTitle">Utenti con lacuna sul Topic</h2>
          <table>
            <thead><tr><th>Utente</th><th>Amministrazione</th><th>Stato Lacuna</th><th>Priorità</th><th>Errori Ripetuti</th><th>Ultima Verifica</th></tr></thead>
            <tbody id="topicUsersBody"></tbody>
          </table>
        </div>
      </section>

      <!-- TAB 4: LEARNING ANALYTICS & INSIGHTS -->
      <section id="tab-analytics" class="hidden">
        <div class="two-col">
          <div class="card">
            <h2>Owner Insights — Suggerimenti Formativi Verificabili</h2>
            <div id="insightsContainer"></div>
          </div>
          <div class="card">
            <h2>Audit Trail Consultazioni Owner</h2>
            <table>
              <thead><tr><th>Data</th><th>Owner</th><th>Azione</th><th>Risorsa</th><th>Target</th></tr></thead>
              <tbody id="auditTableBody"></tbody>
            </table>
          </div>
        </div>
      </section>

      <!-- TAB 5: CUSTOM QUIZ PERFORMANCE -->
      <section id="tab-customquiz" class="hidden">
        <div class="kpi-grid" id="cqKpis"></div>
        <div class="card">
          <h2>Efficacia e Risultati Custom Quiz nel Tempo</h2>
          <svg id="cqChart" class="chart" viewBox="0 0 720 180"></svg>
        </div>
      </section>
    </main>
  </div>

  <script>
    let currentTab = 'overview';
    let usersPage = 1;
    let usersTotal = 0;
    const pageSize = 15;

    function getHeaders() {
      return {
        'X-Tenant-ID': document.getElementById('authTenant').value.trim() || 'default',
        'X-User-ID': document.getElementById('authOwnerId').value.trim() || 'anonymous',
        'X-User-Role': 'owner',
        'X-Owner-Key': document.getElementById('authOwnerKey').value,
        'X-Owner-Scope': document.getElementById('authScope').value.trim(),
      };
    }

    function showError(msg) {
      const el = document.getElementById('statusError');
      if (!msg) { el.classList.add('hidden'); el.textContent = ''; return; }
      el.textContent = msg;
      el.classList.remove('hidden');
    }

    async function apiGet(path) {
      const res = await fetch(path, { headers: getHeaders() });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Errore HTTP ${res.status}`);
      }
      return res.json();
    }

    function filterQS(extra = {}) {
      const p = new URLSearchParams();
      const df = document.getElementById('fDateFrom').value;
      const dt = document.getElementById('fDateTo').value;
      const adm = document.getElementById('fAdmin').value.trim();
      const sw = document.getElementById('fSoftware').value.trim();
      const mod = document.getElementById('fModule').value.trim();
      if (df) p.set('date_from', df + 'T00:00:00Z');
      if (dt) p.set('date_to', dt + 'T23:59:59Z');
      if (adm) p.set('amministrazione', adm);
      if (sw) p.set('software', sw);
      if (mod) p.set('module_name', mod);
      for (const [k, v] of Object.entries(extra)) {
        if (v !== null && v !== undefined && v !== '') p.set(k, String(v));
      }
      const q = p.toString();
      return q ? `?${q}` : '';
    }

    function switchTab(name) {
      currentTab = name;
      ['overview', 'users', 'topics', 'analytics', 'customquiz'].forEach(t => {
        document.getElementById('tab-' + t).classList.toggle('hidden', t !== name);
        document.getElementById('nav-' + t).classList.toggle('active', t === name);
      });
      if (document.getElementById('authOwnerKey').value) refreshCurrentTab(false);
    }

    function connectOwner() {
      refreshAll(true);
    }

    function resetFilters() {
      ['fDateFrom', 'fDateTo', 'fAdmin', 'fSoftware', 'fModule'].forEach(id => document.getElementById(id).value = '');
      refreshAll(true);
    }

    function drawLineChart(svgId, points) {
      const svg = document.getElementById(svgId);
      svg.innerHTML = '';
      if (!points || points.length === 0) {
        svg.innerHTML = '<text x="20" y="95" fill="#94a3b8" font-size="13">Nessun dato temporale nel periodo selezionato.</text>';
        return;
      }
      const w = 720, h = 180, pad = 32;
      const maxX = Math.max(1, points.length - 1);
      const coords = points.map((pt, i) => {
        const x = pad + (i / maxX) * (w - pad * 2);
        const y = (h - pad) - (Math.min(100, Math.max(0, pt.avg_score)) / 100) * (h - pad * 2);
        return { x, y, pt };
      });
      const poly = coords.map(c => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(' ');
      let html = `<line x1="${pad}" y1="${h-pad}" x2="${w-pad}" y2="${h-pad}" stroke="#334155"/>`;
      html += `<polyline fill="none" stroke="#38bdf8" stroke-width="2.5" points="${poly}"/>`;
      coords.forEach(c => {
        html += `<circle cx="${c.x}" cy="${c.y}" r="4" fill="#38bdf8"><title>${c.pt.period}: ${c.pt.avg_score}% (${c.pt.attempts} tent.)</title></circle>`;
      });
      svg.innerHTML = html;
    }

    async function loadOverview(refresh = false) {
      const data = await apiGet('/api/v1/owner/overview' + filterQS(refresh ? { refresh: 'true' } : {}));
      const fmtOpt = v => v === null || v === undefined ? 'N/D' : `${v > 0 ? '+' : ''}${v}%`;
      const cards = [
        ['Utenti Totali', data.total_users, 'Nel perimetro autorizzato'],
        ['Utenti Attivi (Periodo)', data.active_users_in_period, 'Con attività quiz nel periodo'],
        ['Completamento Corsi', data.course_completion_rate + '%', 'Media sui corsi tenant'],
        ['Punteggio Medio Quiz', data.avg_quiz_score + '%', 'Tradizionali + Custom Quiz'],
        ['Learning Improvement', fmtOpt(data.avg_learning_improvement), 'Delta medio topic verificati'],
        ['Gap Resolution Rate', data.knowledge_gap_resolution_rate + '%', 'Lacune risolte / totali'],
        ['Lacune Ancora Aperte', data.open_gaps_count, 'OPEN / IN_PROGRESS / IMPROVING'],
        ['Utenti con Lacune Critiche', data.users_with_critical_gaps, 'Richiedono intervento'],
        ['Delta vs Periodo Prec.', fmtOpt(data.improvement_vs_previous_period), 'Confronto finestra precedente'],
      ];
      document.getElementById('overviewKpis').innerHTML = cards.map(c =>
        `<div class="kpi"><div class="label">${c[0]}</div><div class="value">${c[1]}</div><div class="sub">${c[2]}</div></div>`
      ).join('');
      drawLineChart('overviewChart', data.timeline);
    }

    async function loadUsers(page = 1) {
      usersPage = page;
      const data = await apiGet('/api/v1/owner/users' + filterQS({
        search: document.getElementById('uSearch').value.trim(),
        learning_status: document.getElementById('uStatus').value,
        sort_by: document.getElementById('uSort').value,
        page: usersPage,
        page_size: pageSize,
      }));
      usersTotal = data.total;
      document.getElementById('usersPageInfo').textContent = `Pagina ${data.page} · Totale ${data.total} utenti`;
      document.getElementById('usersTableBody').innerHTML = data.items.map(u => `
        <tr class="clickable" onclick="loadUserDetail('${encodeURIComponent(u.user_id)}')">
          <td><strong>${u.display_name}</strong><br><small style="color:#94a3b8">${u.user_id}</small></td>
          <td>${u.amministrazione}</td>
          <td>${(u.softwares_used || []).join(', ') || '-'}</td>
          <td>${u.courses_completed}</td>
          <td>${u.quiz_success_rate}%</td>
          <td>${u.custom_quizzes_count}</td>
          <td>${u.learning_improvement !== null ? (u.learning_improvement > 0 ? '+' : '') + u.learning_improvement + '%' : 'N/D'}</td>
          <td>${u.open_gaps_count}</td>
          <td>${u.last_activity_at ? u.last_activity_at.slice(0, 16).replace('T', ' ') : '-'}</td>
          <td><span class="badge b-${u.overall_status}">${u.overall_status}</span></td>
        </tr>`).join('') || '<tr><td colspan="10">Nessun utente trovato.</td></tr>';
    }

    function changeUserPage(delta) {
      const maxPage = Math.max(1, Math.ceil(usersTotal / pageSize));
      const next = Math.min(maxPage, Math.max(1, usersPage + delta));
      if (next !== usersPage) loadUsers(next);
    }

    async function loadUserDetail(encodedUid) {
      const uid = decodeURIComponent(encodedUid);
      const d = await apiGet(`/api/v1/owner/users/${encodeURIComponent(uid)}`);
      document.getElementById('userDetailCard').classList.remove('hidden');
      document.getElementById('userDetailTitle').textContent = `${d.display_name} (${d.user_id}) — ${d.amministrazione}`;
      const lp = d.learning_performance;
      document.getElementById('userDetailContent').innerHTML = `
        <p>Stato complessivo: <span class="badge b-${d.overall_status}">${d.overall_status}</span> · Retention: <strong>${lp.retention_rate !== null ? lp.retention_rate + '%' : 'N/D'}</strong> · Corsi completati: <strong>${lp.courses_completed.length}</strong> / ${lp.courses_completed.length + lp.courses_to_complete.length}</p>
        <h3>Knowledge Gaps Utente (${d.knowledge_gaps.length})</h3>
        <table>
          <thead><tr><th>Topic</th><th>Software / Modulo</th><th>Criticità</th><th>Errori</th><th>Verifiche</th><th>Stato</th><th>Ultimo Risultato</th></tr></thead>
          <tbody>
            ${d.knowledge_gaps.map(g => `<tr>
              <td>${g.topic}</td><td>${g.software} / ${g.module_name}</td>
              <td><span class="badge b-${g.criticality}">${g.criticality}</span></td>
              <td>${g.error_count}</td><td>${g.verifications_count}</td>
              <td><span class="badge b-${g.status}">${g.status}</span></td>
              <td>${g.last_result_percentage !== null ? g.last_result_percentage + '%' : 'N/D'}</td>
            </tr>`).join('') || '<tr><td colspan="7">Nessuna lacuna registrata.</td></tr>'}
          </tbody>
        </table>
        <h3 style="margin-top:16px;">Learning History</h3>
        <table>
          <thead><tr><th>Data</th><th>Tipo</th><th>Evento</th><th>Esito</th></tr></thead>
          <tbody>
            ${d.learning_history.slice(0, 15).map(h => `<tr>
              <td>${h.occurred_at.slice(0, 16).replace('T', ' ')}</td><td>${h.event_type}</td>
              <td>${h.title}</td><td>${h.result_summary}${h.percentage !== null ? ' (' + h.percentage + '%)' : ''}</td>
            </tr>`).join('') || '<tr><td colspan="4">Nessun evento registrato.</td></tr>'}
          </tbody>
        </table>`;
    }

    async function loadTopics() {
      const items = await apiGet('/api/v1/owner/topics-to-review' + filterQS());
      document.getElementById('topicsTableBody').innerHTML = items.map(t => `
        <tr class="clickable" onclick="loadTopicDrilldown('${encodeURIComponent(t.topic)}')">
          <td><strong>${t.topic}</strong></td>
          <td>${t.software} / ${t.module_name}</td>
          <td>${t.affected_users_count}</td>
          <td>${t.open_gaps_count} / ${t.total_gaps_count}</td>
          <td>${t.avg_error_rate}%</td>
          <td>${t.evolution_vs_previous_period !== null ? (t.evolution_vs_previous_period > 0 ? '+' : '') + t.evolution_vs_previous_period + '%' : 'N/D'}</td>
          <td><span class="badge b-${t.criticality}">${t.criticality}</span></td>
        </tr>`).join('') || '<tr><td colspan="7">Nessun topic critico rilevato.</td></tr>';
    }

    async function loadTopicDrilldown(encodedTopic) {
      const res = await apiGet(`/api/v1/owner/topics-to-review/${encodedTopic}/users` + filterQS());
      document.getElementById('topicDrilldownCard').classList.remove('hidden');
      document.getElementById('topicDrillTitle').textContent = `Utenti con lacuna su '${res.topic_summary.topic}' (${res.affected_users.length})`;
      document.getElementById('topicUsersBody').innerHTML = res.affected_users.map(u => `
        <tr class="clickable" onclick="switchTab('users'); loadUserDetail('${encodeURIComponent(u.user_id)}')">
          <td>${u.display_name} (${u.user_id})</td><td>${u.amministrazione}</td>
          <td><span class="badge b-${u.gap_status}">${u.gap_status}</span></td>
          <td>${u.priority}</td><td>${u.repeated_error_count}</td>
          <td>${u.last_verified_at ? u.last_verified_at.slice(0, 16).replace('T', ' ') : '-'}</td>
        </tr>`).join('');
    }

    async function loadAnalytics() {
      const [ins, aud] = await Promise.all([
        apiGet('/api/v1/owner/insights' + filterQS()),
        apiGet('/api/v1/owner/audit-logs?limit=20'),
      ]);
      document.getElementById('insightsContainer').innerHTML = (ins.insights || []).map(i => `
        <div class="insight-item">
          <div><span class="badge b-${i.severity}">${i.severity}</span> <small style="color:#94a3b8">${i.category} · ${i.source_engine}</small></div>
          <p style="margin:6px 0;"><strong>${i.message}</strong></p>
          <p style="margin:0; font-size:0.83rem; color:#94a3b8;">Azione: ${i.recommended_action}</p>
        </div>`).join('') || '<p>Nessun insight disponibile con i filtri attuali.</p>';
      document.getElementById('auditTableBody').innerHTML = (aud || []).map(a => `
        <tr><td>${a.created_at.slice(0, 19).replace('T', ' ')}</td><td>${a.owner_id}</td><td>${a.action}</td><td>${a.resource}</td><td>${a.target_user_id || '-'}</td></tr>`
      ).join('');
    }

    async function loadCustomQuizAnalytics() {
      const d = await apiGet('/api/v1/owner/customquiz-analytics' + filterQS());
      const cards = [
        ['Custom Quiz Generati', d.total_generated, 'Nel perimetro filtrato'],
        ['Custom Quiz Completati', d.total_completed, 'Tentativi registrati'],
        ['Media Risposte Corrette', d.avg_correct_percentage + '%', 'Media complessiva'],
        ['Miglioramento Verifiche', d.improvement_between_verifications !== null ? '+' + d.improvement_between_verifications + '%' : 'N/D', 'Tra verifiche successive'],
        ['Lacune Risolte (Follow-up)', d.gaps_resolved_via_followup, 'Con >= 2 verifiche positive'],
        ['Lacune Persistenti', d.persistent_gaps_count, 'Ancora aperte / errori ripetuti'],
        ['Ripetizione Errori', d.repeated_error_rate + '%', 'Sugli stessi argomenti'],
        ['Retention Rate', d.retention_rate !== null ? d.retention_rate + '%' : 'N/D', 'Mantenimento >= 70%'],
      ];
      document.getElementById('cqKpis').innerHTML = cards.map(c =>
        `<div class="kpi"><div class="label">${c[0]}</div><div class="value">${c[1]}</div><div class="sub">${c[2]}</div></div>`
      ).join('');
      drawLineChart('cqChart', d.timeline);
    }

    async function refreshCurrentTab(refresh = false) {
      showError('');
      try {
        if (currentTab === 'overview') await loadOverview(refresh);
        else if (currentTab === 'users') await loadUsers(usersPage);
        else if (currentTab === 'topics') await loadTopics();
        else if (currentTab === 'analytics') await loadAnalytics();
        else if (currentTab === 'customquiz') await loadCustomQuizAnalytics();
      } catch (err) {
        showError(err.message);
      }
    }

    async function refreshAll(refresh = false) {
      showError('');
      try {
        await Promise.all([
          loadOverview(refresh),
          loadUsers(1),
          loadTopics(),
          loadAnalytics(),
          loadCustomQuizAnalytics(),
        ]);
      } catch (err) {
        showError(err.message);
      }
    }
  </script>
</body>
</html>
"""
