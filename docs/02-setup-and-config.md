# Setup and configuration

## Prerequisites

- Docker Desktop (or Docker Engine + Compose v2)
- An OpenRouter API key (free): <https://openrouter.ai/keys>
- Internet access on first run (embedding model download + LLM calls)

## Steps

```bash
cd work
cp .env.example .env
# edit .env: OPENROUTER_API_KEY, OPENROUTER_MODEL, passwords, SECRET_KEY
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
| `POSTGRES_DB/USER/PASSWORD` | database credentials | `ragdb` / `raguser` / `ragpass` |
| `POSTGRES_HOST/PORT` | database address | `localhost:5432` (compose sets `db`) |
| `DJANGO_SUPERUSER_USERNAME/EMAIL/PASSWORD` | first admin user | `admin` / … |
| `MEDIA_ROOT` | uploaded files | `./media` (`/app/media` in Docker) |
| `API_PAGE_SIZE` | history pagination | `20` |
| `ASK_THROTTLE_RATE` | per-user `/api/ask/` limit | `20/min` (empty disables) |

### OpenRouter

| Variable | Meaning | Default |
|---|---|---|
| `OPENROUTER_API_KEY` | API key (never commit it) | empty |
| `OPENROUTER_BASE_URL` | OpenAI-compatible root | `https://openrouter.ai/api/v1` |
| `OPENROUTER_MODEL` | model id, e.g. `inclusionai/ling-3.2-flash:free` | that model |
| `OPENROUTER_PROXY` | optional proxy URL | empty |
| `OPENROUTER_TIMEOUT` | request timeout (s) | `60` |
| `OPENROUTER_MAX_TOKENS` | answer cap | `800` |
| `OPENROUTER_TEMPERATURE` | sampling temperature | `0` |

Do **not** put `/responses` or `/chat/completions` in the base URL. If you do,
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

1. Find a free model: <https://openrouter.ai/models?max_price=0>
2. Set `OPENROUTER_MODEL=provider/model:free` in `.env`
3. `docker compose up -d` (recreates the web container)

If the model is unavailable or rate-limited, the app stores the error in the
history and returns HTTP 503 with a readable message. Try another free model.

## Using a proxy

If direct access fails, set one of:

```env
OPENROUTER_PROXY=http://127.0.0.1:9383
# or
OPENROUTER_PROXY=socks5://127.0.0.1:9382
```

Inside Docker, use `host.docker.internal` for a proxy running on the host:

```env
OPENROUTER_PROXY=http://host.docker.internal:9383
```

Then restart: `docker compose up -d`. Verify with:

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
| `OPENROUTER_API_KEY is not set` | fill `.env`, restart web |
| HTTP 429 / rate limited | free daily cap reached — wait or switch model |
| First indexing is slow | embedding model download (~470 MB), one time |
| `Could not open the .docx file` | file is corrupt or not a real .docx |
| DB connection refused | `docker compose ps`; db healthcheck must be healthy |
| Port 8000 busy | change `ports` in `docker-compose.yml` |
| Admin static files missing | ensure `DEBUG=True` (dev server serves them) |
