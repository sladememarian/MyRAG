# Architecture

## Big picture

```mermaid
flowchart TB
    subgraph Django["Django process (web container)"]
        Admin["Django Admin<br/>(only UI)"]
        API["REST API<br/>/api/"]
        Services["rag/services.py<br/>process_document() · delete_document_index()"]
        QA["qa/services.py<br/>answer_query()"]
    end

    subgraph Data["Persistent services"]
        PG[(PostgreSQL<br/>documents + history)]
        Chroma[(ChromaDB volume<br/>/data/chroma)]
        Media[(media volume<br/>uploaded .docx)]
    end

    subgraph External["External / local"]
        Embed["sentence-transformers<br/>multilingual (local, CPU)"]
        LLM["OpenRouter<br/>free chat model"]
    end

    Admin --> Services
    API --> Services
    Services --> PG
    Services --> Media
    Services --> Embed
    Services --> Chroma
    Admin --> QA
    API --> QA
    QA --> Chroma
    QA --> Embed
    QA --> LLM
    QA --> PG
```

Everything runs in one `web` container; PostgreSQL and the two data directories
are separate containers/volumes. There is no Celery or queue: indexing happens
synchronously on save, which keeps the project small and easy to explain.

## Why the logic lives in `rag/`

- `documents/admin.py` and `documents/views.py` only call
  `process_document()` / `delete_document_index()`.
- `qa/admin.py` and `qa/views.py` only call `answer_query()` / `run_query()`.
- Result: admin and API behave identically, and the RAG code can be tested
  without HTTP or admin.

```mermaid
sequenceDiagram
    participant U as User (admin or API)
    participant S as rag.services
    participant E as rag.extract
    participant I as rag.ingest
    participant C as Chroma

    U->>S: save document
    S->>E: extract_text(file)
    E-->>S: full text
    S->>S: Document.full_text = text (DB)
    S->>I: index_document(doc)
    I->>C: delete old chunks (where document_id)
    I->>C: add chunks + metadata
    S->>S: indexed = chunks > 0
```

## Request flow for a question

```mermaid
sequenceDiagram
    participant U as User
    participant V as POST /api/ask/
    participant Q as qa.services
    participant R as rag.chain
    participant T as rag.retrieval
    participant C as Chroma
    participant L as OpenRouter

    U->>V: {"question": "..."}
    V->>Q: run_query()
    Q->>R: answer_question()
    R->>T: retrieve()
    T->>L: rewrite into N queries (optional)
    T->>C: MMR search per query
    C-->>T: chunks
    T-->>R: de-duplicated chunks + scores
    R->>L: prompt (context + question)
    L-->>R: answer
    R-->>Q: answer + sources + model
    Q->>Q: save Query(history)
    Q-->>V: result (or stored error)
    V-->>U: 200 / 404 / 503
```

## Runtime configuration

| Concern | Where |
|---|---|
| Django settings | `config/settings.py` (all env vars) |
| Compose services, volumes | `docker-compose.yml` |
| Image build, Python 3.12 | `Dockerfile` |
| Migrate + admin bootstrap | `entrypoint.sh` |
| API schema | drf-spectacular at `/api/schema/` |

## Data storage

| Data | Store | Survives `docker compose down`? |
|---|---|---|
| Documents metadata + full text | PostgreSQL volume | yes |
| Question/answer history | PostgreSQL volume | yes |
| Uploaded `.docx` files | `media` volume | yes |
| Chunks + embeddings | `chroma_data` volume | yes |

`docker compose down -v` removes all three volumes.
