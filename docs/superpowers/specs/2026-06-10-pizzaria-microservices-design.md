# Pizzaria Online — Sistema de E-commerce com Microsserviços (Design Spec)

Data: 2026-06-10
Origem dos requisitos: `REQUISITOS.md` (atividade acadêmica de Sistemas Distribuídos)

## 1. Contexto e objetivo

Implementar uma versão simplificada de um e-commerce (tema: **pizzaria**) composta por
três microsserviços (Usuários, Produtos/Pizzas, Pedidos) atrás de um API Gateway, com:

- replicação de dados (Produtos, 2 réplicas, consistência forte para escrita);
- detecção de falhas via heartbeat no Gateway;
- autenticação/autorização via JWT (roles `user`/`admin`);
- bônus: Docker Compose, TLS/HTTPS (certificado autoassinado), dashboard HTML de monitoramento.

Stack: **Python 3.11 + FastAPI + Uvicorn**. Armazenamento: **arquivos JSON**. Comunicação
entre serviços: **HTTP/REST sobre HTTPS**.

## 2. Arquitetura geral

```
Cliente (curl/Postman) ──HTTPS──▶ API Gateway (:8443)
                                      │  proxy + heartbeat + replicação + dashboard
                ┌─────────────────────┼─────────────────────────────┐
                │                     │                              │
          Users :5001        Products-1 :5002 / Products-2 :5012   Orders :5003
         (users.json)         (products.json — 1 por réplica)       (orders.json)
                                                ▲
                                                │ HTTP direto (sem passar pelo gateway)
                                          Orders consulta Products
                                          para validar pizza/preço
```

- **Gateway**: único ponto de entrada externo. Roteia `/users/*`, `/products/*`,
  `/orders/*`, encaminha o header `Authorization`. Mantém o estado de saúde de cada
  instância de backend (heartbeat) e coordena a replicação de Produtos. Serve
  `/dashboard` e `/dashboard/status`.
- **Users**: registro, login (emite JWT), consulta de usuário (JWT).
- **Products** (2 réplicas idênticas, `PORT`/`DATA_FILE` diferentes): listagem/detalhe
  (público) e criação (JWT + role `admin`).
- **Orders**: criação de pedido (JWT) — valida a pizza chamando Products diretamente
  (sem passar pelo gateway); listagem de pedidos por usuário (JWT).
- **Cross-cutting**: cada serviço valida o JWT **independentemente**, usando o mesmo
  `JWT_SECRET`. O Gateway apenas repassa o token, não é o único ponto de validação.

## 3. Decisões de design e justificativas

1. **Replicação coordenada pelo Gateway** (em vez de peer-to-peer entre réplicas):
   o Gateway já precisa rastrear a saúde das réplicas para o heartbeat, então
   reaproveita esse estado para roteamento de leitura/escrita. Cada instância de
   Products fica simples e idêntica (sem saber da outra).
2. **Orders fala diretamente com Products** (sem passar pelo Gateway): comunicação
   leste-oeste entre serviços é direta; o Gateway cuida apenas do tráfego
   norte-sul vindo do cliente externo.
3. **TLS nativo via Uvicorn + certificado autoassinado único** (em vez de proxy
   reverso/CA própria): menor complexidade de infraestrutura para o ganho de bônus.
4. **Consistência forte (CP) na replicação de Produtos**: escritas exigem as duas
   réplicas saudáveis; se uma estiver `DOWN`, a escrita é rejeitada (503) sem
   tocar em nenhuma réplica. Isso garante que, sempre que uma réplica está
   acessível, seu conteúdo é idêntico ao da outra — não é necessária reconciliação
   ao recuperar uma réplica. Trade-off: disponibilidade de escrita é sacrificada
   durante falhas parciais (discutido no relatório, perguntas 2 e 3).
5. **Admin via seed, não via registro**: `POST /users/register` sempre cria
   `role: "user"`. Um usuário admin (`admin@pizzaria.com` / `admin123`) é semeado
   no `users.json` na primeira execução. Isso permite testar `POST /products`
   (admin-only) de forma reprodutível e sustenta a resposta da pergunta 4 do
   relatório (um usuário comum estruturalmente não consegue obter `role: admin`).
