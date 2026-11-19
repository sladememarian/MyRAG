# Setup and configuration

## Prerequisites

- Docker Desktop (or Docker Engine + Compose v2)
- An API key for at least one supported provider (OpenRouter, Itera Compute, Token Harbor, Orca Router)
- Internet access on first run (embedding model download + LLM calls)

## Steps

```bash
cd work
cp .env.example .env
# edit .env: provider key(s), POSTGRES_PASSWORD, SECRET_KEY, optional proxy
docker compose up --build
```

Wait until the log shows `Starting development server at http://0.0.0.0:8000/`
and then open <http://localhost:8000/admin/>.

The entrypoint automatically:

1. waits for PostgreSQL,
2. runs `manage.py migrate`,
3. runs `manage.py ensure_superuser` (uses `DJANGO_SUPERUSER_*`),
4. starts Django.

## Environment variables

### Django / database

| Variable | Meaning | Default |
|---|---|---|
| `DEBUG` | debug mode | `False` (`.env.example` turns it on for local Docker) |
| `SECRET_KEY` | Django secret, at least 50 random characters | empty → temporary key |
| `ALLOWED_HOSTS` | comma separated | `localhost,127.0.0.1,web,testserver` |
| `SECURE_SSL_REDIRECT` | redirect HTTP → HTTPS | `True` when `DEBUG=False` |
| `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` | HTTPS-only cookies | `True` when `DEBUG=False` |
| `SECURE_HSTS_SECONDS` | HSTS lifetime (0 disables) | `31536000` when `DEBUG=False` |
| `TRUST_X_FORWARDED_PROTO` | trust a reverse proxy's scheme header | `False` (set `True` behind TLS proxy) |
| `CSRF_TRUSTED_ORIGINS` | extra trusted origins (comma separated) | empty |
| `POSTGRES_DB/USER/PASSWORD` | database credentials | `ragdb` / `raguser` / **required** (no built-in fallback) |
| `POSTGRES_HOST/PORT` | database address | `localhost:5432` (compose sets `db`) |
| `DJANGO_SUPERUSER_USERNAME/EMAIL/PASSWORD` | first admin user | `admin` / … |
| `MEDIA_ROOT` | uploaded files | `./media` (`/app/media` in Docker) |
| `API_PAGE_SIZE` | history pagination | `20` |
| `ASK_THROTTLE_RATE` | per-user `/api/ask/` limit | `20/min` (empty disables) |

### LLM providers

Only four providers are supported (OpenRouter, Itera Compute, Token Harbor, Orca Router), each with a fixed API root (overridable in
the deployment, not in the admin):

| Variable | Meaning | Default |
|---|---|---|
| `OPENROUTER_API_KEY` | fallback/import key for OpenRouter | empty |
| `OPENROUTER_BASE_URL` | OpenRouter OpenAI-compatible root | `https://openrouter.ai/api/v1` |
| `OPENROUTER_MODEL` | fallback model id, used until a model is selected in admin | `inclusionai/ling-3.2-flash:free` |
| `OPENROUTER_APP_NAME` | `X-Title` sent to OpenRouter | `Document QA RAG` |
| `OPENROUTER_SITE_URL` | optional `HTTP-Referer` for OpenRouter rankings | empty |
| `ITERACOMPUTE_API_KEY` | fallback/import key for Itera Compute | empty |
| `ITERACOMPUTE_BASE_URL` | Itera Compute OpenAI-compatible root | `https://api.iteracompute.com/v1` |
| `ITERACOMPUTE_MODEL` | fallback Itera model id | `Auto` |
| `TOKENHARBOR_API_KEY` / `_BASE_URL` / `_MODEL` | Token Harbor key, root, fallback model | empty / `https://tokenharbor.ai/v1` / empty |
| `ORCAROUTER_API_KEY` / `_BASE_URL` / `_MODEL` | Orca Router key, root, fallback model | empty / `https://api.orcarouter.ai/v1` / `orcarouter/free` |
| `LLM_KEY_ATTEMPTS` | tries per key for 429/5xx/timeouts/empty answers | `3` |
| `LLM_RETRY_BACKOFF` | first wait in seconds (doubles each retry) | `2.0` |
| `LLM_MODELS_TIMEOUT` | timeout for listing a provider's models | `120` |

Keys added in **Admin → Model Management** win over the `.env` keys. The
command `python manage.py import_env_keys` copies the two variables above into
the encrypted database store once, so a fresh checkout starts with working keys.

### LLM client and proxy

| Variable | Meaning | Default |
|---|---|---|
| `LLM_TIMEOUT` | request timeout (s) | `60` |
| `LLM_MAX_TOKENS` | answer cap | `800` |
| `LLM_TEMPERATURE` | sampling temperature | `0` |
| `LLM_MAX_RETRIES` | SDK retries for 429/5xx/timeouts, per key | `3` |
| `LLM_PROXY` | one full proxy URL; wins over the three values below | empty |
| `LLM_PROXY_SCHEME` | `http`, `https`, `socks5`, `socks5h` | `http` |
| `LLM_PROXY_HOST` | proxy host; leave empty for a direct connection | empty |
| `LLM_PROXY_PORT` | proxy port | empty |
| `OPENROUTER_PROXY` | deprecated alias for `LLM_PROXY` | empty |

Inside Docker, a loopback proxy host (`127.0.0.1`, `localhost`) is rewritten to
`host.docker.internal`, so the same `.env` works locally and in the container.
The older `OPENROUTER_TIMEOUT`, `OPENROUTER_MAX_TOKENS` and
`OPENROUTER_TEMPERATURE` names are still accepted as fallbacks.

### API keys at rest

| Variable | Meaning | Default |
|---|---|---|
| `SECRET_ENCRYPTION_KEY` | encrypts provider keys stored in the admin | empty → derive from `SECRET_KEY` |

