/* ── State ────────────────────────────────────────────────────────────────── */
let busy         = false;
let lastMsgId    = null;
let lastRating   = null;
let msgSeq       = 0;

// Stores chart context keyed by plotly container id, used when switching types.
const _chartData = new Map();

/* ── Bootstrap ───────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  loadFeedbackHistory();
  document.getElementById('chatInput').focus();
});

/* ═══════════════════════════════════════════════════════════════════════════
   CHAT
   ═══════════════════════════════════════════════════════════════════════════ */

function handleKeyDown(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 140) + 'px';
}

function useExample(btn) {
  document.getElementById('chatInput').value = btn.textContent.trim();
  sendMessage();
}

async function sendMessage() {
  if (busy) return;
  const input = document.getElementById('chatInput');
  const text  = input.value.trim();
  if (!text) return;

  // Reset
  input.value = '';
  input.style.height = 'auto';
  busy = true;
  document.getElementById('sendBtn').disabled = true;
  lastRating = null;
  resetRateBtns();

  hideWelcome();
  addUserBubble(text);
  const thinkId = addThinking();

  try {
    const res  = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });
    const data = await res.json();
    removeThinking(thinkId);
    if (!res.ok) throw new Error(data.detail || 'Server error');
    addAgentBubble(data);
  } catch (err) {
    removeThinking(thinkId);
    addErrorBubble(err.message);
  } finally {
    busy = false;
    document.getElementById('sendBtn').disabled = false;
    input.focus();
    // Show rating controls for the new response
    showRatingRow();
  }
}

/* ── Message renderers ────────────────────────────────────────────────────── */

function addUserBubble(text) {
  const div = make('div', 'msg user');
  div.innerHTML = `
    <div class="msg-avatar">U</div>
    <div class="msg-body">
      <div class="bubble">${esc(text)}</div>
    </div>`;
  append(div);
}

function addAgentBubble(data) {
  msgSeq++;
  const id      = `m${msgSeq}`;
  const chartId = `chart-${msgSeq}`;
  lastMsgId = id;

  const div = make('div', 'msg agent');
  div.id = id;

  let cards = '';
  if (data.error) {
    cards = `<div class="error-bubble">Error: ${esc(data.error)}</div>`;
  } else {
    if (data.sql_result)     cards += makeCard('Results',        'table',  tableBody(data),                 true);
    if (data.chart_json)     cards += makeCard('Chart',          'chart',  chartBody(data, chartId),        false);
    if (data.interpretation) cards += makeCard('Interpretation', 'interp', interpBody(data.interpretation), false);
  }

  div.innerHTML = `
    <div class="msg-avatar">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <ellipse cx="12" cy="5" rx="9" ry="3"/>
        <path d="M3 5v6c0 1.66 4.03 3 9 3s9-1.34 9-3V5"/>
        <path d="M3 11v6c0 1.66 4.03 3 9 3s9-1.34 9-3v-6"/>
      </svg>
    </div>
    <div class="msg-body">
      <div class="bubble"><div class="response-cards">${cards}</div></div>
      <div class="msg-actions">
        <button class="act-btn" id="${id}-up"   onclick="quickRate('${id}','up')">👍 Good</button>
        <button class="act-btn" id="${id}-down" onclick="quickRate('${id}','down')">👎 Poor</button>
      </div>
    </div>`;

  append(div);

  // Render Plotly chart after DOM insertion
  if (data.chart_json) {
    _chartData.set(chartId, {
      dataframe_json: data.dataframe_json,
      question:       data.question,
      sql_query:      data.sql_query,
    });
    renderPlotlyChart(document.getElementById(chartId), data.chart_json);
  }

  div.querySelectorAll('code.language-sql').forEach(b => hljs.highlightElement(b));
}

function addErrorBubble(msg) {
  const div = make('div', 'msg agent');
  div.innerHTML = `
    <div class="msg-avatar">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <ellipse cx="12" cy="5" rx="9" ry="3"/>
        <path d="M3 5v6c0 1.66 4.03 3 9 3s9-1.34 9-3V5"/>
        <path d="M3 11v6c0 1.66 4.03 3 9 3s9-1.34 9-3v-6"/>
      </svg>
    </div>
    <div class="msg-body">
      <div class="error-bubble">⚠ ${esc(msg)}</div>
    </div>`;
  append(div);
}

/* ── Card helpers ─────────────────────────────────────────────────────────── */

