/* ============================================================
   CORTIQ — Thesis Debate Engine (chat.js)
   Devil's Advocate · Conviction Breakdown · Contextual Q&A
   ============================================================ */

// ── State ─────────────────────────────────────────────────
let chatMode      = '';
let chatKey       = '';
let chatHistory   = [];   // [{role: 'user'|'assistant', content: '...'}]
let chatStreaming  = false;
let devilLoaded   = false;
let convictionLoaded = false;

// ── DOM refs ──────────────────────────────────────────────
const chatDrawer      = document.getElementById('chat-drawer');
const chatOverlay     = document.getElementById('chat-overlay');
const chatMessages    = document.getElementById('chat-messages');
const chatInput       = document.getElementById('chat-input');
const btnChatSend     = document.getElementById('btn-chat-send');
const btnChatClose    = document.getElementById('btn-chat-close');
const btnDebate       = document.getElementById('btn-debate');
const btnDevil        = document.getElementById('btn-devil');
const btnConviction   = document.getElementById('btn-conviction');
const chatDrawerLabel   = document.getElementById('chat-drawer-label');
const chatDrawerVerdict = document.getElementById('chat-drawer-verdict');
const convictionPanel   = document.getElementById('conviction-panel');
const convictionBars    = document.getElementById('conviction-bars');
const chatSuggestions   = document.getElementById('chat-suggestions');

// ── Suggested questions ───────────────────────────────────
const EQUITY_SUGGESTIONS = [
  'Por que INVESTIR e não MONITORAR?',
  'Qual foi o fator decisivo da confiança?',
  'Quais riscos podem invalidar a tese?',
  'Como o valuation se compara aos peers?',
  'O que precisa acontecer para mudar o veredito?',
];
const STARTUP_SUGGESTIONS = [
  'Por que INVESTIR nesta startup agora?',
  'Qual é o principal red flag identificado?',
  'Como o time se compara ao que o mercado exige?',
  'Qual é o maior risco de execução?',
  'O que validaria a tese nos próximos 6 meses?',
];

// ── Open / Close ──────────────────────────────────────────
function openChatDrawer(mode, key, verdict, confidence) {
  chatMode    = mode;
  chatKey     = key;
  chatHistory = [];
  devilLoaded = false;
  convictionLoaded = false;

  chatDrawerLabel.textContent   = key;
  chatDrawerVerdict.textContent = verdict ? `${verdict} · ${confidence}` : '';
  chatDrawerVerdict.className   = 'chat-drawer-verdict ' + verdictColorClass(verdict);

  chatMessages.innerHTML = '';
  convictionPanel.style.display = 'none';
  convictionBars.innerHTML = '';

  renderSuggestions(mode);

  chatDrawer.classList.add('open');
  chatDrawer.setAttribute('aria-hidden', 'false');
  chatOverlay.classList.add('visible');
  chatInput.focus();

  // Auto-trigger Devil's Advocate on open
  setTimeout(() => triggerDevil(true), 300);
}

function closeChatDrawer() {
  chatDrawer.classList.remove('open');
  chatDrawer.setAttribute('aria-hidden', 'true');
  chatOverlay.classList.remove('visible');
}

// ── Verdict color ─────────────────────────────────────────
function verdictColorClass(verdict) {
  if (!verdict) return '';
  const v = verdict.toUpperCase();
  if (['INVESTIR', 'COMPRAR', 'TESE MANTIDA'].some(x => v.includes(x))) return 'green';
  if (['MONITORAR', 'MANTER', 'TESE ALTERADA'].some(x => v.includes(x))) return 'amber';
  if (['PASSAR', 'VENDER', 'REDUZIR', 'TESE INVALIDADA'].some(x => v.includes(x))) return 'red';
  return 'blue';
}

