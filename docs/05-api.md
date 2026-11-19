# REST API

Base URL: `http://localhost:8000/api/`
Interactive documentation: `http://localhost:8000/api/docs/`
OpenAPI schema: `http://localhost:8000/api/schema/` (JSON/YAML)

## Authentication

The API is private. Two schemes are enabled:

1. **Token** (best for curl/scripts)
   ```bash
   docker compose exec web python manage.py drf_create_token admin
   # prints: Token 9944b5912f...
   ```
   Send `Authorization: Token <key>` on every request.

2. **Session** (best for the browsable API / Swagger)
   Log in at `/admin/`, then use the same browser for `/api/`. Unsafe methods
   are CSRF-protected, as usual for session auth.

Why both: tokens are the simplest thing to demonstrate from a terminal, while
sessions make the Swagger "Try it out" button work without copying keys.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/documents/` | list documents |
| POST | `/api/documents/` | upload a `.docx` (multipart) |
| GET | `/api/documents/{id}/` | retrieve one |
| PUT/PATCH | `/api/documents/{id}/` | update fields (re-indexes) |
| DELETE | `/api/documents/{id}/` | delete document + chunks |
| POST | `/api/ask/` | ask a question |
| GET | `/api/history/` | paginated history **for the authenticated user** |
| GET | `/api/history/{id}/` | one of the caller's history entries |
| GET | `/api/health/` | public liveness probe (`{"status": "ok"}`) |

Pagination: `?page=2`, 20 items per page (`API_PAGE_SIZE`), response shape
`{count, next, previous, results}`. History is scoped to the token/session
user: asking as another user never exposes their questions, and requesting a
foreign id returns `404`.

## Examples

### Upload

```bash
curl -X POST http://localhost:8000/api/documents/ \
  -H "Authorization: Token $TOKEN" \
  -F "title=جنگل‌های ایران" \
  -F "file=@sample_data/01-jangal-iran.docx"
```

```json
{
  "id": 1,
  "title": "جنگل‌های ایران",
  "file": "http://localhost:8000/media/documents/2026/11/01-jangal-iran.docx",
  "full_text": "جنگل‌های هیرکانی ...",
  "indexed": true,
  "created_at": "2026-11-18T09:00:00Z",
  "updated_at": "2026-11-18T09:00:00Z"
}
```

### Ask

```bash
curl -X POST http://localhost:8000/api/ask/ \
  -H "Authorization: Token $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "جنگل هیرکانی کجاست؟"}'
```

```json
{
  "query_id": 4,
  "answer": "جنگل هیرکانی در شمال ایران و در استان‌های گلستان، مازندران و گیلان قرار دارد.",
  "sources": [
    {
      "document_id": 1,
      "title": "جنگل‌های ایران",
      "chunk_index": 0,
      "score": 0.81,
      "snippet": "جنگل‌های هیرکانی در شمال ایران ..."
    }
  ],
  "model_name": "inclusionai/ling-3.2-flash:free",
  "status": "ok",
  "created_at": "2026-11-18T09:01:00Z"
}
```

### History

```bash
curl -H "Authorization: Token $TOKEN" \
  "http://localhost:8000/api/history/?page=1"
```

### Delete

```bash
curl -X DELETE -H "Authorization: Token $TOKEN" \
  http://localhost:8000/api/documents/1/
```

## Validation and errors

- `file`: `.docx` only, at most `MAX_DOCUMENT_SIZE_MB` (default 10 MB).
- `question`: 3–2000 characters, trimmed.
- `401/403`: missing or invalid credentials.
- `400`: validation error (fields are named in the response) or an unexpected
  processing failure. Details are logged server-side, never returned.
- `404` on `/api/ask/`: no chunk reached `RETRIEVAL_MIN_SCORE` (nothing
  relevant indexed). The failed question is still stored with
  `status="error"` and `failure_kind="no_content"`.
- `429`: the caller exceeded `ASK_THROTTLE_RATE` (default `20/min`).
- `503` on `/api/ask/`: selected-provider failure (rate limit, timeout, key).
  The failed question is still stored, with `failure_kind="llm"`.
- `503` on `DELETE /api/documents/{id}/`: Chroma could not be updated, so the
  document was **not** deleted. Retry once the vector store is available.

History records include `failure_kind` (`no_content`, `llm`, `other`, or empty
for success), which is the stable machine-readable counterpart of
`error_message`.

### Relevance threshold

`RETRIEVAL_MIN_SCORE` (default `0.2`) drops weakly related chunks. This is what
turns an off-topic question into a `404` instead of an answer built from
unrelated text. Lower it if valid questions are rejected; `0` disables the
filter. If scoring itself fails, retrieval keeps the chunks rather than
silently returning nothing.

## API docs export

Generate a static schema for the submission package:

```bash
docker compose exec web python manage.py spectacular --file docs/openapi.yaml
```

The Swagger UI reads the same schema at runtime, so the export always matches
the code.
