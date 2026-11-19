# Security, reliability, and operations

This page is the operator's guide: what must be set before going live, how the
service protects data and LLM quota, and how to check that everything works.

## 1. Production configuration

| Setting | Production value | Why |
|---|---|---|
| `DEBUG` | `False` (default) | never show tracebacks or settings publicly |
| `SECRET_KEY` | long random value | sessions and tokens are signed with it |
| `SECRET_ENCRYPTION_KEY` | separate long random value | encrypts admin-stored provider keys; empty falls back to `SECRET_KEY` |
| `POSTGRES_PASSWORD` | strong, unique, **must be set** | Compose refuses to start without it; there is no literal fallback |
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
  every restart, which would log everyone out and make encrypted keys
  unreadable).
- `config.E002` — `POSTGRES_PASSWORD` is a shipped placeholder or shorter than
  12 characters.

The literal `ragpass` fallback is gone from both `docker-compose.yml` and
`settings.py`. Compose uses `${POSTGRES_PASSWORD:?...}`, and Django raises
`ImproperlyConfigured` when the variable is missing, so a forgotten password
fails at startup rather than silently deploying a known credential.

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

## 7. Provider credentials at rest

Keys added in **Admin → Model Management** are stored as Fernet ciphertext
(`providers/crypto.py`), keyed from `SECRET_ENCRYPTION_KEY` or `SECRET_KEY`.
Properties:

- the plaintext key is never rendered into HTML after saving;
- the list shows only a mask (`ick_li…3e71`);
- leaving the password input empty keeps the existing ciphertext;
- provider error messages are scrubbed of key material before they are stored;
- changing `SECRET_KEY` (with no separate encryption key) makes old rows
  unreadable by design; the admin shows *unreadable* and the key must be
  re-entered.

`.env` keys remain supported as fallbacks and as the source for
`manage.py import_env_keys`, but the database store is what the admin manages.

## 8. Provider URLs, proxy and SSRF

Provider API roots are constants in `providers/constants.py`; the admin cannot
edit them. Only the deployment can override them through
`<PROVIDER>_BASE_URL` (e.g. `ORCAROUTER_BASE_URL`). This blocks an admin from
turning the answering pipeline into a request-forgery primitive.

The proxy is read from `LLM_PROXY` or `LLM_PROXY_SCHEME/HOST/PORT`. Only
`http`, `https`, `socks4`, `socks5` and `socks5h` are accepted; anything else is
rejected with a configuration error. A loopback host is rewritten to
`host.docker.internal` only when `IN_DOCKER=1`, which Compose sets.

## 9. Upload validation

`documents/validators.py` verifies more than the extension:

- the first two bytes are the ZIP signature (`PK`);
- the archive contains `word/document.xml`;
- the declared uncompressed size is at most 20× the upload limit, which rejects
  small ZIP bombs before `python-docx` parses them.

The size limit is still `MAX_DOCUMENT_SIZE_MB`. Rejected files never reach the
extractor or the vector store.

## 10. Audit results

Scans run on the project source (2026-11-19):

| Scan | Result |
|---|---|
| `bandit -r config documents qa rag providers` | 0 findings after one false positive (`0.0.0.0` in the loopback rewrite set) was annotated with `# nosec B104` and a reason |
| `python manage.py check --deploy` with production values | 0 issues |
| `pip-audit -r requirements-base.txt` | DRF advisories fixed by requiring `djangorestframework>=3.18.2` |

Remaining `pip-audit` advisories (26 in 8 libraries at the time of writing) are
in packages whose affected code paths this project does not use. They are
accepted and listed, not hidden:

| Package | Advisory area | Why it does not apply here |
|---|---|---|
| LangChain 0.3.x | filesystem agents, glob/path confinement, prompt loading from untrusted config | no agents, no `load_prompt()` from user input, no filesystem tools |
| langchain-core / langchain-openai | image token counting SSRF | no images or vision models; only text messages are sent |
| langchain-text-splitters | `split_text_from_url()` redirect SSRF | only local plain text is split; no URL splitting |
| ChromaDB | server-mode pre-auth code injection and tenant authorization | used as an embedded `PersistentClient`, no HTTP server or tenants |
| sentence-transformers / transformers | malicious model directory or checkpoint loading | a fixed official model id is downloaded once; no user-supplied checkpoints or local model paths |
| pytest | local `/tmp` directory handling | test tooling only; not reachable from the web app |

