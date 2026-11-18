# Design decisions (and how to defend them)

Short answers to the questions a reviewer is likely to ask.

### 1. Why Django Admin as the only UI?

The brief allows admin only, and admin already gives authenticated CRUD,
search, filters and bulk actions for free. Building a separate frontend would
duplicate logic and increase the attack surface without adding a required
feature. The REST API covers programmatic and integration use.

### 2. Why PostgreSQL + ChromaDB instead of one database?

PostgreSQL is the reliable source of truth for documents, text and history; it
is transactional and easy to back up. Chroma is purpose-built for vector search
and persists to a Docker volume, so both survive restarts. Keeping them separate
means a vector-store rebuild never risks the history or the uploaded files.

### 3. Why a local embedding model?

The documents are likely Persian, so a multilingual model is required.
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` runs on CPU,
costs nothing per query, and keeps document text inside our infrastructure.
The trade-off is a one-time ~470 MB download and slower first indexing; that is
acceptable for a document QA tool with a small corpus.

### 4. Why chunk size 800 with 120 overlap?

Persian sentences are information-dense; 800 characters holds a few sentences,
enough to answer a question without drowning the prompt in unrelated text. The
overlap preserves a sentence that straddles a boundary. Both values are
environment variables, so they can be tuned without code changes.

### 5. Why put logic in `rag/services.py`?

Admin and API must behave identically. Both call the same
`process_document()` and `delete_document_index()` functions, so fixes and
validation happen once. Views and admin remain thin adapters, which also makes
the pipeline unit-testable without HTTP.

### 6. How does re-indexing avoid duplicate chunks?

Every `index_document()` call deletes all chunks where
`document_id == doc.id` before adding the new ones, and chunk ids are
deterministic (`doc<id>-chunk<n>`). Adding is therefore a replace, not an
append: indexing the same document ten times still yields exactly one copy of
each chunk. The admin action and the API update path both use this function.

### 7. Why MultiQuery + MMR, not plain similarity?

Users phrase questions differently from documents, so one embedding of the
question can miss relevant chunks; the LLM rewrites it into a few variants to
increase recall. MMR then removes near-duplicates so the prompt budget is spent
on diverse evidence. If the rewrite fails, retrieval falls back to plain MMR, so
the LLM is an enhancement, never a dependency.

### 8. What would reranking add?

A cross-encoder would read each `(question, chunk)` pair and produce a more
accurate relevance score than embedding distance. It usually improves answer
precision but costs another model download and extra latency per query. It fits
naturally between `retrieve()` and context building, which is why retrieval is
isolated in one module.

### 9. Why both session and token authentication?

Token auth makes `curl` demos and scripts simple, while session auth lets the
person grading the project use Swagger or the browsable API after logging into
admin. Enabling both costs two lines of configuration and no custom code.
Authorization is still `IsAuthenticated` for every data endpoint.

### 10. Why is indexing synchronous?

Synchronous indexing keeps the architecture small: one web container, no
Celery, no Redis, no broker to explain or operate. For small .docx files the
delay is a second or two after the first model download. If the corpus grew,
moving `process_document()` into a background task would be an isolated change
because all callers already go through the service function.

### 11. Why store failed questions?

History is the audit trail of the system. When the LLM is rate-limited or the
documents contain no answer, the question, timestamp, status and error message
are still saved, and the API returns 404/503. This makes failures diagnosable
instead of invisible, and it demonstrates error handling rather than hiding it.

### 12. Why `/api/v1` and not the `/responses` endpoint?

LangChain's `ChatOpenAI` uses the OpenAI *chat completions* protocol
(`/chat/completions`), so the base URL is the API root
`https://openrouter.ai/api/v1`. The `/responses` URL is a different
(Responses API) endpoint and appending it would produce 404s. This is
documented in `.env.example` and the setup guide.

### 13. Why dotenv + environment variables?

Secrets never live in source code or the image, and the same image works in
Docker, CI and local runs. `.env` is git-ignored; `.env.example` documents every
variable with safe placeholders. This matches the brief's "never hardcode keys".

### 14. Why is history per user?

Question history can contain sensitive business text. The API now filters
`Query` by the authenticated `user`, so a token cannot read someone else's
questions; the admin still shows every row for support. A nullable owner keeps
old rows and survives user deletion (`SET NULL`).

### 15. Why production-safe defaults?

Security should not depend on remembering six flags. `DEBUG` defaults to
`False`, and when debug is off Django enables HTTPS redirects, secure cookies
and HSTS; `manage.py check --deploy` additionally fails on a temporary secret
or the default database password. Local Docker explicitly sets `DEBUG=True` in
`.env.example`, so development convenience is unchanged.

### 16. Why add a relevance threshold?

Without a floor, an unrelated question still retrieves *some* chunk and the LLM
may stretch it into an answer. `RETRIEVAL_MIN_SCORE=0.2` drops weak matches and
makes `/api/ask/` return `404` for off-topic questions. It is configurable
because the right value depends on the embedding model and corpus.

### 17. Why block deletion when Chroma fails?

Deleting the PostgreSQL row while its vectors remain creates invisible data:
the chunks still answer questions, but no document page can show or remove
them. The API returns `503` and the admin keeps the row, so the operator can
retry. The trade-off is that a vector-store outage also blocks deletion; that
is safer than silently leaking content into future answers.

### 18. Why throttle `/api/ask/`?

Every question costs OpenRouter quota, and free models have a shared cap. A
per-user `ASK_THROTTLE_RATE` (default `20/min`) keeps one caller from exhausting
the quota for everyone. It is a simple DRF cache throttle; no Redis or Celery
is needed for a single-container deployment.

### 19. Trade-offs accepted

- Single container, synchronous ingestion: simplest to run and explain, not
  built for thousands of documents.
- No conversation memory: each question is independent, which keeps the API
  and the data model simple.
- Admin-only UI: less polished than a custom frontend, but exactly what was
  requested and fully functional.
- No reranker, no hybrid BM25 search: deliberate scope control; both are noted
  as future improvements.
