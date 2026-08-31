/* ===========================
   The Escalate Frontend — app.js
   Connects to http://localhost:8000
   =========================== */

const API = 'http://localhost:8000/v1';
const WS_ID = 'ws_aurora';

let currentRole = 'ws_admin';
let allMentions = [];
let currentMentionFilter = 'all';
let evalData = null;
let warRoomsData = [];
let holdingsData = [];

/* ===========================
   HELPERS
   =========================== */
async function apiFetch(path, opts = {}) {
  const res = await fetch(`${API}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      'X-Nadi-Role': currentRole,
      ...opts.headers,
    },
    ...opts,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

function toast(msg, type = 'info') {
  const c = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  c.appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

function openModal(title, bodyHTML) {
  document.getElementById('modal-title').textContent = title;
  document.getElementById('modal-body').innerHTML = bodyHTML;
  document.getElementById('modal-overlay').classList.add('open');
}

function closeModal() {
  document.getElementById('modal-overlay').classList.remove('open');
}

function updateRole(val) {
  currentRole = val;
  toast(`Role switched to ${val}`, 'info');
  refreshAll();
}

function sentimentClass(label) {
  const map = { pos: 'pos', neg: 'neg', neu: 'neu', mixed: 'mixed' };
  return `sentiment-${map[label] || 'neu'}`;
}

function sentimentEmoji(label) {
  return { pos: '▲', neg: '▼', neu: '–', mixed: '~' }[label] || '–';
}

function platformClass(p) {
  const k = (p || '').toLowerCase();
  return `platform-${['news','telegram','x','facebook','instagram','tiktok'].includes(k) ? k : 'other'}`;
}

function statusBadgeClass(s) {
  const map = {
    open: 'badge-open', contained: 'badge-contained', closed: 'badge-closed', tabletop: 'badge-tabletop',
    high: 'badge-high', critical: 'badge-critical', medium: 'badge-medium', low: 'badge-low',
  };
  return `badge ${map[s] || 'badge-open'}`;
}

function holdingStatusClass(s) {
  return `badge hld-status-${s}`;
}

function fmtDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-MY', { dateStyle: 'medium', timeStyle: 'short' });
}

function objStatusClass(s) {
  return { green: 'green', amber: 'amber', red: 'red', not_started: 'not_started' }[s] || 'not_started';
}

function ladderId(stage) {
  return { outputs: 'outputs', outtakes: 'outtakes', outcomes: 'outcomes', impact: 'impact' }[stage] || stage;
}

function bandClass(band) {
  return { on_track: 'band-on-track', at_risk: 'band-at-risk', off_track: 'band-off-track', exceeding: 'band-exceeding' }[band] || 'band-at-risk';
}

/* ===========================
   NAVIGATION
   =========================== */
function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.getElementById(`page-${name}`).classList.add('active');
  document.getElementById(`nav-${name}`).classList.add('active');

  const titles = {
    dashboard: ['Dashboard', 'Jalur Kita Merdeka 2026 · 18–24 Aug 2026'],
    mentions: ['Mentions', 'Social listening feed'],
    evaluation: ['Evaluation', 'AMEC Integrated Evaluation Framework'],
    warrooms: ['War Rooms', '3R & crisis management'],
    holdings: ['Holdings', 'Holding briefs · Barcelona 4.0 compliant'],
  };
  document.getElementById('page-title').textContent = titles[name][0];
  document.getElementById('page-sub').textContent = titles[name][1];

  if (name === 'mentions') renderMentions();
  if (name === 'evaluation') loadEvaluation();
  if (name === 'warrooms') loadWarRooms();
  if (name === 'holdings') loadHoldings();
}

/* ===========================
   REFRESH ALL
   =========================== */
async function refreshAll() {
  const btn = document.getElementById('btn-refresh');
  btn.classList.add('spinning');
  try {
    await Promise.all([
      loadDashboard(),
      loadMentionsData(),
      loadWarRooms(),
      loadHoldings(),
    ]);
    toast('Refreshed', 'success');
  } catch (e) {
    toast(`Refresh failed: ${e.message}`, 'error');
  } finally {
    btn.classList.remove('spinning');
  }
}

/* ===========================
   DASHBOARD
   =========================== */
async function loadDashboard() {
  try {
    evalData = await apiFetch(`/workspaces/${WS_ID}/evaluation`);
    renderStatCards(evalData);
    renderObjectives(evalData.objectives || []);
    renderLadder(evalData.ladder || {});
    renderMoves(evalData.moves || []);
    renderNarrative(evalData.contribution || {});
  } catch (e) {
    console.error('Dashboard load error:', e);
  }
}

function renderStatCards(snap) {
  const ladder = snap.ladder || {};
  const stages = Object.values(ladder);
  const weighted = stages.reduce((acc, s) => acc + (s.weight * s.score), 0);
  const contribution = snap.contribution || {};
  const band = contribution.band || 'at_risk';
  const objs = snap.objectives || [];
  const amberRed = objs.filter(o => o.status === 'amber' || o.status === 'red').length;
  const totalMentions = snap.inputs?.mention_count || (allMentions.length || '—');

  document.getElementById('stat-cards').innerHTML = `
    <div class="stat-card">
      <div class="stat-label">Weighted Score</div>
      <div class="stat-value">${weighted.toFixed(1)}</div>
      <div class="stat-sub">/ 100 · AMEC IEF</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Contribution Band</div>
      <div class="stat-value stat-amber">${band.replace('_', ' ').toUpperCase()}</div>
      <div class="stat-sub">Barcelona 4.0</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Objectives at Risk</div>
      <div class="stat-value ${amberRed > 0 ? 'stat-accent' : 'stat-green'}">${amberRed}/${objs.length}</div>
      <div class="stat-sub">Amber or Red</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Mentions</div>
      <div class="stat-value">${totalMentions}</div>
      <div class="stat-sub">In window</div>
    </div>
  `;
}

function renderObjectives(objectives) {
  const el = document.getElementById('objectives-list');
  if (!objectives.length) { el.innerHTML = '<div style="color:var(--text-3);font-size:13px">No objectives found</div>'; return; }
  el.innerHTML = objectives.map(o => {
    const pct = o.target ? Math.round((o.actual / o.target) * 100) : 0;
    const cls = objStatusClass(o.status);
    return `
      <div class="obj-row">
        <div class="obj-dot ${cls}"></div>
        <div class="obj-label">${o.label_en}</div>
        <div class="obj-progress-wrap">
          <div class="obj-progress-bar ${cls}" style="width:${Math.min(pct, 100)}%"></div>
        </div>
        <div class="obj-pct">${pct}%</div>
      </div>
    `;
  }).join('');
}

function renderLadder(ladder) {
  const el = document.getElementById('ladder-bars');
  const order = ['outputs', 'outtakes', 'outcomes', 'impact'];
  const rows = order.map(stage => {
    const s = ladder[stage];
    if (!s) return '';
    return `
      <div class="ladder-row">
        <div class="ladder-top">
          <div class="ladder-stage">${stage}</div>
          <div class="ladder-meta">
            <span class="ladder-weight">×${s.weight}</span>
            <span class="ladder-score">${s.score}</span>
          </div>
        </div>
        <div class="ladder-track">
          <div class="ladder-fill ${stage}" style="width:${s.score}%"></div>
        </div>
      </div>
    `;
  });
  el.innerHTML = rows.join('');
}

function renderMoves(moves) {
  const el = document.getElementById('moves-list');
  if (!moves.length) { el.innerHTML = '<div style="color:var(--text-3);font-size:13px">No moves</div>'; return; }
  el.innerHTML = moves.map(m => `
    <div class="move-row">
      <div class="move-num">${m.id}</div>
      <div>
        <div class="move-text">${m.en || m.bm}</div>
        ${m.bm && m.en ? `<div class="move-bm">${m.bm}</div>` : ''}
        <div class="move-obj-tags">
          ${(m.objective_ids || []).map(id => `<span class="move-obj-tag">${id}</span>`).join('')}
          ${m.horizon_days ? `<span class="move-obj-tag">${m.horizon_days}d</span>` : ''}
        </div>
      </div>
    </div>
  `).join('');
}

function renderNarrative(contribution) {
  const el = document.getElementById('narrative-content');
  const en = contribution.narrative_en || '—';
  const bm = contribution.narrative_bm || '';
  el.innerHTML = `
    <div class="narrative-en">${en}</div>
    ${bm ? `<div class="narrative-bm">${bm}</div>` : ''}
  `;
}

/* ===========================
   MENTIONS
   =========================== */
async function loadMentionsData() {
  try {
    const data = await apiFetch(`/workspaces/${WS_ID}/mentions`);
    allMentions = data.items || [];
    renderMentions();
  } catch (e) {
    console.error('Mentions load error:', e);
  }
}

function filterMentions(filter, btn) {
  currentMentionFilter = filter;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  renderMentions();
}

function renderMentions() {
  const search = (document.getElementById('mention-search')?.value || '').toLowerCase();
  let items = allMentions;

  if (currentMentionFilter === 'three_r') items = items.filter(m => m.three_r?.flags?.length);
  if (currentMentionFilter === 'east_my') items = items.filter(m => m.east_my);
  if (search) items = items.filter(m =>
    (m.text || '').toLowerCase().includes(search) ||
    (m.outlet_name || '').toLowerCase().includes(search) ||
    (m.state || '').toLowerCase().includes(search)
  );

  const el = document.getElementById('mentions-grid');
  if (!items.length) {
    el.innerHTML = `<div style="color:var(--text-3);font-size:14px;grid-column:1/-1;padding:40px;text-align:center">No mentions found</div>`;
    return;
  }

  el.innerHTML = items.map(m => {
    const threeR = m.three_r?.flags?.length > 0;
    return `
      <div class="mention-card ${threeR ? 'three-r-flag' : ''}" onclick="showMentionDetail('${m.id}')">
        <div class="mention-header">
          <span class="mention-platform ${platformClass(m.platform)}">${m.platform || 'other'}</span>
          <span class="mention-outlet">${m.outlet_name || ''}</span>
          ${m.lang ? `<span style="font-size:10px;color:var(--text-3)">${m.lang.toUpperCase()}</span>` : ''}
        </div>
        <div class="mention-text">${m.text || m.excerpt || '—'}</div>
        <div class="mention-footer">
          <span class="sentiment-badge ${sentimentClass(m.sentiment?.label)}">
            ${sentimentEmoji(m.sentiment?.label)} ${m.sentiment?.label || 'neu'}
          </span>
          <div class="mention-meta">
            ${m.east_my ? '<span class="east-my-badge">East MY</span>' : ''}
            ${m.state ? `<span class="mention-state">${m.state}</span>` : ''}
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function showMentionDetail(id) {
  const m = allMentions.find(x => x.id === id);
  if (!m) return;
  const threeR = m.three_r?.flags?.length > 0;
  openModal(`Mention · ${m.outlet_name || m.platform}`, `
    <div class="detail-key">Platform</div>
    <div class="detail-val">${m.platform} · ${m.lang?.toUpperCase()}</div>
    <div class="detail-key">Outlet</div>
    <div class="detail-val">${m.outlet_name || '—'} (${m.outlet_tier || '—'})</div>
    <div class="detail-key">Full Text</div>
    <div style="font-size:13px;color:var(--text-1);line-height:1.6;background:var(--bg-3);padding:12px;border-radius:8px;margin-bottom:12px">${m.text || '—'}</div>
    <div class="detail-key">Sentiment</div>
    <div class="detail-val">${m.sentiment?.label} (score: ${m.sentiment?.score})</div>
    <div class="detail-key">State</div>
    <div class="detail-val">${m.state || '—'} · East MY: ${m.east_my ? 'Yes' : 'No'}</div>
    ${threeR ? `
      <div class="detail-key">3R Flags</div>
      <div class="detail-val">${m.three_r.flags.join(', ').toUpperCase()} · severity: ${m.three_r.severity}</div>
    ` : ''}
    <div class="detail-key">Codes</div>
    <div class="detail-val">${(m.codes || []).join(', ') || '—'}</div>
    <div class="detail-key">Published</div>
    <div class="detail-val">${fmtDate(m.published_at)}</div>
    <div class="modal-actions">
      <button class="btn-secondary" onclick="closeModal()">Close</button>
    </div>
  `);
}

async function syncFeeds() {
  try {
    toast('Syncing Malaysian news RSS feeds…', 'info');
    const res = await apiFetch(`/workspaces/${WS_ID}/mentions/ingest/trigger`, {
      method: 'POST',
      body: JSON.stringify({}),
    });
    await loadMentionsData();
    toast(`Sync complete: ${res.ingested_count || 0} new mentions ingested`, 'success');
  } catch (e) {
    toast(`Feed sync failed: ${e.message}`, 'error');
  }
}

function openIngestModal() {
  openModal('Ingest Webhook Mention', `
    <div class="form-group">
      <label class="form-label">Platform / Source</label>
      <select class="form-select" id="ingest-platform">
        <option value="x">X (Twitter)</option>
        <option value="facebook">Meta (Facebook)</option>
        <option value="telegram">Telegram Broadcast</option>
        <option value="news">News Portal</option>
        <option value="tiktok">TikTok</option>
      </select>
    </div>
    <div class="form-group">
      <label class="form-label">Author / Outlet</label>
      <input class="form-input" id="ingest-author" placeholder="e.g. @sabah_news or Berita Harian" />
    </div>
    <div class="form-group">
      <label class="form-label">Content / Mention Text</label>
      <textarea class="form-textarea" id="ingest-text" placeholder="Enter post or article content (supports BM, English, 3R keywords, East MY locations)..."></textarea>
    </div>
    <div class="modal-actions">
      <button class="btn-secondary" onclick="closeModal()">Cancel</button>
      <button class="btn-primary" onclick="submitIngestWebhook()">Ingest Mention</button>
    </div>
  `);
}

async function submitIngestWebhook() {
  const platform = document.getElementById('ingest-platform').value;
  const author = document.getElementById('ingest-author').value.trim();
  const text = document.getElementById('ingest-text').value.trim();

  if (!text) {
    toast('Content text is required', 'error');
    return;
  }

  try {
    const res = await apiFetch(`/workspaces/${WS_ID}/mentions/ingest/webhook`, {
      method: 'POST',
      body: JSON.stringify({
        platform,
        text,
        author_handle: author.startsWith('@') ? author : undefined,
        author_name: !author.startsWith('@') ? author : undefined,
        outlet_name: !author.startsWith('@') ? author : undefined,
        source_type: platform === 'telegram' ? 'telegram' : 'social',
      }),
    });
    await loadMentionsData();
    closeModal();
    toast('Mention ingested & enriched ✓', 'success');
  } catch (e) {
    toast(`Ingest error: ${e.message}`, 'error');
  }
}


/* ===========================
   EVALUATION
   =========================== */
async function loadEvaluation() {
  try {
    evalData = evalData || await apiFetch(`/workspaces/${WS_ID}/evaluation`);
    renderEvaluationPage(evalData);
  } catch (e) {
    document.getElementById('eval-hero').innerHTML = `<div style="color:var(--text-3)">Could not load evaluation: ${e.message}</div>`;
  }
}

function renderEvaluationPage(snap) {
  const c = snap.contribution || {};
  const band = c.band || 'at_risk';
  const ladder = snap.ladder || {};
  const stages = Object.values(ladder);
  const weighted = stages.reduce((acc, s) => acc + (s.weight * s.score), 0);

  document.getElementById('eval-hero').innerHTML = `
    <div class="eval-title">${snap.title || 'Evaluation'}</div>
    <div class="eval-window">${snap.window?.label || ''} · ${snap.campaign?.name || ''}</div>
    <div class="eval-score-row">
      <div class="eval-score-block">
        <div class="eval-score-val" style="color:var(--accent-2)">${weighted.toFixed(1)}</div>
        <div class="eval-score-label">Weighted Score</div>
      </div>
      <div class="eval-divider"></div>
      <div class="eval-score-block">
        <div class="eval-score-val" style="color:var(--gold)">${c.score_pct ? (c.score_pct * 100).toFixed(0) + '%' : weighted.toFixed(0)}</div>
        <div class="eval-score-label">Contribution</div>
      </div>
      <div class="eval-divider"></div>
      <span class="contribution-band ${bandClass(band)}">${band.replace('_', ' ')}</span>
    </div>
  `;

  const grid = document.getElementById('eval-grid');
  const integrityItems = Object.entries(snap.integrity || {}).map(([k, v]) =>
    `<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);font-size:13px">
      <span style="color:var(--text-2)">${k}</span>
      <span style="color:${v === false ? 'var(--green)' : v === true ? 'var(--red)' : 'var(--text-1)'}; font-family:var(--mono)">${JSON.stringify(v)}</span>
    </div>`
  ).join('');

  const govItems = Object.entries(snap.governance || {}).map(([k, v]) =>
    `<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);font-size:13px">
      <span style="color:var(--text-2)">${k.replace(/_/g,' ')}</span>
      <span style="color:var(--text-1);font-family:var(--mono)">${String(v)}</span>
    </div>`
  ).join('');

  grid.innerHTML = `
    <div class="card">
      <div class="card-header"><h2>Integrity Checks</h2><span class="card-tag">Barcelona 4.0</span></div>
      ${integrityItems || '<div style="color:var(--text-3);font-size:13px">—</div>'}
    </div>
    <div class="card">
      <div class="card-header"><h2>Governance</h2><span class="card-tag">Methodology</span></div>
      ${govItems || '<div style="color:var(--text-3);font-size:13px">—</div>'}
    </div>
  `;
}

/* ===========================
   EXECUTIVE BRIEF / REPORTS
   No AVE is computed anywhere in this module. The preview is print-styled
   HTML rendered server-side, "Print / Save PDF" below uses the browser's
   own print dialog on that HTML, this does not generate a PDF file
   directly, there is no PDF library involved.
   =========================== */
function openExecutiveBriefModal() {
  if (!evalData || !evalData.id) {
    toast('Lock an evaluation snapshot first', 'error');
    return;
  }
  const previewUrl = `${API}/workspaces/${WS_ID}/reports/preview?snapshot_id=${evalData.id}`;
  openModal('Executive Brief', `
    <div style="display:flex;flex-direction:column;gap:14px">
      <div style="display:flex;gap:8px">
        <button class="btn-primary" onclick="printExecutiveBrief()">Print / Save PDF</button>
        <button class="btn-secondary" onclick="toggleScheduleForm()">Schedule Weekly Email</button>
      </div>

      <iframe id="exec-brief-frame" src="${previewUrl}"
        style="width:100%;height:420px;border:1px solid var(--border,#2a2f3a);border-radius:6px;background:#fff"
        title="Executive brief preview"></iframe>

      <div id="schedule-form" style="display:none;flex-direction:column;gap:8px;padding-top:6px;border-top:1px solid var(--border,#2a2f3a)">
        <div style="display:flex;gap:8px">
          <select id="sched-day" style="flex:1">
            <option value="0">Monday</option><option value="1">Tuesday</option>
            <option value="2">Wednesday</option><option value="3">Thursday</option>
            <option value="4">Friday</option><option value="5">Saturday</option>
            <option value="6">Sunday</option>
          </select>
          <input id="sched-hour" type="number" min="0" max="23" value="9" style="width:70px" title="Hour, MYT, 24h" />
        </div>
        <input id="sched-recipients" type="text" placeholder="recipient@aurora.example, comma-separated" />
        <input id="sched-webhook" type="text" placeholder="Webhook URL (optional, public URLs only)" />
        <button class="btn-primary" onclick="submitSchedule()">Save schedule</button>
        <div id="schedule-status" style="font-size:12px;color:var(--text-3)"></div>
      </div>
    </div>
  `);
}

function toggleScheduleForm() {
  const f = document.getElementById('schedule-form');
  f.style.display = f.style.display === 'none' ? 'flex' : 'none';
}

function printExecutiveBrief() {
  const frame = document.getElementById('exec-brief-frame');
  try {
    frame.contentWindow.focus();
    frame.contentWindow.print();
  } catch (e) {
    toast('Open the report in a new tab to print if the inline preview blocks it', 'error');
  }
}

async function submitSchedule() {
  const day_of_week = parseInt(document.getElementById('sched-day').value, 10);
  const hour_myt = parseInt(document.getElementById('sched-hour').value, 10);
  const recipients = document.getElementById('sched-recipients').value
    .split(',').map(s => s.trim()).filter(Boolean);
  const webhook_url = document.getElementById('sched-webhook').value.trim() || null;
  const statusEl = document.getElementById('schedule-status');

  try {
    const sched = await apiFetch(`/workspaces/${WS_ID}/reports/schedule`, {
      method: 'POST',
      body: JSON.stringify({
        snapshot_id: evalData.id, cadence: 'weekly', day_of_week, hour_myt, recipients, webhook_url,
      }),
    });
    const persistNote = sched.persistent
      ? 'Persisted to the database, survives a restart.'
      : 'In-memory only — will NOT survive a server restart until DB store is enabled.';
    statusEl.textContent = `Scheduled. Next run: ${new Date(sched.next_run_at).toLocaleString()}. ${persistNote}`;
    toast('Report schedule saved', 'success');
  } catch (e) {
    statusEl.textContent = '';
    toast(`Schedule failed: ${e.message}`, 'error');
  }
}

async function lockEvaluation() {
  const btn = document.getElementById('btn-lock');
  btn.disabled = true;
  btn.textContent = 'Locking…';
  try {
    const snap = await apiFetch(`/workspaces/${WS_ID}/evaluation/lock`, {
      method: 'POST',
      body: JSON.stringify({ title: 'Jalur Kita — Locked Snapshot' }),
    });
    evalData = snap;
    renderEvaluationPage(snap);
    toast('Snapshot locked successfully ✓', 'success');
  } catch (e) {
    toast(`Lock failed: ${e.message}`, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg> Lock Evaluation Snapshot`;
  }
}

/* ===========================
   WAR ROOMS
   =========================== */
async function loadWarRooms() {
  try {
    const data = await apiFetch(`/workspaces/${WS_ID}/war-rooms`);
    warRoomsData = data.items || [];
    renderWarRooms();
  } catch (e) {
    document.getElementById('warrooms-list').innerHTML = `<div style="color:var(--text-3)">Could not load war rooms: ${e.message}</div>`;
  }
}

function renderWarRooms() {
  const el = document.getElementById('warrooms-list');
  if (!warRoomsData.length) {
    el.innerHTML = `<div style="color:var(--text-3);font-size:14px;padding:40px;text-align:center">No war rooms open</div>`;
    return;
  }
  el.innerHTML = warRoomsData.map(wr => {
    const canContain = wr.status === 'open';
    const canClose = wr.status === 'open' || wr.status === 'contained';
    return `
      <div class="wr-card severity-${wr.severity}">
        <div class="wr-top">
          <div class="wr-title">${wr.title}</div>
          <div class="wr-badges">
            <span class="${statusBadgeClass(wr.status)}">${wr.status}</span>
            <span class="${statusBadgeClass(wr.severity)}">${wr.severity}</span>
          </div>
        </div>
        <div class="wr-meta">
          <span>Opened ${fmtDate(wr.opened_at)}</span>
          <span>${(wr.holdings || []).length} holding(s)</span>
          <span>${(wr.decisions || []).length} decision(s)</span>
          ${wr.three_r?.flags?.length ? `<span style="color:var(--red)">3R: ${wr.three_r.flags.join(', ')}</span>` : ''}
        </div>
        <div class="wr-actions">
          ${canContain ? `<button class="btn-sm" onclick="containWR('${wr.id}')">Contain</button>` : ''}
          ${canClose ? `<button class="btn-sm danger" onclick="closeWR('${wr.id}')">Close</button>` : ''}
          <button class="btn-sm" onclick="addDecisionModal('${wr.id}')">Add Decision</button>
          <button class="btn-sm" onclick="showWRDetail('${wr.id}')">Details</button>
        </div>
      </div>
    `;
  }).join('');
}

function showWRDetail(id) {
  const wr = warRoomsData.find(w => w.id === id);
  if (!wr) return;
  const decisions = (wr.decisions || []).map(d =>
    `<div style="padding:8px 0;border-bottom:1px solid var(--border);font-size:13px">
      <span style="color:var(--text-3);font-size:11px">${fmtDate(d.at)}</span><br/>
      <strong>${d.action}</strong>${d.note ? ` — ${d.note}` : ''}
    </div>`
  ).join('');
  const residue = (wr.queues?.residue || []).map(r =>
    `<div style="padding:6px 0;font-size:12px;color:var(--text-2)">${r.asset} · ${r.location || ''} · <span style="color:var(--amber)">${r.status}</span></div>`
  ).join('');
  openModal(`War Room · ${wr.title}`, `
    <div class="detail-key">Status / Severity</div>
    <div style="display:flex;gap:6px;margin-bottom:12px">
      <span class="${statusBadgeClass(wr.status)}">${wr.status}</span>
      <span class="${statusBadgeClass(wr.severity)}">${wr.severity}</span>
    </div>
    <div class="detail-key">3R</div>
    <div class="detail-val">${wr.three_r?.flags?.join(', ') || '—'} · ${wr.three_r?.posture || ''}</div>
    <div class="detail-key">Trigger</div>
    <div class="detail-val">${wr.trigger?.kind || '—'}</div>
    ${residue ? `<div class="detail-key">Residue</div><div>${residue}</div>` : ''}
    <div class="detail-key">Decisions (${(wr.decisions||[]).length})</div>
    <div>${decisions || '<div style="color:var(--text-3);font-size:13px">None</div>'}</div>
    <div class="modal-actions" style="margin-top:12px">
      <button class="btn-secondary" onclick="closeModal()">Close</button>
    </div>
  `);
}

async function containWR(id) {
  try {
    const updated = await apiFetch(`/workspaces/${WS_ID}/war-rooms/${id}/contain`, { method: 'POST', body: '{}' });
    const idx = warRoomsData.findIndex(w => w.id === id);
    if (idx >= 0) warRoomsData[idx] = updated;
    renderWarRooms();
    toast('War room contained', 'success');
  } catch (e) { toast(e.message, 'error'); }
}

async function closeWR(id) {
  try {
    const updated = await apiFetch(`/workspaces/${WS_ID}/war-rooms/${id}/close`, { method: 'POST', body: '{}' });
    const idx = warRoomsData.findIndex(w => w.id === id);
    if (idx >= 0) warRoomsData[idx] = updated;
    renderWarRooms();
    toast('War room closed', 'success');
  } catch (e) { toast(e.message, 'error'); }
}

function addDecisionModal(wrId) {
  openModal('Add Decision', `
    <div class="form-group">
      <label class="form-label">Action</label>
      <input class="form-input" id="dec-action" placeholder="e.g. escalate, brief-approved…" />
    </div>
    <div class="form-group">
      <label class="form-label">Note</label>
      <textarea class="form-textarea" id="dec-note" placeholder="Additional context…"></textarea>
    </div>
    <div class="modal-actions">
      <button class="btn-secondary" onclick="closeModal()">Cancel</button>
      <button class="btn-primary" onclick="submitDecision('${wrId}')">Add Decision</button>
    </div>
  `);
}

async function submitDecision(wrId) {
  const action = document.getElementById('dec-action').value.trim();
  const note = document.getElementById('dec-note').value.trim();
  if (!action) { toast('Action is required', 'error'); return; }
  try {
    const updated = await apiFetch(`/workspaces/${WS_ID}/war-rooms/${wrId}/decisions`, {
      method: 'POST',
      body: JSON.stringify({ action, note }),
    });
    const idx = warRoomsData.findIndex(w => w.id === wrId);
    if (idx >= 0) warRoomsData[idx] = updated;
    closeModal();
    renderWarRooms();
    toast('Decision added', 'success');
  } catch (e) { toast(e.message, 'error'); }
}

function openNewWarRoomModal() {
  openModal('New War Room', `
    <div class="form-group">
      <label class="form-label">Title</label>
      <input class="form-input" id="wr-title" placeholder="Describe the issue…" />
    </div>
    <div class="form-group">
      <label class="form-label">Severity</label>
      <select class="form-select" id="wr-severity">
        <option value="low">Low</option>
        <option value="medium" selected>Medium</option>
        <option value="high">High</option>
        <option value="critical">Critical</option>
      </select>
    </div>
    <div class="form-group">
      <label class="form-label">3R Flags (optional)</label>
      <select class="form-select" id="wr-3r" multiple style="height:80px">
        <option value="race">Race</option>
        <option value="religion">Religion</option>
        <option value="royalty">Royalty</option>
      </select>
    </div>
    <div class="modal-actions">
      <button class="btn-secondary" onclick="closeModal()">Cancel</button>
      <button class="btn-primary" onclick="submitNewWarRoom()">Open War Room</button>
    </div>
  `);
}

async function submitNewWarRoom() {
  const title = document.getElementById('wr-title').value.trim();
  const severity = document.getElementById('wr-severity').value;
  const flags = Array.from(document.getElementById('wr-3r').selectedOptions).map(o => o.value);
  if (!title) { toast('Title is required', 'error'); return; }
  try {
    const wr = await apiFetch(`/workspaces/${WS_ID}/war-rooms`, {
      method: 'POST',
      body: JSON.stringify({
        title, severity,
        trigger: { kind: 'manual', at: new Date().toISOString() },
        three_r: flags.length ? { flags, posture: 'self_regulated_not_directed' } : undefined,
      }),
    });
    warRoomsData.push(wr);
    closeModal();
    renderWarRooms();
    toast('War room opened', 'success');
  } catch (e) { toast(e.message, 'error'); }
}

/* ===========================
   HOLDINGS
   =========================== */
async function loadHoldings() {
  try {
    // Holdings are stored by ID; try to collect from war rooms
    const data = await apiFetch(`/workspaces/${WS_ID}/war-rooms`);
    const wrs = data.items || [];
    const ids = [];
    for (const wr of wrs) {
      for (const h of (wr.holdings || [])) { if (h.id) ids.push(h.id); }
    }
    // Fetch each holding
    holdingsData = [];
    await Promise.all(ids.map(async id => {
      try {
        const h = await apiFetch(`/workspaces/${WS_ID}/holdings/${id}`);
        holdingsData.push(h);
      } catch {}
    }));
    renderHoldings();
  } catch (e) {
    document.getElementById('holdings-list').innerHTML = `<div style="color:var(--text-3)">Could not load holdings: ${e.message}</div>`;
  }
}

function renderHoldings() {
  const el = document.getElementById('holdings-list');
  if (!holdingsData.length) {
    el.innerHTML = `<div style="color:var(--text-3);font-size:14px;padding:40px;text-align:center">No holdings yet. Click "Draft Holding Brief" to generate one.</div>`;
    return;
  }
  el.innerHTML = holdingsData.map(h => {
    const linesHTML = Object.keys(h.lines || {}).length
      ? `<div class="hld-lines">${Object.entries(h.lines).map(([lang, text]) => `
          <div class="hld-line-block">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
              <span class="hld-line-lang">${lang.toUpperCase()}</span>
              <button class="btn-sm" style="padding:2px 8px;font-size:11px" onclick="navigator.clipboard.writeText(${JSON.stringify(text)});toast('Copied to clipboard!','success')">Copy</button>
            </div>
            <div class="hld-line-text">${text}</div>
          </div>`).join('')}</div>`
      : '';
    const doNotSay = (h.do_not_say || []).length
      ? `<div style="font-size:12px;color:var(--red);margin-bottom:8px;background:rgba(239,68,68,0.1);padding:6px 10px;border-radius:6px"><strong>Do not say:</strong> ${h.do_not_say.join(' · ')}</div>`
      : '';
    const gaps = (h.gaps || []).length
      ? `<div style="font-size:12px;color:var(--yellow);margin-bottom:8px;background:rgba(234,179,8,0.1);padding:6px 10px;border-radius:6px"><strong>Information gaps:</strong> ${h.gaps.join(' · ')}</div>`
      : '';
    const ops = (h.ops || []).length
      ? `<div style="font-size:12px;margin-bottom:10px;background:var(--bg-3);padding:8px 12px;border-radius:6px">
          <strong>Operational Next Steps (SLA):</strong>
          <ul style="margin:4px 0 0 16px;padding:0">
            ${h.ops.map(op => `<li>${op.action} <span style="color:var(--text-3);font-size:11px">(${op.owner_role || 'comms'} · ${op.sla_hours || 24}h)</span></li>`).join('')}
          </ul>
        </div>`
      : '';
    const transitions = ['draft','legal_review','approved','sent_external']
      .filter(s => s !== h.status)
      .map(s => `<button class="btn-sm" onclick="transitionHolding('${h.id}','${s}')">${s.replace('_',' ')}</button>`).join('');
    return `
      <div class="hld-card">
        <div class="hld-top">
          <div class="hld-title">Brief ${h.brief_id || h.id}</div>
          <div style="display:flex;gap:6px;align-items:center">
            <span class="${holdingStatusClass(h.status)}">${h.status.replace('_',' ')}</span>
            <span style="font-size:11px;color:var(--text-3)">v${h.version} · ${h.locale} · ${h.audience} · ${h.model_version || 'nadi-brief'}</span>
          </div>
        </div>
        <div class="hld-meta">${h.war_room_id ? `War Room: ${h.war_room_id}` : 'Standalone brief'} ${h.posture ? `· Posture: ${h.posture}` : ''}</div>
        ${linesHTML}
        ${gaps}
        ${doNotSay}
        ${ops}
        <div class="hld-guardrail">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
          Human must send · AVE disabled (Barcelona 4.0) · Auto-publish off
        </div>
        <div class="wr-actions" style="margin-top:10px">${transitions}</div>
      </div>
    `;
  }).join('');
}

async function transitionHolding(hldId, status) {
  try {
    const h = await apiFetch(`/workspaces/${WS_ID}/holdings/${hldId}/transition`, {
      method: 'POST',
      body: JSON.stringify({ status }),
    });
    const idx = holdingsData.findIndex(x => x.id === hldId);
    if (idx >= 0) holdingsData[idx] = h;
    renderHoldings();
    toast(`Holding → ${status.replace('_', ' ')}`, 'success');
  } catch (e) { toast(e.message, 'error'); }
}

function openNewBriefModal() {
  const wrOptions = warRoomsData.map(wr =>
    `<option value="${wr.id}">${wr.title.substring(0, 50)}</option>`
  ).join('');
  openModal('Draft Holding Brief (LLM & Barcelona 4.0)', `
    <div class="form-group">
      <label class="form-label">War Room (optional)</label>
      <select class="form-select" id="brief-wr">
        <option value="">— Standalone —</option>
        ${wrOptions}
      </select>
    </div>
    <div class="form-group">
      <label class="form-label">Locale</label>
      <select class="form-select" id="brief-locale">
        <option value="bilingual">Bilingual (EN + BM)</option>
        <option value="en">English only</option>
        <option value="bm">Bahasa Malaysia only</option>
      </select>
    </div>
    <div class="form-group">
      <label class="form-label">Audience</label>
      <select class="form-select" id="brief-audience">
        <option value="press">Press / Media</option>
        <option value="internal">Internal Comms</option>
        <option value="social">Social Media Response</option>
        <option value="regulator">Regulator / Ministry</option>
      </select>
    </div>
    <div class="form-group">
      <label class="form-label">Additional Comms Context (optional)</label>
      <input class="form-input" id="brief-context" placeholder="e.g. 48h retail sweep ordered, legal review pending" />
    </div>
    <div class="form-group" style="display:flex;gap:8px;align-items:center;margin-top:8px">
      <input type="checkbox" id="brief-tabletop" style="width:16px;height:16px;cursor:pointer" />
      <label for="brief-tabletop" style="font-size:13px;color:var(--text-2);cursor:pointer">Tabletop Crisis Simulation Mode (watermarks output)</label>
    </div>
    <div style="font-size:12px;color:var(--text-3);background:var(--bg-3);padding:10px;border-radius:8px;border-left:3px solid var(--accent);margin-top:10px">
      Human-send enforced · AVE disabled · Guarded by Barcelona Principles 4.0
    </div>
    <div class="modal-actions">
      <button class="btn-secondary" onclick="closeModal()">Cancel</button>
      <button class="btn-primary" onclick="submitNewBrief()">Generate AI Brief</button>
    </div>
  `);
}

async function submitNewBrief() {
  const war_room_id = document.getElementById('brief-wr').value || null;
  const locale = document.getElementById('brief-locale').value;
  const audience = document.getElementById('brief-audience').value;
  const extra_context = document.getElementById('brief-context').value.trim() || undefined;
  const tabletop = document.getElementById('brief-tabletop').checked;

  try {
    toast('Generating holding brief…', 'info');
    const h = await apiFetch(`/workspaces/${WS_ID}/briefs`, {
      method: 'POST',
      body: JSON.stringify({
        kind: 'holding',
        war_room_id,
        locale,
        audience,
        extra_context,
        tabletop,
        use_llm: true,
      }),
    });
    holdingsData.unshift(h);
    closeModal();
    renderHoldings();
    toast('Holding brief generated ✓', 'success');
  } catch (e) { toast(e.message, 'error'); }
}


/* ===========================
   INIT
   =========================== */
document.addEventListener('DOMContentLoaded', async () => {
  try {
    await Promise.all([loadDashboard(), loadMentionsData()]);
  } catch (e) {
    toast('Could not connect to API — is the server running on :8000?', 'error');
  }
});