Set a separate value if you expect to rotate `SECRET_KEY`; otherwise a rotation
makes stored keys unreadable and they must be entered again.

### Choosing the answering model

Open **Admin → Model Management**, choose the provider tab, add keys and models,
and tick *is active* on the model that should answer. The active model overrides
the `.env` defaults at either provider; the variables remain the fallback while
no model is active. No restart is needed.

Do **not** put `/responses` or `/chat/completions` in a base URL. If you do,
the app logs a warning and removes the suffix automatically, because
`ChatOpenAI` uses the chat-completions protocol.

### Embeddings and Chroma

| Variable | Meaning | Default |
|---|---|---|
| `EMBEDDING_BACKEND` | `sentence-transformers` or `fake` (tests) | `sentence-transformers` |
| `EMBEDDING_MODEL` | Hugging Face model id | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` |
| `EMBEDDING_DEVICE` | `cpu` or `cuda` | `cpu` |
| `CHROMA_DIR` | persistent directory | `./chroma_db`, `/data/chroma` in Docker |
| `CHROMA_COLLECTION` | collection name | `documents` |

In Docker, `HF_HOME=/data/hf` points at the `hf_cache` volume, so the ~470 MB
embedding model is downloaded only once and survives `docker compose up --build`.
The first upload blocks until it finishes; watch the transfer with
`scripts/watch-model-download.ps1` (progress bar, rate, ETA).

### Retrieval

| Variable | Meaning | Default |
|---|---|---|
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | characters per chunk / overlap | `800` / `120` |
| `RETRIEVAL_K` | chunks returned | `5` |
| `RETRIEVAL_FETCH_K` | MMR candidates | `20` |
| `RETRIEVAL_LAMBDA` | MMR relevance↔diversity (0..1) | `0.5` |
| `RETRIEVAL_USE_MULTI_QUERY` | enable question rewriting (extra LLM call) | `False` |
| `MULTI_QUERY_COUNT` | number of rewrites | `3` |
| `RETRIEVAL_MIN_SCORE` | drop chunks below this 0..1 score | `0.2` |
| `CONTEXT_MAX_CHARS` | max prompt context | `6000` |
| `MAX_DOCUMENT_SIZE_MB` | upload limit | `10` |

## Production settings

A production deployment must set `DEBUG=False`, a real `SECRET_KEY`, and a
strong `POSTGRES_PASSWORD`. With `DEBUG=False`, Django also enables HTTPS
redirects, secure session/CSRF cookies and one-year HSTS by default. If Nginx
or another proxy terminates TLS, set `TRUST_X_FORWARDED_PROTO=True` and make
sure the proxy overwrites (not appends) `X-Forwarded-Proto`. Leave it off when
Django is directly exposed, so clients cannot claim a plain-HTTP request was
HTTPS.

Before going live, run the deployment checks (they fail on a temporary secret
or the default database password):

```bash
docker compose exec -T web python manage.py check --deploy
```

See [Security and operations](10-security-and-operations.md) for the full
checklist, throttling and deletion behavior.

## Changing the LLM

1. Open **Admin → Model Management** and pick the provider tab.
2. Add the key(s) and the model id, tick *is active*, press **Test connection**
   if you want to verify the key immediately.
3. Ask a question; the selection is read from the database on every request, so
   no restart is needed.

For a fresh checkout without admin changes, set `OPENROUTER_MODEL=` (or
`ITERACOMPUTE_MODEL=`) in `.env` and `docker compose up -d`.

If a model is unavailable or rate-limited, the app tries the next key of the
same provider, then stores the error in history and returns HTTP 503 with a
readable message. There is no silent cross-provider fallback: the model you
selected is the model that answers, which keeps history auditable. Switch the
active model if you want another provider.

## Using a proxy

Change only the port when the proxy moves; everything else can stay:

```env
LLM_PROXY_SCHEME=http
LLM_PROXY_HOST=127.0.0.1
LLM_PROXY_PORT=14927
# SOCKS5 instead:
# LLM_PROXY=socks5://127.0.0.1:14926
```

`LLM_PROXY` (a full URL) wins over the three parts and accepts `http://`,
`https://`, `socks4://`, `socks5://` and `socks5h://`. Inside Docker,
`127.0.0.1` is rewritten to `host.docker.internal` automatically, so the same
values work on the host and in the container. Leave `LLM_PROXY_HOST` empty for
a direct connection.

Restart the web container after changing `.env` (`docker compose up -d`). Verify
with:

```bash
docker compose exec web python manage.py ask "test connection"
```

## Local development without Docker

Docker is the supported path. If you want to run locally anyway: Python 3.12,
a PostgreSQL instance, `pip install -r requirements.txt` (Docker uses
`requirements-docker.txt`), copy `.env` and set
`POSTGRES_HOST=localhost`, then `python manage.py migrate && python manage.py
runserver`. Using `DB_ENGINE=sqlite` also works for a quick look.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `OPENROUTER_API_KEY is not set` | add a key in **Model Management**, or fill `.env` |
| HTTP 429 / rate limited | add a backup key, wait, or switch the active model |
| Stored key shows *unreadable* | `SECRET_KEY`/`SECRET_ENCRYPTION_KEY` changed; re-enter the key |
| Compose refuses to start | set `POSTGRES_PASSWORD` in `.env`; there is no default |
| First indexing is slow | embedding model download (~470 MB), one time |
| `Could not open the .docx file` | file is corrupt or not a real .docx |
| DB connection refused | `docker compose ps`; db healthcheck must be healthy |
| Port 8000 busy | change `ports` in `docker-compose.yml` |
| Admin static files missing | ensure `DEBUG=True` (dev server serves them) |
