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

## Provider, APIKey and LLMModel (app `providers`)

The **Model Management** app stores configuration, not history. It is separate
from **Questions & Answers**, so an operator never has to scroll past question
rows to change a model.

### `Provider`

| Field | Type | Notes |
|---|---|---|
| `slug` | `CharField(40)` | `openrouter` or `iteracompute`; unique, created by migration |
| `name` | `CharField(100)` | shown on the tab and in messages |
| `is_enabled` | `BooleanField` | a disabled provider is skipped even if its model is active |
| `notes` | `TextField` | optional operator note |

Only four rows exist and the admin cannot add or delete providers: the code only
knows how to speak to these APIs. Their roots are constants
(`providers/constants.py`, overridable through `OPENROUTER_BASE_URL` /
`ITERACOMPUTE_BASE_URL`) rather than editable database fields, which prevents an
admin from pointing the answering pipeline at an arbitrary host (SSRF).

### `APIKey`

| Field | Type | Notes |
|---|---|---|
| `provider` | `ForeignKey(Provider)` | cascade |
| `label` | `CharField(100)` | optional, e.g. *primary* or *backup* |
| `secret` | `TextField` | **Fernet ciphertext**, never the plain key |
| `is_active` | `BooleanField` | inactive keys are skipped |
| `priority` | `PositiveSmallIntegerField` | lower is tried first when a key fails |
| `last_checked_at` / `last_ok` / `last_error` | | filled by **Test connection** |
| `created_at` | `DateTimeField` | automatic |

Several keys per provider are supported. The admin input is a password field
that is never rendered with the stored value; leaving it empty keeps the current
key. The list shows only a mask (`ick_li…3e71`). Encryption uses
`SECRET_ENCRYPTION_KEY`, or `SECRET_KEY` when that variable is empty; if the
secret is rotated, the admin shows *unreadable* instead of returning a corrupted
value, and the key must be entered again.

### `LLMModel`

| Field | Type | Notes |
|---|---|---|
| `provider` | `ForeignKey(Provider)` | which API answers |
| `slug` | `CharField(200)` | provider model id, e.g. `inclusionai/ling-3.2-flash:free` or `Auto` |
| `label` | `CharField(200)` | optional friendly name |
| `is_active` | `BooleanField` | exactly one row across all providers |
| `created_at` | `DateTimeField` | automatic |

A model id is unique per provider, so `Auto` can exist at both. Activating a
model deactivates the previous one in `save()`, and a partial unique constraint
(`only_one_active_model`) makes a second active row impossible even through raw
SQL. `Query.model_name` stores the qualified id (`iteracompute/Auto`) so history
records which provider produced the answer.

When no row is active the pipeline falls back to `OPENROUTER_MODEL` from `.env`,
so the project works before anything is configured. Both paths are resolved in
`rag/llm.py` on every question, so the admin choice applies without a restart.

## Model Management admin (one tab per provider)

| Feature | Behaviour |
|---|---|
| Tabs | one per provider (OpenRouter, Itera Compute, Token Harbor, Orca Router); the changelist opens the tab of the active provider |
| `Answering with:` | banner shows the current model and provider |
| API keys inline | add several keys, set label, active flag and failover priority |
| Models inline | add a model id, tick *is active* to make it answer questions |
| **Find free models** | asks the provider's `/models` endpoint and adds every free model (id ending `:free` or `/free`, or zero prompt and completion price) as an inactive row |
| **Test connection** | sends a one-word prompt through every active key of the provider and stores the result |
| Stored key column | masked; plaintext is never rendered |
| Permissions | providers cannot be added or deleted |

The **Test connection** button is a POST (it costs quota). Results update
`last_checked_at`, `last_ok` and `last_error`, and provider errors are scrubbed
of key material before they are stored.

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
- List columns: id, truncated question, truncated answer, **State**, owner,
  model, created date and **Retry**; filters by status and date; search over
  question and answer. Both the question and the answer cells are links: click
  either one to open the change page and read the full answer — the list only
  shows a one-line preview.
- **State** is the row's current outcome: green *Succeeded*, or red *Failed*
  with the stored reason (no relevant content, language model error, other).
  A retry updates the same row, so the list always shows the latest attempt.
- **Retry** appears only on failed rows. It is a POST button (it costs an LLM
  call), asks the same question again and stores the new answer or the new
  error; the admin shows the result as a message.
- New questions are owned by the admin user who created them; `failure_kind`
  is shown on the detail page for failed questions.

## Choosing the answering provider and model

1. Open **Model Management → OpenRouter** (or another provider tab).
2. Add one or more API keys in the inline table. Priority decides failover
   order; the first working key is used.
3. Add the model id and tick **is active**. The previous active model, at either
   provider, is deactivated automatically.
4. Press **Test connection** to verify every key before asking a real question.

Instead of typing ids, press **Find free models** on a provider tab: the free
models it lists are added (inactive), then tick one and save. Some providers
need extra account steps for free models (Orca Router asks for a linked,
established GitHub account). Otherwise copy ids from the provider: <https://openrouter.ai/models> for
OpenRouter, and `Auto` for Itera Compute (its router chooses a model). Selecting
a model affects metadata (`Query.model_name`) as well as the actual requests, so
history records which provider/model produced each answer.

The key import command copies the initial `.env` keys into the encrypted store
once, for providers that have no keys yet (all four providers have an `*_API_KEY` variable):

```bash
docker compose exec web python manage.py import_env_keys
```

## Why admin only

The brief requires Django Admin as the only UI. Uploading, editing, deleting,
asking and reading history are all available there, so a separate frontend
would add code without adding functionality. The REST API covers programmatic
use and Swagger documents it.
