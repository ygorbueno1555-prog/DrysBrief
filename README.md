# Cortiq Decision Copilot

> Camada de decisão para profissionais de investimento — fecha o loop entre pesquisa e ação.

O Credit Guide da Cortiq agrega dados e análise. O Decision Copilot transforma esse conhecimento em **recomendação rastreável e operável** — com trilha de evidências, gatilhos de invalidação e impacto no portfólio.

---

## O que faz

**Modo Equity** — valida se uma tese de investimento continua válida:
1. Pesquisa automaticamente 6 ângulos (resultados, valuation, catalisadores, riscos, notícias, tese)
2. Processa com DeepSeek via análise fundamentalista
3. Entrega: `TESE MANTIDA / ALTERADA / INVALIDADA` + ação recomendada + trilha de evidências

**Modo Startup** — due diligence automatizada para angel investing / VC:
1. Pesquisa 7 dimensões (time, funding, mercado, concorrentes, tração, notícias, red flags)
2. Gera VC memo estruturado com DeepSeek
3. Entrega: `INVESTIR / MONITORAR / PASSAR` + confiança + gatilhos de invalidação

Tudo em **tempo real via SSE** — você vê cada etapa da pesquisa acontecendo.

---

## Stack

```
Python · FastAPI · SSE · Tavily (research) · DeepSeek (synthesis) · HTML/CSS/JS
```

---

## Como rodar (local)

```bash
# 1. Clone
git clone https://github.com/SEU_USER/cortiq-copilot.git
cd cortiq-copilot

# 2. Instale dependências
pip install -r requirements.txt

# 3. Configure as chaves
cp .env.example .env
# Edite .env:
# TAVILY_API_KEY=tvly-...
# DEEPSEEK_API_KEY=sk-...

# 4. Suba o servidor
uvicorn main:app --host 0.0.0.0 --port 8000

# 5. Abra
# http://localhost:8000
```

---

## Deploy (Railway — gratuito)

1. Fork no GitHub
2. Novo projeto em [railway.app](https://railway.app) → Deploy from GitHub
3. Adicione as variáveis: `TAVILY_API_KEY` e `DEEPSEEK_API_KEY`
4. Deploy automático

---

## Endpoints

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/` | Frontend |
| GET | `/health` | Health check |
| GET | `/analyze/equity?ticker=VALE3&thesis=...&mandate=...` | SSE — Equity |
| GET | `/analyze/startup?name=...&url=...&thesis=...` | SSE — Startup |

---

## Eventos SSE

| Evento | Payload | Descrição |
|--------|---------|-----------|
| `status` | string | Etapa atual da pesquisa |
| `queries` | JSON array | Queries sendo executadas |
| `chunk` | string | Fragmento do relatório (streaming) |
| `done` | string | Análise concluída |
| `error` | string | Erro ocorrido |

---

## Arquitetura

```
Input (ticker ou startup)
    ↓
agent.py: build_queries() → 6-7 queries específicas por modo
    ↓
researcher.py: Tavily API → 5 resultados por query (search_depth: advanced)
    ↓
reporter.py: DeepSeek streaming → relatório estruturado em markdown
    ↓
main.py: SSE → frontend em tempo real
```

---

## Output — Equity

```
## VEREDITO
**TESE MANTIDA**
Confiança: ALTA
Racional: Fundamentos operacionais seguem robustos apesar de baixas contábeis pontuais.

## AÇÃO RECOMENDADA
**MANTER**
EBITDA proforma +17% no 4T25 confirma a tese de geração de caixa...

## O QUE MUDOU
→ Prejuízo líquido de US$3,8bi majoritariamente de baixas contábeis não recorrentes
→ EBITDA proforma avançou +17% para US$4,8bi no 4T25
→ Valuation considerado "fairly priced" após rali recente

## CATALISADORES (30-90 dias)
→ Novos estímulos econômicos da China impactando preço do minério
→ Continuação do fluxo para ativos reais e mercados emergentes

## RISCOS E GATILHOS DE INVALIDAÇÃO
→ Risco China: queda sustentada abaixo de US$100/ton invalida a tese
→ Risco regulatório: novas exigências pós-Mariana afetando fluxo de caixa

## TRILHA DE EVIDÊNCIAS
→ EBITDA 4T25: US$4,8bi (+17% vs. estimativas) — Valor Econômico
→ Valuation: preço justo R$76,83 vs. cotação R$78,3 — BTG Research
```

---

## Output — Startup

```
## VEREDITO
**INVESTIR**
Confiança: MÉDIA
Racional: Time forte, mercado validado, mas métricas de tração ainda incipientes.

## TIME
→ Força: founders com experiência prévia em fintech e saídas anteriores
→ Gap: ausência de perfil comercial sênior no C-level

## MERCADO
→ TAM estimado: R$4,2bi (crédito consignado privado)
→ Crescimento: 28% a.a. nos últimos 3 anos
→ Timing: No tempo certo

...
```
