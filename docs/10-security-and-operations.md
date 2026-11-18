# Security, reliability, and operations

This page is the operator's guide: what must be set before going live, how the
service protects data and LLM quota, and how to check that everything works.

## 1. Production configuration

| Setting | Production value | Why |
|---|---|---|
| `DEBUG` | `False` (default) | never show tracebacks or settings publicly |
| `SECRET_KEY` | long random value | sessions and tokens are signed with it |
| `POSTGRES_PASSWORD` | strong, unique | the default `ragpass` is rejected by a deploy check |
| `ALLOWED_HOSTS` | your domain(s) | blocks Host-header spoofing |
| `CSRF_TRUSTED_ORIGINS` | `https://your-domain` | lets the admin login form work behind HTTPS |
| `SECURE_PROXY_SSL_HEADER` | `True` only behind a trusted proxy | tells Django the request was HTTPS |

Generate a secret and put it in the server's environment (never in Git):

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

When `DEBUG=False`, the project automatically enables:

- HTTP → HTTPS redirect,
- secure and HttpOnly session/CSRF cookies,
- HSTS for one year, including subdomains and preload,
- `X-Content-Type-Options: nosniff` and a referrer policy.

If the app is reached over plain HTTP inside a private network, set
`SECURE_SSL_REDIRECT=False` explicitly; otherwise browsers will loop.

### Deploy checks

`config/checks.py` adds two errors:

- `config.E001` — no `SECRET_KEY` was provided (the ephemeral key changes on
  every restart, which would log everyone out).
- `config.E002` — `POSTGRES_PASSWORD` is still the development default.

Run the full check with real production values:

```bash
docker compose exec web python manage.py check --deploy
```

A correct production environment prints `System check identified no issues`.
Warnings about HTTPS appear if you run this locally with `DEBUG=True`; that is
expected and is exactly what the command is for.

## 2. Ask rate limiting

`/api/ask/` is throttled per authenticated user:

```text
ASK_THROTTLE_RATE=20/min
```

Exceeding it returns `429 Too Many Requests` with a `Retry-After`-style wait in
the response. Admin users are throttled the same way, because the cost is the
OpenRouter call, not the caller's role. Set the value to an empty string to
disable the limit.

The counter lives in Django's cache. The default local-memory cache is per
process, so with several web workers each worker counts separately. A shared
cache (for example Redis) would be needed for a strict global limit; this
project intentionally avoids that extra service for a single-container setup.

## 3. Private history

Every `Query` optionally belongs to the user who asked it:

- `GET /api/history/` returns only the caller's rows;
- `GET /api/history/<id>/` returns `404` for another user's row;
- Django admin still shows all rows, so support can investigate failures;
- rows created before the migration, or from the `ask` command / admin, have
  no owner and are therefore not visible through the API.

The question, answer, sources, model name, status, failure kind and timestamp
are stored. Unexpected server errors are stored as `failure_kind=other`; the
exception itself goes to the logs, not to the database or the client.

## 4. Relevance threshold

`RETRIEVAL_MIN_SCORE=0.2` drops chunks whose cosine similarity to the question
is below the threshold. The effects:

- an off-topic question retrieves nothing and `/api/ask/` returns `404`;
- weakly related chunks no longer tempt the model into an unsupported answer;
- `0` disables the filter and restores the old behaviour.

Tune it with a small labelled set of real questions. Raise it if answers quote
irrelevant text; lower it if valid questions are rejected. Scores are always
attached to sources, so you can inspect the values in a response before
changing the setting.

## 5. Deletion, vectors, and files

Deleting a document is all-or-nothing:

1. the API/admin asks Chroma to remove the document's chunks;
2. if Chroma fails, the request returns `503` and the database row stays;
3. only after the index is clean is the row (and its file) removed.

This prevents orphan vectors that would keep answering questions with no
document to inspect. Admin bulk deletion applies the same rule per document;
documents whose index cleanup fails remain and are reported as errors.

Replacing a file deletes the old chunks and the old media file. Re-indexing is
idempotent because chunks use deterministic ids and the document's previous
chunks are removed first. File cleanup is implemented with model signals, so
it also runs for admin bulk deletes and test teardown.

## 6. Health and errors

`GET /api/health/` returns only:

```json
{"status": "ok"}
```

It deliberately does not reveal the model, database or index state. A client
should treat any non-200 response as "not ready".

API clients receive short, safe messages. LLM, embedding, parsing and
unexpected failures are logged with full detail server-side. This keeps stack
traces and provider responses out of public JSON without making debugging
harder.

## 7. Dependencies

- `requirements-base.txt` — Django, DRF, LangChain, Chroma, document tooling.
- `requirements.txt` — base plus the local test/lint tools.
- `requirements-docker.txt` — base plus the CPU-only embedding runtime.

The Docker image installs the base and Docker files, keeping PyTorch CPU-only
and avoiding a second multi-gigabyte CUDA download.

## 8. Verification checklist

```bash
# apply migrations (adds query owner and failure kind)
docker compose exec web python manage.py migrate

# 74 offline tests, PostgreSQL, fake embeddings and mocked LLM
docker compose exec web pytest

# production configuration
docker compose exec web python manage.py check --deploy

# live smoke test (needs a DRF token)
E2E_TOKEN=<token> .venv/Scripts/python.exe scripts/e2e_check.py
```

The e2e script needs a working `OPENROUTER_API_KEY`; free models can return
`503` when their shared quota is exhausted. That is an external limit, not an
application failure — the query is still stored with `status=error`.

## Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| `config.E001` on start | no `SECRET_KEY` | set a long random value |
| `config.E002` on start | default DB password | set `POSTGRES_PASSWORD` |
| admin login loops over HTTP | secure cookies + redirect | terminate HTTPS at the proxy or set `SECURE_SSL_REDIRECT=False` |
| `429` on every ask | rate limit too low for a shared account | raise `ASK_THROTTLE_RATE` |
| valid question returns `404` | threshold too high | lower `RETRIEVAL_MIN_SCORE` and compare source scores |
| delete returns `503` | Chroma unavailable or locked | retry after the index is reachable; the document is untouched |
| upload indexed `0` chunks | empty or unreadable `.docx` | inspect `processing_error` in admin and re-upload |