Upstream fix versions for several of these are major-version upgrades
(LangChain 1.x, transformers 5.x). Upgrading them without an integration pass
would risk breaking the RAG stack, so they are tracked as dependency-upgrade
work rather than silently forced. Re-run `pip-audit` before the next release.

Two accepted application-level risks are documented rather than silently
ignored:

- any authenticated API user can manage documents (the brief does not define
  roles beyond authentication); put the API behind a trusted network or add
  per-object permissions if that changes;
- the development image runs as root and uses Django's development server, as
  the brief requires `docker compose up`; use a non-root user and a WSGI server
  for an internet-facing deployment.

## 11. GitGuardian: the Postgres password finding

The reported line was:

```yaml
POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-ragpass}
```

`.env` did supply the real password, and Compose prefers it, so the running
container was not using `ragpass`. The problem is the **inline default itself**:
a scanner sees a literal credential committed to Git, and anyone who starts the
stack without `.env` (CI, a fresh clone, a forgotten variable) silently gets
that known password. "It is only a fallback" is not a security boundary.

The fix removes the literal from every layer:

- `docker-compose.yml` uses `${POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}`,
  so Compose stops with an explanatory error;
- `config/settings.py` raises `ImproperlyConfigured` when the variable is
  missing;
- `.env.example` contains `change-me-strong-password`, an obvious placeholder;
- `.env` stays git-ignored, so the real value is never committed.

## 12. Dependencies

- `requirements-base.txt` — Django, DRF, LangChain, Chroma, document tooling.
- `requirements.txt` — base plus the local test/lint tools.
- `requirements-docker.txt` — base plus the CPU-only embedding runtime.

The Docker image installs the base and Docker files, keeping PyTorch CPU-only
and avoiding a second multi-gigabyte CUDA download.

## 13. Verification checklist

```bash
# apply migrations (providers, encrypted keys, model split)
docker compose exec web python manage.py migrate

# import existing .env keys once (admin store)
docker compose exec web python manage.py import_env_keys

# 115 offline tests, PostgreSQL, fake embeddings and mocked LLM
docker compose exec web pytest

# production configuration
docker compose exec web python manage.py check --deploy

# live smoke test (needs a DRF token)
E2E_TOKEN=<token> .venv/Scripts/python.exe scripts/e2e_check.py
```

The e2e script needs a working selected provider key; free models can return
`503` when their shared quota is exhausted. That is an external limit, not an
application failure — the query is still stored with `status=error`.

### Credential rotation

If a key is pasted into chat, a ticket, or a log, treat it as compromised:
create a new key at the provider, add it in **Model Management**, press **Test
connection**, then deactivate and delete the old key. Rotating the `.env`
fallback follows the same rule: update `.env`, recreate the container, and run
`import_env_keys` only for providers that have no admin keys yet.

## Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| `config.E001` on start | no `SECRET_KEY` | set a long random value |
| `config.E002` on start | `POSTGRES_PASSWORD` is a placeholder or too short | set a unique password of at least 12 characters |
| Compose says `Set POSTGRES_PASSWORD in .env` | missing variable | add it to `.env`; there is no default |
| stored key shows *unreadable* | `SECRET_KEY`/`SECRET_ENCRYPTION_KEY` changed | re-enter the key in Model Management |
| `has no usable API key` | provider has no active key and no `.env` fallback | add a key in Model Management or run `import_env_keys` |
| admin login loops over HTTP | secure cookies + redirect | terminate HTTPS at the proxy or set `SECURE_SSL_REDIRECT=False` |
| `429` on every ask | rate limit too low for a shared account | raise `ASK_THROTTLE_RATE` |
| valid question returns `404` | threshold too high | lower `RETRIEVAL_MIN_SCORE` and compare source scores |
| delete returns `503` | Chroma unavailable or locked | retry after the index is reachable; the document is untouched |
| upload indexed `0` chunks | empty or unreadable `.docx` | inspect `processing_error` in admin and re-upload |
