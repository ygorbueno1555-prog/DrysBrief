/* ============================================================
   CORTIQ DECISION COPILOT — Frontend
   SSE streaming, markdown rendering, verdict detection
   ============================================================ */

let currentMode = 'equity';
let currentES = null;       // active EventSource
let reportBuffer = '';      // accumulated markdown text
let renderPending = false;  // rAF flag
let startTime = null;

// ── DOM refs ─────────────────────────────────────────────
const tabs          = document.querySelectorAll('.mode-tab');
const equityForm    = document.getElementById('equity-form');
const startupForm   = document.getElementById('startup-form');
const statusPanel   = document.getElementById('status-panel');
const statusDot     = document.getElementById('status-dot');
const statusText    = document.getElementById('status-text');
const queriesList   = document.getElementById('queries-list');
const emptyState    = document.getElementById('empty-state');
const verdictBar    = document.getElementById('verdict-bar');
const verdictTag    = document.getElementById('verdict-tag');
const verdictMeta   = document.getElementById('verdict-meta');
const verdictTime   = document.getElementById('verdict-time');
const reportWrapper = document.getElementById('report-wrapper');
const reportContent = document.getElementById('report-content');

// ── Mode switching ────────────────────────────────────────
tabs.forEach(tab => {
  tab.addEventListener('click', () => {
    currentMode = tab.dataset.mode;
    tabs.forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    equityForm.style.display  = currentMode === 'equity'  ? 'block' : 'none';
    startupForm.style.display = currentMode === 'startup' ? 'block' : 'none';
    resetOutput();
  });
});

// ── Analyze buttons ───────────────────────────────────────
document.getElementById('btn-equity').addEventListener('click', () => {
  const ticker  = document.getElementById('ticker').value.trim().toUpperCase();
  const thesis  = document.getElementById('thesis').value.trim();
  const mandate = document.getElementById('mandate').value.trim();
  if (!ticker) { shake('ticker'); return; }
  startAnalysis(`/analyze/equity?ticker=${enc(ticker)}&thesis=${enc(thesis)}&mandate=${enc(mandate)}`);
});

document.getElementById('btn-startup').addEventListener('click', () => {
  const name   = document.getElementById('startup-name').value.trim();
  const url    = document.getElementById('startup-url').value.trim();
  const thesis = document.getElementById('startup-thesis').value.trim();
  if (!name) { shake('startup-name'); return; }
  startAnalysis(`/analyze/startup?name=${enc(name)}&url=${enc(url)}&thesis=${enc(thesis)}`);
});

// Enter key shortcut
document.getElementById('ticker').addEventListener('keydown', e => {
  if (e.key === 'Enter') document.getElementById('btn-equity').click();
});
document.getElementById('startup-name').addEventListener('keydown', e => {
  if (e.key === 'Enter') document.getElementById('btn-startup').click();
});

// ── Core: start SSE analysis ──────────────────────────────
function startAnalysis(url) {
  // Close existing stream
  if (currentES) { currentES.close(); currentES = null; }

  resetOutput();
  reportBuffer = '';
  startTime = Date.now();

  // Show status panel
  statusPanel.classList.add('visible');
  setStatus('Conectando...', 'pulse');

  // Show empty state briefly then switch to report
  emptyState.style.display = 'none';
  reportWrapper.classList.add('visible');
  verdictBar.classList.add('visible');
  verdictTag.textContent = 'ANALISANDO';
  verdictTag.className = 'verdict-tag blue';
  verdictMeta.textContent = '';
  verdictTime.textContent = '';
  reportContent.innerHTML = '';
  reportContent.classList.add('cursor-blink');

  // Disable buttons during analysis
  setBtnState(true);

  currentES = new EventSource(url);

  currentES.addEventListener('status', e => {
    setStatus(e.data, 'pulse');
  });

  currentES.addEventListener('queries', e => {
    try {
      const queries = JSON.parse(e.data);
      renderQueries(queries);
    } catch {}
  });

  currentES.addEventListener('chunk', e => {
    reportBuffer += e.data;
    scheduleRender();
    detectVerdict(reportBuffer);
  });

  currentES.addEventListener('done', e => {
    currentES.close();
    currentES = null;
    reportContent.classList.remove('cursor-blink');
    setStatus(e.data, 'done');
    setBtnState(false);
    markQueriesDone();

    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
    verdictTime.textContent = `${elapsed}s`;

    // Final render
    renderReport();
  });

  currentES.addEventListener('error', e => {
    if (e.data) {
      reportBuffer += `\n\n## Erro\n${e.data}`;
      scheduleRender();
    }
  });

  currentES.onerror = () => {
    if (currentES && currentES.readyState === EventSource.CLOSED) {
      setStatus('Conexão encerrada', 'error');
      reportContent.classList.remove('cursor-blink');
      setBtnState(false);
      currentES = null;
    }
  };
}

