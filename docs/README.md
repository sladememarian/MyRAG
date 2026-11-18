# Documentation index

Read in this order:

| File | What it covers |
|---|---|
| [01-architecture.md](01-architecture.md) | containers, volumes, request and indexing flows |
| [02-setup-and-config.md](02-setup-and-config.md) | Docker setup, every env variable, proxy, troubleshooting |
| [03-data-model-and-admin.md](03-data-model-and-admin.md) | `Document`, `Query`, admin features, immutability |
| [04-rag-pipeline.md](04-rag-pipeline.md) | extraction, chunking, embeddings, retrieval, prompting |
| [05-api.md](05-api.md) | endpoints, auth, curl examples, errors, schema export |
| [06-testing.md](06-testing.md) | how to run tests, fixtures, what is mocked |
| [07-decisions.md](07-decisions.md) | why each design choice was made (presentation prep) |
| [08-checklist.md](08-checklist.md) | brief requirement → implementation mapping |
| [09-presentation.md](09-presentation.md) | 10-minute demo and talk outline |
| [10-security-and-operations.md](10-security-and-operations.md) | production settings, throttling, privacy, deletion, verification |
| [openapi.yaml](openapi.yaml) | exported OpenAPI 3 schema |

External quick links (when running locally):

- Admin: <http://localhost:8000/admin/>
- Swagger UI: <http://localhost:8000/api/docs/>
- OpenAPI schema: <http://localhost:8000/api/schema/>
- Health: <http://localhost:8000/api/health/>
