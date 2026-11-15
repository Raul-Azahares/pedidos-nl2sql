# pedidos-nl2sql

Natural-language questions about order data. An LLM translates the question into SQL, the SQL is
**validated** before it runs (read-only, allowed tables only), and the result is returned by a
FastAPI API.

> Technical test in progress: this README is completed as the project moves forward.

## How to run it

_Pending._

## Architecture

_Pending._

## Decisions

### Environment and dependencies

- **Environment: Python 3.12 + uv.** `uv sync` installs exactly the versions pinned in `uv.lock`,
  so a reviewer gets the same environment with a single command.
- **Database: SQLite.** It ships with Python, so it adds no dependencies or infrastructure for the
  reviewer. It also allows a strong guarantee in the API: the connection is read-only (`mode=ro`)
  and an *authorizer* makes the engine itself reject anything other than reading the allowed
  tables, even if the validator failed. With a few thousand rows, performance doesn't matter. The
  downside: there are no `DATE` or `DECIMAL` types. Dates are stored as ISO text with a `CHECK`,
  and amounts as `REAL`, rounded in the views. In production I would use PostgreSQL with a
  read-only role.
- **LLM: Gemini, Google AI Studio free tier.** It is free and needs no credit card, which is enough
  for a test. In exchange, Google may use the request content to improve its products. That is
  acceptable here because the data is synthetic and the model only receives the schema, never
  customer rows. In production I would use the paid tier or Vertex AI. The provider sits behind an
  interface, so switching to another LLM means writing another implementation without touching the
  rest.
- **Gemini is called over HTTP with httpx, without the official SDK.** `google-genai` pulls in
  `google-auth` and `cryptography`, about 5 MB of native binaries, for what is a single POST
  request. With httpx I control timeouts and errors directly, and the tests simulate it without
  network access.
- **Minimal dependencies.** Six direct dependencies, none with heavy binaries. When I started, my
  connection to PyPI ran at ~10 KB/s, and DuckDB + pandas + numpy (~50 MB) were not viable.
- **Language.** Code, comments, commits and docs are in English. The data (column names,
  countries, statuses) and the messages returned by the API are in Spanish, because the business
  and the questions are in Spanish.

### Data

- **Deterministic test data.** `make data` generates 1,200 orders from 2024 and 2025 with a fixed
  seed, so the CSV is always the same and the tests can reproduce it. A few customers concentrate
  many purchases (weight 1/√rank), so the top 10 is meaningful.
- **A `pedido_id` column is added.** Without an identifier, duplicates cannot be detected reliably.
- **Errors injected on purpose:** 3% duplicates (half of them reformatted), 5% dates in other
  formats, 2% impossible or garbage dates, 3% empty amounts, 4% amounts with a decimal comma, and
  countries and statuses written in several ways.
- **The CSV is versioned** (`data/raw/pedidos.csv`, 1,236 rows) so the errors can be inspected
  without running anything.

## Known limitations

_Pending._

## What I would do with more time

_Pending._

## How I used AI

Tools: **Claude Code** (Claude Opus 5.5) as a coding assistant, and **Gemini** as the LLM the API
uses at runtime.

| Phase | What I asked for | What I accepted | What I corrected or decided |
|---|---|---|---|
| Plan | A plan to complete the test in 3 hours at most | The architecture (layered SQL validation), the phases and the commit order | Switching the LLM from Claude to Gemini (free tier), because I don't have an Anthropic key |
| Environment | Installing the planned dependencies (DuckDB + pandas) | Its diagnosis: PyPI ran at ~10 KB/s and those libraries weigh ~50 MB | I chose SQLite + the standard library instead of DuckDB + pandas: nothing to download, and the engine can enforce the allowed-table list |
| Environment | Installing the Gemini SDK (`google-genai`) | The download of `cryptography` (4.5 MB, an SDK dependency) failed 9 times; it proposed calling the REST API with httpx | Accepted: one POST request doesn't justify 5 MB of native dependencies |
| Docs | Commit messages, this README and code comments | Their content | It wrote them in Spanish; I switched them to English (the data stays in Spanish) |

## Time spent

_Pending._
