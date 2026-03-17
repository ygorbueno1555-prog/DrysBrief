"""reporter.py — Cortiq Decision Copilot v2
Generates structured investment reports via Claude (async streaming).
"""
import os
from typing import AsyncGenerator, List, Dict, Optional
from anthropic import AsyncAnthropic

EQUITY_PROMPT = """\
Você é um analista fundamentalista sênior com 20 anos de experiência no mercado brasileiro.

Com base nas pesquisas abaixo sobre {ticker}, avalie se a tese de investimento continua válida \
e gere um relatório de decisão estruturado.

TESE ATUAL: {thesis}
MANDATO DA CARTEIRA: {mandate}
{prev_context}
{market_data_section}
PESQUISAS (cite fontes pelo número [N] ao lado de cada afirmação):
{research}

---
REGRAS:
- Use APENAS informações presentes nas pesquisas acima
- Cite fontes com [N] em cada afirmação relevante
- Separe fatos confirmados de inferências (use "estimado" ou "provável" para inferências)
- Se não há dados suficientes para um ponto, diga "dados insuficientes"

Gere o relatório EXATAMENTE neste formato (use ## para seções, **negrito** para destaques):

## VEREDITO
**[TESE MANTIDA | TESE ALTERADA | TESE INVALIDADA]**
Confiança: [ALTA | MÉDIA | BAIXA]
Racional da confiança: [1 frase — baseada na qualidade, quantidade e recência das evidências encontradas]
Racional: [1 frase direta e objetiva sobre a tese]

## AÇÃO RECOMENDADA
**[COMPRAR | MANTER | REDUZIR | VENDER]**
[1-2 frases com dados concretos e citações [N]]

{what_changed_section}

## O QUE MUDOU
- [fato relevante 1 com dado e citação [N]]
- [fato relevante 2 com dado e citação [N]]
- [fato relevante 3 com dado e citação [N]]

## CATALISADORES (próximos 30-90 dias)
- [catalisador 1 com citação [N] se disponível]
- [catalisador 2]

## RISCOS E GATILHOS DE INVALIDAÇÃO
- **[risco 1]**: [descrição + o que tornaria a tese inválida]
- **[risco 2]**: [descrição + o que tornaria a tese inválida]

## IMPACTO NO PORTFÓLIO
[Análise do impacto considerando o mandato informado. Se mandato não informado, análise geral de risco/retorno.]

## TRILHA DE EVIDÊNCIAS
- **[N]** [título da fonte] — [afirmação principal suportada] — [URL completa]
- **[N]** [título da fonte] — [afirmação principal suportada] — [URL completa]
- **[N]** [título da fonte] — [afirmação principal suportada] — [URL completa]

## EXPLORAR TAMBÉM
Sugira 3 ativos/empresas que o analista pode querer comparar ou pesquisar em seguida:
- **[ticker ou empresa 1]** — [por que é relevante comparar]
- **[ticker ou empresa 2]** — [por que é relevante comparar]
- **[ticker ou empresa 3]** — [por que é relevante comparar]

Seja direto e use dados das pesquisas. Se não há dados suficientes para algum ponto, diga explicitamente.
"""

