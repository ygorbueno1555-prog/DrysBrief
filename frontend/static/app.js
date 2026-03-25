/* ============================================================
   CORTIQ DECISION COPILOT — Frontend v3
   Claude-powered · Gap detection · Evidence trail · Comparison
   ============================================================ */

let currentMode      = 'equity';
let currentES        = null;
let reportBuffer     = '';
let renderFrame      = null;
let startTime        = null;
let sourcesMap       = [];  // [{title, url, source_type}] indexed from 1
let currentEvaluation = null;  // evaluation metrics from last SSE stream

// ── DOM ──────────────────────────────────────────────────
const $ = id => document.getElementById(id);

const equityForm    = $('equity-form');
const startupForm   = $('startup-form');
const inputPanel    = $('input-panel');
const statusPanel   = $('status-panel');
const statusDot     = $('status-dot');
const statusText    = $('status-text');
const queriesList   = $('queries-list');
const emptyState    = $('empty-state');
const verdictBar    = $('verdict-bar');
const verdictTag    = $('verdict-tag');
const verdictMeta   = $('verdict-meta');
const verdictTime   = $('verdict-time');
const reportWrapper = $('report-wrapper');
const reportContent = $('report-content');
const historyView   = $('history-view');

// ── Mode tabs ─────────────────────────────────────────────
document.querySelectorAll('.mode-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    currentMode = tab.dataset.mode;
    document.querySelectorAll('.mode-tab').forEach(t => {
      t.classList.remove('active');
      t.setAttribute('aria-selected', 'false');
    });
    tab.classList.add('active');
    tab.setAttribute('aria-selected', 'true');

    if (currentMode === 'history') {
      inputPanel.style.display = 'none';
      historyView.style.display = 'flex';
      emptyState.style.display = 'none';
      reportWrapper.classList.remove('visible');
      verdictBar.classList.remove('visible');
      statusPanel.classList.remove('visible');
      renderHistoryView();
    } else {
      inputPanel.style.display = '';
      historyView.style.display = 'none';
      equityForm.style.display  = currentMode === 'equity'  ? 'block' : 'none';
      startupForm.style.display = currentMode === 'startup' ? 'block' : 'none';
      resetOutput();
    }
  });
});

// ── Analyze buttons ───────────────────────────────────────
$('btn-equity').addEventListener('click', () => {
  const ticker  = $('ticker').value.trim().toUpperCase();
  const thesis  = $('thesis').value.trim();
  const mandate = $('mandate').value.trim();
  if (!ticker) { highlight('ticker'); return; }

  // Check history for comparison
  const prev = historyFind('equity', ticker);
  const prevVerdict = prev ? encodeURIComponent(prev.verdict || '') : '';
  const prevDate    = prev ? encodeURIComponent(prev.date ? new Date(prev.date).toLocaleDateString('pt-BR') : '') : '';

  startAnalysis(
    `/analyze/equity?ticker=${enc(ticker)}&thesis=${enc(thesis)}&mandate=${enc(mandate)}&prev_verdict=${prevVerdict}&prev_date=${prevDate}`,
    ticker
  );
});

$('btn-startup').addEventListener('click', () => {
  const name   = $('startup-name').value.trim();
  const url    = $('startup-url').value.trim();
  const thesis = $('startup-thesis').value.trim();
  if (!name) { highlight('startup-name'); return; }

  const prev = historyFind('startup', name);
  const prevVerdict = prev ? encodeURIComponent(prev.verdict || '') : '';
  const prevDate    = prev ? encodeURIComponent(prev.date ? new Date(prev.date).toLocaleDateString('pt-BR') : '') : '';

  startAnalysis(
    `/analyze/startup?name=${enc(name)}&url=${enc(url)}&thesis=${enc(thesis)}&prev_verdict=${prevVerdict}&prev_date=${prevDate}`,
    name
  );
});

// Enter shortcuts
$('ticker').addEventListener('keydown',       e => e.key === 'Enter' && $('btn-equity').click());
$('startup-name').addEventListener('keydown', e => e.key === 'Enter' && $('btn-startup').click());

