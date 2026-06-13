# Relatório
## 1. Como a comunicação entre os microsserviços foi implementada?

Toda a comunicação é **REST/HTTP com payloads JSON**, usando `httpx` como
cliente HTTP assíncrono.

- **Cliente → Gateway:** o cliente externo (curl/Postman) fala apenas com o
  API Gateway (`:8443` com TLS via Docker Compose, `:8000` sem TLS no modo
  manual). O Gateway expõe `/users/*`, `/products*`, `/orders*`,
  `/dashboard` e `/dashboard/status`.
- **Gateway → serviços:** o Gateway repassa requisições de `/users/*` e
  `/orders/*` por proxy transparente (`entrega/gateway/main.py`,
  `_proxy_single`), encaminhando o header `Authorization` e o corpo/query
  string originais. Para `/products*`, o Gateway usa `ProductsRouter`
  (`entrega/gateway/replication.py`) para escolher a réplica de leitura
  (round-robin) ou propagar a escrita para as duas réplicas.
- **Orders → Products (leste-oeste, direto):** ao criar um pedido, o serviço
  de Pedidos chama `GET {PRODUCTS_URL}/products/{id}` diretamente em uma das
  réplicas de Produtos (sem passar pelo Gateway), para validar a existência
  da pizza e obter nome/preço atuais (`entrega/orders/main.py`,
  `_fetch_product`).
- **Autenticação entre camadas:** o token JWT (`Authorization: Bearer <token>`)
  é emitido pelo serviço de Usuários no login e validado **de forma
  independente** por cada serviço (`auth.py` duplicado em
  `users/`, `products/`, `orders/`), todos compartilhando o mesmo
  `JWT_SECRET`. O Gateway não decodifica o token — apenas o repassa.
- **Heartbeat:** o Gateway faz `GET /health` periodicamente em cada instância
  de backend (`entrega/gateway/heartbeat.py`) para manter o estado
  UP/DOWN usado no roteamento e no dashboard.

## 2. Qual estratégia de consistência foi adotada na replicação? Forte ou eventual? Por quê?

Foi adotada **consistência forte (CP, no espectro do teorema CAP)** para as
escritas no serviço de Produtos.

- `POST /products` só é aceito pelo Gateway se **as duas réplicas** estiverem
  `UP` no momento da requisição (`ProductsRouter.create_product`). Se alguma
  réplica estiver `DOWN`, o Gateway responde `503` imediatamente, **sem
  escrever em nenhuma réplica**.
- Quando ambas estão `UP`, o Gateway gera um `id` (UUID4) único, monta o
  payload com esse `id` e envia o **mesmo payload em sequência para as duas
  réplicas**. Se **ambas** responderem com o **mesmo status** (seja sucesso
  `2xx` ou uma rejeição uniforme, como `403` quando o token não é de admin),
  essa resposta é repassada ao cliente sem alterações. Só quando as réplicas
  **divergem** entre si (ex.: uma responde `201` e a outra `500`) é registrado
  um log `[REPLICATION]` de inconsistência e o Gateway responde `502`.
- **Justificativa:** essa escolha garante que, sempre que uma réplica está
  acessível, seu conteúdo de produtos é idêntico ao da outra — não é
  necessário nenhum mecanismo de reconciliação ao recuperar uma réplica que
  caiu. O trade-off é a **disponibilidade de escrita**: durante uma falha
  parcial (uma réplica `DOWN`), `POST /products` fica indisponível até a
  réplica voltar, mesmo que a outra réplica esteja saudável.
- As **leituras** (`GET /products`, `GET /products/{id}`) são distribuídas
  por **round-robin simples** entre as réplicas que estão `UP`
  (`ProductsRouter.pick_read_replica`). Se ambas estiverem `DOWN`, o Gateway
  responde `503`.

## 3. O que acontece com o sistema se o Serviço de Pedidos cair? O restante continua funcionando?

Sim. Os microsserviços são independentes e o Gateway trata cada um
isoladamente:

- O heartbeat do Gateway (`entrega/gateway/heartbeat.py`) faz `GET
  {ORDERS_URL}/health` a cada `HEARTBEAT_INTERVAL` segundos (padrão 5s). Após
  `HEARTBEAT_FAILURE_THRESHOLD` falhas consecutivas (padrão 2, ou seja, ~10s),
  a instância `orders` é marcada `DOWN` e o Gateway registra
  `[FAILURE] orders (<url>) DOWN after 2 failed checks`.
- A partir desse momento, **qualquer requisição para `/orders/*`** recebe
  `503 {"error": "Servico de orders indisponivel no momento"}` do Gateway,
  sem tentar contatar o serviço (`_proxy_single`).
