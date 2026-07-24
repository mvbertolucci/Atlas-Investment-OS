# ADR-053 — Disparar o pipeline pelo visor local, com allowlist e trava

- **Status**: Aceito
- **Data**: 2026-07-24
- **Relacionado**: `api/runner.py` (novo), `api/server.py`, `api/home.py`,
  ADR-041 (endurecimento do `POST /journal` — mesma superfície, escrita menor),
  ADR-022 (serviço de runtime operacional), Fase 1 de usabilidade (porta única)

## Contexto

A Fase 1 fechou a porta de entrada — `atlas.py` e a home em `api/home.py` —,
mas a costura seguia aberta no ponto que mais importa no uso diário: **atualizar
os dados**. O visor era estritamente read-only, e a home apenas *imprimia o
comando* para o usuário copiar e colar num terminal.

Na prática isso significa que o fluxo "abrir o visor, ver que o dado está
velho, atualizar" exige sair do visor, achar um terminal, colar um comando e
voltar. A alternativa que já existia — o menu do `Atlas.bat` — é o mesmo motor
por outro caminho.

## Decisão

`POST /run` dispara o pipeline a partir do visor, expondo **os mesmos dois
modos que o menu já oferece** (`--portfolio` e `--full`), sem criar um terceiro
contrato de execução. `GET /run/status` acompanha.

A lógica vive em `api/runner.py`, que **não sabe o que é HTTP**: devolve
`(status, payload)` e o servidor adapta. Isso o torna testável sem subir porta,
e mantém a decisão de segurança no servidor, onde ela pertence.

### Três invariantes, em ordem de importância

**1. Uma execução por vez.** Duas runs simultâneas escreveriam ao mesmo tempo
em `data/atlas_history.db` e `output/dados/dashboard.json`. A trava
(`threading.Lock` + estado explícito) é o requisito central, não um
refinamento: sem ela um duplo-clique no botão corrompe o histórico. Segunda
chamada durante uma run recebe **409**, nunca é enfileirada — enfileirar
esconderia do usuário que o clique não fez o que ele pensava.

**2. Modo vem de allowlist.** O cliente envia uma chave (`portfolio` |
`full`); os argumentos são montados no servidor. **Nada vindo do HTTP chega a
`run_all` como argumento.** Isso não é validação de entrada, é ausência de
caminho: não existe forma de o corpo da requisição influenciar o argv.

**3. Local por construção, com defesa em camada.** O servidor liga só em
`127.0.0.1`, então a rota já é inalcançável de fora por desenho. A checagem
explícita de origem (`_is_local`) existe para o caso em que esse desenho falha
— um bind acidental em `0.0.0.0` não pode virar execução remota de processo.
É a única proteção do conjunto cuja falha é irreversível.

`serve(allow_run=False)` remove as rotas: é assim que o visor hospedado da
Fase 2 deve subir, já que lá não há motor do outro lado. Desligada, a rota
responde **404, não 403** — dizer "proibido" revelaria um recurso que aquele
modo não tem.

### Herdado do ADR-041

`POST /run` passa pela mesma checagem de `Content-Type: application/json` já
aplicada ao `/journal` (verificado: a checagem está em `do_POST` antes do
roteamento). Um formulário cross-site não consegue definir esse cabeçalho sem
preflight CORS, que não respondemos.

## Alternativas consideradas

- **Manter o comando impresso para copiar.** Zero superfície nova, mas deixa a
  costura aberta justamente na ação mais frequente.
- **Aceitar argv livre no corpo.** Flexível e indefensável: transforma um
  endpoint local em execução arbitrária de processo.
- **Fila de execuções em vez de 409.** Esconderia do usuário que o segundo
  clique não iniciou nada, e a trava existe justamente para tornar isso visível.
- **Subprocesso em vez de thread.** Isolaria melhor, mas duplicaria a
  inicialização do motor e afastaria o comportamento do que `atlas.py` já faz
  no mesmo processo.

## Consequências

- O ciclo "ver dado velho → atualizar → reler" fecha dentro do visor.
- `SystemExit` do Health Check é traduzido como **falha com causa nos logs**,
  não como encerramento do servidor — sem isso, um aborto do Health Check
  derrubaria o visor junto.
- A trava é liberada em `finally`, inclusive em `BaseException`: uma exceção
  inesperada não pode deixar o runner travado em `running` para sempre.
- **Risco assumido**: qualquer processo local pode disparar uma run. Para uma
  ferramenta pessoal de loopback isso é aceitável e é o mesmo nível do
  `/journal`; num contexto multiusuário não seria.

## Verificação

- `tests/test_run_from_viewer.py` — 13 testes: allowlist recusa modo
  desconhecido; o cliente escolhe chave e nunca o argv; segundo start durante
  execução recebe 409 e não enfileira; falha reporta causa e **libera a
  trava**; `SystemExit` lê como falha, não como shutdown; integração HTTP real
  (202, 409, 415); a rota some com `allow_run=False`; a home só mostra botões
  quando a execução é permitida.
- Defesa em camada coberta em separado: cliente fora da máquina recebe 403; as
  três formas de loopback (IPv4, IPv6, IPv4-mapeado) são aceitas; a rota
  desligada responde 404 mesmo para localhost.
- Suíte completa verde.
