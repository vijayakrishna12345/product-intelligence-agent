# Database Schema

Supabase Postgres with 8 tables. Migration: `supabase/migrations/20260907_init.sql`.

## Tables

| Table | Purpose |
|---|---|
| `products` | Ingested product metadata (SKU is PK) |
| `product_reviews` | Individual reviews with sentiment labels |
| `crawl_runs` | Ingest run status, counts, errors |
| `crawl_pages` | Per-URL fetch record with content hash |
| `chats` | Conversation metadata with titles |
| `chat_messages` | Ordered message timeline (user/assistant/tool) |
| `agent_runs` | Per-turn status, token counts, latency |
| `tool_calls` | Tool name, arguments, result JSON, timing |

## Security

All tables have RLS enabled with `deny_anon` and `deny_authenticated` policies (service-role only access). No client-facing API key can read or write data directly.

## Key Constraints

- `products.sku` — primary key, matches ingested SKU strings.
- `product_reviews` — foreign key to `products.sku`, unique on `(sku, review_identity_hash)`.
- `chat_messages.seq` — allocated via `next_chat_seq()` function for strict ordering.
- `agent_runs` — foreign key to `chats.id`, stores token counts and timing as numeric columns.
- `tool_calls` — foreign key to `agent_runs.id`, stores tool name, arguments JSON, result JSON, and duration.
- `crawl_pages.content_hash` — SHA-256 of raw HTML for incremental ingestion (skip unchanged pages).

## Telemetry Columns

Usage telemetry is stored on `agent_runs` and `tool_calls` as numeric columns (prompt/completion tokens, latency, cache hit counts). These are never joined back into agent prompts or tool-choice logic.
