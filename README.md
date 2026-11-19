# Document QA (RAG) — Django + LangChain + ChromaDB

A small, readable **document question-answering system**. Upload Persian or
English `.docx` files in Django Admin, ask a question through the REST API (or
admin), and get an answer that is grounded **only** in those documents. Every
question, answer and source list is stored as history.

**Stack:** Django 5 · Django REST Framework · drf-spectacular · PostgreSQL ·
LangChain · ChromaDB (embedded, `PersistentClient`) · local multilingual
sentence-transformers · OpenRouter, Itera Compute, Token Harbor and Orca Router · Docker Compose.
**UI: Django Admin only.**

---

## Quick start (Docker)

```bash
cp .env.example .env       # set provider key(s), POSTGRES_PASSWORD and SECRET_KEY
docker compose up --build
```

Open:

| What | URL |
|---|---|
| Admin | http://localhost:8000/admin/ |
| Swagger UI | http://localhost:8000/api/docs/ |
| OpenAPI schema | http://localhost:8000/api/schema/ |
| Health check | http://localhost:8000/api/health/ |

The first start creates the admin user from `.env`:

```
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_PASSWORD=admin12345
```

> The first time a document is indexed, the multilingual embedding model
> (~470 MB) is downloaded and cached in the `hf_cache` volume, so it survives
> container rebuilds. Expect a one-off delay; later uploads are fast.
> The upload page stays "loading" while this happens — watch it live with:
>
> ```powershell
> powershell -ExecutionPolicy Bypass -File .\scripts\watch-model-download.ps1
> ```
>
> It prints a progress bar, transfer rate and ETA every few seconds and exits
> when the download finishes (then `docker compose logs -f web` shows indexing).

---

## 60-second demo

1. Log in at `/admin/` and open **Documents → Add document**.
2. Upload `sample_data/01-jangal-iran.docx`, title it *جنگل‌های ایران*, save.
   The admin message says how many chunks were indexed.
3. Open **Model Management**, pick a provider tab (OpenRouter, Itera Compute, Token Harbor or Orca Router), add a key
   and a model, and tick *is active*. (Keys from `.env` can be imported once with
   `python manage.py import_env_keys`.)
4. Open **Queries → Add query**, type `جنگل هیرکانی کجاست؟`, save.
   The answer, sources and model name are filled in and stored in history.
5. Or use the API:

```bash
# get a token once
docker compose exec web python manage.py drf_create_token admin

curl -s http://localhost:8000/api/ask/ \
  -H "Authorization: Token <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"question": "جنگل هیرکانی کجاست؟"}'
```

---

## How it works

```mermaid
flowchart LR
    A[.docx upload<br/>Admin or API] --> B[extract text<br/>python-docx]
    B --> C[split into chunks<br/>RecursiveCharacterTextSplitter]
    C --> D[(ChromaDB<br/>persistent volume)]
    Q[Question] --> E[Multi-query (optional)<br/>LLM rewrites question]
    E --> F[MMR search<br/>diverse chunks]
    F --> D
    D --> G[context + sources]
    G --> H[ChatOpenAI → selected provider<br/>OpenRouter or Itera Compute]
    H --> I[Answer + sources]
    I --> J[(Query history<br/>PostgreSQL)]
```

More detail: [architecture](docs/01-architecture.md) ·
[RAG pipeline](docs/04-rag-pipeline.md) · [API](docs/05-api.md) ·
[security and operations](docs/10-security-and-operations.md) ·
[decisions](docs/07-decisions.md).

---

## Configuration

All settings come from environment variables (`.env`). The important ones:

| Variable | Purpose | Default |
|---|---|---|
| `DEBUG` | development mode (off by default) | `False` |
| `SECRET_KEY` | Django secret (required in production) | temporary key |
| `SECRET_ENCRYPTION_KEY` | encrypts admin-stored provider keys | empty → derive from `SECRET_KEY` |
| `POSTGRES_PASSWORD` | database password (required) | — (Compose refuses to start) |
| `ASK_THROTTLE_RATE` | per-user `/api/ask/` limit | `20/min` |
| `OPENROUTER_API_KEY` | OpenRouter fallback/import key | — |
| `OPENROUTER_BASE_URL` | OpenRouter API root | `https://openrouter.ai/api/v1` |
| `OPENROUTER_MODEL` | fallback model id | `inclusionai/ling-3.2-flash:free` |
| `ITERACOMPUTE_API_KEY` | Itera Compute fallback/import key | — |
| `ITERACOMPUTE_BASE_URL` | Itera Compute API root | `https://api.iteracompute.com/v1` |
| `ITERACOMPUTE_MODEL` | fallback Itera model id | `Auto` |
| `TOKENHARBOR_API_KEY` / `TOKENHARBOR_BASE_URL` | Token Harbor key / API root | — / `https://tokenharbor.ai/v1` |
| `ORCAROUTER_API_KEY` / `ORCAROUTER_BASE_URL` | Orca Router key / API root | — / `https://api.orcarouter.ai/v1` |
| `LLM_KEY_ATTEMPTS` / `LLM_RETRY_BACKOFF` | tries per key for 429/5xx/empty answers / first backoff seconds | `3` / `2.0` |
| `LLM_TIMEOUT` / `LLM_MAX_RETRIES` | request timeout / SDK retries | `60` / `3` |
| `LLM_PROXY` | full proxy URL (wins over the parts) | empty |
| `LLM_PROXY_SCHEME` / `HOST` / `PORT` | proxy parts, e.g. http / 127.0.0.1 / 14927 | `http` / empty / empty |
| `EMBEDDING_MODEL` | Local multilingual model | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` |
| `CHROMA_DIR` | Persistent vector store | `/data/chroma` in Docker |
| `RETRIEVAL_K` / `RETRIEVAL_FETCH_K` | chunks kept / candidates per query | `5` / `20` |
| `RETRIEVAL_MIN_SCORE` | drop weak chunks (0 disables) | `0.2` |
| `RETRIEVAL_USE_MULTI_QUERY` | extra LLM rewrite call per question | `False` |
| `MULTI_QUERY_COUNT` | question rewrites when enabled | `3` |
| `MAX_DOCUMENT_SIZE_MB` | upload limit | `10` |

**Base URL note:** LangChain's `ChatOpenAI` talks to the *chat completions*
API, so base URLs must stop at the API root. Do not use the `/responses`
endpoint (`.../api/v1/responses`) — that is a different API.

**Production security:** set `DEBUG=False`, a random `SECRET_KEY` and a strong
`POSTGRES_PASSWORD`, then run `python manage.py check --deploy`. HTTPS redirects,
secure cookies and HSTS turn on automatically. Details:
[security and operations](docs/10-security-and-operations.md).

**Providers and models:** open **Admin → Model Management**. Each provider has
its own tab; add several API keys (priority controls failover) and tick the
model that should answer. The selected model overrides the `.env` fallback on
the next question, with no restart. OpenRouter free models have a shared daily
cap; on HTTP 429 the app tries the next key, then stores the error and returns a
clear message. There is no silent cross-provider switch.

**Proxy:** change only the port when the proxy moves:

```env
LLM_PROXY_SCHEME=http
LLM_PROXY_HOST=127.0.0.1
LLM_PROXY_PORT=14927
# or a full URL, e.g. socks5://127.0.0.1:14926
LLM_PROXY=
```

Inside Docker a loopback host is rewritten to `host.docker.internal`, so the
same `.env` works on the host and in the container. Leave `LLM_PROXY_HOST`
empty for a direct connection.

**ChromaDB** runs embedded inside the Django process and persists to the
`chroma_data` volume; it is deliberately not a Compose service. See
[architecture](docs/01-architecture.md#why-chromadb-is-embedded-not-a-compose-service).

---

## Running tests

```bash
docker compose run --rm web pytest              # 115 deterministic, offline tests
docker compose run --rm web pytest -m live      # real selected-provider call (uses quota)
```

Tests use fake deterministic embeddings and a temporary Chroma directory; the
LLM is mocked. Details: [docs/06-testing.md](docs/06-testing.md).

---

## Project layout

```
config/            Django settings, URLs, deployment checks
documents/         Document model, admin, REST API, file cleanup signals
qa/                Query model, admin, ask API, history, throttling, commands
providers/         Model Management: providers, encrypted keys, models, tabs
rag/
  extract.py       .docx → clean text (paragraphs + tables, RTL-safe)
  vectorstore.py   local embeddings + embedded persistent Chroma
  ingest.py        chunking, indexing, deletion
  retrieval.py     MMR + multi-query + de-duplication + scores
  chain.py         grounded prompt, LLM call, answer + sources
  llm.py           provider/model selection, proxy, key failover, probing
  services.py      shared by admin and API (no duplicated logic)
tests/             pytest suite (documents / rag / qa / providers / api)
docs/              design notes, API docs, checklist, presentation
sample_data/       Persian sample .docx files + test questions
```

---

## Useful commands

```bash
docker compose logs -f web                         # watch the server
docker compose exec web python manage.py ask "جنگل چیست؟"
docker compose exec web python manage.py import_env_keys   # copy .env keys once
docker compose exec web python manage.py createsuperuser
docker compose run --rm web python manage.py makemigrations --check
docker compose down                                # stop (data kept in volumes)
docker compose down -v                             # stop and erase all data
```

## License / data

Sample documents are original, short, Persian texts written for this project.