// ── Suggestions ───────────────────────────────────────────
function renderSuggestions(mode) {
  const list = mode === 'equity' ? EQUITY_SUGGESTIONS : STARTUP_SUGGESTIONS;
  chatSuggestions.innerHTML = list.map(q =>
    `<button class="chat-suggestion" type="button">${q}</button>`
  ).join('');
  chatSuggestions.querySelectorAll('.chat-suggestion').forEach(btn => {
    btn.addEventListener('click', () => {
      chatInput.value = btn.textContent;
      sendMessage();
    });
  });
}

// ── Messages ──────────────────────────────────────────────
function addMessage(role, content, isStreaming = false) {
  const el = document.createElement('div');
  el.className = `chat-msg chat-msg-${role}${isStreaming ? ' streaming' : ''}`;

  if (role === 'assistant' || role === 'devil') {
    el.innerHTML = renderMd(content);
  } else {
    el.textContent = content;
  }

  chatMessages.appendChild(el);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return el;
}

function renderMd(text) {
  if (typeof marked !== 'undefined') {
    return marked.parse(text);
  }
  return text.replace(/\n/g, '<br>');
}

function addTypingIndicator() {
  const el = document.createElement('div');
  el.className = 'chat-msg chat-msg-assistant chat-typing';
  el.innerHTML = '<span></span><span></span><span></span>';
  el.id = 'chat-typing';
  chatMessages.appendChild(el);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return el;
}

function removeTypingIndicator() {
  const el = document.getElementById('chat-typing');
  if (el) el.remove();
}

// ── Send message ──────────────────────────────────────────
async function sendMessage() {
  const question = chatInput.value.trim();
  if (!question || chatStreaming) return;

  chatInput.value = '';
  chatInput.style.height = 'auto';
  chatSuggestions.style.display = 'none';

  addMessage('user', question);
  chatHistory.push({ role: 'user', content: question });

  chatStreaming = true;
  btnChatSend.disabled = true;

  addTypingIndicator();

  // Use fetch + SSE stream
  let buffer = '';
  let msgEl  = null;

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        mode: chatMode,
        key: chatKey,
        question,
        history: chatHistory.slice(0, -1), // exclude the just-added user msg
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      removeTypingIndicator();
      addMessage('assistant', `Erro: ${err.detail || res.statusText}`);
      chatStreaming = false;
      btnChatSend.disabled = false;
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let sseBuffer = '';

    removeTypingIndicator();
    msgEl = addMessage('assistant', '', true);

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      sseBuffer += decoder.decode(value, { stream: true });
      const lines = sseBuffer.split('\n');
      sseBuffer = lines.pop();

      for (const line of lines) {
        if (line.startsWith('event: done')) {
          break;
        }
        if (line.startsWith('data: ')) {
          const data = line.slice(6);
          buffer += data;
          msgEl.innerHTML = renderMd(buffer);
          chatMessages.scrollTop = chatMessages.scrollHeight;
        }
      }
    }

    msgEl.classList.remove('streaming');
    chatHistory.push({ role: 'assistant', content: buffer });

  } catch (e) {
    removeTypingIndicator();
    addMessage('assistant', `Erro de conexão: ${e.message}`);
  } finally {
    chatStreaming = false;
    btnChatSend.disabled = false;
    chatInput.focus();
  }
}

// ── Devil's Advocate ──────────────────────────────────────
async function triggerDevil(auto = false) {
  if (devilLoaded && auto) return;

  const typing = addTypingIndicator();

  try {
    const res = await fetch(`/api/chat/devil/${chatMode}/${encodeURIComponent(chatKey)}`);
    removeTypingIndicator();

    if (!res.ok) {
      if (!auto) addMessage('assistant', 'Não foi possível gerar o devil\'s advocate.');
      return;
    }

    const data = await res.json();
    devilLoaded = true;

    const el = document.createElement('div');
    el.className = 'chat-msg chat-msg-devil';
    el.innerHTML = renderMd(data.devil);
    chatMessages.appendChild(el);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    // Add to history so follow-up questions have context
    chatHistory.push({
      role: 'assistant',
      content: `[Devil's Advocate automático]\n${data.devil}`,
    });

  } catch (e) {
    removeTypingIndicator();
  }
}

