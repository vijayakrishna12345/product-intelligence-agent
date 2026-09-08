# Project Structure

```
product-intelligence-agent/
├── streamlit_app.py              # Entrypoint: st.navigation across 4 pages
├── pyproject.toml                # uv/hatch, Python 3.12, deps
├── pytest.ini                    # Markers: unit (default), eval, conversation, release
├── .env.example                  # All env vars with placeholder values
│
├── src/pia/
│   ├── settings.py               # All tunables from env/Streamlit secrets
│   ├── db.py                     # Supabase client factory with retry transport
│   ├── logging.py                # Structured logging config
│   ├── privacy.py                # PII redaction (email, phone), review identity hash
│   │
│   ├── domain/
│   │   ├── models.py             # Pydantic: Product, Review, Chat, AgentRun, Usage, etc.
│   │   └── errors.py             # Typed exceptions (ProductNotFound, DomainNotAllowed, …)
│   │
│   ├── agent/
│   │   ├── factory.py            # create_agent wiring, run_query(), token extraction
│   │   ├── tools.py              # 4 StructuredTools wrapping services
│   │   ├── prompts.py            # Static SYSTEM_PROMPT (cache-friendly)
│   │   ├── guardrails.py         # GuardrailMiddleware (input/output/tool filters)
│   │   └── context.py            # build_context(): last N completed turns
│   │
│   ├── services/
│   │   ├── catalog.py            # CatalogService: fuzzy resolve, search, detail/review payloads
│   │   ├── comparison.py         # ComparisonService: 2–3 product side-by-side
│   │   ├── agent_runner.py       # AgentRunner: submit → ThreadPoolExecutor → run_query
│   │   ├── ingest.py             # IngestService: sitemap → fetch → parse → upsert → snapshot
│   │   └── usage.py              # Token totals, cache hit rate, usage tables
│   │
│   ├── repositories/
│   │   ├── catalog.py            # CatalogRepository: Postgres → catalog.json → sample fallback
│   │   ├── chats.py              # ChatRepository: CRUD for chats + chat_messages
│   │   ├── agent_runs.py         # AgentRunRepository: agent_runs + tool_calls
│   │   └── crawl.py              # CrawlRepository: crawl_runs, crawl_pages, products, reviews
│   │
│   ├── ingestion/
│   │   ├── policy.py             # URL allowlist, deny patterns, robots.txt
│   │   ├── http.py               # UrlFetcher with retry, delay, raw file writer
│   │   ├── sitemap.py            # Sitemap index traversal, product URL collection
│   │   ├── product_parser.py     # JSON-LD product metadata extraction
│   │   ├── reviews.py            # Playwright review extraction + shadow DOM + pagination
│   │   └── quality.py            # Quality gate for products and reviews
│   │
│   ├── analysis/
│   │   ├── sentiment.py          # VADER sentiment scoring
│   │   └── taxonomy.py           # Species/kind/category inference and normalization
│   │
│   └── ui/
│       ├── chat.py               # Chat page: message rendering, follow-ups, snapshot footer
│       ├── catalog_page.py       # Crawled catalog browser
│       ├── usage_page.py         # Usage & execution tables
│       ├── about.py              # About page
│       ├── charts.py             # Compare table, details card, review charts, sources caption
│       ├── followups.py          # Heuristic follow-up chip generation
│       └── stores.py             # Shared session-state singletons
│
├── scripts/
│   ├── ingest.py                 # CLI: offline catalog ingestion
│   └── check_ready.py            # Pre-push readiness: secret scan + catalog + Groq + Supabase
│
├── tests/
│   ├── conftest.py               # Shared fixtures (fake catalog, settings, etc.)
│   ├── test_catalog.py           # CatalogService + CatalogRepository
│   ├── test_tools.py             # Tool output shape and error handling
│   ├── test_guardrails.py        # Input refusal, output leak, tool-call blocking
│   ├── test_prompts.py           # System prompt assertions
│   ├── test_context.py           # Context window building
│   ├── test_charts.py            # Source captions, chart rendering
│   ├── test_followups.py         # Follow-up chip deduplication
│   ├── test_chats.py             # ChatRepository CRUD
│   ├── test_agent_runs.py        # AgentRunRepository
│   ├── test_crawl_policy.py      # URL policy, domain allowlist, deny patterns
│   ├── test_product_parser.py    # JSON-LD parsing
│   ├── test_reviews.py           # Review HTML/JSON-LD parsing
│   ├── test_ingest_identity.py   # Review deduplication hashing
│   ├── test_sentiment.py         # VADER scoring
│   ├── test_quality.py           # Quality gate
│   ├── test_usage.py             # Token counting and tables
│   ├── test_settings.py          # Settings loading
│   ├── test_db.py                # Supabase client factory
│   ├── test_secret_scan.py       # No secrets in tracked files
│   └── eval/
│       ├── goldens.json          # 21 single-turn golden test cases
│       ├── difficult_goldens.json # 12 difficult release-gate cases
│       ├── conversational_goldens.json
│       ├── attack_scenarios.py   # Adversarial simulation graphs
│       ├── groq_judge.py         # GroqJudge DeepEval adapter (retries 429s)
│       ├── simulator.py          # Conversation model callback
│       ├── load_dataset.py       # Golden → DeepEval Golden mapper
│       ├── test_agent_eval.py    # Single-turn eval harness
│       ├── test_difficult_eval.py # Release gate (difficult questions)
│       ├── test_conversation_eval.py  # Multi-turn simulator harness
│       └── test_dataset_schema.py     # Golden JSON schema validation
│
├── data/
│   ├── seed_products.json        # 10 priority products with SKU, URL, name
│   ├── sample_catalog.json       # Synthetic fallback (source_type=synthetic_sample)
│   ├── catalog.json              # Compact Petbarn snapshot after ingest (excerpts only)
│   └── manifest.json             # Ingest metadata: crawl_run_id, counts
│
├── supabase/
│   └── migrations/
│       └── 20260907_init.sql     # 8 tables, indexes, RLS policies, sequence function
│
└── eval/results/
    ├── .gitkeep
    └── latest.json               # (gitignored) Most recent eval scores
```
