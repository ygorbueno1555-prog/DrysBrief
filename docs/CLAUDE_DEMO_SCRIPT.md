# Roteiro de demo para gravar com Claude

Use este prompt no Claude para ele te ajudar a narrar uma demo curta e objetiva do produto:

```text
Quero gravar uma demo de 2 minutos e 30 segundos do meu projeto "Cortiq Decision Copilot" para uma candidatura de AI builder.

Contexto:
- Público: Luis Felipe Amaral, Drys Capital / Cortiq
- O brief dele pedia algo simples que funcionasse, com auto-research + Claude/OpenClaw + agente funcional
- Exemplos citados por ele: AI startup research agent, AI stock research tool, AI tool discovery engine

O produto tem 2 workflows:
1. Decision Copilot
- Análise on-demand para equities e startups
- Gera queries automaticamente
- Pesquisa a web via Tavily
- Usa Claude Haiku para detectar lacunas e gerar follow-up queries
- Usa Claude Sonnet para sintetizar um relatório estruturado com citações
- Mantém histórico local para comparar "o que mudou desde a última análise"

2. Portfolio Watch
- Gera relatórios diários por gestor/carteira
- Cada portfolio tem seus ativos, startups, recipients e mandato
- Cria um draft por carteira
- Detecta alertas automáticos comparando com o draft anterior
- Se o veredito muda ou o alerta piora, destaca isso em "Alertas Automáticos"
- Pode enviar por email via Resend depois de aprovação humana

Também há dados estruturados via yfinance no fluxo de equity.

Quero que você escreva:
1. Um roteiro falado em português brasileiro, natural, direto, com no máximo 2min30
2. Uma versão ainda mais curta de 60 segundos
3. Uma lista de cenas para gravar a tela na ordem ideal
4. Uma frase final forte de encerramento conectando o projeto à ideia de AI-native workflow para analistas

Tom:
- builder
- execution-first
- sem hype exagerado
- sem soar como pitch comercial pronto
- mostrar produto funcionando > explicar stack
```

## Ordem sugerida de gravação

1. Abrir a home do `Decision Copilot`
2. Rodar uma análise de equity mostrando queries, follow-up e streaming
3. Mostrar uma análise de startup já salva no histórico
4. Entrar em `Portfolio Watch`
5. Mostrar que agora existe relatório por gestor/carteira
6. Destacar `Alertas Automáticos`
7. Mostrar edição/aprovação do draft
8. Encerrar com GitHub + demo link