STARTUP_PROMPT = """\
Você é um analista de venture capital sênior com experiência em early-stage no Brasil e globalmente.

Com base nas pesquisas abaixo sobre {name}, gere um VC memo de due diligence completo.

TESE DE INVESTIMENTO: {thesis}
SITE: {url}
{prev_context}
PESQUISAS (cite fontes pelo número [N] ao lado de cada afirmação):
{research}

---
REGRAS:
- Use APENAS informações presentes nas pesquisas acima
- Cite fontes com [N] em cada afirmação relevante
- Separe fatos confirmados de inferências (use "estimado" ou "provável" para inferências)
- Se não há dados suficientes, indique claramente "dados insuficientes"

Gere o VC memo EXATAMENTE neste formato (use ## para seções, **negrito** para destaques):

## VEREDITO
**[INVESTIR | MONITORAR | PASSAR]**
Confiança: [ALTA | MÉDIA | BAIXA]
Racional da confiança: [1 frase — baseada na qualidade, quantidade e recência das evidências encontradas]
Racional: [1 frase direta e objetiva]

## RESUMO EXECUTIVO
[2-3 frases: o que fazem, para quem, por que importa agora, qual o diferencial]

{what_changed_section}

## TIME
- **Força**: [pontos fortes dos founders com citações [N]]
- **Gap**: [o que falta no time]

## MERCADO
- **TAM estimado**: [valor com citação [N] ou "dados insuficientes"]
- **Crescimento**: [taxa anual ou tendência identificada com citação [N]]
- **Timing**: [Cedo demais | No tempo certo | Tarde — com justificativa]

## TRAÇÃO
- [métrica ou sinal de tração 1 com citação [N]]
- [métrica ou sinal de tração 2]

## CONCORRENTES
- **[concorrente 1]**: [como se diferenciam desta startup]
- **[concorrente 2]**: [como se diferenciam desta startup]

## RED FLAGS
- [red flag 1 com citação [N] se disponível]
- [red flag 2]

## TESE DE INVESTIMENTO
**Por que INVESTIR**: [argumento principal de upside]
**Por que PASSAR**: [contra-argumento principal de risco]

## GATILHOS DE INVALIDAÇÃO
- [evento que mudaria o veredito para PASSAR]
- [métrica que, se não atingida, invalida a tese]

## TRILHA DE EVIDÊNCIAS
- **[N]** [título da fonte] — [afirmação principal suportada] — [URL completa]
- **[N]** [título da fonte] — [afirmação principal suportada] — [URL completa]
- **[N]** [título da fonte] — [afirmação principal suportada] — [URL completa]

## PRÓXIMOS PASSOS
- [due diligence adicional recomendada]
- [pergunta prioritária para os founders]

## EXPLORAR TAMBÉM
Sugira 3 startups similares que o analista pode querer pesquisar para comparação:
- **[startup 1]** — [por que é relevante comparar ou o que têm em comum]
- **[startup 2]** — [por que é relevante comparar ou o que têm em comum]
- **[startup 3]** — [por que é relevante comparar ou o que têm em comum]

Seja direto. Use dados das pesquisas. Se não há dados suficientes, indique claramente.
"""


def _format_research(results: List[Dict]) -> str:
    parts = []
    for i, r in enumerate(results[:20], 1):
        source_label = f"[{r.get('source_type', 'web')}]" if r.get('source_type') else ""
        parts.append(f"[{i}] {r['title']} {source_label}\n{r['content']}\nFonte: {r['url']}")
    return "\n\n".join(parts)


def _get_client() -> AsyncAnthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY não configurada")
    return AsyncAnthropic(api_key=api_key)


def _get_model() -> str:
    return os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")


def _load_critic_rules() -> dict:
    import json
    base = os.getenv("CORTIQ_CONFIG_DIR", os.path.join(os.path.dirname(__file__), "config"))
    path = os.path.join(base, "critic_rules.json")
    if not os.path.exists(path):
        return {"max_bullets": 6}
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


