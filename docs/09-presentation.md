# 10-minute presentation outline

## 0. One sentence (15 s)

"A Django + LangChain RAG service: upload Word documents, ask questions in
Persian or English, get answers grounded only in those documents, with sources
and full history."

## 1. Demo (3 min)

1. `docker compose up` → show `/admin/` logged in.
2. Model Management → show the provider tabs and the Find free models button, masked key,
   "Answering with", and **Test connection**.
3. Documents → upload `01-jangal-iran.docx` → point at the message
   "indexed into N chunks" and the read-only full text.
4. Queries → Add query → `جنگل هیرکانی کجاست؟` → show the Persian answer,
   sources JSON, model name, status.
5. `/api/docs/` → POST `/api/ask/` with a token → show JSON answer + sources.
6. History list → point out the stored question, sources and date, and one
   failed entry with `status=error` (LLM failures are history too). Show that
   history is scoped to the logged-in user.
7. Ask an off-topic question → `404` because no chunk reaches
   `RETRIEVAL_MIN_SCORE`; ask again quickly to show the `429` throttle.

## 2. Architecture (2 min)

Show `docs/01-architecture.md` diagram:

- Django (admin + DRF) in one container
- PostgreSQL (documents, history, provider config), Chroma volume (chunks),
  media volume
- Chroma is embedded in the Django process (not a separate container) with one
  writer and a persistent volume
- local multilingual embeddings; OpenRouter, Itera Compute, Token Harbor or Orca Router for generation,
  selected in Model Management
- `rag/services.py` is the single path used by admin and API

## 3. End-to-end flow (2 min)

`extract → chunk → embed → store`, then
`question → rewrite → MMR → de-duplicate → prompt → answer → history`.

Mention the concrete numbers: 800/120 chunking, k=5, fetch_k=20, 3 rewrites,
context cap 6000 chars.

## 4. Key decisions (2 min)

Pick four from `docs/07-decisions.md`:

1. service layer shared by admin/API → no duplicated logic
2. delete-before-add + deterministic ids → re-indexing is idempotent
3. MultiQuery + MMR with fallback → better recall, no hard dependency on the LLM
4. errors stored in history + safe messages + clear HTTP status codes →
   debuggable without leaking internals

## 5. Trade-offs and next steps (45 s)

- synchronous indexing: simple, fine for small corpora; Celery if it grows
- no reranker yet: isolated insertion point in `retrieve()`
- no hybrid keyword search or conversation memory
- next: reranker, background jobs, a labelled evaluation set for tuning the
  relevance threshold

## 6. Close (15 s)

"Everything is in the README: Docker one-liner, API examples, sample documents
with expected answers, and 115 offline tests."

---

## Likely questions and short answers

| Question | Answer |
|---|---|
| Why Chroma and not pgvector? | Chroma is a dedicated vector store with persistence; PostgreSQL stays the source of truth. It runs embedded in Django with one writer, so no extra service is needed. Swapping is isolated in `rag/vectorstore.py`. |
| Why is Chroma not a Compose container? | Embedded `PersistentClient` + `chroma_data` volume is enough for a single-writer, small corpus; a server would add a port, auth surface and healthcheck without a benefit. Server mode is the upgrade path for multiple writers. |
| What if a provider is down? | The question is still saved with `status=error`; API returns 503 with a readable message; retrieval itself does not depend on the LLM. Key failover stays within the selected provider, so history never lies about the model. |
| How are API keys protected? | Several keys per provider, encrypted at rest with Fernet; the admin only renders a mask; `.env` keys are a fallback/import source. |
| Why fake embeddings in tests? | Determinism and offline runs; the real model's semantic quality is not what unit tests should assert. |
| How do you avoid duplicate chunks? | Delete by `document_id` before add + deterministic ids. |
| Is the answer really grounded? | The prompt forbids outside knowledge, requires an explicit "not in the documents" answer, and the returned sources are exactly the chunks used. |
| How would you scale? | Run Chroma in server mode for multiple web replicas (the embedded store assumes one writer), move indexing to a queue, add a reranker, cache embeddings. |
| Why no frontend? | The brief requires admin only; the API is documented for integrations. |
