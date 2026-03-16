# CORTIQ Decision Copilot

> Um agente de research financeiro que investiga teses de investimento em equities e startups, busca evidências na web, detecta lacunas, aprofunda a pesquisa e gera recomendações acionáveis com trilha de evidências verificável.

**[→ Demo ao vivo](https://drysbrief-production.up.railway.app/)**

---

## Por que isso é um agente, não um wrapper

A maioria dos "AI tools" faz: *input → LLM → output*.

Este sistema faz:

1. **Recebe** a tese ou empresa a analisar
2. **Gera** queries de pesquisa especializadas automaticamente
3. **Pesquisa** a web em paralelo (Tavily, search_depth=advanced)
4. **Detecta lacunas** — usa Claude Haiku para identificar o que está faltando
5. **Aprofunda** com queries de follow-up direcionadas
6. **Sintetiza** com Claude, citando fontes numeradas
7. **Compara** com análises anteriores: "o que mudou desde a última análise?"
8. **Salva** um artefato JSON estruturado por análise

---

## Modos

### ⬡ Equity — Validação de Tese
Analisa um ativo brasileiro (VALE3, PETR4, ITUB4...) e retorna:
- **VEREDITO**: TESE MANTIDA | TESE ALTERADA | TESE INVALIDADA
- Ação recomendada (COMPRAR | MANTER | REDUZIR | VENDER)
- O que mudou desde a última análise
- Catalisadores (30–90 dias)
- Riscos e gatilhos de invalidação
- Trilha de evidências com links clicáveis
- Sugestões de comparação (Explorar Também)

### ◈ Startup — Due Diligence
Gera um VC memo completo para qualquer startup:
- **VEREDITO**: INVESTIR | MONITORAR | PASSAR
- Time, mercado, tração, concorrentes
- Red flags e gatilhos de invalidação
- Tese de investimento (upside vs. risco)
- Próximos passos de diligência

---

## Arquitetura

```
main.py          FastAPI + SSE streaming
  └── agent.py   Orquestrador: queries → gap check → follow-up → síntese
        ├── researcher.py   Tavily web search + deduplicação + source typing
        └── reporter.py     Claude streaming + prompts estruturados
```

### Fluxo SSE (Server-Sent Events)
```
status          → atualização de progresso
queries         → lista de queries iniciais geradas
followup_queries→ queries de follow-up após gap detection
sources         → lista de fontes para linkagem de citações [N]
chunk           → fragmentos do relatório em tempo real
done            → análise concluída
```

### Artefatos gerados
Cada análise salva em `artifacts/{mode}_{key}_{timestamp}/analysis.json`:
```json
{
  "mode": "equity",
  "key": "VALE3",
  "queries": [...],
  "followup_queries": [...],
  "sources": [{"title", "url", "source_type"}],
  "verdict": "TESE MANTIDA",
  "confidence": "MÉDIA",
  "report": "...",
  "generated_at": "2025-01-15T10:30:00Z"
}
```

---

## Stack

| Componente | Tecnologia |
|---|---|
| LLM | Claude (Anthropic API) |
| Web Research | Tavily (`search_depth=advanced`) |
| Gap Detection | Claude Haiku |
| Backend | FastAPI + SSE |
| Frontend | HTML/CSS/JS vanilla |
| Deploy | Railway |

---

## Rodando localmente

```bash
git clone https://github.com/ygorbueno1555-prog/DrysBrief
cd DrysBrief

pip install -r requirements.txt

cp .env.example .env
# Edite .env com suas chaves

uvicorn main:app --reload
# Acesse http://localhost:8000
```

## Variáveis de ambiente

```env
ANTHROPIC_API_KEY=   # Chave da API Claude (obrigatório)
ANTHROPIC_MODEL=     # Padrão: claude-sonnet-4-6
TAVILY_API_KEY=      # Chave da API Tavily (obrigatório)
```

---

## Próximos passos

- [ ] Dados estruturados via yfinance (P/E, EBITDA, preço real)
- [ ] Monitoramento de tese com alertas automáticos
- [ ] Comparação lado a lado entre dois ativos
- [ ] Export PDF do relatório

---

*Construído como portfolio para demonstrar capacidade de construir AI agents aplicados a finanças.*
