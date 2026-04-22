# Lab MCP-like Ops com Prometheus, Alertmanager, Ansible e MCP Gateway

Este projeto nasceu para provar uma ideia de forma concreta: **um agente de decisão operacional** que observa contexto real, toma uma decisão baseada em regra e aciona automação de forma controlada.

Em vez de ficar no discurso genérico de “IA para operações”, o lab mostra um fluxo reproduzível:

- uma fila acumula backlog
- um worker consome jobs e gera carga real
- o Prometheus observa fila e CPU
- o Alertmanager dispara um webhook
- o decision-agent consulta contexto adicional
- o agent executa remediação com `ansible-runner`
- o worker é recarregado com novo paralelismo
- o mesmo agente também pode ser exposto via MCP para consumo por Inspector ou outros clientes

A arquitetura: workload local, observabilidade com Prometheus/Grafana, decision-agent com `ansible-runner` e um MCP gateway opcional por cima do fluxo operacional. 

---

## Objetivo

A proposta aqui não é “simular um monte de coisa”.  
É mostrar, de ponta a ponta, um padrão operacional que faz sentido no mundo real:

- **telemetria**
- **regra**
- **alerta**
- **decisão**
- **ação**
- **interface padronizada**

O resultado é um laboratório local que ajuda a responder perguntas como:

- Como transformar observabilidade em ação?
- Como acoplar automação a contexto operacional sem cair em improviso?
- Como expor esse mesmo motor de decisão por MCP sem duplicar lógica?
- Onde um LLM entra de forma útil sem virar o centro da remediação?

---

## Arquitetura

Hoje o fluxo principal do projeto é este:

```text
queue -> worker -> Prometheus -> Alertmanager -> decision-agent -> ansible-runner -> worker reload
                                           \
                                            -> Grafana
```

E por cima disso existe uma segunda camada:

```text
Inspector / MCP client -> MCP gateway -> decision-agent
                                       \-> llm-assistant -> Ollama local
```

## Componentes

### `queue`

API simples que recebe jobs e mantém uma fila em memória.
Expõe:

* `/enqueue`
* `/dequeue`
* `/health`
* `/metrics`

Métrica principal:

* `lab_queue_length`

### `worker`

Consome jobs da fila, gera carga CPU-bound e expõe estado operacional.
Expõe:

* `/health`
* `/reload`
* `/metrics`

Também lê o arquivo compartilhado `shared/parallelism.txt`, que define o paralelismo atual.

### `prometheus`

Coleta métricas de:

* `queue`
* `worker`
* `agent`

Além disso:

* carrega regras de alerta
* envia alertas para o Alertmanager

### `alertmanager`

Recebe os alertas do Prometheus e roteia notificações via webhook para o decision-agent. O lab prevê esse uso explícito de webhook para o agente. 

### `agent`

É o coração do projeto.

Responsabilidades:

* receber webhook do Alertmanager
* consultar contexto adicional no Prometheus
* aplicar cooldown e idempotência
* executar remediação com `ansible-runner`
* expor endpoints administrativos e de contexto
* servir métricas próprias

Endpoints:

* `/health`
* `/metrics`
* `/context`
* `/run`
* `/alertmanager`

### `mcp_gateway`

Expõe o mesmo motor por MCP, sem reimplementar a lógica operacional.

Tools disponíveis:

* `get_context`
* `get_status`
* `remediate`
* `explain_current_state`

### `llm_assistant`

Camada cognitiva local do projeto.

Responsabilidades:
- coletar contexto do `agent`
- consultar alertas ativos no Prometheus
- chamar um modelo local via Ollama
- gerar explicação e recomendação sem tocar no fluxo automático de remediação

Endpoints:
- `/health`
- `/explain`
- `/recommend`

### `ollama`

Runtime local para o modelo open source usado pelo `llm_assistant`.

Neste projeto, ele entra apenas para:
- explicação
- contextualização
- recomendação

Ele não participa da remediação automática.

### `grafana`

Camada visual do lab:

* datasource provisionado
* dashboard provisionado
* útil para demonstrar backlog, CPU e efeito da remediação

---

## Estrutura do projeto

```text
## Estrutura do projeto

```text
mcp-ansible-lab/
├── agent/
│   ├── Dockerfile
│   ├── app.py
│   ├── requirements.txt
│   ├── rules.yml
│   └── runner/
│       ├── inventory/
│       │   └── hosts
│       └── project/
│           ├── scale_parallelism.yml
│           └── vars.yml
├── alertmanager/
│   └── alertmanager.yml
├── grafana/
│   ├── dashboards/
│   └── provisioning/
├── llm_assistant/
│   ├── Dockerfile
│   ├── app.py
│   └── requirements.txt
├── mcp_gateway/
│   ├── Dockerfile
│   ├── app.py
│   └── requirements.txt
├── prometheus/
│   ├── alerts.yml
│   └── prometheus.yml
├── queue/
│   ├── Dockerfile
│   ├── app.py
│   └── requirements.txt
├── scripts/
│   ├── check_prom_queries.sh
│   ├── enqueue_burst.sh
│   └── post_fake_alert.sh
├── shared/
│   └── parallelism.txt
├── worker/
│   ├── Dockerfile
│   ├── app.py
│   └── requirements.txt
└── docker-compose.yml
```

## Requisitos

### Ambiente

* Linux ou WSL2
* Docker + Docker Compose
* `curl`
* `jq`
* Node.js moderno para usar o MCP Inspector

### Para usar o Inspector

Foi necessário atualizar o Node para uma versão recente. No ambiente deste lab, Node 12 quebrou o Inspector e Node 22 resolveu.

---

## Como subir o projeto

Na raiz do repositório:

```bash
docker compose up -d --build
```

Para derrubar:

```bash
docker compose down --remove-orphans
```

---

## Endpoints úteis

### Operacionais

* Prometheus: `http://127.0.0.1:9090`
* Alertmanager: `http://127.0.0.1:9093`
* Grafana: `http://127.0.0.1:3000`
* Queue: `http://127.0.0.1:8000/health`
* Worker: `http://127.0.0.1:9000/health`
* Agent: `http://127.0.0.1:8081/health`
* LLM Assistant: `http://127.0.0.1:8100/health`
* Ollama API: `http://127.0.0.1:11434/api/tags`

### MCP

* MCP Gateway: `http://127.0.0.1:8001/mcp`

---

## Primeira validação

### Health checks

```bash
curl -s http://127.0.0.1:8000/health | jq
curl -s http://127.0.0.1:9000/health | jq
curl -s http://127.0.0.1:8081/health | jq
```

### Targets do Prometheus

```bash
curl -s http://127.0.0.1:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health, lastError: .lastError}'
```

O esperado é:

* `queue` = `up`
* `worker` = `up`
* `agent` = `up`

---

## Como demonstrar o fluxo completo

### 1. Gerar carga

```bash
./scripts/enqueue_burst.sh 1000 500
```

Esse comando aumenta backlog e força o worker a gerar CPU real.

### 2. Conferir contexto no Prometheus

```bash
./scripts/check_prom_queries.sh
```

Você deve ver algo como:

* `max(lab_queue_length)` alto
* `rate(process_cpu_seconds_total{job="worker"}[1m])` acima do threshold

### 3. Conferir alerta

```bash
curl -s http://127.0.0.1:9090/api/v1/alerts | jq
```

O alerta esperado é:

* `LabBacklogAndCpuHigh`

### 4. Ver logs do agent

```bash
docker compose logs --tail=100 agent
```

O comportamento esperado do agent é:

* logar `decision_context`
* executar o playbook
* logar `decision_triggered`
* depois passar a responder `decision_no_match` quando o paralelismo já estiver no alvo

### 5. Verificar efeito da remediação

```bash
cat shared/parallelism.txt
curl -s http://127.0.0.1:9000/health | jq
```

O esperado:

* `parallelism.txt` muda de `1` para `4`
* o worker passa a responder `"parallelism": 4`