// ── Markdown rendering (batched via rAF) ──────────────────
function scheduleRender() {
  if (renderPending) return;
  renderPending = true;
  requestAnimationFrame(() => {
    renderPending = false;
    renderReport();
  });
}

function renderReport() {
  if (!reportBuffer) return;
  reportContent.innerHTML = marked.parse(reportBuffer);
}

// ── Verdict detection ─────────────────────────────────────
const VERDICTS = {
  green: ['TESE MANTIDA', 'INVESTIR', 'COMPRAR'],
  amber: ['TESE ALTERADA', 'MONITORAR', 'MANTER'],
  red:   ['TESE INVALIDADA', 'PASSAR', 'REDUZIR', 'VENDER'],
};

const VERDICT_LABELS = {
  'TESE MANTIDA':    'Tese Mantida',
  'TESE ALTERADA':   'Tese Alterada',
  'TESE INVALIDADA': 'Tese Invalidada',
  'INVESTIR':        'Investir',
  'MONITORAR':       'Monitorar',
  'PASSAR':          'Passar',
  'COMPRAR':         'Comprar',
  'MANTER':          'Manter',
  'REDUZIR':         'Reduzir',
  'VENDER':          'Vender',
};

function detectVerdict(text) {
  const upper = text.toUpperCase();
  for (const [color, keywords] of Object.entries(VERDICTS)) {
    for (const kw of keywords) {
      if (upper.includes(kw)) {
        verdictTag.textContent = VERDICT_LABELS[kw] || kw;
        verdictTag.className = `verdict-tag ${color}`;

        // Try to extract confidence line
        const confMatch = text.match(/Confiança:\s*\*?\*?([A-ZÁÉÍÓÚÃÕ]+)\*?\*?/i);
        if (confMatch) {
          verdictMeta.innerHTML = `Confiança: <strong>${confMatch[1]}</strong>`;
        }
        return;
      }
    }
  }
}

// ── Queries list ──────────────────────────────────────────
let queryItems = [];

function renderQueries(queries) {
  queriesList.innerHTML = '';
  queryItems = [];
  queries.forEach((q, i) => {
    const el = document.createElement('div');
    el.className = 'query-item';
    el.textContent = `${i + 1}. ${q.length > 50 ? q.slice(0, 50) + '…' : q}`;
    el.id = `query-${i}`;
    queriesList.appendChild(el);
    queryItems.push(el);
  });
}

let queryDoneCount = 0;

function markQueriesDone() {
  queryItems.forEach(el => el.classList.add('done'));
}

// ── Status helpers ────────────────────────────────────────
function setStatus(text, state) {
  statusText.textContent = text;
  statusDot.className = `status-dot ${state}`;

  // Highlight active query
  if (state === 'pulse') {
    const match = text.match(/\[(\d+)\//);
    if (match) {
      const idx = parseInt(match[1]) - 1;
      queryItems.forEach((el, i) => {
        el.classList.remove('active');
        if (i < idx) el.classList.add('done');
        if (i === idx) el.classList.add('active');
      });
    }
  }
}

// ── Utility ───────────────────────────────────────────────
function enc(s) { return encodeURIComponent(s); }

function resetOutput() {
  reportBuffer = '';
  reportContent.innerHTML = '';
  reportWrapper.classList.remove('visible');
  verdictBar.classList.remove('visible');
  queriesList.innerHTML = '';
  statusPanel.classList.remove('visible');
  queryItems = [];
  emptyState.style.display = 'flex';
}

function setBtnState(disabled) {
  document.getElementById('btn-equity').disabled  = disabled;
  document.getElementById('btn-startup').disabled = disabled;
}

function shake(inputId) {
  const el = document.getElementById(inputId);
  el.style.borderColor = 'var(--red)';
  el.focus();
  setTimeout(() => { el.style.borderColor = ''; }, 1500);
}

// ── marked.js config ──────────────────────────────────────
marked.setOptions({
  breaks: true,
  gfm: true,
});
