# Instruções de Execução

Sistema de e-commerce de pizzaria composto por 4 serviços (Gateway, Usuários,
Produtos com 2 réplicas, Pedidos), com replicação coordenada, heartbeat,
autenticação JWT, TLS autoassinado e dashboard de monitoramento.

## Pré-requisitos

- **Via Docker (recomendado):** Docker + Docker Compose v2 (`docker compose version`).
- **Manual (sem Docker):** Python 3.11+ e `openssl` (apenas se quiser gerar o
  certificado TLS também no modo manual).

Credenciais do administrador semeado (usadas para criar pizzas):

```
email: admin@pizzaria.com
senha: admin123
```

---

## Opção 1: Docker Compose

1. Gere o certificado TLS autoassinado (uma vez):

   ```bash
   bash ./entrega/certs/generate_certs.sh
   ```

2. Crie o arquivo de variáveis de ambiente:

   ```bash
   cp entrega/.env.example entrega/.env
   ```

3. Suba toda a stack:

   ```bash
   cd entrega
   docker compose up --build -d
   ```

4. Verifique que os 5 containers estão rodando:

   ```bash
   docker compose ps
   ```

5. Acesse o dashboard de monitoramento:

   ```
   https://localhost:8443/dashboard
   ```

   (o navegador vai alertar sobre o certificado autoassinado, aceite o risco
   para visualizar).

6. Use os exemplos de `curl` da seção [Exemplos de uso](#exemplos-de-uso)
   abaixo, trocando a base URL para `https://localhost:8443` e adicionando a
   flag `-k` (ignora a verificação do certificado autoassinado a partir do host).

7. Para encerrar:

   ```bash
   docker compose down
   ```

---

## Opção 2: Execução manual (sem Docker)

Cada serviço roda em um terminal separado, sem TLS (HTTP simples). Todos os
terminais precisam da **mesma** `JWT_SECRET`.

### 1. Criar o virtualenv e instalar dependências (uma vez)

```bash
cd entrega
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pip install -r products/requirements.txt
.venv/bin/pip install -r orders/requirements.txt
```

### 2. Terminal 1: Serviço de Usuários (porta 5001)

```bash
cd entrega/users
JWT_SECRET=segredo-pizzaria JWT_EXPIRES_MINUTES=60 \
  ../.venv/bin/uvicorn main:app --host 0.0.0.0 --port 5001
```

### 3. Terminal 2: Serviço de Produtos, réplica 1 (porta 5002)

```bash
cd entrega/products
JWT_SECRET=segredo-pizzaria DATA_FILE=products_5002.json SEED_FILE=products_seed.json \
  ../.venv/bin/uvicorn main:app --host 0.0.0.0 --port 5002
```

### 4. Terminal 3: Serviço de Produtos, réplica 2 (porta 5012)

```bash
cd entrega/products
JWT_SECRET=segredo-pizzaria DATA_FILE=products_5012.json SEED_FILE=products_seed.json \
  ../.venv/bin/uvicorn main:app --host 0.0.0.0 --port 5012
```

### 5. Terminal 4: Serviço de Pedidos (porta 5003)

```bash
cd entrega/orders
JWT_SECRET=segredo-pizzaria DATA_FILE=orders.json PRODUCTS_URL=http://localhost:5002 \
  ../.venv/bin/uvicorn main:app --host 0.0.0.0 --port 5003
```

### 6. Terminal 5: API Gateway (porta 8000)

```bash
cd entrega/gateway
USERS_URL=http://localhost:5001 \
ORDERS_URL=http://localhost:5003 \
PRODUCTS_URLS=http://localhost:5002,http://localhost:5012 \
HEARTBEAT_INTERVAL=5 HEARTBEAT_TIMEOUT=2 HEARTBEAT_FAILURE_THRESHOLD=2 \
  ../.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
```

Acesse o dashboard em `http://localhost:8000/dashboard`. Use os exemplos de
`curl` abaixo com a base URL `http://localhost:8000` (sem `-k`).

---

## Exemplos de uso

Os exemplos abaixo usam `http://localhost:8000` (modo manual). No modo Docker,
troque para `https://localhost:8443 -k`.

### 1. Registrar um novo usuário

```bash
curl -X POST http://localhost:8000/users/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Cliente Teste","email":"cliente@example.com","password":"senha123"}'
```

### 2. Login (cliente)

```bash
curl -X POST http://localhost:8000/users/login \
  -H "Content-Type: application/json" \
  -d '{"email":"cliente@example.com","password":"senha123"}'
```

Resposta: `{"token": "<JWT>"}`. Exporte para uso nos próximos comandos:

```bash
TOKEN="<cole o token aqui>"
```

### 3. Consultar dados do usuário (requer JWT)

```bash
curl http://localhost:8000/users/<userId> \
  -H "Authorization: Bearer $TOKEN"
```

### 4. Listar pizzas

```bash
curl http://localhost:8000/products
```

### 5. Detalhar uma pizza

```bash
curl http://localhost:8000/products/<productId>
```

### 6. Criar uma nova pizza (requer JWT de admin)

Faça login com o admin semeado:

```bash
curl -X POST http://localhost:8000/users/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@pizzaria.com","password":"admin123"}'
```

```bash
ADMIN_TOKEN="<cole o token do admin aqui>"

curl -X POST http://localhost:8000/products \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Pizza Vegetariana","description":"Tomate, pimentao, cebola, azeitona","price":37.50}'
```

Tentar o mesmo comando com `$TOKEN` (usuário comum) deve retornar `403`.

### 7. Criar um pedido (requer JWT)

```bash
curl -X POST http://localhost:8000/orders \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"productId":"<productId>","quantity":2}'
```

### 8. Listar pedidos de um usuário (requer JWT)

```bash
curl http://localhost:8000/orders/<userId> \
  -H "Authorization: Bearer $TOKEN"
```

---

## Simulando falha de um serviço (heartbeat)

### Modo Docker

1. Derrube o serviço de pedidos:

   ```bash
   docker compose stop orders
   ```

2. Aguarde ~10s (2 ciclos de heartbeat) e verifique o log do gateway:

   ```bash
   docker compose logs gateway | grep FAILURE
   ```

3. Tente criar um pedido, o gateway responde `503`:

   ```bash
   curl -k https://localhost:8443/orders \
     -X POST -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"productId":"<productId>","quantity":1}'
   ```

4. Verifique que `/users` e `/products` continuam funcionando normalmente
   (`curl -k https://localhost:8443/products`).

5. Verifique o dashboard (`https://localhost:8443/dashboard`) — o card
   `orders` aparece em vermelho (`DOWN`).

6. Suba o serviço novamente:

   ```bash
   docker compose start orders
   ```

7. Aguarde ~10s e verifique a recuperação:

   ```bash
   docker compose logs gateway | grep RECOVERY
   ```

   O dashboard volta a mostrar `orders` em verde (`UP`).

### Modo manual

Pressione `Ctrl+C` no Terminal 4 (Pedidos) para derrubá-lo, observe os logs
`[FAILURE]` no terminal do Gateway após ~10s, repita os passos 3–5 acima com
`http://localhost:8000`, depois reinicie o Terminal 4 com o mesmo comando da
seção "Execução manual" e observe o log `[RECOVERY]`.
