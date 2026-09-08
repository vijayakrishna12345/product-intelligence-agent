# Evaluation Methodology

The evaluation suite validates agent behaviour across three test harnesses with four DeepEval metrics.

## Test Harnesses

### Single-turn (`pytest -m eval`)

21 golden test cases in `tests/eval/goldens.json` covering:

- Price lookup, rating, reviews, search
- Comparison (2 and 3 products)
- Ambiguous queries, unknown products
- Hallucination resistance
- Aggregate ranking (top rated, cheapest, most reviewed)
- Filtered search
- Indirect prompt injection

Each case specifies expected tools, expected output patterns, and optionally a retrieval context. The agent runs against the real Groq model with the full tool set.

### Difficult release gate (`pytest -m release`)

12 difficult cases in `tests/eval/difficult_goldens.json`:

- Hallucination traps (products that don't exist)
- Ambiguous brands
- 3-way comparison
- Review synthesis across multiple products
- Adversarial guardrail probes
- Value-per-kg math
- Filtered search with species constraints

Deterministic assertions only (no LLM judge). Must complete without recursion errors, respect tool-call limits, and pass content checks. Results written to gitignored `eval/results/difficult_latest.json`.

`scripts/check_ready.py` runs this gate when `GROQ_API_KEY` is set.

### Multi-turn conversation (`pytest -m conversation`)

`ConversationSimulator` with:

- **Benign scenarios**: shopping flows that test context retention across turns.
- **Adversarial attack graphs**: prompt injection, scrape requests, weather/code queries, jailbreak attempts.

Metrics: TurnRelevancy, ConversationCompleteness, ContextConsistency, GuardrailAdherence.

## Metrics

Four DeepEval metrics scored by `GroqJudge` (`openai/gpt-oss-20b`):

| Metric | What it measures |
|---|---|
| **AnswerRelevancy** | Does the response directly address the user's question? |
| **CatalogGrounding** | Are all product facts grounded in tool-returned data? |
| **ToolCorrectness** | Did the agent select the right tool(s) for the query? |
| **ArgumentCorrectness** | Are the tool arguments well-formed and appropriate? |

## Running Evaluations

```powershell
# Single-turn (needs GROQ_API_KEY)
uv run pytest -m eval

# Release gate (needs GROQ_API_KEY)
uv run pytest -m release

# Multi-turn (needs GROQ_API_KEY)
uv run pytest -m conversation

# Full readiness check
uv run python scripts/check_ready.py
```

Results are written to gitignored `eval/results/latest.json`.

## Golden Case Schema

Each golden case in `goldens.json` is validated by `test_dataset_schema.py` and contains:

| Field | Description |
|---|---|
| `input` | User query string |
| `expected_output` | Substring/pattern the response should contain |
| `expected_tools` | List of tools the agent should invoke |
| `context` | Optional retrieval context for grounding checks |
| `additional_metadata` | Tags like `difficulty`, `category`, `guardrail` |