// ── Start analysis ────────────────────────────────────────
function startAnalysis(url, label) {
  if (currentES) { currentES.close(); currentES = null; }

  resetOutput();
  reportBuffer      = '';
  sourcesMap        = [];
  currentEvaluation = null;
  startTime         = Date.now();

  statusPanel.classList.add('visible');
  setStatus('Preparando pesquisa...', 'pulse');

  // Show skeleton queries immediately (before SSE arrives)
  // agent.py emits queries right away, but SSE handshake takes ~100-300ms
  const skeletonCount = currentMode === 'startup' ? 7 : 6;
  queriesList.innerHTML = '';
  queryEls = [];
  for (let i = 1; i <= skeletonCount; i++) {
    const el = document.createElement('div');
    el.className = 'query-item query-skeleton';
    el.textContent = `${i}. ···`;
    queriesList.appendChild(el);
    queryEls.push(el);
  }

  emptyState.style.display = 'none';
  reportWrapper.classList.add('visible');
  verdictBar.classList.add('visible');
  verdictTag.textContent  = label.toUpperCase();
  verdictTag.className    = 'verdict-tag blue';
  const debateBtnStart = document.getElementById('btn-debate');
  if (debateBtnStart) debateBtnStart.style.display = 'none';
  verdictMeta.textContent = '';
  verdictTime.textContent = '';
  reportContent.innerHTML = '<div class="streaming-cursor cursor-blink"></div>';

  setBtnState(true);

  currentES = new EventSource(url);

  currentES.addEventListener('status', e => setStatus(e.data, 'pulse'));

  currentES.addEventListener('queries', e => {
    try { renderQueries(JSON.parse(e.data), 'initial'); } catch {}
  });

  currentES.addEventListener('followup_queries', e => {
    try { renderQueries(JSON.parse(e.data), 'followup'); } catch {}
  });

  currentES.addEventListener('sources', e => {
    try { sourcesMap = JSON.parse(e.data); } catch {}
  });

  currentES.addEventListener('evaluation', e => {
    try { currentEvaluation = JSON.parse(e.data); } catch {}
  });

  currentES.addEventListener('market_data', e => {
    try { renderMarketDataBar(JSON.parse(e.data)); } catch {}
  });

  currentES.addEventListener('chunk', e => {
    reportBuffer += e.data;
    scheduleRender(false);
    detectVerdict(reportBuffer);
  });

  currentES.addEventListener('done', () => {
    if (currentES) { currentES.close(); currentES = null; }
    scheduleRender(true);
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    verdictTime.textContent = `${elapsed}s`;
    setStatus('Análise concluída', 'done');
    setBtnState(false);
    markQueriesDone();

    // Save to history
    const confMatch = reportBuffer.match(/Confiança:\s*\*?\*?([A-ZÁÉÍÓÚÃÕ]+)\*?\*?/i);
    const confidence = confMatch ? confMatch[1] : '';
    const mode  = currentMode;
    const key   = mode === 'equity'
      ? $('ticker').value.trim().toUpperCase()
      : $('startup-name').value.trim();
    const extras = mode === 'equity'
      ? { thesis: $('thesis').value.trim(), mandate: $('mandate').value.trim() }
      : { url: $('startup-url').value.trim(), thesis: $('startup-thesis').value.trim() };

    if (key) {
      historySaveCompleted(
        mode, key, reportBuffer,
        verdictTag.textContent, verdictTag.className.replace('verdict-tag ', ''),
        confidence, extras
      );
    }

    // Show Debate button once analysis is complete
    const debateBtn = document.getElementById('btn-debate');
    if (debateBtn && key) debateBtn.style.display = 'inline-flex';
  });

  currentES.addEventListener('error', e => {
    if (e.data) { reportBuffer += `\n\n## Erro\n${e.data}`; scheduleRender(true); }
  });

  currentES.onerror = () => {
    if (currentES?.readyState === EventSource.CLOSED) {
      setStatus('Conexão encerrada', 'error');
      setBtnState(false);
      currentES = null;
      scheduleRender(true);
    }
  };
}

// ── Render ────────────────────────────────────────────────
function scheduleRender(final) {
  if (renderFrame) cancelAnimationFrame(renderFrame);
  if (final) {
    renderBlocks(reportBuffer, true);
  } else {
    renderFrame = requestAnimationFrame(() => renderBlocks(reportBuffer, false));
  }
}

// Section color mapping
const SECTION_COLORS = {
  'VEREDITO':                       'green',
  'AÇÃO RECOMENDADA':               'green',
  'O QUE MUDOU':                    'amber',
  'CATALISADORES':                  'blue',
  'RISCOS':                         'red',
  'IMPACTO':                        'amber',
  'TRILHA DE EVIDÊNCIAS':           'purple',
  'RESUMO EXECUTIVO':               'blue',
  'TIME':                           'blue',
  'MERCADO':                        'amber',
  'TRAÇÃO':                         'green',
  'CONCORRENTES':                   'amber',
  'RED FLAGS':                      'red',
  'TESE DE INVESTIMENTO':           'blue',
  'GATILHOS':                       'red',
  'PRÓXIMOS PASSOS':                'purple',
  'EXPLORAR TAMBÉM':                'purple',
};

function sectionColor(title) {
  const upper = title.toUpperCase();
  for (const [key, color] of Object.entries(SECTION_COLORS)) {
    if (upper.includes(key)) return color;
  }
  return 'blue';
}