6. **IDs**: UUID4 em todas as entidades. Para Produtos, o **Gateway gera o UUID**
   antes de propagar a escrita às duas réplicas, garantindo que ambas armazenem o
   mesmo registro sob a mesma chave.

## 4. Modelos de dados

### `users.json`
```json
[
  {
    "id": "uuid4",
    "name": "string",
    "email": "string",
    "passwordHash": "bcrypt hash",
    "role": "user | admin",
    "createdAt": "ISO-8601"
  }
]
```
Seed inicial: 1 admin (`admin@pizzaria.com` / `admin123`, `role: admin`).

### `products.json` (idêntico nas duas réplicas na inicialização)
```json
[
  {
    "id": "uuid4",
    "name": "string",
    "description": "string",
    "price": "number",
    "createdAt": "ISO-8601",
    "updatedAt": "ISO-8601"
  }
]
```
Seed inicial (tema pizzaria):

| name | description | price |
|---|---|---|
| Pizza Margherita | Molho de tomate, mussarela, manjericão fresco | 35.00 |
| Pizza Calabresa | Molho de tomate, mussarela, calabresa fatiada, cebola | 38.00 |
| Pizza Quatro Queijos | Mussarela, provolone, parmesão, gorgonzola | 42.00 |
| Pizza Portuguesa | Presunto, ovos, cebola, azeitona, ervilha | 40.00 |
| Pizza Frango com Catupiry | Frango desfiado, catupiry, milho | 39.00 |

### `orders.json`
```json
[
  {
    "id": "uuid4",
    "userId": "uuid4",
    "productId": "uuid4",
    "productName": "string (snapshot)",
    "unitPrice": "number (snapshot)",
    "quantity": "integer",
    "total": "number",
    "status": "created",
    "createdAt": "ISO-8601"
  }
]
```

### Inicialização dos dados

Cada serviço lê seu arquivo de dados a partir de `DATA_FILE` (env var). Se o
arquivo não existir na primeira execução, é criado a partir de um seed:
`users_seed.json` (1 admin), `products_seed.json` (5 pizzas, copiado
identicamente para o `DATA_FILE` de cada réplica). Orders não tem seed —
inicia com `[]`. Os arquivos de dados (`users.json`, `products_5002.json`,
`products_5012.json`, `orders.json`) **não** são versionados (gerados em
runtime); apenas os `*_seed.json` ficam no repositório.

## 5. Autenticação JWT

- Algoritmo HS256, segredo em `JWT_SECRET` (mesmo valor em todos os serviços).
- Payload: `{ "userId", "email", "role", "exp" }`.
- Expiração: `JWT_EXPIRES_MINUTES` (padrão 60).
- Bibliotecas: `python-jose` (JWT) + `passlib[bcrypt]` (hash de senha).
- Cada serviço implementa uma dependency FastAPI `get_current_user(required_role=None)`
  que decodifica o token, valida assinatura/expiração e, se `required_role` for
  passado, verifica `payload.role == required_role` (senão `403`).
- Endpoints protegidos:
  - `GET /users/:id` — qualquer usuário autenticado.
  - `POST /products` — somente `role: admin`.
  - `POST /orders`, `GET /orders/:userId` — qualquer usuário autenticado;
    `GET /orders/:userId` exige `userId == token.userId` ou `role: admin`.

## 6. Endpoints por serviço

### Users (`:5001`)
| Endpoint | Método | Auth | Descrição |
|---|---|---|---|
| `/health` | GET | - | `{"status":"ok"}` |
| `/users/register` | POST | - | `{name, email, password}` → cria usuário `role:user` |
| `/users/login` | POST | - | `{email, password}` → `{token}` |
| `/users/{id}` | GET | JWT | Retorna dados do usuário (sem passwordHash) |