Esse é exatamente o efeito desejado no playbook `scale_parallelism.yml`. 

---

## Regras do decision-agent

O arquivo `agent/rules.yml` contém a regra principal do lab.

Hoje, a lógica é:

* backlog acima de 50
* CPU do worker acima de 0.70
* só agir se o paralelismo atual ainda estiver abaixo do alvo

Além disso, o agent aplica:

* cooldown
* idempotência
* logs estruturados

O do lab previa explicitamente esses mecanismos para evitar uma demo frágil e comportamento repetitivo. 

---

## Remediação manual

O agent também expõe um endpoint `/run`, que serve como interface administrativa e backend do MCP gateway.

### Exemplo com `curl`

Dry-run:

```bash
curl -s -X POST http://127.0.0.1:8081/run \
  -H "Content-Type: application/json" \
  -d '{
    "desired_parallelism": 4,
    "dry_run": true,
    "token": "lab-secret-token",
    "reason": "manual_test"
  }' | jq
```

Execução real:

```bash
curl -s -X POST http://127.0.0.1:8081/run \
  -H "Content-Type: application/json" \
  -d '{
    "desired_parallelism": 4,
    "dry_run": false,
    "token": "lab-secret-token",
    "reason": "manual_test"
  }' | jq
```

---

## MCP Gateway

O gateway existe para expor esse mesmo motor de decisão via MCP, sem duplicar a lógica.

### Tools disponíveis

* `get_status`
* `get_context`
* `explain_current_state`
* `explain_with_llm`
* `recommend_next_action`
* `remediate`

### Ideia central

O gateway não substitui o agent.
Ele usa o agent como backend.

Isso mantém:

* decisão operacional no lugar certo
* MCP como interface
* uma separação clara entre execução e acesso

A ideia inicial sempre foi: gateway por cima do lab, e não lógica duplicada. 

---

## Usando o MCP Inspector

### 1. Subir o Inspector

```bash
npx -y @modelcontextprotocol/inspector
```

### 2. Abrir a URL com token

O Inspector imprime uma URL com `MCP_PROXY_AUTH_TOKEN`. Abra exatamente aquela URL no navegador.

### 3. Configuração da conexão

* **Transport Type**: `Streamable HTTP`
* **Connection Type**: `Proxy`
* **URL**: `http://127.0.0.1:8001/mcp`

### 4. Validar as tools

As tools que devem aparecer:

* `get_status`
* `get_context`
* `remediate`
* `explain_current_state`

### 5. Testes recomendados

#### `get_status`

Confirma health do agent.

#### `get_context`

Retorna fila, CPU e paralelismo atual.

#### `explain_current_state`

Retorna uma explicação determinística do estado do sistema.

#### `remediate`

Primeiro rode com `dry_run=true`, depois com `dry_run=false`.

---

## Exemplo real das tools MCP

Durante os testes finais do projeto, as tools responderam com o comportamento esperado:

### `get_context`

Retornou:

* `queue_length`
* `worker_cpu`
* `current_parallelism`

### `get_status`

Retornou o health do agent.

### `explain_current_state`

Retornou uma explicação coerente do estado atual, por exemplo:

* fila abaixo/acima do threshold
* CPU abaixo/acima do threshold
* paralelismo já no alvo ou ainda escalável

### `remediate`

* com `dry_run=true`, retornou só a intenção da ação
* com `dry_run=false`, respeitou a idempotência e respondeu `already_at_or_above_target` quando o sistema já estava em `4`


### `explain_with_llm`

Retornou uma explicação mais natural do estado atual, usando o mesmo contexto operacional do projeto, mas com uma camada cognitiva local rodando em cima do Ollama.

### `recommend_next_action`

Retornou uma recomendação conservadora e coerente com o estado observado.  
Quando o sistema estava sem backlog e sem alertas ativos, a recomendação foi essencialmente “no action recommended”, o que é exatamente o comportamento esperado para esse papel.

Esse comportamento confirma que a camada MCP não é “fake”: ela conversa com o mesmo backend operacional do projeto.