const CARD_ICONS = {
  sql: `<path d="M4 4h16v3H4zM4 11h16M4 17h10" stroke="currentColor" stroke-width="2" fill="none"/>`,
  table: `<rect x="3" y="3" width="18" height="18" rx="2" fill="none" stroke="currentColor" stroke-width="2"/>
          <path d="M3 9h18M9 21V9" stroke="currentColor" stroke-width="2"/>`,
  chart: `<polyline points="22 12 18 12 15 21 9 3 6 12 2 12" stroke="currentColor" stroke-width="2" fill="none"/>`,
  interp: `<circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="2" fill="none"/>
           <line x1="12" y1="8" x2="12" y2="12" stroke="currentColor" stroke-width="2"/>
           <circle cx="12" cy="16" r="0.5" fill="currentColor" stroke="currentColor" stroke-width="2"/>`,
};

function makeCard(title, type, bodyHtml, startClosed) {
  const closed = startClosed ? 'closed' : '';
  const hidden = startClosed ? 'hidden' : '';
  return `
    <div class="res-card">
      <div class="res-card-header ${closed}" onclick="toggleCard(this)">
        <div class="res-card-title">
          <svg viewBox="0 0 24 24" fill="none" width="13" height="13">${CARD_ICONS[type] || ''}</svg>
          ${title}
        </div>
        <svg class="chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>
      <div class="res-card-body ${hidden}">${bodyHtml}</div>
    </div>`;
}

function sqlBody(sql) {
  return `<div class="sql-block"><pre><code class="language-sql">${esc(sql)}</code></pre></div>`;
}

function tableBody(data) {
  // Prefer JSON data for clean table rendering
  let rows = [];
  try { rows = JSON.parse(data.dataframe_json || '[]'); } catch {}

  if (!rows.length) {
    if (data.sql_result) {
      return `<pre style="font-size:12px;font-family:var(--mono);color:var(--txt1);
                          overflow-x:auto;white-space:pre;">${esc(data.sql_result)}</pre>
              <div class="row-count">${data.row_count} row${data.row_count !== 1 ? 's' : ''}</div>`;
    }
    return '<p style="color:var(--txt2);font-size:12px;">No rows returned.</p>';
  }

  const cols = Object.keys(rows[0]);
  let th = cols.map(c => `<th>${esc(c)}</th>`).join('');
  const displayRows = rows.slice(0, 100);
  let tb = displayRows.map(r =>
    `<tr>${cols.map(c => `<td>${esc(r[c] == null ? '' : String(r[c]))}</td>`).join('')}</tr>`
  ).join('');

  const extra = data.row_count > 100 ? ` (showing 100 of ${data.row_count})` : '';
  return `<div class="tbl-wrap">
    <table class="data-table">
      <thead><tr>${th}</tr></thead>
      <tbody>${tb}</tbody>
    </table>
  </div>
  <div class="row-count">${data.row_count} row${data.row_count !== 1 ? 's' : ''}${extra}</div>`;
}

function chartBody(data, chartId) {
  const options     = data.chart_options && data.chart_options.length ? data.chart_options : [data.chart_type || 'bar'];
  const recommended = data.chart_type || options[0];

  const pills = options.map(type => {
    const active = type === recommended;
    return `<button class="chart-pill${active ? ' active' : ''}"
      onclick="switchChart('${chartId}','${type}',this)">${type}${active ? ' &#10022;' : ''}</button>`;
  }).join('');

  const reasonHtml = data.chart_reason
    ? `<div class="chart-reason">&#10022; ${esc(data.chart_reason)}</div>`
    : '';

  return `
    <div class="chart-controls">
      <div class="chart-type-selector">${pills}</div>
      ${reasonHtml}
    </div>
    <div class="plotly-chart" id="${chartId}"></div>`;
}

function renderPlotlyChart(container, chartJson) {
  if (!container) return;
  try {
    const fig = JSON.parse(chartJson);
    Plotly.newPlot(container, fig.data, fig.layout || {}, {
      responsive:     true,
      displayModeBar: true,
      displaylogo:    false,
      modeBarButtonsToRemove: ['lasso2d', 'select2d'],
    });
  } catch (e) {
    container.innerHTML = `<div class="error-bubble">Chart render error: ${esc(e.message)}</div>`;
  }
}

async function switchChart(chartId, chartType, btn) {
  const container = document.getElementById(chartId);
  const ctx       = _chartData.get(chartId);
  if (!container || !ctx) return;

  // Update active pill immediately
  btn.closest('.chart-type-selector').querySelectorAll('.chart-pill')
    .forEach(p => {
      const isThis = p === btn;
      p.classList.toggle('active', isThis);
      p.textContent = p.textContent.replace(' ✦', '') + (isThis ? ' ✦' : '');
    });

  // Show loading state inside the chart area
  Plotly.purge(container);
  container.innerHTML = '<div class="chart-loading">Generating chart…</div>';

  try {
    const res = await fetch('/api/chart', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        dataframe_json: ctx.dataframe_json,
        question:       ctx.question,
        sql_query:      ctx.sql_query,
        chart_type:     chartType,
      }),
    });
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || 'Server error');
    container.innerHTML = '';
    renderPlotlyChart(container, result.chart_json);
  } catch (err) {
    container.innerHTML = `<div class="error-bubble">Failed to switch chart: ${esc(err.message)}</div>`;
  }
}

