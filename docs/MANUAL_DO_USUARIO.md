# Manual do Usuário — Atlas Investment OS

> Versão do produto: **v1.2.0** · Este manual descreve **como usar** o Atlas no dia
> a dia. Para o que o código faz internamente, veja `STATUS.md`; para intenção de
> projeto, veja `docs/ARCHITECTURE.md` e os ADRs em `docs/adr/`.

O Atlas transforma dados de mercado e fundamentos em **scores transparentes,
decisões, teses, inteligência de carteira e relatórios**. Ele **não executa
ordens** — é consultivo. Toda compra/venda é decisão sua; o Atlas organiza a
evidência e registra o que você decidiu.

---

## 1. O que o Atlas entrega

| Saída | Para quê | Onde abrir |
|---|---|---|
| **Cockpit "Atlas — Hoje"** | Página única de decisão do dia (Agir agora / Oportunidades / Acompanhar) | `output/relatorios/decision_cockpit.html` |
| **Relatório HTML** | Relatório completo com detalhe por ativo, scores e teses | `output/relatorios/atlas_report_latest.html` |
| **One-pager por ticker** | Análise de um símbolo só | `output/relatorios/atlas_report_{SYMBOL}_*.html` |
| **Excel** | Ranking, decisões, explicabilidade, histórico | `output/relatorios/latest.xlsx` |
| **Morning Brief** | Resumo curto em Markdown | `output/relatorios/morning_brief.md` |

> Os arquivos em `output/dados/*.json` são **contrato interno** entre motor e
> relatório (chegam a vários MB) — não são feitos para abrir direto. Abra só o que
> está em `output/relatorios/`.

---

## 2. Primeira configuração (uma vez)

```cmd
.venv\Scripts\activate
pip install -r requirements.txt
```

Crie o arquivo de segredos a partir do exemplo (fica **fora do Git**):

```text
config/provider_secrets.json   ← copie de config/provider_secrets.example.json
```

Preencha: **SEC User-Agent**, **chave FMP** e **chave Massive**. Se você habilitar
uma fonte secundária sem a chave correspondente, o Atlas emite um *warning*
explícito — nunca falha em silêncio.

Confirme que está tudo verde antes de rodar de verdade:

```cmd
pytest
```

---

## 3. Suas duas listas de entrada

O Atlas trabalha sobre dois arquivos CSV que **você edita à mão**:

### Carteira real — `config/portfolio.csv`
Colunas obrigatórias: `symbol,quantity,average_price`.
Opcionais: `currency,sector,country,notes`.

```csv
symbol,quantity,average_price,currency,sector,country,notes
MSFT,10,410.50,USD,Technology,USA,Core holding
BUD,20,58.10,USD,Consumer Defensive,Belgium,
```

Regras: `quantity > 0`, `average_price ≥ 0`, símbolos duplicados são somados,
linhas inválidas são reportadas.

### Watchlist — `config/watchlist.csv`
Lista curada de candidatas a acompanhar. Você pode editar à mão (`source=manual`).
Desde a curadoria automática (ADR-036), o Atlas **também** pode incluir/remover
entradas `source=auto` durante um run — mas **nunca** remove um holding real nem
uma entrada manual sua.

---

## 4. Rodando o Atlas — os três modos

Sempre com o ambiente ativado (`.venv\Scripts\activate`).

### 4.1 Completo (padrão)
Universo + funil de oportunidades + carteira + watchlist. É o mais lento (lê os
screeners amplos).

```cmd
python run_all.py
```

(equivalente a `python run_all.py --full`)

### 4.2 Só carteira + watchlist
Pula o funil de screener. Uso diário mais rápido, focado nas suas posições.

```cmd
python run_all.py --portfolio
```

### 4.3 Um único ticker
Analisa um símbolo e gera o one-pager, sem tocar carteira/watchlist.

```cmd
python run_all.py --ticker MSFT
```

> **Leitura vs. escrita:** `--full` e `--portfolio` **gravam** (curadoria
> automática da watchlist, snapshots de histórico, ledger). `--ticker` é a opção
> mais contida quando você só quer olhar um nome.

---

## 5. Lendo os resultados

### 5.1 Comece pelo Cockpit — "Atlas — Hoje"
`output/relatorios/decision_cockpit.html`. É a **página humana única**, organizada
em três níveis de prioridade:

1. **Agir agora** — vendas/ajustes a executar (EXECUTE) e o que precisa de
   investigação (INVESTIGATE).
2. **Oportunidades** — candidatas de compra fora da carteira e gatilhos de entrada
   aguardando. Um gatilho disparado vira **"revisar para compra"**, nunca compra
   automática.
3. **Acompanhar** — monitoramento, colapsado para não competir com decisões reais.

No topo: **"Mudou desde a última execução"** (o que escalou, entrou ou saiu desde
o run anterior) e um resumo do **cenário** (caixa/turnover/concentração se você
executasse as vendas SELL/TRIM sugeridas).

Cards com confiança ou cobertura de dados baixas (abaixo de 60) ganham um bloco
que explica **por que** o dado falta e **se recoletar resolve**:
- divergência/rejeição de fonte → recoletar **não** resolve (checar a fonte);
- gap de coleta ou dado velho → recoletar via skill `atualizar-ticker`.

### 5.2 As decisões que o Atlas dá

| Voz | O que significa | Escopo |
|---|---|---|
| **Decision** (`STRONG_BUY…AVOID`) | A **única** voz de compra. Pondera Opportunity + Conviction + risco + deal breakers | Qualquer ação analisada |
| **Score Band** (Elite/Alto/Bom/Médio/Baixo) | Rótulo **descritivo** do Investment Score — sem verbo de compra | Qualquer ação |
| **Ação de venda** (`SELL/TRIM/HOLD/REVISAR/ACOMPANHAR`) | Só para **holdings reais** da carteira | `config/portfolio.csv` |

