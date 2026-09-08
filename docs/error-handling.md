# Error Handling

All domain errors inherit from `PiaError` (`src/pia/domain/errors.py`). Each layer catches, wraps, or surfaces errors differently.

## Error Hierarchy

```
PiaError
├── ProductNotFound          # Fuzzy resolve found no match; carries candidate list
├── AmbiguousProduct         # Multiple close matches; carries candidate names
├── CatalogUnavailable       # Catalog source completely down
├── ToolValidationError      # Bad tool arguments (e.g. compare with 1 product)
├── LLMError                 # Groq API failure, missing key, recursion limit
├── PersistenceError         # Supabase/PostgREST failure
└── IngestionError           # Offline crawl errors (never reaches runtime)
    ├── DomainNotAllowed     # URL not on Petbarn allowlist, IP literal, non-HTTPS
    ├── PathNotAllowed       # URL matches deny pattern (bvstate=, /checkout/, etc.)
    └── RobotsDisallowed     # robots.txt blocks the URL
```

## Runtime Agent Errors (what the user sees)

| Error | Where raised | How handled | User-facing result |
|---|---|---|---|
| **ProductNotFound** | `CatalogService.resolve()` | Caught in tool functions → returned as `{"ok": false, "error": "not_found", "candidates": [...]}` | Agent tells user the product wasn't found and suggests candidates |
| **AmbiguousProduct** | `CatalogService.resolve()` | Caught in tool functions → returned as `{"ok": false, "error": "ambiguous", "candidates": [...]}` | Agent asks user to clarify which product they meant |
| **ToolValidationError** | `ComparisonService.compare()` | Caught in `compare_products` tool → `{"ok": false, "error": "..."}` | Agent explains it needs 2–3 products to compare |
| **LLMError (no key)** | `build_model()` in `factory.py` | Caught in `get_stores()` → `agent = None` → `runner = None` | `st.error("The language model is not configured.")` |
| **LLMError (recursion limit)** | `run_query()` on `GraphRecursionError` | Re-raised with user-friendly message → caught in `AgentRunner._execute()` | Agent replies: "I hit my step limit… ask a narrower question." |
| **LLMError (Groq API)** | `run_query()` wraps any `agent.invoke()` exception | Caught in `AgentRunner._execute()` → run marked `failed` | Agent replies: "I could not complete that request. Please try again." |
| **PersistenceError** | Any repository method (Supabase call) | `render_chat()` top-level catch → `st.error(...)` | "Could not load this conversation. Refresh to try again." |
| **PersistenceError (submit)** | `runner.submit()` | Caught in `_submit_prompt()` → `st.error(str(exc))` | Error banner with Supabase error details |
| **Session limit** | `_submit_prompt()` checks `request_count >= max_requests_per_session` | Prevents submit | `st.error("Session request limit reached.")` |
| **Guardrail refusal** | `GuardrailMiddleware.wrap_model_call()` | Returns `AIMessage(content=REFUSAL)` instead of calling model | Agent replies: "I can only help with products, reviews, and comparisons in this catalog." |
| **Tool guardrail** | `GuardrailMiddleware.wrap_tool_call()` | Returns `ToolMessage(content=REFUSAL)` instead of executing tool | Agent sees refusal as tool result; responds accordingly |
| **Output leak** | `GuardrailMiddleware.wrap_model_call()` post-check | Replaces leaked response with `REFUSAL` | Same refusal message; secrets/prompt never reach user |

## Agent Worker Error Flow

```
AgentRunner._execute()
  ├── try: run_query() → persist tools → persist assistant message → run.status = "completed"
  └── except Exception:
        ├── log.exception("agent run failed")
        ├── run.status = "failed", run.error_type, run.error_message (truncated to 300 chars)
        ├── update_run() — persists failure metadata for observability
        └── append_message(role="assistant", content=<user-friendly error>)
              └── if "step limit" in error: show the step-limit message
                  else: "I could not complete that request. Please try again."
```

## Persistence Resilience

| Scenario | Handling |
|---|---|
| **Supabase down at startup** | `create_client()` returns `None` → repositories use in-memory dicts → app works with JSON catalog |
| **Supabase down mid-request** | Repository wraps PostgREST exception → `PersistenceError` → UI shows error banner |
| **Transient connection drops** | `db.py` `retry_call()` retries up to 3× with exponential backoff for `ConnectError`, `PoolTimeout`, `ReadTimeout`, etc. |
| **HTTP/2 issues** | `_RetryTransport` forces HTTP/1.1 to avoid postgrest-py's default HTTP/2 framing issues |
| **Postgres unreachable (catalog)** | `CatalogRepository` catches `PersistenceError` → falls back to `catalog.json` → then `sample_catalog.json` |
| **Stale agent runs** | `fail_stale_runs()` marks runs older than `AGENT_RUN_STALE_SECONDS` (180s) as failed on page load |

## Offline Ingest Errors

| Error | Where raised | How handled |
|---|---|---|
| **DomainNotAllowed** | `check_url_offline()` — non-HTTPS, IP literal, userinfo in URL, unknown domain | Skips URL; logs error; increments `products_failed` |
| **PathNotAllowed** | `check_url_offline()` — URL matches deny pattern | Same skip-and-log pattern |
| **RobotsDisallowed** | `check_robots()` — `robots.txt` blocks the path | Same skip-and-log pattern |
| **IngestionError (HTTP 4xx)** | `UrlFetcher._get()` | Immediately raised (no retry for client errors) |
| **IngestionError (HTTP 5xx)** | `UrlFetcher._get()` | Retried up to `INGEST_MAX_RETRIES` with exponential backoff |
| **IngestionError (redirects)** | `UrlFetcher.fetch()` | Follows up to 5 hops; policy-checks each; raises on loop |
| **IngestionError (Playwright missing)** | `extract_reviews_playwright()` | Raises with install instructions |
| **Quality gate rejection** | `product_from_input()` returns `None` | `RuntimeError("quality gate rejected product")` → skipped |
| **Review branch failure** | Any exception in review extraction | Caught per-SKU; logged; product still saved without reviews |
| **bvstate= in URL** | Review pagination detects bvstate in `page.url` | Pagination aborted immediately; reviews collected so far are kept |
| **One bad SKU** | Any exception during product processing | Logged; error added to `error_summary`; crawl continues; run status = `partial` |
| **All SKUs fail** | `products_ok == 0` | Run status = `failed`; `ingest.py` exits with code 1 |