function interpBody(text) {
  return `<div class="interp-text">${esc(text)}</div>`;
}

function toggleCard(header) {
  header.classList.toggle('closed');
  header.nextElementSibling.classList.toggle('hidden');
}

/* ── Thinking indicator ───────────────────────────────────────────────────── */

let thinkSeq = 0;
function addThinking() {
  const id = `think${++thinkSeq}`;
  const div = make('div', 'msg agent');
  div.id = id;
  div.innerHTML = `
    <div class="msg-avatar">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <ellipse cx="12" cy="5" rx="9" ry="3"/>
        <path d="M3 5v6c0 1.66 4.03 3 9 3s9-1.34 9-3V5"/>
        <path d="M3 11v6c0 1.66 4.03 3 9 3s9-1.34 9-3v-6"/>
      </svg>
    </div>
    <div class="msg-body">
      <div class="thinking-bubble">
        <div class="dots"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>
        Analyzing your question…
      </div>
    </div>`;
  append(div);
  return id;
}
function removeThinking(id) { document.getElementById(id)?.remove(); }

/* ── Clear & welcome ──────────────────────────────────────────────────────── */

function hideWelcome() {
  document.getElementById('welcomeScreen')?.remove();
}

document.getElementById('clearChatBtn').addEventListener('click', () => {
  document.getElementById('messages').innerHTML = `
    <div class="welcome-screen" id="welcomeScreen">
      <div class="welcome-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <ellipse cx="12" cy="5" rx="9" ry="3"/>
          <path d="M3 5v6c0 1.66 4.03 3 9 3s9-1.34 9-3V5"/>
          <path d="M3 11v6c0 1.66 4.03 3 9 3s9-1.34 9-3v-6"/>
        </svg>
      </div>
      <h2>Northwind SQL Analyst</h2>
      <p>Ask anything about customers, orders, products, or employees.</p>
      <div class="example-grid">
        <button class="example-chip" onclick="useExample(this)">Top 10 customers by revenue</button>
        <button class="example-chip" onclick="useExample(this)">Monthly sales trend this year</button>
        <button class="example-chip" onclick="useExample(this)">Products with low stock</button>
        <button class="example-chip" onclick="useExample(this)">Employee sales performance</button>
        <button class="example-chip" onclick="useExample(this)">Orders pending shipment</button>
        <button class="example-chip" onclick="useExample(this)">Top suppliers by spend</button>
      </div>
    </div>`;
  lastMsgId  = null;
  lastRating = null;
  hideRatingRow();
  resetRateBtns();
});

/* ═══════════════════════════════════════════════════════════════════════════
   FEEDBACK
   ═══════════════════════════════════════════════════════════════════════════ */

/* Quick-rate buttons on each message */
function quickRate(msgId, direction) {
  lastMsgId  = msgId;
  lastRating = direction;
  // Highlight sidebar rating buttons too
  syncRateBtns(direction);
  // Persist
  postFeedback({ message_id: msgId, rating: direction, text: direction === 'up' ? 'Good response' : 'Poor response', type: 'response_feedback' });
  // Offer sidebar
  switchTab('feedback');
}

/* Sidebar rating buttons */
function castRating(direction) {
  if (!lastMsgId) return;
  lastRating = direction;
  syncRateBtns(direction);
  // Also mark the inline buttons
  markInlineBtns(lastMsgId, direction);
  postFeedback({ message_id: lastMsgId, rating: direction, text: direction === 'up' ? 'Good response' : 'Poor response', type: 'response_feedback' });
}

function showRatingRow() {
  document.getElementById('rateHint').style.display = 'none';
  document.getElementById('ratingRow').style.display = 'flex';
  resetRateBtns();
}

function hideRatingRow() {
  document.getElementById('rateHint').style.display = '';
  document.getElementById('ratingRow').style.display = 'none';
}

function syncRateBtns(direction) {
  document.getElementById('rateUp').classList.toggle('active-up',   direction === 'up');
  document.getElementById('rateDown').classList.toggle('active-down', direction === 'down');
}

function resetRateBtns() {
  document.getElementById('rateUp')?.classList.remove('active-up');
  document.getElementById('rateDown')?.classList.remove('active-down');
}

function markInlineBtns(msgId, direction) {
  document.getElementById(`${msgId}-up`)?.classList.toggle('is-up',   direction === 'up');
  document.getElementById(`${msgId}-down`)?.classList.toggle('is-down', direction === 'down');
}

