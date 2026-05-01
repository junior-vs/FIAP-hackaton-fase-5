# Worker RabbitMQ — Runbook Operacional

Referencia rapida para operar o consumer RabbitMQ do `ai_module`.

---

## 1. Iniciar o worker

### Localmente (sem Docker)

```bash
cd ai_module
cp .env.example .env   # edite as variaveis necessarias
# Defina RABBITMQ_WORKER_ENABLED=true no .env
uv run uvicorn ai_module.main:app --host 0.0.0.0 --port 8000
```

O worker e iniciado automaticamente junto com o FastAPI quando `RABBITMQ_WORKER_ENABLED=true`.

### Com Docker Compose

```bash
docker compose -f infra/compose.yaml up --build
```

O `compose.yaml` sobe o broker RabbitMQ e o servico em conjunto.

### Variaveis de ambiente obrigatorias

| Variavel                  | Exemplo                              | Descricao                         |
|---------------------------|--------------------------------------|-----------------------------------|
| `RABBITMQ_WORKER_ENABLED` | `true`                               | Habilita o consumer               |
| `RABBITMQ_URL`            | `amqp://guest:guest@localhost:5672/` | URL de conexao ao broker          |
| `RABBITMQ_INPUT_QUEUE`    | `analysis.requests`                  | Fila onde chegam as requisicoes   |
| `RABBITMQ_OUTPUT_QUEUE`   | `analysis.results`                   | Fila onde sao publicados resultados |

---

## 2. Verificar saude do worker

### Endpoint de saude

```bash
curl http://localhost:8000/health
```

Resposta esperada (saudavel):

```json
{"status": "ok"}
```

Resposta em modo degradado:

```json
{"status": "degraded", "details": "..."}
```

### Metricas de consumo

```bash
curl http://localhost:8000/metrics
```

Contadores relevantes para o worker:

- `ai_module_messages_consumed_total` — mensagens processadas com sucesso
- `ai_module_validation_errors_total` — mensagens descartadas por erro de schema
- `ai_module_pipeline_errors_total` — erros durante o pipeline de IA

### Painel do RabbitMQ Management

Acesse `http://localhost:15672` (usuario/senha: `guest/guest` por padrao).

- **Queues → analysis.requests**: mensagens enfileiradas / taxa de consumo
- **Queues → analysis.results**: resultados publicados
- **Queues → analysis.requests.dlq** (se configurada): mensagens descartadas

---

## 3. Monitorar a fila

### Verificar tamanho da fila via CLI

```bash
docker exec rabbit rabbitmqctl list_queues name messages consumers
```

Saida esperada em operacao normal:

```
name                   messages  consumers
analysis.requests      0         1
analysis.results       0         0
```

### Alertas recomendados

| Condicao                              | Acao                                     |
|---------------------------------------|------------------------------------------|
| `analysis.requests` com > 100 msgs    | Investigar lentidao no pipeline ou escalar workers |
| `consumers` = 0 em `analysis.requests` | Worker nao esta conectado — reiniciar servico |
| `pipeline_errors_total` crescendo     | Verificar logs e saude do provedor LLM   |

---

## 4. Tratar mensagens na DLQ

Se configurada, mensagens invalidas (JSON malformado, schema errado) sao movidas para `analysis.requests.dlq`.

### Inspecionar mensagens da DLQ

Via painel web: Queues → analysis.requests.dlq → Get messages.

Via CLI:

```bash
docker exec rabbit rabbitmqadmin get queue=analysis.requests.dlq ackmode=ack_requeue_false count=5
```

### Corrigir e reenviar

1. Copie o corpo da mensagem da DLQ.
2. Corrija o payload (verifique o schema `QueueAnalysisRequest`).
3. Republique na fila original:

```bash
docker exec rabbit rabbitmqadmin publish \
  exchange='' \
  routing_key=analysis.requests \
  payload='{"analysis_id":"...","file_bytes_b64":"...","file_name":"..."}'
```

### Schema esperado da requisicao

```json
{
  "analysis_id": "<string nao vazia>",
  "file_bytes_b64": "<base64 do arquivo>",
  "file_name": "<nome do arquivo, ex: diagram.png>",
  "context_text": "<opcional>"
}
```

---

## 5. Escalar workers

O servico e stateless: multiplas instancias podem consumir a mesma fila em paralelo.

### Com Docker Compose

```bash
docker compose -f infra/compose.yaml up --scale ai-module=3
```

### Consideracoes

- Cada instancia mantem um canal de consumo independente no RabbitMQ.
- O RabbitMQ distribui mensagens em round-robin entre os consumidores.
- Nao ha risco de processamento duplicado — cada mensagem e entregue a um unico consumidor.

---

## 6. Problemas comuns

### Worker nao inicia

**Sintoma**: servico sobe, mas nenhuma mensagem e consumida.

**Verificar**:

```bash
grep RABBITMQ_WORKER_ENABLED ai_module/.env
```

Deve retornar `RABBITMQ_WORKER_ENABLED=true`. Se estiver `false`, altere e reinicie.

---

### Conexao recusada ao broker

**Sintoma**: log com `ConnectionRefusedError` ou `AMQPConnectionError`.

**Verificar se o broker esta rodando**:

```bash
docker ps | grep rabbit
```

**Reiniciar o broker**:

```bash
docker compose -f infra/compose.yaml restart rabbit
```

---

### Mensagens publicadas como erro com `TIMEOUT`

**Sintoma**: fila `analysis.results` recebe mensagens com `error_code: TIMEOUT`.

**Causa**: o LLM nao respondeu dentro do timeout configurado.

**Solucao**: aumente `LLM_TIMEOUT_SECONDS` no `.env` e reinicie o servico.

---

### Mensagens publicadas como erro com `AI_FAILURE`

**Sintoma**: `error_code: AI_FAILURE` na fila de resultados.

**Causa**: falha na chamada ao provedor LLM (quota excedida, API key invalida, etc.).

**Verificar**:

```bash
curl http://localhost:8000/health
```

Se degradado, verifique a API key no `.env` (`GEMINI_API_KEY` ou `OPENAI_API_KEY`).

---

### Worker trava / para de consumir

**Sintoma**: consumidor presente no broker, mas mensagens acumulando na fila.

**Diagnostico**:

```bash
docker logs <container_id> --tail=50
```

**Reiniciar**:

```bash
docker compose -f infra/compose.yaml restart ai-module
```

---

## 7. Logs estruturados

O worker emite logs estruturados em JSON. Eventos relevantes:

| `event`                  | Nivel   | Descricao                                        |
|--------------------------|---------|--------------------------------------------------|
| `consumer_started`       | INFO    | Consumer registrado e aguardando mensagens        |
| `consumer_stopped`       | INFO    | Consumer encerrado graciosamente                 |
| `message_received`       | INFO    | Mensagem valida recebida, pipeline sera executado |
| `message_malformed_json` | WARNING | JSON invalido — mensagem descartada (NACK)       |
| `message_schema_invalid` | WARNING | Schema invalido — mensagem descartada (NACK)     |
| `message_decode_error`   | WARNING | Erro ao decodificar base64                       |
| `pipeline_start`         | INFO    | Pipeline de IA iniciando                         |
| `pipeline_error`         | ERROR   | Erro durante o pipeline                          |
| `message_processed`      | INFO    | Mensagem processada e resultado publicado        |

Exemplo de filtro de logs com `jq`:

```bash
docker logs <container_id> 2>&1 | jq 'select(.event == "pipeline_error")'
```
