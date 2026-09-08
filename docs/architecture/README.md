# Architecture diagrams

Interactive Archify HTML maps for the two isolated PIA surfaces. Open the HTML files in a browser (no server required).

| Diagram | Type | Open |
|---------|------|------|
| Offline ingestion pipeline | dataflow | [ingestion-pipeline.html](ingestion-pipeline.html) |
| Agent runtime (no REST API) | architecture | [agent-runtime.html](agent-runtime.html) |

JSON IR used to compile each artifact sits beside the HTML (`*.ir.json`). Install [Archify](https://github.com/tt-a1i/archify) then re-render:

```powershell
node path/to/archify/bin/archify.mjs deliver dataflow docs/architecture/ingestion-pipeline.ir.json docs/architecture/ingestion-pipeline.html --quality showcase
node path/to/archify/bin/archify.mjs deliver architecture docs/architecture/agent-runtime.ir.json docs/architecture/agent-runtime.html --quality showcase
```

## Ingestion pipeline

Covers `scripts/ingest.py` → `IngestService`: seeds and Petbarn sitemap discovery, URL policy, UrlFetcher, JSON-LD parse, Playwright Bazaarvoice reviews, quality + VADER, then dual persist through `CrawlRepository` (Supabase Postgres + compact `catalog.json`).

Not on this diagram: Groq, Streamlit, LangChain, eval/CI.

## Agent runtime

Covers the hosted chat path: Streamlit → `AgentRunner` (thread pool) → `run_query` / `create_agent` → Groq, with Guardrail + LoopGuard + call limits, four catalog tools wrapping Catalog/Comparison services, and catalog fallback Postgres → `catalog.json` → `sample_catalog.json`. Chat timeline and telemetry write to `chats`, `chat_messages`, `agent_runs`, and `tool_calls`.

Not on this diagram: Petbarn HTTP, Playwright, FastAPI/SSE, eval harnesses.