/* Style feedback submission */
async function submitStyleFeedback() {
  const text = document.getElementById('feedbackText').value.trim();
  if (!text) return;

  await postFeedback({ message_id: lastMsgId, rating: lastRating, text, type: 'style_feedback' });
  document.getElementById('feedbackText').value = '';
  loadFeedbackHistory();

  // Switch to Prompt Editor and auto-generate a suggestion
  switchTab('prompt');
  await generateSuggestionFromText(text);
}

async function postFeedback(payload) {
  try {
    await fetch('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    loadFeedbackHistory();
  } catch {}
}

async function loadFeedbackHistory() {
  try {
    const res  = await fetch('/api/feedback');
    const data = await res.json();
    renderFeedbackList(data.feedback || []);
  } catch {}
}

function renderFeedbackList(items) {
  const section = document.getElementById('feedbackHistorySection');
  const list    = document.getElementById('feedbackList');
  if (!items.length) { section.style.display = 'none'; return; }

  section.style.display = '';
  list.innerHTML = items.slice(-6).reverse().map(f => {
    const badgeClass = f.type === 'style_feedback' ? 'style' : (f.rating === 'up' ? 'up' : 'down');
    const badgeText  = f.type === 'style_feedback' ? 'Style' : (f.rating === 'up' ? '👍' : '👎');
    return `<div class="fb-item">
      <div class="fb-item-top">
        <span class="fb-badge ${badgeClass}">${badgeText}</span>
        <span class="fb-time">${relTime(f.created_at)}</span>
      </div>
      <div class="fb-text">${esc(f.text)}</div>
    </div>`;
  }).join('');
}

/* ═══════════════════════════════════════════════════════════════════════════
   PROMPT SUGGESTIONS
   ═══════════════════════════════════════════════════════════════════════════ */

/* AI suggestion from sidebar "AI Suggest" button */
async function generateSuggestion() {
  // Collect recent style feedback as the source
  let feedbackText = document.getElementById('feedbackText').value.trim();
  if (!feedbackText) {
    try {
      const res  = await fetch('/api/feedback');
      const data = await res.json();
      const style = (data.feedback || []).filter(f => f.type === 'style_feedback');
      if (style.length) feedbackText = style.slice(-3).map(f => f.text).join('; ');
    } catch {}
  }
  if (!feedbackText) { setStatus('Enter or submit feedback first', 'var(--yellow)'); return; }
  await generateSuggestionFromText(feedbackText);
}

async function generateSuggestionFromText(feedbackText) {
  const btn = document.getElementById('suggestBtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner-inline"></span>Generating…';

  try {
    const res  = await fetch('/api/system-prompt/suggest', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ feedback_text: feedbackText }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed');
    showSuggestion(data.suggestion);
  } catch (e) {
    setStatus(`Suggestion failed: ${e.message}`, 'var(--red)');
  } finally {
    btn.disabled = false;
    btn.textContent = 'AI Suggest from Feedback';
  }
}

function showSuggestion(text) {
  const panel = document.getElementById('suggestionPanel');
  document.getElementById('suggestionEditor').value = text;
  panel.style.display = 'flex';
}

async function applySuggestion() {
  const template = document.getElementById('suggestionEditor').value.trim();
  if (!template) return;
  try {
    const res = await fetch('/api/system-prompt', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ template }),
    });
    if (res.ok) {
      dismissSuggestion();
      setStatus('Suggestion applied — new queries will use it');
    } else {
      const e = await res.json();
      setStatus(e.detail || 'Apply failed', 'var(--red)');
    }
  } catch { setStatus('Apply failed', 'var(--red)'); }
}

function dismissSuggestion() {
  document.getElementById('suggestionPanel').style.display = 'none';
}

function setStatus(msg, color = 'var(--green)') {
  const el = document.getElementById('saveStatus');
  el.style.color = color;
  el.textContent = msg;
  setTimeout(() => { el.textContent = ''; }, 3500);
}

/* ═══════════════════════════════════════════════════════════════════════════
   TABS
   ═══════════════════════════════════════════════════════════════════════════ */

function switchTab(name) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.toggle('active', p.id === `tab-${name}`));
}

/* ═══════════════════════════════════════════════════════════════════════════
   HELPERS
   ═══════════════════════════════════════════════════════════════════════════ */

function esc(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#039;');
}

function make(tag, cls) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  return el;
}

function append(el) {
  const msgs = document.getElementById('messages');
  msgs.appendChild(el);
  msgs.scrollTop = msgs.scrollHeight;
}

function relTime(iso) {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  if (diff < 60000)   return 'just now';
  if (diff < 3600000) return Math.floor(diff / 60000) + 'm ago';
  if (diff < 86400000)return Math.floor(diff / 3600000) + 'h ago';
  return new Date(iso).toLocaleDateString();
}