O que cada estado de venda pede de você:
- **SELL / TRIM** — decisão de saída/redução sugerida (2+ famílias de evidência).
- **HOLD** — manter.
- **REVISAR** — gate de confiança bloqueado ou distress preliminar; **confirme o
  dado** antes de decidir.
- **ACOMPANHAR** — sinal informativo/comparativo só (não pede decisão); fica na
  seção "Sinais informativos", fora da fila de ação.

### 5.3 Detalhe por ativo (relatório HTML)
`atlas_report_latest.html` traz, para cada símbolo: decomposição do score, fórmula
e inputs brutos por métrica, status de cada regra de venda, sparkline por métrica
com histórico e a tese da posição (com idade e alerta se `fundamental_decay`
disparou). Os símbolos nas tabelas linkam para a âncora do ativo.

---

## 6. Registrando suas decisões (opcional, mas recomendado)

O cockpit pode registrar o que você decidiu, com os botões **Aceitar / Adiar /
Rejeitar** por card. Isso alimenta o *journal* (histórico consultivo, append-only)
e permite acompanhar cada decisão ao longo dos dias.

Os botões só funcionam quando o cockpit é servido pela API local (same-origin).
Suba o servidor:

```cmd
python -m api.server
```

Depois abra **http://127.0.0.1:8000/cockpit**. O servidor liga só em `127.0.0.1`
(loopback) — não exponha em rede. `GET` é read-only; a única escrita é
`POST /journal` (a própria revisão humana). Abrindo o HTML por `file://` os botões
ficam desativados, com aviso.

Depois de executar uma venda de verdade na sua corretora, você pode registrar o
*fill* real (quantidade, preço, taxas) no ledger de execução — o Atlas reconcilia
esse fill com os snapshots de custódia, mas **nunca** envia ordem nem altera sua
carteira. Detalhes em `docs/EXECUTION_LEDGER.md` e
`docs/EXECUTION_RECONCILIATION.md`.

---

## 7. Onde ficam os arquivos

| Caminho | Conteúdo |
|---|---|
| `output/relatorios/` | **Para você abrir** — HTML, Excel, Morning Brief |
| `output/dados/` | Contrato interno JSON (não abrir direto) |
| `logs/atlas.log` | Log de execução |
| `logs/execution_metrics.csv` | Métricas de cada run |
| `data/atlas_history.db` | Histórico (SQLite) — base dos sparklines e outcomes |

Esses artefatos são **locais** e não devem ir para o Git. Os *raw snapshots*
imutáveis nesta estação ficam em
`C:\Users\marcu\AppData\Local\Atlas_Investment_OS\raw_snapshots` — não são
sincronizados; faça backup próprio antes de trocar de disco ou reinstalar o
Windows.

---

## 8. Rotina sugerida

**Diária (rápida):**
```cmd
.venv\Scripts\activate
python run_all.py --portfolio
```
Abra o cockpit, resolva "Agir agora", registre decisões.

**Semanal/quinzenal (completa):**
```cmd
python run_all.py
```
Revê o funil de oportunidades e a curadoria da watchlist.

**Pontual:** `python run_all.py --ticker XYZ` quando quiser olhar um nome
específico.

Para atualizar as métricas de um ticker a partir de fontes públicas, use a skill
`atualizar-ticker` (última versão disponível).

---

## 9. Limites importantes (leia antes de confiar)

- **O Atlas não dá ordem e não é conselho de investimento personalizado.** Ele é
  uma ferramenta de organização de evidência; a decisão é sua.
- **REVISAR quando duas fontes discordam é o resultado correto**, não uma falha a
  contornar. Nomes que reportam em moeda estrangeira (ADRs) frequentemente têm
  market cap / enterprise value divergentes entre vendors — o Atlas rejeita o campo
  de propósito em vez de confiar cego numa fonte.
- **Backtest ainda não publica performance.** A cobertura histórica é incompleta;
  o Atlas não afirma retorno realizado de estratégia.
- **A referência de scoring está congelada no snapshot de 2026-07-13.** Percentis
  oficiais envelhecem; renovar exige rodar a coleta ampla conscientemente.

---

## 10. Solução de problemas

| Sintoma | Provável causa | O quê fazer |
|---|---|---|
| Warning de fonte secundária | Flag habilitada sem chave em `provider_secrets.json` | Preencher a chave ou desabilitar a flag |
| Muitas posições em REVISAR | Dados `stale` ou fontes divergentes (ADRs) | Ver bloco de explicação no card; recoletar só resolve se a causa for gap/dado velho |
| Botões do cockpit desativados | Aberto via `file://` | Suba `python -m api.server` e abra `/cockpit` |
| Cobertura de EV baixa em nomes amplos | Cota gratuita do FMP atingida | Limite de plano, não bug — reexecutar depois |
| Execução interrompida pelo Health Check | Pré-condição de dados não satisfeita | Ver `logs/atlas.log` para a causa |

---

## 11. Para aprofundar

- `STATUS.md` — o que o código faz **hoje**, com citação de arquivo/função
- `docs/SCORING_MODEL.md` — como os scores são calculados
- `docs/DECISION_QUEUE.md` / `docs/DECISION_JOURNAL.md` — fila e registro de decisão
- `docs/ACTIVE_WATCHLIST.md` — watchlist como fila ativa
- `docs/OUTCOME_ANALYTICS.md` — acompanhamento de resultado das decisões
- `docs/adr/` — decisões de arquitetura (o "porquê")