### Products (`:5002` e `:5012`, mesmo código)
| Endpoint | Método | Auth | Descrição |
|---|---|---|---|
| `/health` | GET | - | `{"status":"ok"}` |
| `/products` | GET | - | Lista pizzas (desta réplica) |
| `/products/{id}` | GET | - | Detalhe da pizza |
| `/products` | POST | JWT admin | Cria pizza; aceita `id` opcional no payload (gerado pelo Gateway) |

### Orders (`:5003`)
| Endpoint | Método | Auth | Descrição |
|---|---|---|---|
| `/health` | GET | - | `{"status":"ok"}` |
| `/orders` | POST | JWT | `{productId, quantity}` → valida pizza via Products, cria pedido |
| `/orders/{userId}` | GET | JWT | Lista pedidos do usuário |

### Gateway (`:8443`)
| Endpoint | Descrição |
|---|---|
| `/users/*`, `/products/*`, `/orders/*` | Proxy com lógica de heartbeat/replicação |
| `/dashboard` | HTML de monitoramento |
| `/dashboard/status` | JSON com status UP/DOWN de cada instância |

## 7. Heartbeat e detecção de falhas (Gateway)

- Registro de instâncias: `users` (1), `products` (2 réplicas), `orders` (1) — 4 alvos.
- Task assíncrona em background, intervalo `HEARTBEAT_INTERVAL` (padrão 5s),
  `GET {url}/health` com timeout `HEARTBEAT_TIMEOUT` (padrão 2s).
- Estado por instância: `status (UP/DOWN)`, `consecutive_failures`, `last_check`.
- Falha → incrementa `consecutive_failures`; ao atingir
  `HEARTBEAT_FAILURE_THRESHOLD` (padrão 2) muda para `DOWN` e loga
  `[FAILURE] <service> (<url>) DOWN @ <timestamp>`.
- Sucesso após `DOWN` → volta a `UP`, zera contador, loga
  `[RECOVERY] <service> (<url>) back UP @ <timestamp>`.
- Logs via módulo `logging` (stdout + arquivo `gateway.log`).

## 8. Roteamento e replicação no Gateway

- **Users / Orders** (instância única): se `DOWN` → `503
  {"error": "Serviço <nome> indisponível no momento"}` sem encaminhar. Se `UP` →
  proxy transparente.
- **Products GET** (`/products`, `/products/{id}`): round-robin apenas entre
  réplicas `UP`. Se ambas `DOWN` → `503`.
- **Products POST** (`/products`): exige as duas réplicas `UP`. Se alguma `DOWN`
  → `503 {"error": "Replicação indisponível: uma réplica do serviço de produtos
  está fora do ar"}` sem escrever em nenhuma. Se ambas `UP`: Gateway gera UUID,
  envia o mesmo payload (com `id`) em paralelo às duas réplicas; só responde
  sucesso ao cliente se **ambas** confirmarem (caso contrário `502` + log de
  inconsistência).

## 9. TLS/HTTPS (bônus)

- Um único par certificado/chave autoassinado (`certs/cert.pem`, `certs/key.pem`),
  gerado por `certs/generate_certs.sh` via `openssl`, com SANs cobrindo
  `localhost`, `127.0.0.1` e os nomes de serviço do docker-compose (`gateway`,
  `users`, `products-1`, `products-2`, `orders`).
- Todos os serviços sobem com Uvicorn `--ssl-keyfile/--ssl-certfile`.
- Clientes HTTP internos (Gateway→serviços, Orders→Products) usam
  `verify=<caminho-do-cert>`. Se a verificação cross-hostname se mostrar inviável
  na implementação, o fallback documentado é `verify=False` apenas para chamadas
  internas — limitação a registrar na pergunta 5 do relatório.

## 10. Docker Compose (bônus)

- `docker-compose.yml` na raiz de `entrega/` com serviços: `gateway`, `users`,
  `products-1`, `products-2`, `orders`, todos na mesma rede (acesso por nome de
  serviço, ex. `https://users:5001`).
