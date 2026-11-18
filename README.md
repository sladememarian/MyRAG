# Document QA (RAG) — Django + LangChain + ChromaDB

A small, readable **document question-answering system**. Upload Persian or
English `.docx` files in Django Admin, ask a question through the REST API (or
admin), and get an answer that is grounded **only** in those documents. Every
question, answer and source list is stored as history.

**Stack:** Django 5 · Django REST Framework · drf-spectacular · PostgreSQL ·
LangChain · ChromaDB · local multilingual sentence-transformers · OpenRouter
(free model) · Docker Compose. **UI: Django Admin only.**

---

## Quick start (Docker)

```bash
cp .env.example .env       # then set OPENROUTER_API_KEY (and change passwords)
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
3. Open **Queries → Add query**, type `جنگل هیرکانی کجاست؟`, save.
   The answer, sources and model name are filled in and stored in history.
4. Or use the API:

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
    G --> H[ChatOpenAI → OpenRouter<br/>free model]
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
| `ASK_THROTTLE_RATE` | per-user `/api/ask/` limit | `20/min` |
| `OPENROUTER_API_KEY` | OpenRouter key | — |
| `OPENROUTER_BASE_URL` | OpenAI-compatible API root | `https://openrouter.ai/api/v1` |
| `OPENROUTER_MODEL` | Chat model id | `inclusionai/ling-3.2-flash:free` |
| `OPENROUTER_PROXY` | Optional HTTP/SOCKS proxy | empty |
| `EMBEDDING_MODEL` | Local multilingual model | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` |
| `CHROMA_DIR` | Persistent vector store | `/data/chroma` in Docker |
| `RETRIEVAL_K` / `RETRIEVAL_FETCH_K` | chunks kept / candidates per query | `5` / `20` |
| `RETRIEVAL_MIN_SCORE` | drop weak chunks (0 disables) | `0.2` |
| `RETRIEVAL_USE_MULTI_QUERY` | extra LLM rewrite call per question | `False` |
| `MULTI_QUERY_COUNT` | question rewrites when enabled | `3` |
| `MAX_DOCUMENT_SIZE_MB` | upload limit | `10` |

**Base URL note:** LangChain's `ChatOpenAI` talks to the *chat completions*
API, so the base URL must be `https://openrouter.ai/api/v1`. Do not use the
`/responses` endpoint (`.../api/v1/responses`) — that is a different API.

**Production security:** set `DEBUG=False`, a random `SECRET_KEY` and a strong
`POSTGRES_PASSWORD`, then run `python manage.py check --deploy`. HTTPS redirects,
secure cookies and HSTS turn on automatically. Details:
[security and operations](docs/10-security-and-operations.md).

**Free models:** create a key at <https://openrouter.ai/keys> and choose any
`":free"` model from <https://openrouter.ai/models?max_price=0>. Free models
have a shared daily cap; on HTTP 429 the app stores the error in history and
returns a clear message. To switch models, edit `OPENROUTER_MODEL` and restart.

**Proxy:** if OpenRouter is unreachable directly, set e.g.
`OPENROUTER_PROXY=http://127.0.0.1:9383` or `socks5://127.0.0.1:9382`.
When Django runs in Docker, `127.0.0.1` is the container itself — use
`http://host.docker.internal:9383` instead.

---

## Running tests

```bash
docker compose run --rm web pytest              # 74 deterministic, offline tests
docker compose run --rm web pytest -m live      # real OpenRouter call (uses quota)
```

Tests use fake deterministic embeddings and a temporary Chroma directory; the
LLM is mocked. Details: [docs/06-testing.md](docs/06-testing.md).

---

## Project layout

```
config/            Django settings, URLs, deployment checks
documents/         Document model, admin, REST API, file cleanup signals
qa/                Query model, admin, ask API, history, throttling, commands
rag/
  extract.py       .docx → clean text (paragraphs + tables, RTL-safe)
  vectorstore.py   local embeddings + persistent Chroma
  ingest.py        chunking, indexing, deletion
  retrieval.py     MMR + multi-query + de-duplication + scores
  chain.py         grounded prompt, LLM call, answer + sources
  services.py      shared by admin and API (no duplicated logic)
tests/             pytest suite (documents / rag / qa / api)
docs/              design notes, API docs, checklist, presentation
sample_data/       Persian sample .docx files + test questions
```

---

## Useful commands

```bash
docker compose logs -f web                         # watch the server
docker compose exec web python manage.py ask "جنگل چیست؟"
docker compose exec web python manage.py createsuperuser
docker compose run --rm web python manage.py makemigrations --check
docker compose down                                # stop (data kept in volumes)
docker compose down -v                             # stop and erase all data
```

## License / data

Sample documents are original, short, Persian texts written for this project.