// targetEl + srcs are optional; defaults to global reportContent / sourcesMap
function renderBlocks(markdown, final, targetEl, srcs) {
  if (!markdown) return;

  const el   = targetEl || reportContent;
  const refs = srcs !== undefined ? srcs : sourcesMap;

  const rawSections = markdown.split(/(?=^## )/m);
  const blocks = [];

  rawSections.forEach(section => {
    const trimmed = section.trim();
    if (!trimmed) return;
    if (trimmed.startsWith('## ')) {
      const lines = trimmed.split('\n');
      const title = lines[0].replace(/^## /, '').trim();
      const body  = lines.slice(1).join('\n').trim();
      blocks.push({ title, body });
    } else {
      if (trimmed) blocks.push({ title: null, body: trimmed });
    }
  });

  if (!blocks.length) {
    el.innerHTML =
      `<div class="report-section"><div class="report-section-body"><p>${escHtml(markdown)}</p></div></div>`
      + (final ? '' : '<div class="streaming-cursor cursor-blink"></div>');
    return;
  }

  let html = '';
  blocks.forEach((block, idx) => {
    const isLast     = idx === blocks.length - 1;
    const color      = block.title ? sectionColor(block.title) : 'blue';
    const isExplore  = block.title?.toUpperCase().includes('EXPLORAR');
    const isEvidence = block.title?.toUpperCase().includes('TRILHA');
    const isChanged  = block.title?.toUpperCase().includes('MUDOU');

    html += `<div class="report-section${isChanged ? ' section-changed' : ''}">`;

    if (block.title) {
      html += `<div class="report-section-header">
        <div class="section-accent ${color}"></div>
        <div class="section-title">${escHtml(block.title)}</div>
      </div>`;
    }

    html += `<div class="report-section-body">`;

    if (isExplore && block.body) {
      html += renderExploreCards(block.body);
    } else if (isEvidence && block.body) {
      html += renderEvidenceTrail(block.body);
    } else if (block.body) {
      html += parseBodyToHtml(block.body);
    }

    if (isLast && !final) {
      html += '<span class="cursor-blink" style="display:inline-block;"></span>';
    }

    html += `</div></div>`;
  });

  el.innerHTML = html;

  // Make citation numbers [N] clickable
  if (refs.length) {
    el.querySelectorAll('p, li').forEach(row => {
      row.innerHTML = row.innerHTML.replace(/\[(\d+)\]/g, (match, n) => {
        const idx = parseInt(n) - 1;
        const src = refs[idx];
        if (src && src.url) {
          return `<a href="${escHtml(src.url)}" target="_blank" rel="noopener" class="citation" title="${escHtml(src.title)}">[${n}]</a>`;
        }
        return match;
      });
    });
  }

  if (!final && !targetEl) {
    const wrapper = document.getElementById('report-wrapper');
    wrapper.scrollTop = wrapper.scrollHeight;
  }
}

// Render evidence trail with clickable links
function renderEvidenceTrail(body) {
  const lines = body.split('\n').filter(l => l.trim());
  if (!lines.length) return parseBodyToHtml(body);

  let html = '<div class="evidence-list">';
  lines.forEach(line => {
    // Format: - **[N]** title — claim — URL
    // or plain list items
    const citMatch = line.match(/^-\s+\*\*\[(\d+)\]\*\*\s+(.+?)(?:\s+—\s+(.+?))?(?:\s+—\s+(https?:\/\/\S+))?$/);
    if (citMatch) {
      const num   = citMatch[1];
      const title = citMatch[2] || '';
      const claim = citMatch[3] || '';
      const url   = citMatch[4] || (sourcesMap[parseInt(num)-1]?.url || '');
      html += `<div class="evidence-item">
        <span class="evidence-num">[${num}]</span>
        <div class="evidence-body">
          ${url ? `<a href="${escHtml(url)}" target="_blank" rel="noopener" class="evidence-title">${escHtml(title)}</a>` : `<span class="evidence-title">${escHtml(title)}</span>`}
          ${claim ? `<span class="evidence-claim">— ${escHtml(claim)}</span>` : ''}
        </div>
      </div>`;
    } else {
      // Fallback: try to linkify any URL in the line
      const text = line.replace(/^-\s+/, '');
      const withLinks = escHtml(text).replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener" class="evidence-link">$1</a>');
      html += `<div class="evidence-item evidence-fallback"><span class="evidence-body">${withLinks}</span></div>`;
    }
  });
  html += '</div>';
  return html;
}

// Convert markdown body text to HTML
function parseBodyToHtml(body) {
  const lines = body.split('\n');
  let html   = '';
  let inList = false;

  lines.forEach(rawLine => {
    const line = rawLine.trim();
    if (!line) {
      if (inList) { html += '</ul>'; inList = false; }
      return;
    }

    if (line.startsWith('- ')) {
      if (!inList) { html += '<ul>'; inList = true; }
      html += `<li>${inlineMarkdown(line.slice(2))}</li>`;
    } else {
      if (inList) { html += '</ul>'; inList = false; }
      html += `<p>${inlineMarkdown(line)}</p>`;
    }
  });

  if (inList) html += '</ul>';
  return html;
}

// Inline markdown: **bold**, `code`
function inlineMarkdown(text) {
  return escHtml(text)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code>$1</code>');
}

// Render "Explorar Também" section as clickable cards
function renderExploreCards(body) {
  const lines = body.split('\n').filter(l => l.trim().startsWith('- '));
  if (!lines.length) return parseBodyToHtml(body);

  let html = '<div class="explore-cards">';
  lines.forEach(line => {
    const match = line.match(/^-\s+\*\*(.+?)\*\*\s*[—–-]\s*(.+)$/);
    if (match) {
      const name = match[1].trim();
      const desc = match[2].trim();
      html += `
        <div class="explore-card" onclick="exploreItem('${escAttr(name)}')">
          <div class="explore-card-name">${escHtml(name)}</div>
          <div class="explore-card-desc">${escHtml(desc)}</div>
          <div class="explore-card-arrow">→</div>
        </div>`;
    } else {
      const text  = line.replace(/^-\s+/, '').replace(/\*\*/g, '');
      const parts = text.split(/[—–-]/);
      const name  = parts[0].trim();
      const desc  = parts.slice(1).join('-').trim();
      html += `
        <div class="explore-card" onclick="exploreItem('${escAttr(name)}')">
          <div class="explore-card-name">${escHtml(name)}</div>
          <div class="explore-card-desc">${escHtml(desc || '')}</div>
          <div class="explore-card-arrow">→</div>
        </div>`;
    }
  });
  html += '</div>';
  return html;
}

window.exploreItem = function(name) {
  if (currentMode === 'equity') {
    $('ticker').value = name;
    $('thesis').value = '';
    $('btn-equity').click();
  } else {
    $('startup-name').value = name;
    $('startup-thesis').value = '';
    $('btn-startup').click();
  }
};

// ── Market data bar ───────────────────────────────────────
function renderMarketDataBar(d) {
  const existing = document.getElementById('market-data-bar');
  if (existing) existing.remove();

  if (!d || !d.price) return;

  const pct = d.change_pct || '';
  const isPos = pct.startsWith('-') ? false : true;
  const changeClass = pct ? (isPos ? 'md-pos' : 'md-neg') : '';

  const pills = [
    d.pe_trailing ? `P/L ${d.pe_trailing}` : null,
    d.ev_ebitda   ? `EV/EBITDA ${d.ev_ebitda}` : null,
    d.pb          ? `P/VP ${d.pb}` : null,
    d.div_yield   ? `DY ${d.div_yield}` : null,
    d.market_cap  ? `Mktcap ${d.market_cap}` : null,
  ].filter(Boolean);

  const bar = document.createElement('div');
  bar.id = 'market-data-bar';
  bar.className = 'market-data-bar';
  bar.innerHTML = `
    <span class="md-ticker">${escHtml(d.ticker)}</span>
    <span class="md-price">${escHtml(d.price)}</span>
    ${pct ? `<span class="md-change ${changeClass}">${isPos ? '+' : ''}${escHtml(pct)}</span>` : ''}
    <span class="md-sep">|</span>
    ${pills.map(p => `<span class="md-pill">${escHtml(p)}</span>`).join('')}
    ${d.week_52_high && d.week_52_low ? `<span class="md-range">52w ${escHtml(d.week_52_low)}–${escHtml(d.week_52_high)}</span>` : ''}
  `;

  // Insert after verdict-bar
  verdictBar.insertAdjacentElement('afterend', bar);
}

// ── Verdict detection ─────────────────────────────────────
const VERDICTS = {
  green: ['TESE MANTIDA', 'INVESTIR', 'COMPRAR'],
  amber: ['TESE ALTERADA', 'MONITORAR', 'MANTER'],
  red:   ['TESE INVALIDADA', 'PASSAR', 'REDUZIR', 'VENDER'],
};

function detectVerdict(text) {
  const upper = text.toUpperCase();
  for (const [color, keywords] of Object.entries(VERDICTS)) {
    for (const kw of keywords) {
      if (upper.includes(`**${kw}**`) || upper.includes(`**[${kw}]**`)) {
        verdictTag.textContent = kw;
        verdictTag.className   = `verdict-tag ${color}`;
        const confMatch = text.match(/Confiança:\s*\*?\*?([A-ZÁÉÍÓÚÃÕ]+)\*?\*?/i);
        if (confMatch) verdictMeta.innerHTML = `Confiança: <strong>${confMatch[1]}</strong>`;
        return;
      }
    }
  }
}

// ── Queries ───────────────────────────────────────────────
let queryEls = [];

function renderQueries(queries, type) {
  if (type === 'initial') {
    queriesList.innerHTML = '';
    queryEls = [];
  } else {
    // Add separator for follow-up queries
    const sep = document.createElement('div');
    sep.className = 'query-separator';
    sep.textContent = '↳ follow-up';
    queriesList.appendChild(sep);
  }

  queries.forEach((q, i) => {
    const el = document.createElement('div');
    el.className = type === 'followup' ? 'query-item followup' : 'query-item';
    el.textContent = `${type === 'followup' ? '↳' : (queryEls.length + 1) + '.'} ${q.length > 46 ? q.slice(0, 46) + '…' : q}`;
    queriesList.appendChild(el);
    if (type === 'initial') queryEls.push(el);
  });
}

function setStatus(text, state) {
  statusText.textContent = text;
  statusDot.className    = `status-dot ${state}`;
  const match = text.match(/\[(\d+)\//);
  if (match) {
    const idx = parseInt(match[1]) - 1;
    queryEls.forEach((el, i) => {
      el.classList.remove('active');
      if (i < idx)   el.classList.add('done');
      if (i === idx) el.classList.add('active');
    });
  }
}

function markQueriesDone() {
  queryEls.forEach(el => { el.classList.remove('active'); el.classList.add('done'); });
  queriesList.querySelectorAll('.query-item.followup').forEach(el => el.classList.add('done'));
}

// ── Utils ─────────────────────────────────────────────────
function resetOutput() {
  reportBuffer = '';
  sourcesMap   = [];
  reportContent.innerHTML = '';
  reportWrapper.classList.remove('visible');
  verdictBar.classList.remove('visible');
  queriesList.innerHTML = '';
  statusPanel.classList.remove('visible');
  queryEls = [];
  emptyState.style.display = 'flex';
  if (renderFrame) { cancelAnimationFrame(renderFrame); renderFrame = null; }
  const mdBar = document.getElementById('market-data-bar');
  if (mdBar) mdBar.remove();
}

function setBtnState(disabled) {
  $('btn-equity').disabled  = disabled;
  $('btn-startup').disabled = disabled;
}

function highlight(id) {
  const el = $(id);
  el.style.borderColor = 'var(--red)';
  el.focus();
  setTimeout(() => { el.style.borderColor = ''; }, 1500);
}

function enc(s)     { return encodeURIComponent(s); }
function escHtml(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function escAttr(s) { return String(s).replace(/'/g,"\\'"); }

// ── HISTORY (server-side) ─────────────────────────────────
let historyCache = [];

async function historyInit() {
  try {
    const res = await fetch('/history');
    historyCache = await res.json();
  } catch {
    historyCache = [];
  }
  renderHistoryPanel();
  _openFromUrlParams();
}

function _openFromUrlParams() {
  const p = new URLSearchParams(window.location.search);
  const ticker  = p.get('ticker');
  const startup = p.get('startup');
  const url     = p.get('url') || '';

  if (ticker) {
    const entry = historyFind('equity', ticker);
    if (entry) {
      historyOpen(ticker, 'equity');
    } else {
      $('ticker').value = ticker;
    }
  } else if (startup) {
    const entry = historyFind('startup', startup);
    if (entry) {
      historyOpen(startup, 'startup');
    } else {
      document.querySelector('.mode-tab[data-mode="startup"]')?.click();
      $('startup-name').value = startup;
      $('startup-url').value  = url;
    }
  }
}

function historyLoad() {
  return historyCache;
}

function historySave(entry) {
  // Append to cache — do NOT deduplicate (full timeline preserved)
  historyCache.unshift(entry);
  if (historyCache.length > 2000) historyCache = historyCache.slice(0, 2000);
  renderHistoryPanel();
  if (currentMode === 'history') renderHistoryView();

  // Persist to server (fire and forget)
  fetch('/history', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(entry),
  }).catch(() => {});
}

function historyFind(mode, key) {
  return historyCache.find(e => e.mode === mode && e.key.toLowerCase() === key.toLowerCase());
}

function historyFormatDate(iso) {
  const d = new Date(iso);
  const now = new Date();
  const diffDays = Math.floor((now - d) / 86400000);
  if (diffDays === 0) return 'Hoje';
  if (diffDays === 1) return 'Ontem';
  if (diffDays < 7)  return `${diffDays}d atrás`;
  return d.toLocaleDateString('pt-BR', { day:'2-digit', month:'2-digit' });
}

function renderHistoryPanel() {
  const list  = historyLoad();
  const panel = $('history-panel');
  const listEl = $('history-list');

  if (!list.length) { panel.classList.remove('visible'); return; }
  panel.classList.add('visible');

  // Show only most recent entry per (mode, key) in sidebar
  const seen = new Set();
  const unique = list.filter(e => {
    const k = `${e.mode}:${(e.key||'').toLowerCase()}`;
    if (seen.has(k)) return false;
    seen.add(k); return true;
  });

  listEl.innerHTML = unique.map(e => {
    const count = list.filter(x => x.mode === e.mode && (x.key||'').toLowerCase() === (e.key||'').toLowerCase()).length;
    return `
    <div class="history-item" onclick="historyOpen('${escAttr(e.key)}','${e.mode}')">
      <div class="history-item-badge ${e.verdictColor}">${escHtml(e.verdict)}</div>
      <div class="history-item-name">${escHtml(e.key)}</div>
      <div class="history-item-date">${historyFormatDate(e.date)}${count > 1 ? ` <span style="color:var(--accent);font-size:.65rem">${count}×</span>` : ''}</div>
    </div>`;
  }).join('');
}

// ── History full view (tab mode) ─────────────────────────

function historyExtractSummary(report) {
  if (!report) return '';
  // Try RESUMO EXECUTIVO or VEREDITO section
  const match = report.match(/## (?:RESUMO EXECUTIVO|VEREDITO)[^\n]*\n+([\s\S]+?)(?=\n##|$)/i);
  if (match) {
    return match[1]
      .replace(/\*\*/g, '')
      .replace(/^[-*]\s+/gm, '')
      .replace(/\n+/g, ' ')
      .trim()
      .slice(0, 200);
  }
  // Fallback: first content lines after a heading
  const lines = report.split('\n');
  const result = [];
  let inContent = false;
  for (const line of lines) {
    if (line.startsWith('## ')) { inContent = true; continue; }
    if (inContent && line.trim() && !line.startsWith('#')) {
      result.push(line.trim().replace(/\*\*/g, ''));
      if (result.join(' ').length > 180) break;
    }
  }
  return result.join(' ').slice(0, 200);
}

function renderHistoryView(selectedKey, selectedMode, selectedDate) {
  const list = historyCache;

  if (!list.length) {
    historyView.innerHTML = `
      <div class="hist-empty">
        <div class="hist-empty-icon">▦</div>
        <p>Nenhuma análise salva ainda</p>
        <div class="hist-empty-hint">analise um ativo ou startup para começar</div>
      </div>`;
    return;
  }

  // Group by (mode, key) — preserving order of first occurrence (newest first)
  const groupMap = new Map();
  list.forEach(e => {
    const gk = `${e.mode}:${(e.key||'').toLowerCase()}`;
    if (!groupMap.has(gk)) groupMap.set(gk, { mode: e.mode, key: e.key, entries: [] });
    groupMap.get(gk).entries.push(e);
  });
  const groups = Array.from(groupMap.values());

  const groupsHtml = groups.map(g => {
    const latest  = g.entries[0];
    const count   = g.entries.length;
    const modeLabel = g.mode === 'equity' ? '⬡ EQUITY' : '◈ STARTUP';
    const modeClass = g.mode === 'equity' ? 'equity' : 'startup';
    const isActiveGroup = g.key === selectedKey && g.mode === selectedMode;

    // Timeline rows
    const timelineRows = g.entries.map((e, idx) => {
      const isLatest = idx === 0;
      const prev = g.entries[idx + 1];
      const dateStr = new Date(e.date).toLocaleDateString('pt-BR', { day:'2-digit', month:'2-digit', year:'numeric' });
      const timeStr = new Date(e.date).toLocaleTimeString('pt-BR', { hour:'2-digit', minute:'2-digit' });
      const isActiveEntry = isActiveGroup && e.date === selectedDate;

      // Inline delta badge vs previous entry
      let deltaBadge = '';
      if (isLatest && prev) {
        const verdictChanged = e.verdict !== prev.verdict;
        const daysBetween = Math.abs(Math.round((new Date(e.date) - new Date(prev.date)) / 86400000));
        if (verdictChanged) {
          deltaBadge = `<span class="hist-delta-badge changed">veredito mudou: ${escHtml(prev.verdict)} → ${escHtml(e.verdict)}</span>`;
        } else {
          deltaBadge = `<span class="hist-delta-badge same">mantido (${daysBetween}d)</span>`;
        }
      }

      return `
        <div class="hist-timeline-row${isActiveEntry ? ' active' : ''}"
             data-key="${escAttr(g.key)}" data-mode="${escAttr(g.mode)}" data-date="${escAttr(e.date)}">
          <div class="hist-tl-dot ${e.verdictColor || 'neutral'}"></div>
          <div class="hist-tl-date">${dateStr} <span class="hist-tl-time">${timeStr}</span></div>
          <span class="verdict-tag ${escHtml(e.verdictColor||'')} hist-verdict-sm">${escHtml(e.verdict)}</span>
          ${e.confidence ? `<span class="hist-tl-conf">${escHtml(e.confidence)}</span>` : ''}
          ${deltaBadge}
          <button class="hist-card-open hist-tl-open">Ver →</button>
        </div>`;
    }).join('');

    return `
      <div class="hist-group${isActiveGroup ? ' active' : ''}" data-key="${escAttr(g.key)}" data-mode="${escAttr(g.mode)}">
        <div class="hist-group-header">
          <span class="hist-mode-badge ${modeClass}">${modeLabel}</span>
          <span class="hist-group-key">${escHtml(g.key)}</span>
          <span class="verdict-tag ${escHtml(latest.verdictColor||'')} hist-verdict">${escHtml(latest.verdict)}</span>
          ${count > 1 ? `<span class="hist-group-count">${count} análises</span>` : ''}
          <span class="hist-group-date">${new Date(latest.date).toLocaleDateString('pt-BR', { day:'2-digit', month:'2-digit', year:'numeric' })}</span>
          <button class="hist-delete-key" title="Remover histórico de ${escAttr(g.key)}"
                  data-key="${escAttr(g.key)}" data-mode="${escAttr(g.mode)}">✕</button>
        </div>
        <div class="hist-timeline">${timelineRows}</div>
      </div>`;
  }).join('');

  const totalEntries = list.length;
  const totalKeys = groups.length;

  historyView.innerHTML = `
    <div class="hist-layout" id="hist-layout">
      <div class="hist-list-col" id="hist-list-col">
        <div class="hist-view-header">
          <div class="hist-view-title">HISTÓRICO <span class="hist-view-count">${totalKeys} ativos · ${totalEntries} análises</span></div>
          <button class="hist-view-clear" id="btn-clear-all">LIMPAR TUDO</button>
        </div>
        <div class="hist-cards" id="hist-cards">${groupsHtml}</div>
      </div>
      <div class="hist-detail-col" id="hist-detail-col"></div>
    </div>`;

  // Timeline row click → open detail
  historyView.querySelectorAll('.hist-timeline-row').forEach(row => {
    row.addEventListener('click', (ev) => {
      if (ev.target.classList.contains('hist-delete-key')) return;
      openHistoryDetail(row.dataset.key, row.dataset.mode, row.dataset.date);
    });
  });

  // Per-key delete button
  historyView.querySelectorAll('.hist-delete-key').forEach(btn => {
    btn.addEventListener('click', (ev) => {
      ev.stopPropagation();
      const { key, mode } = btn.dataset;
      if (!confirm(`Remover todo o histórico de ${key}?`)) return;
      historyCache = historyCache.filter(e => !(e.mode === mode && (e.key||'').toLowerCase() === key.toLowerCase()));
      renderHistoryPanel();
      renderHistoryView();
      fetch(`/history/${mode}/${encodeURIComponent(key)}`, { method: 'DELETE' }).catch(() => {});
    });
  });

  $('btn-clear-all').addEventListener('click', () => {
    if (confirm('Limpar todo o histórico de análises?')) {
      historyCache = [];
      renderHistoryPanel();
      renderHistoryView();
      $('cache-hint').style.display = 'none';
      fetch('/history', { method: 'DELETE' }).catch(() => {});
    }
  });

  // Re-open selected item if any
  if (selectedKey) openHistoryDetail(selectedKey, selectedMode, selectedDate);
}

function openHistoryDetail(key, mode, date) {
  // Find specific entry by date, or fall back to most recent
  const allForKey = historyCache.filter(e => e.mode === mode && (e.key||'').toLowerCase() === key.toLowerCase());
  const entry = date ? allForKey.find(e => e.date === date) : allForKey[0];
  if (!entry) return;

  const entryIdx = allForKey.indexOf(entry);
  const prevEntry = allForKey[entryIdx + 1] || null;  // older entry

  const layout = $('hist-layout');
  const detail = $('hist-detail-col');
  if (!layout || !detail) return;

  // Highlight active timeline row
  historyView.querySelectorAll('.hist-timeline-row').forEach(c => {
    c.classList.toggle('active', c.dataset.key === key && c.dataset.mode === mode && c.dataset.date === entry.date);
  });
  historyView.querySelectorAll('.hist-group').forEach(g => {
    g.classList.toggle('active', g.dataset.key === key && g.dataset.mode === mode);
  });

  layout.classList.add('has-detail');

  const dateStr = new Date(entry.date).toLocaleDateString('pt-BR', {
    day:'2-digit', month:'2-digit', year:'numeric', hour:'2-digit', minute:'2-digit'
  });
  const modeLabel = entry.mode === 'equity' ? '⬡ Equity' : '◈ Startup';

  // Delta box HTML (compare this entry vs previous for same key)
  let deltaHtml = '';
  if (prevEntry) {
    const verdictChanged = entry.verdict !== prevEntry.verdict;
    const confChanged    = entry.confidence !== prevEntry.confidence;
    const daysBetween    = Math.abs(Math.round((new Date(entry.date) - new Date(prevEntry.date)) / 86400000));
    const prevDateStr    = new Date(prevEntry.date).toLocaleDateString('pt-BR', { day:'2-digit', month:'2-digit', year:'numeric' });

    // Evaluation delta
    const evalNew = entry.evaluation || {};
    const evalOld = prevEntry.evaluation || {};
    const covDelta = (evalNew.coverage_score != null && evalOld.coverage_score != null)
      ? ((evalNew.coverage_score - evalOld.coverage_score) * 100).toFixed(0)
      : null;
    const evDelta  = (evalNew.evidence_score != null && evalOld.evidence_score != null)
      ? ((evalNew.evidence_score - evalOld.evidence_score) * 100).toFixed(0)
      : null;

    // Sources delta
    const srcsNew = new Set((entry.sources||[]).map(s=>s.url).filter(Boolean));
    const srcsOld = new Set((prevEntry.sources||[]).map(s=>s.url).filter(Boolean));
    const newSrcsCount = [...srcsNew].filter(u => !srcsOld.has(u)).length;
    const remSrcsCount = [...srcsOld].filter(u => !srcsNew.has(u)).length;

    const deltaItems = [];
    if (verdictChanged) deltaItems.push(`<span class="hist-delta-item changed">Veredito: <strong>${escHtml(prevEntry.verdict)}</strong> → <strong>${escHtml(entry.verdict)}</strong></span>`);
    if (confChanged)    deltaItems.push(`<span class="hist-delta-item">Confiança: ${escHtml(prevEntry.confidence||'?')} → ${escHtml(entry.confidence||'?')}</span>`);
    if (covDelta !== null) {
      const cls = Number(covDelta) > 0 ? 'pos' : Number(covDelta) < 0 ? 'neg' : '';
      deltaItems.push(`<span class="hist-delta-item ${cls}">Cobertura: ${Number(covDelta) > 0 ? '+' : ''}${covDelta}pp</span>`);
    }
    if (evDelta !== null) {
      const cls = Number(evDelta) > 0 ? 'pos' : Number(evDelta) < 0 ? 'neg' : '';
      deltaItems.push(`<span class="hist-delta-item ${cls}">Evidência: ${Number(evDelta) > 0 ? '+' : ''}${evDelta}pp</span>`);
    }
    if (newSrcsCount > 0) deltaItems.push(`<span class="hist-delta-item pos">+${newSrcsCount} nova${newSrcsCount>1?'s':''} fonte${newSrcsCount>1?'s':''}</span>`);
    if (remSrcsCount > 0) deltaItems.push(`<span class="hist-delta-item neg">-${remSrcsCount} fonte${remSrcsCount>1?'s':''} removida${remSrcsCount>1?'s':''}</span>`);

    deltaHtml = `
      <div class="hist-delta-box">
        <div class="hist-delta-header">
          <span class="hist-delta-label">Δ vs ${prevDateStr}</span>
          <span class="hist-delta-days">${daysBetween} dia${daysBetween !== 1 ? 's' : ''} entre análises</span>
          <button class="hist-delta-view-prev" id="hist-delta-prev-btn" title="Ver análise anterior">Ver anterior →</button>
        </div>
        <div class="hist-delta-items">${deltaItems.length ? deltaItems.join('') : '<span class="hist-delta-item">Sem mudanças estruturais detectadas</span>'}</div>
      </div>`;
  }

  detail.innerHTML = `
    <div class="hist-detail-header">
      <span class="hist-detail-mode">${modeLabel}</span>
      <span class="hist-detail-key">${escHtml(entry.key)}</span>
      <span class="verdict-tag ${escHtml(entry.verdictColor)}">${escHtml(entry.verdict)}</span>
      ${entry.confidence ? `<span class="hist-detail-meta">Confiança: <strong>${escHtml(entry.confidence)}</strong></span>` : ''}
      <span class="hist-detail-date">${dateStr}</span>
      ${allForKey.length > 1 ? `<span class="hist-detail-meta" style="color:var(--accent)">${allForKey.length} análises salvas</span>` : ''}
      <button class="hist-detail-rerun" id="hist-detail-rerun">↺ Reanalisar</button>
      <button class="hist-detail-close" id="hist-detail-close">×</button>
    </div>
    ${deltaHtml}
    <div class="hist-detail-body">
      <div class="report-content" id="hist-report-content"></div>
    </div>`;

  // Render cached report — zero API calls
  renderBlocks(entry.report, true, $('hist-report-content'), entry.sources || []);

  // View previous entry
  if (prevEntry) {
    $('hist-delta-prev-btn')?.addEventListener('click', () => {
      openHistoryDetail(key, mode, prevEntry.date);
    });
  }

  // Close
  $('hist-detail-close').addEventListener('click', () => {
    layout.classList.remove('has-detail');
    detail.innerHTML = '';
    historyView.querySelectorAll('.hist-timeline-row, .hist-group').forEach(c => c.classList.remove('active'));
  });

  // Reanalisar
  $('hist-detail-rerun').addEventListener('click', () => {
    if (mode === 'equity') {
      $('ticker').value  = entry.key;
      $('thesis').value  = entry.thesis || '';
      $('mandate').value = entry.mandate || '';
    } else {
      $('startup-name').value   = entry.key;
      $('startup-url').value    = entry.url || '';
      $('startup-thesis').value = entry.thesis || '';
    }
    document.querySelector(`.mode-tab[data-mode="${mode}"]`)?.click();
  });
}

window.historyOpen = function(key, mode) {
  const entry = historyFind(mode, key);
  if (!entry) return;

  // Switch to the correct analysis mode (equity or startup)
  if (currentMode !== mode) {
    document.querySelector(`.mode-tab[data-mode="${mode}"]`)?.click();
  }

  if (mode === 'equity') {
    $('ticker').value  = entry.key;
    $('thesis').value  = entry.thesis || '';
    $('mandate').value = entry.mandate || '';
  } else {
    $('startup-name').value   = entry.key;
    $('startup-url').value    = entry.url || '';
    $('startup-thesis').value = entry.thesis || '';
  }

  showCachedReport(entry);
};

// showHint=false when opening from history (avoids confusing "Reanalisar" button)
function showCachedReport(entry, showHint = false) {
  emptyState.style.display = 'none';
  reportWrapper.classList.add('visible');
  verdictBar.classList.add('visible');
  verdictTag.textContent  = entry.verdict;
  verdictTag.className    = `verdict-tag ${entry.verdictColor}`;
  verdictMeta.innerHTML   = entry.confidence ? `Confiança: <strong>${entry.confidence}</strong>` : '';
  verdictTime.textContent = historyFormatDate(entry.date);
  reportBuffer            = entry.report;
  sourcesMap              = entry.sources || [];
  renderBlocks(entry.report, true);
  if (showHint) showCacheHint(entry);
}

function showCacheHint(entry) {
  const hint    = $('cache-hint');
  const text    = $('cache-hint-text');
  const btnView = $('btn-view-cache');
  const btnRun  = $('btn-rerun');

  const dateStr = new Date(entry.date).toLocaleDateString('pt-BR', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit'
  });
  text.textContent = `Análise de ${dateStr}`;
  hint.style.display = 'flex';

  btnView.onclick = () => showCachedReport(entry);
  btnRun.onclick  = () => {
    hint.style.display = 'none';
    if (entry.mode === 'equity') $('btn-equity').click();
    else $('btn-startup').click();
  };
}

function historySaveCompleted(mode, key, report, verdict, verdictColor, confidence, extras) {
  historySave({
    mode, key, report, verdict, verdictColor, confidence,
    sources: sourcesMap,
    evaluation: currentEvaluation,
    date: new Date().toISOString(),
    ...extras,
  });
}

function bindHistoryHints() {
  function check(inputId, mode, keyFn) {
    const el = $(inputId);
    if (!el) return;
    el.addEventListener('input', () => {
      const key  = keyFn().trim();
      const hint = $('cache-hint');
      if (!key) { hint.style.display = 'none'; return; }
      const found = historyFind(mode, key);
      if (found) {
        const dateStr = new Date(found.date).toLocaleDateString('pt-BR', {
          day: '2-digit', month: '2-digit', year: 'numeric',
        });
        $('cache-hint-text').textContent = `Análise anterior: ${dateStr} (${found.verdict})`;
        hint.style.display = 'flex';
        $('btn-view-cache').onclick = () => showCachedReport(found);
        $('btn-rerun').onclick = () => {
          hint.style.display = 'none';
          if (mode === 'equity') $('btn-equity').click();
          else $('btn-startup').click();
        };
      } else {
        hint.style.display = 'none';
      }
    });
  }

  check('ticker',       'equity',  () => $('ticker').value.toUpperCase());
  check('startup-name', 'startup', () => $('startup-name').value);
}

// ── Init ──────────────────────────────────────────────────
(function init() {
  historyInit();  // loads from server, then renders panel
  bindHistoryHints();

  $('btn-clear-history').addEventListener('click', () => {
    historyCache = [];
    renderHistoryPanel();
    $('cache-hint').style.display = 'none';
    fetch('/history', { method: 'DELETE' }).catch(() => {});
  });
})();
