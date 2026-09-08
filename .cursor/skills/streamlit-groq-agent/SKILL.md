---
name: streamlit-groq-agent
description: Streamlit + Groq catalog agent wiring for PIA. Use when changing create_agent, tools, Streamlit chat UX, SCC secrets, or demo queries.
---

# Streamlit Groq agent

## Local

```powershell
uv run streamlit run streamlit_app.py
```

Secrets from `.env` via lazy `python-dotenv`. Cloud uses Streamlit secrets dashboard (`GROQ_API_KEY`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`).

## Agent

- `from langchain.agents import create_agent`
- Model `settings.groq_model` with `model_kwargs={"include_reasoning": False}`
- Middleware: input/tool/output guardrails + `ModelCallLimitMiddleware` + `ToolCallLimitMiddleware`
- `run_query` appends exactly one `HumanMessage`. `build_context` is completed turns only.

## UI checks

- Pages: Chat, Crawled catalog, Context & usage, About (`st.navigation`)
- `?chat=` plus session recents; sidebar shows chat **title**, not UUID
- Chat shows follow-up chips; sources and charts stay hidden until the user asks
- Snapshot disclaimer sits once under the chat input, not in every assistant reply
- Sidebar shows chat **title** and total tokens for the open conversation
- Usage page is per recent conversation (no `list_all`)
- `source_type` labels; compare table + rating chart
- Demo questions come from `data/seed_products.json` names
