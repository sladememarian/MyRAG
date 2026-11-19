# Testing

## Run

```bash
docker compose run --rm web pytest            # default: everything except live
docker compose run --rm web pytest -v         # verbose
docker compose run --rm web pytest tests/rag  # one folder
docker compose run --rm web pytest -m live    # real provider call (uses quota)
```

`pytest.ini` sets `DJANGO_SETTINGS_MODULE=config.settings`,
`testpaths=tests` and `-m "not live"`.

## End-to-end check against the running app

`scripts/e2e_check.py` exercises the real HTTP API: it uploads two generated
AI-company `.docx` files, asks human-style questions, edits a title and replaces
a file, checks history, and deletes the documents (verifying they disappear
from retrieval sources). It uses the app's real embeddings and real LLM, so it
is not part of pytest.

```bash
# stack running, plus a token for a staff/superuser account
docker compose exec web python manage.py drf_create_token <user>
E2E_TOKEN=<token> python scripts/e2e_check.py

# or from inside the container
E2E_TOKEN=<token> docker compose exec -T web python scripts/e2e_check.py
```

Set `E2E_BASE_URL` for another host and `E2E_KEEP=1` to leave the test
documents in place. It exits non-zero if any check fails.

The check makes only five LLM calls (two facts, one edited fact, one
ungrounded question, one post-delete question) so it is cheap on free quotas.
Set `RETRIEVAL_USE_MULTI_QUERY=False` on the server to avoid the extra
query-rewrite calls. Without the local `sentence-transformers` package, start
the server with `EMBEDDING_BACKEND=fake RETRIEVAL_MIN_SCORE=0`.

## Why the tests are offline and deterministic

`tests/conftest.py` applies an autouse fixture to every test:

| Piece | Test setting |
|---|---|
| Embeddings | `EMBEDDING_BACKEND=fake` (`DeterministicFakeEmbedding`) |
| Vector store | temporary directory + unique collection per test |
| Media files | temporary `MEDIA_ROOT` |
| LLM | monkeypatched with `FakeListChatModel` or `BrokenLLM` |
| Multi-query | disabled by default; enabled explicitly where tested |
| Relevance | `RETRIEVAL_MIN_SCORE=0.0`; a test raises it explicitly |
| Throttle counters | cleared before and after every test |

No network, no model download, no shared state between tests.

## Layout

```
tests/
  conftest.py               fixtures: docx factory, indexed document, fake LLM
  documents/
    test_models.py          fields, validators, replaced/deleted file cleanup
    test_admin.py           admin upload, delete (including blocked delete), re-index
  rag/
    test_extract.py         paragraphs + tables in order, bidi cleaning, errors
    test_ingest.py          chunking, metadata, idempotent re-index, deletion
    test_retrieval.py       scores, multi-query merge, fallback, score threshold
    test_chain.py           grounded answer, sources, no-docs, 429, empty answer
    test_live_llm.py        @pytest.mark.live, skipped by default
  qa/
    test_models.py          Query defaults, history string
    test_services.py        success, ownership, no-content, LLM/safe unexpected errors
    test_admin.py           question answering in admin, ownership, immutability
    test_ask_command.py     management command output + errors
  providers/
    test_models.py          provider seed, encryption, masks, exclusive active model
    test_admin.py           tabs, inline keys/models, masking, test-connection button
    test_import_env_keys.py one-time .env key import, no overwrite
  api/
    test_documents.py       auth, upload, safe errors, update, blocked delete
    test_ask.py             answer + history, 404, 503, validation, throttling
    test_history.py         pagination, ownership, token auth, health
```

Every test has a one-line docstring naming the brief requirement it verifies.

**Last run:** `115 passed, 1 deselected` (the `live` test) in ~84 s locally
with SQLite. Inside the Docker image with PostgreSQL the same suite runs without
extra setup. To run locally, set `DB_ENGINE=sqlite` before pytest; Docker uses
PostgreSQL through the same settings. `pytest -m live` calls the real selected
provider (OpenRouter by default).

## Live test

`tests/rag/test_live_llm.py` uses the real selected model (OpenRouter by default)
and the real `answer_question()` flow (embeddings stay fake for speed). It is
skipped unless you pass `-m live` and the configured provider has a key. Free
models have a daily cap, so it is deliberately excluded from normal runs.

## What is not covered

- Browser JavaScript behaviour (the admin is Django's own UI).
- Real sentence-transformers quality (it is a local model; asserting semantic
  quality would make tests slow and non-deterministic).
- Concurrency (indexing is synchronous by design).
