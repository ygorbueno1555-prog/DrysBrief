"""reporter.py — Cortiq Decision Copilot
Generates structured investment reports via DeepSeek (async streaming).
"""
import os
from typing import AsyncGenerator, List, Dict
from openai import AsyncOpenAI

EQUITY_PROMPT = """\
Você é um analista fundamentalista sênior com 20 anos de experiência no mercado brasileiro.

Com base nas pesquisas abaixo sobre {ticker}, avalie se a tese de investimento continua válida \
e gere um relatório de decisão estruturado.

TESE ATUAL: {thesis}
MANDATO DA CARTEIRA: {mandate}

PESQUISAS:
{research}

---
Gere o relatório EXATAMENTE neste formato (use ## para seções, **negrito** para destaques):

## VEREDITO
**[TESE MANTIDA | TESE ALTERADA | TESE INVALIDADA]**
Confiança: [ALTA | MÉDIA | BAIXA]
Racional: [1 frase direta e objetiva]

## AÇÃO RECOMENDADA
**[COMPRAR | MANTER | REDUZIR | VENDER]**
[1-2 frases de justificativa com dados concretos]

## O QUE MUDOU
- [fato relevante 1 com dado/fonte]
- [fato relevante 2 com dado/fonte]
- [fato relevante 3 com dado/fonte]

## CATALISADORES (próximos 30-90 dias)
- [catalisador 1]
- [catalisador 2]

## RISCOS E GATILHOS DE INVALIDAÇÃO
- **[risco 1]**: [descrição + o que tornaria a tese inválida]
- **[risco 2]**: [descrição + o que tornaria a tese inválida]

## IMPACTO NO PORTFÓLIO
[Análise do impacto considerando o mandato informado. Se mandato não informado, análise geral de risco/retorno.]

## TRILHA DE EVIDÊNCIAS
- [evidência 1 com fonte]
- [evidência 2 com fonte]
- [evidência 3 com fonte]

Seja direto e use dados das pesquisas. Se não há dados suficientes para algum ponto, diga explicitamente.
"""

STARTUP_PROMPT = """\
Você é um analista de venture capital sênior com experiência em early-stage no Brasil e globalmente.

Com base nas pesquisas abaixo sobre {name}, gere um VC memo de due diligence completo.

TESE DE INVESTIMENTO: {thesis}
SITE: {url}

PESQUISAS:
{research}

---
Gere o VC memo EXATAMENTE neste formato (use ## para seções, **negrito** para destaques):

## VEREDITO
**[INVESTIR | MONITORAR | PASSAR]**
Confiança: [ALTA | MÉDIA | BAIXA]
Racional: [1 frase direta e objetiva]

## RESUMO EXECUTIVO
[2-3 frases: o que fazem, para quem, por que importa agora, qual o diferencial]

## TIME
- **Força**: [pontos fortes dos founders — experiência, exits, domínio do problema]
- **Gap**: [o que falta no time — perfil técnico, comercial, setor]

## MERCADO
- **TAM estimado**: [valor se disponível, caso contrário "dados insuficientes"]
- **Crescimento**: [taxa anual ou tendência identificada]
- **Timing**: [Cedo demais | No tempo certo | Tarde — com justificativa]

## TRAÇÃO
- [métrica ou sinal de tração 1]
- [métrica ou sinal de tração 2]

## CONCORRENTES
- **[concorrente 1]**: [como se diferenciam desta startup]
- **[concorrente 2]**: [como se diferenciam desta startup]

## RED FLAGS
- [red flag 1 — risco concreto identificado]
- [red flag 2 — risco concreto identificado]

## TESE DE INVESTIMENTO
**Por que INVESTIR**: [argumento principal de upside]
**Por que PASSAR**: [contra-argumento principal de risco]

## GATILHOS DE INVALIDAÇÃO
- [evento que mudaria o veredito para PASSAR]
- [métrica que, se não atingida, invalida a tese]

## PRÓXIMOS PASSOS
- [due diligence adicional recomendada]
- [pergunta prioritária para os founders]

Seja direto. Use dados das pesquisas. Se não há dados suficientes, indique claramente "dados insuficientes".
"""


def _format_research(results: List[Dict]) -> str:
    parts = []
    for i, r in enumerate(results[:20], 1):
        parts.append(f"[{i}] {r['title']}\n{r['content']}\nFonte: {r['url']}")
    return "\n\n".join(parts)


def _get_client() -> AsyncOpenAI:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY não configurada")
    return AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com")


async def stream_equity_report(
    results: List[Dict], ticker: str, thesis: str, mandate: str
) -> AsyncGenerator[str, None]:
    try:
        client = _get_client()
    except ValueError as e:
        yield f"## Erro de Configuração\n{e}"
        return

    prompt = EQUITY_PROMPT.format(
        ticker=ticker,
        thesis=thesis or "Sem tese específica — gere análise geral do ativo",
        mandate=mandate or "Sem mandato específico — análise geral",
        research=_format_research(results),
    )

    try:
        stream = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            max_tokens=2000,
            temperature=0.3,
        )
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                yield content
    except Exception as e:
        yield f"\n\n## Erro na Análise\n{e}"


async def stream_startup_report(
    results: List[Dict], name: str, url: str, thesis: str
) -> AsyncGenerator[str, None]:
    try:
        client = _get_client()
    except ValueError as e:
        yield f"## Erro de Configuração\n{e}"
        return

    prompt = STARTUP_PROMPT.format(
        name=name,
        url=url or "não informado",
        thesis=thesis or "Sem tese específica — gere análise geral da startup",
        research=_format_research(results),
    )

    try:
        stream = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            stream=True,
            max_tokens=2500,
            temperature=0.3,
        )
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                yield content
    except Exception as e:
        yield f"\n\n## Erro na Análise\n{e}"
