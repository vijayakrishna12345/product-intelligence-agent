# Architecture diagrams

Interactive Archify HTML maps for PIA. Open the HTML files in a browser (no server required).

| Diagram | Type | Open |
|---------|------|------|
| Offline ingestion pipeline | dataflow | [ingestion-pipeline.html](ingestion-pipeline.html) |
| Agent runtime (HLD) | architecture | [agent-runtime.html](agent-runtime.html) |
| Agent runtime (LLD) | architecture | [agent-runtime-lld.html](agent-runtime-lld.html) |
| Evaluation harness | architecture | [evaluation.html](evaluation.html) |

JSON IR used to compile each artifact sits beside the HTML (`*.ir.json`). Install [Archify](https://github.com/tt-a1i/archify) then re-render:

```powershell
$archify = ".agents/skills/archify"
$docs = "docs/architecture"
node $archify/bin/archify.mjs deliver dataflow $docs/ingestion-pipeline.ir.json $docs/ingestion-pipeline.html --quality showcase
node $archify/bin/archify.mjs deliver architecture $docs/agent-runtime.ir.json $docs/agent-runtime.html --quality showcase
node $archify/bin/archify.mjs deliver architecture $docs/agent-runtime-lld.ir.json $docs/agent-runtime-lld.html --quality showcase
node $archify/bin/archify.mjs deliver architecture $docs/evaluation.ir.json $docs/evaluation.html --quality showcase
```

PNG previews are exported from `visual-check` sidecars (`*.visual-check.2048x1320.light.png` → `*.png`).

## Previews

### Ingestion pipeline

![Offline ingestion pipeline](ingestion-pipeline.png)

### Agent runtime (HLD)

![Agent runtime architecture](agent-runtime.png)

### Agent runtime (LLD)

![Agent runtime LLD](agent-runtime-lld.png)

### Evaluation harness

![Evaluation harness](evaluation.png)

## Ingestion pipeline

Covers `scripts/ingest.py` → `IngestService`: seeds and Petbarn sitemap discovery, URL policy, UrlFetcher, JSON-LD parse, Playwright Bazaarvoice reviews, quality + VADER, then dual persist through `CrawlRepository` (Supabase Postgres + compact `catalog.json`).

Not on this diagram: Groq, Streamlit, LangChain, eval/CI.

## Agent runtime (HLD)

Covers the hosted chat path: Streamlit → `AgentRunner` (thread pool) → `run_query` / `create_agent` → Groq, with Guardrail + LoopGuard + call limits, four catalog tools wrapping Catalog/Comparison services, and catalog fallback Postgres → `catalog.json` → `sample_catalog.json`. Chat timeline and telemetry write to `chats`, `chat_messages`, `agent_runs`, and `tool_calls`.

Not on this diagram: Petbarn HTTP, Playwright, eval harnesses.

## Agent runtime (LLD)

Zooms into `build_context` → `AgentRunner` → `create_agent`: static `SYSTEM_PROMPT` for Groq prompt caching, middleware chain (Guardrail → LoopGuard → call limits 15/6), `_clip` on untrusted tool output, and `CatalogService` / `CompareService` behind the four tools.

## Evaluation harness

Covers `scripts/check_ready.py` (release gate with `pytest -m release` and `difficult_goldens.json`), single-turn eval (`pytest -m eval`, `goldens.json`, `GroqJudge`), and gitignored result files (`difficult_latest.json`, `latest.json`).