- Cada pasta tem seu `Dockerfile` (`python:3.11-slim`).
- `products-1`/`products-2` compartilham o mesmo build, diferindo via env
  (`PORT`, `DATA_FILE`) e mapeamento de portas do host (5002, 5012).
- `.env` (raiz) com `JWT_SECRET`, portas etc.; `.env.example` versionado.
- `certs/` montado como volume somente leitura em todos os containers.

## 11. Dashboard (bônus)

- Gateway serve `GET /dashboard` (HTML estático "Pizzaria Online — Painel de
  Monitoramento") com JS que faz polling de `GET /dashboard/status` a cada ~2s.
- `/dashboard/status` retorna o estado de heartbeat (UP/DOWN + último check) de
  `users`, `products-1`, `products-2`, `orders`.
- Cada serviço exibido como card/linha com indicador verde/vermelho.

## 12. Estrutura de entrega

```
entrega/
├── gateway/
│   ├── main.py
│   ├── proxy.py
│   ├── heartbeat.py
│   ├── replication.py
│   ├── auth.py
│   ├── static/dashboard.html
│   ├── requirements.txt
│   └── Dockerfile
├── users/
│   ├── main.py
│   ├── auth.py
│   ├── storage.py
│   ├── users_seed.json
│   ├── requirements.txt
│   └── Dockerfile
├── products/
│   ├── main.py
│   ├── auth.py
│   ├── storage.py
│   ├── products_seed.json
│   ├── requirements.txt
│   └── Dockerfile
├── orders/
│   ├── main.py
│   ├── auth.py
│   ├── storage.py
│   ├── requirements.txt
│   └── Dockerfile
├── certs/
│   └── generate_certs.sh
├── docker-compose.yml
├── .env.example
├── README_execucao.md
└── relatorio.md
```

## 13. README_execucao.md (conteúdo previsto)

- Pré-requisitos (Python 3.11+, Docker/Docker Compose opcional).
- Passo a passo via Docker Compose (`docker compose up --build`), URLs
  (`https://localhost:8443/dashboard` etc., uso de `curl -k` por causa do
  certificado autoassinado).
- Passo a passo manual (sem Docker): criar venv por serviço, variáveis de
  ambiente, comandos `uvicorn` com portas e certificados.
- Credenciais do admin semeado.
- Exemplos `curl` para cada endpoint (registro, login, criar pizza, criar
  pedido, listar pedidos).
- Como simular falha de um serviço e observar heartbeat/dashboard/503.

## 14. relatorio.md (conteúdo previsto, 1-2 páginas)

Responder objetivamente, com base na implementação real:
1. Comunicação via REST/HTTP entre Gateway↔serviços e Orders→Products
   diretamente; payloads JSON; JWT no header `Authorization: Bearer`.
2. Consistência forte (CP) nas escritas de Produtos — justificativa do item 4
   da seção 3 deste spec.
3. Comportamento se Orders cair: heartbeat detecta após 2 falhas, Gateway passa
   a responder `503` só para `/orders/*`; Users e Products continuam
   funcionando normalmente (demonstra independência dos microsserviços).
4. JWT garante autorização: `POST /products` exige `role: admin` no token;
   tokens de usuários comuns são emitidos com `role: user` (vindo de
   `users.json`, nunca alterável via registro), então a validação no próprio
   serviço de Produtos rejeita com `403`.
5. Limitações vs. produção: JSON como "banco" sem transações reais/locking
   concorrente robusto, certificado autoassinado/sem CA, sem reconciliação de
   réplicas após partição prolongada, sem fila de mensagens/retry assíncrono,
   sem rate limiting, segredo JWT compartilhado via `.env` em texto plano.

## 15. Fora de escopo (YAGNI)

- Banco relacional/SQLite (explicitamente dispensado pelo enunciado).
- Atualização (`PUT`) de produtos — não exigida pelo enunciado; não será
  implementada para manter o escopo fiel aos requisitos obrigatórios.
- Fila de mensagens, service discovery dinâmico, autenticação mTLS.
