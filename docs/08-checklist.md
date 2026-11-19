# Requirements checklist

Mapping of every requirement in the brief to where it is implemented and
verified.

| # | Requirement | Implementation | Verified by |
|---|---|---|---|
| 1 | Django is mandatory | Django 5.2 project `config`, apps `documents`, `qa`, `providers` | `docker compose up`, all tests |
| 2 | Must run with Docker Compose | `Dockerfile`, `docker-compose.yml`, `entrypoint.sh` | manual `docker compose up` |
| 3 | LangChain for processing and LLM | `rag/ingest.py`, `rag/retrieval.py`, `rag/chain.py`, `rag/llm.py` | `tests/rag/*` |
| 4 | Complete, usable REST API | DRF viewsets + `POST /api/ask/` + history | `tests/api/*` |
| 5 | UI is Django Admin only | No frontend; admin for documents, queries and Model Management | `tests/documents/test_admin.py`, `tests/qa/test_admin.py`, `tests/providers/test_admin.py` |
| 6 | Add / edit / delete documents | Admin + `DocumentViewSet` | `test_admin.py`, `test_documents.py` |
| 7 | Support `.docx` | `documents/validators.py` (ZIP + Word check), `rag/extract.py` | `test_models.py`, `test_extract.py` |
| 8 | Store full text | `Document.full_text` filled by `process_document` | `test_admin_upload_extracts_and_indexes` |
| 9 | Submit a question | Admin add-query, `POST /api/ask/`, `manage.py ask` | `test_ask.py`, `test_admin.py`, `test_ask_command.py` |
| 10 | Find relevant content | `rag/retrieval.py` (MMR) | `test_retrieval.py` |
| 11 | Advanced retrieval for accurate answers | MultiQueryRetriever + MMR + de-duplication + scores + relevance floor | `test_retrieve_merges_multi_query_without_duplicates`, `test_retrieve_drops_chunks_below_the_relevance_threshold` |
| 12 | Generate a grounded text answer | `rag/chain.py` prompt + selected provider | `test_chain.py`, live test |
| 13 | Store question/answer history | `qa.Query`, `qa/services.py` | `test_services.py`, `test_history.py` |
| 14 | Free OpenRouter model | `OPENROUTER_MODEL=...:free` env, `rag/llm.py` | live test (optional) |
| 15 | API documentation | drf-spectacular, `/api/docs/`, `docs/openapi.yaml` | manual |
| 16 | Config via env, no hardcoded keys | `config/settings.py`, `.env.example`, `.gitignore`; encrypted admin keys | review, `test_api_keys_are_encrypted_at_rest` |
| 17 | Simplicity / explainability | Service layer, small functions, comments | `docs/07-decisions.md` |
| 18 | Private history per user | API filters `Query` by owner; admin sees all | `test_history_is_private_to_its_owner` |
| 19 | Protect the LLM quota | per-user DRF throttle + `LLM_MAX_RETRIES` + key failover | `test_ask_is_rate_limited_per_user`, `test_failover_tries_the_next_key_for_a_retryable_error` |
| 20 | Production-safe deployment | secure defaults, `config/checks.py`, `check --deploy` | manual deployment check (0 issues) |
| 21 | No orphan vectors or files | delete stops on Chroma failure; media cleanup signals | `test_delete_is_blocked_when_the_index_cannot_be_updated`, file cleanup tests |
| 22 | Do not leak internals | generic API errors, full details in logs | `test_ask_hides_unexpected_error_details`, `test_upload_hides_processing_error_details` |
| 23 | Separate Model Management section | `providers` app, `verbose_name = "Model Management"`, tabbed change form | `test_model_management_is_a_separate_admin_section`, `test_both_providers_are_tabs` |
| 24 | Only the four supported providers | fixed `Provider` rows + constants; no add/delete in admin | `test_a_model_id_is_unique_per_provider`, `test_providers_cannot_be_added_or_deleted` |
| 25 | Multiple keys per provider, selectable model | `APIKey` inline, priority failover, exclusive active `LLMModel` | `tests/providers/*`, `test_activate_*` |
| 26 | Minimum request failures | SDK retries + key rotation on retryable errors, probe timeout capped at 60 s | `test_failover_*` |
| 27 | Changeable proxy in `.env` | `LLM_PROXY` or scheme/host/port; loopback rewrite in Docker | `test_proxy_*` |
| 28 | No secrets in the compose file | required `${POSTGRES_PASSWORD:?}` substitution, no literal fallback | review, `git check-ignore .env` |

## Prompt-by-prompt deliverables

| Prompt | What was built | Doc |
|---|---|---|
| 1. Skeleton + Docker | `config/`, `documents/`, `qa/`, `rag/`, compose, entrypoint, env | `docs/02-setup-and-config.md` |
| 2. Document model + admin | `Document`, validator, admin, hook `process_document()` | `docs/03-data-model-and-admin.md` |
| 3. Ingestion | `extract.py`, `vectorstore.py`, `ingest.py`, admin actions | `docs/04-rag-pipeline.md` |
| 4. Retrieval | `retrieval.py` MMR + multi-query + fallback + scores | `docs/04-rag-pipeline.md` |
| 5. Answer generation | `chain.py`, prompt rules, error handling, `ask` command | `docs/04-rag-pipeline.md` |
| 6. History | `Query` model + admin (immutable, sources view) | `docs/03-data-model-and-admin.md` |
| 7. REST API | serializers, viewsets, token/session auth, Swagger, tests | `docs/05-api.md` |
| 8. Deliverables | README, `docs/`, `sample_data/`, checklist, presentation | `docs/` |
| 9. Model Management + providers | `providers/` app, tabbed admin, encrypted keys, failover, proxy settings | `docs/02`, `docs/03`, `docs/10` |

## Testing rules

| Rule | Where |
|---|---|
| Docs in top-level `docs/` | `docs/` |
| Tests in top-level `tests/` by app | `tests/documents`, `tests/rag`, `tests/qa`, `tests/api` |
| Deterministic + offline | fake embeddings + mocked LLM in `tests/conftest.py` |
| Real-LLM test separate + `live` | `tests/rag/test_live_llm.py` |
| One-line docstring per test | every test |
| `pytest.ini` + runnable in Docker | `pytest.ini`, `docker compose run --rm web pytest` |
