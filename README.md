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

### Cleaning (`make etl`)

The rules live in [`cleaning.py`](src/pedidos/cleaning.py) as pure functions, each one tested on
its own. They run in this order: normalize text → parse → validate → deduplicate.

- **Dates:** only formats from an explicit list are accepted. Ambiguous dates (`03/04/2025`) are
  read as day/month, the convention in every country we sell to. Impossible dates (February 30th)
  and garbage (`N/A`, `ayer`) are rejected.
- **Amounts:** a decimal comma is accepted and the value is rounded to cents. Empty, non-numeric
  or non-positive amounts are rejected. **They are not imputed:** inventing sales is worse than
  leaving them out.
- **Text:** extra spaces are removed, and countries and statuses are mapped to their canonical
  value (`ES`, ` ESPAÑA`, `Espana` → `España`). An unknown country is rejected, not guessed.
- **Duplicates:** detected by `pedido_id` after normalizing, so reformatted duplicates are caught
  too. The first valid row is kept, and the report flags it if two copies have different data.
  There is no deduplication by business key: a customer can buy the same product twice on the
  same day.
- **Rejected rows** are saved with their reason in `data/processed/rechazados.csv`, **outside the
  database**: the database the API reads only contains valid data.
- **The load is idempotent and atomic:** the database is built in a temporary file that replaces
  the previous one, so the ETL can be rerun and nobody ever sees a half-finished load. The schema
  ([`schema.sql`](src/pedidos/sql/schema.sql)) uses `STRICT` tables and `CHECK` constraints as the
  last barrier.

Result with the generated data:

```text
Rows read:                 1236
Orders loaded:             1141
Duplicates removed:          35
Rows rejected:               60
  fecha_invalida             24
  importe_vacio              37
Fields fixed in loaded rows:
  cliente                     6
  estado                     44
  fecha                      57
  importe                    48
  pais                       70
```

`loaded + rejected + duplicates = read` holds. One row has two rejection reasons, so the reasons
add up to 61. There are 35 duplicates removed rather than 36 because, in one case, both copies had
errors and both were rejected.

### Models (SQL views)

They live in [`views.sql`](src/pedidos/sql/views.sql), and the ETL creates them on every load.

- **`ventas_mes_pais(mes, pais, num_pedidos, ventas)`**, with `mes` formatted as `YYYY-MM`.
- **`top_clientes(cliente, num_pedidos, total_comprado)`**: the 10 customers with the highest total
  spent. The tie-break on the name makes the result deterministic.
- **Business decision: a sale is a `completado` (completed) order.** Cancelled, returned and
  pending orders do not count. The rule lives in the views, which act as a semantic layer: the LLM
  uses them to talk about sales and never has to decide what counts as one.
- Amounts are in euros (assumption: a single currency), rounded to 2 decimals in the views because
  SQLite has no `DECIMAL` type.

### Safety of the generated SQL

The SQL returned by the LLM is treated as untrusted input, just like anything a user types. There
are two independent layers, and either one is enough to block a dangerous query:

1. **Validator** ([`sql_guard.py`](src/pedidos/sql_guard.py)): inspects the syntax tree with
   sqlglot. The query has to meet all of these:
   - a single `SELECT` statement (or `UNION` / `WITH … SELECT`), with no writes or DDL;
   - it only reads `pedidos`, `ventas_mes_pais` and `top_clientes`, including inside CTEs,
     subqueries and joins;
   - no table functions in `FROM`, no recursive CTEs and no dangerous functions such as
     `load_extension`.

   A regex would not be enough: it can be dodged with comments or functions, and it would block
   harmless columns such as `deleted_at`.
2. **Database** ([`db.py`](src/pedidos/db.py)): the API opens SQLite read-only (`mode=ro`) with an
   *authorizer*. The engine itself denies anything other than `SELECT`, reading the allowed tables
   or calling harmless functions. So even if sqlglot and SQLite read a query differently, no door
   opens.

On top of that, every query has a time limit (a *progress handler* cancels it), a cap on the
returned rows (the response says whether it was truncated) and a size limit per value.

The database tests ([`test_db.py`](tests/test_db.py)) send dangerous SQL straight to the
connection, skipping the validator, to prove that the second layer works on its own.

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
| Data, cleaning and views | The generator with errors, the cleaning, the load and the views, with their tests | The cleaning rules and the definition of a sale (a completed order) | _To be completed after reviewing the code_ |
| SQL validation | Writing the attack tests first, then the validator and the locked-down connection | The two-layer validation | The tests caught two bugs in the first version (how `COUNT(*)` and denied functions reach SQLite's authorizer); they were fixed before the commit |

## Time spent

_Pending._