---

## Grafana

O Grafana serve como camada visual do case.

Login padrão:

* usuário: `admin`
* senha: `admin`

O dashboard provisionado é mínimo, mas suficiente para mostrar:

* queue length
* worker CPU

A ideia foi exatamente esse tipo de dashboard simples para sustentar prints do artigo, sem transformar o lab em ornamentação hehe. 

---

## O que esse projeto já demonstra

Esse repositório já demonstra, de forma prática:

* observabilidade acionando automação
* decisão baseada em contexto, não só em um alerta cru
* remediação com `ansible-runner`
* aumento controlado de paralelismo
* idempotência
* cooldown
* interface MCP em cima do motor operacional
* LLM local open source para explicação e recomendação
* separação clara entre motor operacional determinístico e camada cognitiva auxiliar

Em outras palavras: não é só “alerta com script”.
É um mini padrão de operações automatizadas, desenhado para ser explicado, testado e expandido.

---

## O que ainda pode evoluir

### Curto prazo

* melhorar dashboards do Grafana
* adicionar screenshots e evidências no repositório
* gerar uma demo gravada curta
* incluir scripts PowerShell para uso mais confortável no Windows

### Médio prazo

* adicionar endpoint administrativo mais granular
* expor histórico de decisões
* melhorar logs estruturados
* criar uma camada de policy separada

### Opcional / próximos passos

* melhorar os prompts e o grounding da LLM local
* adicionar `summarize_incident`
* adicionar `generate_postmortem_summary`
* expor histórico de decisões para enriquecer explicações futuras

O uso de LLM aqui continua intencionalmente fora do caminho crítico da remediação.  
Ela explica e recomenda; quem decide e executa continua sendo o motor determinístico do agent.
Exemplos de próximos passos sensatos:

* `explain_current_state_llm`
* `summarize_incident`
* `suggest_next_action`

O uso de LLM aqui faz mais sentido como copiloto ou explicador, não como substituto da lógica determinística do agent.

---

## Filosofia do projeto

A ideia nunca foi fazer um “brinquedo de IA para operações”.

A ideia foi construir algo que mostrasse, sem maquiagem:

* onde a automação realmente agrega valor
* onde a observabilidade deixa de ser passiva
* como um padrão moderno como MCP pode conversar com esse mundo sem virar teatro

Se você chegou até aqui, o projeto já entregou o mais importante: **contexto real, decisão real, ação real**.

---

## Roteiro curto de demo

Se quiser demonstrar o projeto em poucos minutos, este é o caminho:

### 1. Subir tudo

```bash
docker compose up -d --build
```

### 2. Confirmar health

```bash
curl -s http://127.0.0.1:8000/health | jq
curl -s http://127.0.0.1:9000/health | jq
curl -s http://127.0.0.1:8081/health | jq
```

### 3. Gerar backlog

```bash
./scripts/enqueue_burst.sh 1000 500
```

### 4. Confirmar alerta

```bash
./scripts/check_prom_queries.sh
curl -s http://127.0.0.1:9090/api/v1/alerts | jq
```

### 5. Mostrar decisão

```bash
docker compose logs --tail=100 agent
```

### 6. Mostrar efeito

```bash
cat shared/parallelism.txt
curl -s http://127.0.0.1:9000/health | jq
```

### 7. Abrir Inspector

```bash
npx -y @modelcontextprotocol/inspector
```

### 8. Testar tools MCP

* `get_status`
* `get_context`
* `explain_current_state`
* `remediate`

---

## Licença / observações finais

Este projeto é um lab técnico e educacional.
Ele foi desenhado para rodar localmente e demonstrar padrões de integração entre observabilidade, automação e interface MCP.

Para uso real em ambiente corporativo, ainda faria sentido acrescentar:

* autenticação mais forte
* auditoria formal
* proteção de secrets
* persistência
* política declarativa separada
* integração com plataforma de automação maior

Mas para o objetivo deste projeto, o ponto central já está demonstrado.