// ── Conviction Breakdown ──────────────────────────────────
async function toggleConviction() {
  if (convictionPanel.style.display !== 'none') {
    convictionPanel.style.display = 'none';
    return;
  }

  if (convictionLoaded) {
    convictionPanel.style.display = 'block';
    return;
  }

  convictionBars.innerHTML = '<div class="conviction-loading">Calculando scores...</div>';
  convictionPanel.style.display = 'block';

  try {
    const res = await fetch(`/api/chat/conviction/${chatMode}/${encodeURIComponent(chatKey)}`);
    if (!res.ok) {
      convictionBars.innerHTML = '<div class="conviction-loading">Dados insuficientes para breakdown.</div>';
      return;
    }

    const data = await res.json();
    const breakdown = data.breakdown;

    const LABELS = {
      valuation:         'Valuation',
      resultado_recente: 'Resultado Recente',
      macro_setor:       'Macro / Setor',
      execucao_gestao:   'Execução / Gestão',
      catalise_proxima:  'Catalisador Próximo',
    };

    convictionBars.innerHTML = Object.entries(breakdown).map(([key, val]) => {
      const score = val.score || 0;
      const color = score >= 75 ? 'green' : score >= 50 ? 'amber' : 'red';
      return `
        <div class="conviction-item">
          <div class="conviction-item-header">
            <span class="conviction-label">${LABELS[key] || key}</span>
            <span class="conviction-score ${color}">${score}</span>
          </div>
          <div class="conviction-bar-bg">
            <div class="conviction-bar-fill ${color}" style="width:${score}%"></div>
          </div>
          <div class="conviction-reason">${val.reason || ''}</div>
        </div>
      `;
    }).join('');

    convictionLoaded = true;
  } catch (e) {
    convictionBars.innerHTML = '<div class="conviction-loading">Erro ao carregar.</div>';
  }
}

// ── Event listeners ───────────────────────────────────────
btnChatClose.addEventListener('click', closeChatDrawer);
chatOverlay.addEventListener('click', closeChatDrawer);

btnChatSend.addEventListener('click', sendMessage);

chatInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// Auto-resize textarea
chatInput.addEventListener('input', () => {
  chatInput.style.height = 'auto';
  chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
});

btnDevil.addEventListener('click', () => triggerDevil(false));
btnConviction.addEventListener('click', toggleConviction);

document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && chatDrawer.classList.contains('open')) {
    closeChatDrawer();
  }
});

// ── Hook into app.js analysis completion ─────────────────
// app.js calls historySaveCompleted() on 'done' — we hook the btn-debate visibility here
// via MutationObserver on verdict-tag (set after analysis completes)
const verdictTagEl = document.getElementById('verdict-tag');
const btnDebateEl  = document.getElementById('btn-debate');

if (verdictTagEl && btnDebateEl) {
  const observer = new MutationObserver(() => {
    const text = verdictTagEl.textContent || '';
    const isDone = !['ANALISANDO'].includes(text) && text.length > 0;
    btnDebateEl.style.display = isDone ? 'inline-flex' : 'none';
  });
  observer.observe(verdictTagEl, { childList: true, characterData: true, subtree: true });
}

btnDebateEl.addEventListener('click', () => {
  // Read current analysis state from app.js globals (mode, key, verdict)
  const mode    = window.currentMode || 'equity';
  const ticker  = document.getElementById('ticker')?.value?.trim()?.toUpperCase() || '';
  const startup = document.getElementById('startup-name')?.value?.trim() || '';
  const key     = mode === 'equity' ? ticker : startup;
  const verdict = verdictTagEl?.textContent || '';
  const confMatch = document.getElementById('verdict-meta')?.textContent || '';

  if (!key) return;
  openChatDrawer(mode, key, verdict, confMatch);
});
