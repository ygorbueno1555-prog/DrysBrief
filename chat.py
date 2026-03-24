"""chat.py — Cortiq Thesis Debate Engine
Loads analysis artifacts and enables contextual Q&A with streaming.
Devil's Advocate mode auto-generates the strongest counter-argument.
"""
import glob
import json
import os
from typing import AsyncGenerator, List, Dict, Optional


def _safe_slug(value: str) -> str:
    cleaned = "".join(ch for ch in value.lower() if ch.isalnum() or ch in ("-", "_"))
    return cleaned[:32] if cleaned else "item"


def load_latest_artifact(mode: str, key: str, base_dir: str) -> Optional[Dict]:
    """Find the most recent artifact for a given mode+key."""
    slug = _safe_slug(key)
    pattern = os.path.join(base_dir, f"analysis-{slug}-*.json")
    files = sorted(glob.glob(pattern), reverse=True)
    if not files:
        return None
    try:
        with open(files[0], encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _build_context(artifact: Dict) -> str:
    key        = artifact.get("key") or artifact.get("ticker") or ""
    mode       = artifact.get("mode", "")
    verdict    = artifact.get("verdict", "N/A")
    confidence = artifact.get("confidence", "N/A")
    thesis     = artifact.get("thesis", "") or "não informada"
    mandate    = artifact.get("mandate", "") or ""
    report     = artifact.get("report", "")[:4000]
    critic     = artifact.get("critic_notes", "")
    evaluation = artifact.get("evaluation", {})
    sources    = artifact.get("sources", [])[:12]
    queries    = artifact.get("queries", [])
    generated  = artifact.get("generated_at", "")

    sources_text = "\n".join(
        f"[{i+1}] {s.get('title','')} — {s.get('url','')}"
        for i, s in enumerate(sources)
    )

    market = artifact.get("market_data", {})
    market_text = ""
    if market:
        fields = []
        if market.get("price"):     fields.append(f"Preço: R${market['price']}")
        if market.get("pe"):        fields.append(f"P/L: {market['pe']}")
        if market.get("ev_ebitda"): fields.append(f"EV/EBITDA: {market['ev_ebitda']}")
        if market.get("mkt_cap"):   fields.append(f"Mkt Cap: {market['mkt_cap']}")
        if fields:
            market_text = "DADOS DE MERCADO: " + " | ".join(fields) + "\n\n"

    return f"""{market_text}ATIVO/EMPRESA: {key}
MODO: {mode}
VEREDITO: {verdict}
CONFIANÇA: {confidence}
TESE ORIGINAL: {thesis}
{f'MANDATO: {mandate}' if mandate else ''}
GERADO EM: {generated}

RELATÓRIO COMPLETO:
{report}

NOTAS DO CRÍTICO (pontos fracos identificados):
{critic or 'nenhuma nota'}

QUALIDADE DA PESQUISA:
- Coverage score: {evaluation.get('coverage_score', 'N/A')}
- Evidence score: {evaluation.get('evidence_score', 'N/A')}
- Primary source ratio: {evaluation.get('primary_source_ratio', 'N/A')}
- Seções faltantes: {', '.join(evaluation.get('missing_sections', [])) or 'nenhuma'}

FONTES CONSULTADAS ({len(sources)}):
{sources_text}

QUERIES EXECUTADAS: {len(queries)} pesquisas realizadas
""".strip()


CHAT_SYSTEM = """\
Você é o analista sênior que executou este research. Você tem acesso completo ao relatório, \
fontes, notas críticas e dados de mercado. Responda como quem realmente fez a análise — \
com autoridade, mas reconhecendo limitações quando existirem.

CONTEXTO DA ANÁLISE:
{context}

REGRAS:
- Responda APENAS com base nas evidências do relatório e fontes acima
- Seja direto: sem rodeios, sem disclaimers genéricos
- Use dados concretos com referência à fonte quando relevante
- Se não há dados suficientes para algo, diga explicitamente
- Quando defender a tese, cite as evidências específicas que a sustentam
- Mantenha foco no que é acionável para decisão de investimento
- Máximo 4 parágrafos por resposta — qualidade sobre quantidade
"""

DEVIL_SYSTEM = """\
Você é um analista cético especializado em identificar falhas de tese.
Sua função é construir o contra-argumento mais forte possível contra o veredito da análise.
Use os dados do próprio relatório para isso — a melhor crítica é a que usa os mesmos fatos \
para chegar a conclusões opostas.
"""

DEVIL_PROMPT = """\
Análise:
{context}

---
Construa o CONTRA-ARGUMENTO mais forte contra o veredito "{verdict}".

Se INVESTIR/COMPRAR → qual é o bear case mais sólido?
Se MONITORAR → por que deveria ser PASSAR agora?
Se PASSAR → existe uma hipótese realista que tornaria INVESTIR válido?

Formato: exatamente 4 bullets curtos e impactantes (máximo 20 palavras cada).
Comece com "⚠️ Devil's Advocate:" seguido dos bullets.
Seja específico — use números e fatos do relatório.
"""


def _get_client_and_model():
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY não configurada")
    from anthropic import AsyncAnthropic
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    return AsyncAnthropic(api_key=api_key), model


async def stream_chat(
    artifact: Dict,
    question: str,
    history: List[Dict],
) -> AsyncGenerator[str, None]:
    """Stream a chat response grounded in the analysis artifact."""
    try:
        client, model = _get_client_and_model()
    except ValueError as e:
        yield str(e)
        return

    context = _build_context(artifact)
    system  = CHAT_SYSTEM.format(context=context)
    messages = [*history, {"role": "user", "content": question}]

    try:
        async with client.messages.stream(
            model=model,
            max_tokens=900,
            temperature=0.3,
            system=system,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text
    except Exception as e:
        yield f"\n\nErro: {e}"


async def generate_devil(artifact: Dict) -> str:
    """Generate the strongest counter-argument against the verdict (non-streaming)."""
    try:
        client, model = _get_client_and_model()
    except ValueError as e:
        return f"Erro: {e}"

    context = _build_context(artifact)
    verdict = artifact.get("verdict", "")

    prompt = DEVIL_PROMPT.format(context=context[:3000], verdict=verdict)

    try:
        msg = await client.messages.create(
            model=model,
            max_tokens=350,
            temperature=0.4,
            system=DEVIL_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        return f"Erro ao gerar devil's advocate: {e}"


async def generate_conviction_breakdown(artifact: Dict) -> Dict:
    """Score the thesis across 5 investment dimensions (Haiku for speed)."""
    try:
        client, model = _get_client_and_model()
    except ValueError as e:
        return {"error": str(e)}

    context = _build_context(artifact)

    prompt = f"""
Com base nesta análise:

{context[:2500]}

---
Gere um breakdown de convicção em 5 dimensões. Para cada dimensão, dê uma pontuação de 0 a 100 \
e uma justificativa de 1 frase.

Responda APENAS com JSON válido neste formato exato:
{{
  "valuation":         {{"score": 85, "reason": "EV/EBITDA 4.2x abaixo da média histórica de 5.1x"}},
  "resultado_recente": {{"score": 75, "reason": "EBITDA +17% a/a, mas prejuízo líquido de US$3.8bi"}},
  "macro_setor":       {{"score": 60, "reason": "Demanda chinesa incerta, minério de ferro volátil"}},
  "execucao_gestao":   {{"score": 80, "reason": "Capex crescendo 15%, Novo Carajás em andamento"}},
  "catalise_proxima":  {{"score": 50, "reason": "Resultado 1T26 é o próximo gatilho crítico"}}
}}
"""

    try:
        msg = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        import re
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return {}