- **Usuários e Produtos continuam funcionando normalmente**: `POST
  /users/register`, `POST /users/login`, `GET /users/{id}`, `GET /products`,
  `GET /products/{id}` e `POST /products` não dependem do serviço de Pedidos
  e seguem respondendo normalmente, pois cada serviço é monitorado e roteado
  de forma independente.
- Quando o serviço de Pedidos volta a responder `GET /health` com
  `{"status": "ok"}`, o Gateway registra
  `[RECOVERY] orders (<url>) back UP` e volta a encaminhar requisições
  normalmente — sem necessidade de reiniciar o Gateway.
- O dashboard (`/dashboard`) reflete essa transição em tempo real (polling de
  `/dashboard/status` a cada 2s), mostrando o card `orders` em vermelho
  durante a indisponibilidade e em verde após a recuperação.

## 4. Como o JWT garante que um usuário comum não consiga criar produtos?

- No login (`POST /users/login`), o serviço de Usuários gera um JWT
  (`create_access_token` em `auth.py`) cujo payload contém `userId`, `email`,
  `role` e `exp`. O valor de `role` vem **diretamente do registro do usuário
  em `users.json`** — nunca de um campo enviado pelo cliente na requisição de
  login.
- `POST /users/register` **sempre** cria o usuário com `role: "user"`
  (`entrega/users/main.py`). Não existe nenhum endpoint que permita a um
  usuário comum alterar seu próprio `role`. O único usuário com
  `role: "admin"` é o administrador semeado em `users_seed.json`
  (`admin@pizzaria.com`).
- O endpoint `POST /products`, em **cada réplica** do serviço de Produtos,
  depende de `require_admin` (definida em `auth.py`): essa dependency chama
  `get_current_user` (decodifica e valida o JWT com o `JWT_SECRET`
  compartilhado) e, em seguida, verifica `payload["role"] == "admin"`. Se o
  token for de um usuário comum (`role: "user"`), a dependency levanta
  `HTTPException(403)` — a requisição é rejeitada **antes** de qualquer
  lógica de criação de produto ser executada.
- Como o `role` é assinado dentro do JWT (HS256) com um segredo que o cliente
  não possui, e a verificação ocorre no próprio serviço de Produtos (não
  apenas no Gateway), um usuário comum **não tem como** forjar um token com
  `role: "admin"` nem burlar a checagem chamando o serviço diretamente.

## 5. Quais limitações a implementação possui em relação a um sistema real de produção?

- **Persistência em arquivos JSON**: não há transações atômicas nem locking
  concorrente robusto. Escritas concorrentes no mesmo arquivo (`save_data`)
  podem, em teoria, causar condições de corrida sob alta concorrência — em um
  sistema real seria substituído por um banco de dados (relacional ou NoSQL)
  com controle transacional.
- **TLS autoassinado, sem CA**: o certificado gerado por
  `certs/generate_certs.sh` não é validado por uma autoridade certificadora
  pública; clientes precisam confiar manualmente nele (`curl -k` ou
  `verify=<caminho-do-cert>`). Em produção seria necessário um certificado
  emitido por uma CA confiável (ex: Let's Encrypt).
- **Sem reconciliação de réplicas após partição prolongada**: a estratégia CP
  evita divergência ao **rejeitar escritas** quando uma réplica está `DOWN`,
  mas não há um processo de sincronização automática caso uma réplica fique
  fora do ar por muito tempo e seja substituída/reiniciada com dados
  desatualizados — seria necessário um mecanismo de reconciliação (ex:
  versionamento, snapshots, ou um log de operações a ser reaplicado).
- **Sem fila de mensagens / retry assíncrono**: a propagação de escrita para
  as réplicas de Produtos e a validação de pedidos via Products são chamadas
  HTTP síncronas. Falhas transitórias de rede não têm retry automático; um
  sistema real usaria filas (ex: RabbitMQ/Kafka) e padrões como outbox para
  garantir entrega.
- **Sem rate limiting / proteção contra abuso**: o Gateway não limita a taxa
  de requisições por cliente, o que o deixa vulnerável a abuso ou negação de
  serviço acidental.
- **Segredo JWT compartilhado em texto plano**: `JWT_SECRET` é distribuído via
  `.env`/variáveis de ambiente, sem rotação ou cofre de segredos (ex:
  Vault/KMS). Em produção seria necessário gerenciamento centralizado e
  rotação periódica de segredos.
- **Heartbeat simples**: o mecanismo de heartbeat detecta falhas de
  disponibilidade (serviço não responde a `/health`), mas não detecta
  degradação parcial (ex: serviço lento, porém respondendo `200`).
