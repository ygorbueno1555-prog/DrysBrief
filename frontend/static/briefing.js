/* ============================================================
   CORTIQ PORTFOLIO WATCH — Review & Approve UI
   ============================================================ */

let currentDraftId = null;
let editMode = false;

const $ = id => document.getElementById(id);

// ── Init ──────────────────────────────────────────────────
(async function init() {
  await loadDraftList();

  $('btn-generate').addEventListener('click', generateBrief);
  $('btn-edit').addEventListener('click', toggleEdit);
  $('btn-discard').addEventListener('click', discardDraft);
  $('btn-send').addEventListener('click', sendDraft);
  $('btn-save-recipients').addEventListener('click', saveRecipients);
})();

// ── Draft list ────────────────────────────────────────────
async function loadDraftList() {
  const res = await fetch('/api/drafts');
  const drafts = await res.json();
  renderDraftList(drafts);

  // Auto-open first draft if nothing selected
  if (!currentDraftId && drafts.length) {
    openDraft(drafts[0].id);
  }
}

function renderDraftList(drafts) {
  const el = $('draft-list');
  if (!drafts.length) {
    el.innerHTML = '<div class="draft-list-empty">Nenhum relatório gerado ainda</div>';
    return;
  }
  el.innerHTML = drafts.map(d => `
    <div class="draft-item ${d.id === currentDraftId ? 'active' : ''} status-${d.status}"
         onclick="openDraft('${d.id}')">
      <div class="draft-item-date">${d.date || d.id}</div>
      <div class="draft-item-subject">${truncate(d.subject || '', 38)}</div>
      <div class="draft-item-status ${d.status}">${statusLabel(d.status)}</div>
    </div>
  `).join('');
}

function statusLabel(s) {
  return { draft: 'Draft', sent: 'Enviado', discarded: 'Descartado' }[s] || s;
}

// ── Open draft ────────────────────────────────────────────
async function openDraft(id) {
  currentDraftId = id;
  editMode = false;

  const res = await fetch(`/api/drafts/${id}`);
  const draft = await res.json();

  $('brief-empty').style.display = 'none';
  $('draft-panel').style.display = 'flex';

  renderDraft(draft);
  await loadDraftList(); // refresh to update active state
}

function renderDraft(draft) {
  $('draft-subject').value = draft.subject || '';
  $('draft-recipients').value = (draft.recipients || []).join(', ');
  $('draft-preview').innerHTML = marked.parse(draft.content || '');
  $('draft-textarea').value = draft.content || '';

  // Status badge
  const badge = $('draft-status-badge');
  badge.textContent = statusLabel(draft.status).toUpperCase();
  badge.className = `status-badge ${draft.status}`;

  // Buttons
  const isSent       = draft.status === 'sent';
  const isDiscarded  = draft.status === 'discarded';
  const inactive     = isSent || isDiscarded;
  $('btn-send').disabled    = inactive;
  $('btn-discard').disabled = inactive;
  $('btn-edit').disabled    = inactive;
  $('btn-edit').textContent = editMode ? 'Ver Preview' : 'Editar';

  // Edit mode
  $('draft-preview').style.display  = editMode ? 'none' : 'block';
  $('draft-textarea').style.display = editMode ? 'block' : 'none';

  // Sent info
  if (draft.sent_at) {
    $('draft-sent-info').style.display = 'block';
    $('draft-sent-info').textContent =
      `Enviado em ${new Date(draft.sent_at).toLocaleString('pt-BR')} para ${(draft.recipients||[]).join(', ')}`;
  } else {
    $('draft-sent-info').style.display = 'none';
  }
}

// ── Actions ───────────────────────────────────────────────
function toggleEdit() {
  editMode = !editMode;
  $('btn-edit').textContent = editMode ? 'Ver Preview' : 'Editar';

  if (editMode) {
    $('draft-preview').style.display  = 'none';
    $('draft-textarea').style.display = 'block';
    $('draft-textarea').focus();
  } else {
    // Save on exit edit
    saveDraftContent();
    $('draft-preview').style.display  = 'block';
    $('draft-textarea').style.display = 'none';
  }
}

async function saveDraftContent() {
  if (!currentDraftId) return;
  const content = $('draft-textarea').value;
  const subject = $('draft-subject').value;
  await fetch(`/api/drafts/${currentDraftId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, subject }),
  });
  // Update preview
  $('draft-preview').innerHTML = marked.parse(content);
}

async function saveRecipients() {
  if (!currentDraftId) return;
  const raw = $('draft-recipients').value;
  const recipients = raw.split(',').map(s => s.trim()).filter(Boolean);
  await fetch(`/api/drafts/${currentDraftId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ recipients }),
  });
  showToast('Destinatários salvos');
}

async function discardDraft() {
  if (!currentDraftId) return;
  if (!confirm('Descartar este briefing?')) return;
  await fetch(`/api/drafts/${currentDraftId}`, { method: 'DELETE' });
  await loadDraftList();
  showToast('Briefing descartado');
}

async function sendDraft() {
  if (!currentDraftId) return;

  // Save any pending edits first
  if (editMode) await saveDraftContent();

  const recipients = $('draft-recipients').value.split(',').map(s => s.trim()).filter(Boolean);
  if (!recipients.length) {
    alert('Adicione pelo menos um destinatário antes de enviar.');
    $('draft-recipients').focus();
    return;
  }

  // Save recipients
  await fetch(`/api/drafts/${currentDraftId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ recipients }),
  });

  $('btn-send').disabled = true;
  $('btn-send').textContent = 'Enviando...';

  const res = await fetch(`/api/drafts/${currentDraftId}/send`, { method: 'POST' });
  if (res.ok) {
    showToast('Brief enviado com sucesso!', 'green');
    await openDraft(currentDraftId);
  } else {
    const err = await res.json().catch(() => ({}));
    alert(`Erro ao enviar: ${err.detail || 'verifique RESEND_API_KEY'}`);
    $('btn-send').disabled = false;
    $('btn-send').textContent = 'Aprovar e Enviar →';
  }
}

// ── Generate new brief ────────────────────────────────────
async function generateBrief() {
  $('generating-overlay').style.display = 'flex';
  $('btn-generate').disabled = true;

  const msgs = [
    'Pesquisando ativos e startups em paralelo...',
    'Detectando lacunas de cobertura...',
    'Gerando resumos com Claude...',
    'Montando o relatório da carteira...',
  ];
  let i = 0;
  const interval = setInterval(() => {
    $('generating-sub').textContent = msgs[i % msgs.length];
    i++;
  }, 4000);

  try {
    const res = await fetch('/api/briefing/run', { method: 'POST' });
    if (res.ok) {
      const data = await res.json();
      clearInterval(interval);
      $('generating-overlay').style.display = 'none';
      $('btn-generate').disabled = false;
      await loadDraftList();
      await openDraft(data.id);
      showToast('Relatório gerado!', 'green');
    } else {
      throw new Error('Falha na geração');
    }
  } catch (e) {
    clearInterval(interval);
    $('generating-overlay').style.display = 'none';
    $('btn-generate').disabled = false;
    alert('Erro ao gerar brief. Verifique os logs.');
  }
}

// ── Utils ─────────────────────────────────────────────────
function truncate(s, n) {
  return s.length > n ? s.slice(0, n) + '…' : s;
}

function showToast(msg, type = 'blue') {
  const t = document.createElement('div');
  t.className = `toast toast-${type}`;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.classList.add('visible'), 10);
  setTimeout(() => { t.classList.remove('visible'); setTimeout(() => t.remove(), 300); }, 3000);
}