async def stream_equity_report(
    results: List[Dict],
    ticker: str,
    thesis: str,
    mandate: str,
    prev_verdict: str = "",
    prev_date: str = "",
    market_data: Optional[dict] = None,
) -> AsyncGenerator[str, None]:
    try:
        client = _get_client()
    except ValueError as e:
        yield f"## Erro de Configuração\n{e}"
        return

    from equity_data import format_market_data

    # Build comparison context if we have previous analysis
    prev_context = ""
    what_changed_section = ""
    if prev_verdict and prev_date:
        prev_context = f"\nANÁLISE ANTERIOR ({prev_date}): O veredito foi **{prev_verdict}**.\n"
        what_changed_section = f"## O QUE MUDOU DESDE {prev_date}\n[Compare com o veredito anterior ({prev_verdict}) e destaque o que mudou: novos riscos, novos catalisadores, mudança de recomendação, fatos relevantes novos]"

    market_data_section = ""
    if market_data:
        formatted = format_market_data(market_data)
        if formatted:
            market_data_section = formatted + "\n\n"

    prompt = EQUITY_PROMPT.format(
        ticker=ticker,
        thesis=thesis or "Sem tese específica — gere análise geral do ativo",
        mandate=mandate or "Sem mandato específico — análise geral",
        research=_format_research(results),
        prev_context=prev_context,
        what_changed_section=what_changed_section,
        market_data_section=market_data_section,
    )

    try:
        async with client.messages.stream(
            model=_get_model(),
            max_tokens=2500,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            async for text in stream.text_stream:
                yield text
    except Exception as e:
        yield f"\n\n## Erro na Análise\n{e}"


async def stream_startup_report(
    results: List[Dict],
    name: str,
    url: str,
    thesis: str,
    prev_verdict: str = "",
    prev_date: str = "",
) -> AsyncGenerator[str, None]:
    try:
        client = _get_client()
    except ValueError as e:
        yield f"## Erro de Configuração\n{e}"
        return

    prev_context = ""
    what_changed_section = ""
    if prev_verdict and prev_date:
        prev_context = f"\nANÁLISE ANTERIOR ({prev_date}): O veredito foi **{prev_verdict}**.\n"
        what_changed_section = f"## O QUE MUDOU DESDE {prev_date}\n[Compare com o veredito anterior ({prev_verdict}) e destaque mudanças: tração, time, mercado, funding, riscos novos]"

    prompt = STARTUP_PROMPT.format(
        name=name,
        url=url or "não informado",
        thesis=thesis or "Sem tese específica — gere análise geral da startup",
        research=_format_research(results),
        prev_context=prev_context,
        what_changed_section=what_changed_section,
    )

    try:
        async with client.messages.stream(
            model=_get_model(),
            max_tokens=2500,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            async for text in stream.text_stream:
                yield text
    except Exception as e:
        yield f"\n\n## Erro na Análise\n{e}"


async def generate_critic_notes(
    mode: str,
    report: str,
    evidence: str,
    evaluation: Dict,
) -> str:
    try:
        client = _get_client()
    except ValueError as e:
        return f"Erro: {e}"

    rules = _load_critic_rules()
    max_bullets = rules.get("max_bullets", 6)
    missing = ", ".join(evaluation.get("missing_sections", [])) or "nenhuma"

    prompt = f"""
Você é um revisor crítico de research.

Contexto:
- mode: {mode}
- coverage_score: {evaluation.get('coverage_score')}
- evidence_score: {evaluation.get('evidence_score')}
- primary_source_ratio: {evaluation.get('primary_source_ratio')}
- missing_sections: {missing}

Tarefa:
- Aponte afirmações sem evidência forte
- Indique se a confiança parece superestimada
- Sinalize seções fracas
- Sugira até 2 queries extras

Responda em até {max_bullets} bullets curtos.

Relatório:
{report}

Evidências:
{evidence}
""".strip()

    try:
        msg = await client.messages.create(
            model=_get_model(),
            max_tokens=400,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        return f"Erro critic: {e}"


BRIEF_ENTRY_PROMPT = """\
Você é um analista financeiro sênior. Com base nas pesquisas abaixo sobre {name} ({mode}), \
gere um briefing matinal CONCISO para um profissional de investimentos.

PESQUISAS:
{research}

---
Gere EXATAMENTE neste formato (máximo 6 linhas):

**[TESE MANTIDA | TESE ALTERADA | TESE INVALIDADA | INVESTIR | MONITORAR | PASSAR]** | Confiança: [ALTA | MÉDIA | BAIXA]
Alerta hoje: [VERDE | AMARELO | VERMELHO]
[2-3 frases com fatos concretos: o que mudou recentemente, situação atual, dado principal]
Gatilho: [principal risco/evento a observar hoje, ou "sem alerta crítico"]

Use apenas dados das pesquisas. Se dados insuficientes, diga explicitamente.
"""


async def generate_brief_entry(
    results: List[Dict], name: str, mode: str
) -> str:
    """Generate a concise briefing entry (non-streaming)."""
    try:
        client = _get_client()
    except ValueError as e:
        return f"**ERRO** | {e}"

    prompt = BRIEF_ENTRY_PROMPT.format(
        name=name,
        mode=mode,
        research=_format_research(results[:8]),
    )

    try:
        msg = await client.messages.create(
            model=_get_model(),
            max_tokens=300,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as e:
        return f"**ERRO** | {e}"
