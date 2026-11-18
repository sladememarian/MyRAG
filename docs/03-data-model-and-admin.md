# Data model and Django Admin

## `Document` (app `documents`)

| Field | Type | Notes |
|---|---|---|
| `title` | `CharField(255)` | shown everywhere, also stored in chunk metadata |
| `file` | `FileField` | `.docx` only, validated, max size from env |
| `full_text` | `TextField` | filled by the ingestion pipeline; read-only |
| `indexed` | `BooleanField` | true when chunks exist in Chroma |
| `created_at` / `updated_at` | `DateTimeField` | automatic |

Validation: `documents/validators.py` checks the extension (case-insensitive)
and the size (`MAX_DOCUMENT_SIZE_MB`, default 10 MB). It runs in the admin form,
in the API serializer and in model `full_clean()`.

## `Query` (app `qa`)

| Field | Type | Notes |
|---|---|---|
| `user` | `ForeignKey(User, null)` | owner of the history entry; null for rows created before scoping |
| `question` | `TextField` | editable only when creating |
| `answer` | `TextField` | generated, read-only |
| `sources` | `JSONField` | list of `{document_id, title, chunk_index, score, snippet}` |
| `model_name` | `CharField` | which model produced the answer |
| `status` | `ok` / `error` | failures are stored too |
| `failure_kind` | `no_content` / `llm` / `other` | persisted reason used to choose the API status |
| `error_message` | `TextField` | readable reason for failures |
| `created_at` | `DateTimeField` | history ordering |

`Query` **is** the history: no separate table is needed. The REST API filters
it by `user`, so callers only see their own questions. The admin sees all rows
for support and oversight.

## Document admin

| Feature | Implementation |
|---|---|
| List + filters | `list_display`, `list_filter`, `date_hierarchy` |
| Search title and text | `search_fields = ("title", "full_text")` |
| Read-only extracted text | `readonly_fields` |
| Extract + index on save | `save_model()` → `process_document()` |
| Delete chunks with document | `delete_model()` + `delete_queryset()`; the row is kept if Chroma fails |
| Re-index action | `reindex_selected` action |
| Feedback | success/error messages from `django.contrib.messages` |

### Why editing never duplicates chunks

`index_document()` always calls `delete_document(document.pk)` **before**
adding new chunks. Deletion uses a metadata filter
`{"document_id": <id>}`, so it removes every chunk of that document only.
Chunk ids are also deterministic (`doc<id>-chunk<n>`), which makes accidental
duplicates impossible even if a delete is retried. Re-indexing is therefore
idempotent: run it ten times and the number of chunks stays the same.

### Deletion is all-or-nothing

The database row is deleted only after its chunks are removed from Chroma. If
the vector store fails, the API returns `503` and the admin shows an error;
the document stays so the delete can be retried. This avoids orphaned chunks
that would still answer questions but no longer belong to any visible document.

### Files are cleaned up

Django does not delete `FileField` files automatically. Model signals handle
both cases: deleting a document removes its `.docx`, and uploading a
replacement removes the previous file after the save succeeds.

## Query admin

- **Add query** page: only `question` is editable. Saving calls the RAG chain
  and fills answer, sources, model and status.
- **Change query** page: everything is read-only, including the question, so
  history cannot silently change. Delete is still possible (standard admin).
  The full answer is shown under **Answer**, keeping its line breaks and `[n]`
  citations.
- Sources are rendered as pretty-printed JSON in a `<pre>` block.
- List columns: id, truncated question, truncated answer, owner, status, model,
  created date; filters by status and date; search over question and answer.
  Both the question and the answer cells are links: click either one to open
  the change page and read the full answer — the list only shows a one-line
  preview.
- New questions are owned by the admin user who created them; `failure_kind`
  is shown on the detail page for failed questions.

## Why admin only

The brief requires Django Admin as the only UI. Uploading, editing, deleting,
asking and reading history are all available there, so a separate frontend
would add code without adding functionality. The REST API covers programmatic
use and Swagger documents it.
