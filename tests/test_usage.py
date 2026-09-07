from pia.domain.models import AgentRun, Usage
from pia.services.usage import (
    cache_hit_rate,
    estimate_tokens,
    token_totals,
    usage_from_run,
    usage_tables,
)


def test_estimate_and_hit_rate():
    assert estimate_tokens("abcd") == 1
    assert cache_hit_rate(80, 100) == 0.8
    assert cache_hit_rate(None, 100) is None


def test_tables_unavailable_cache():
    usage = Usage(input_tokens=10, output_tokens=2, cached_tokens=None)
    table_a, table_b = usage_tables(usage)
    cached = next(row for row in table_a if row["Metric"] == "Cached tokens")
    assert cached["Current turn"] == "unavailable"


def test_usage_from_run_no_transcript():
    from datetime import UTC, datetime
    from uuid import uuid4

    run = AgentRun(
        id=uuid4(),
        chat_id=uuid4(),
        turn_id=uuid4(),
        status="completed",
        user_message_id=uuid4(),
        input_tokens=100,
        cached_tokens=80,
        started_at=datetime.now(UTC),
    )
    usage = usage_from_run(run)
    assert usage.cache_hit_rate == 0.8
    assert "content" not in usage.model_dump()


def test_token_totals_sums_missing_as_zero():
    from datetime import UTC, datetime
    from uuid import uuid4

    chat_id = uuid4()
    base = dict(
        chat_id=chat_id,
        status="completed",
        user_message_id=uuid4(),
        started_at=datetime.now(UTC),
    )
    first = AgentRun(id=uuid4(), turn_id=uuid4(), input_tokens=100, output_tokens=20, **base)
    second = AgentRun(id=uuid4(), turn_id=uuid4(), input_tokens=None, output_tokens=5, **base)
    inp, out, total = token_totals([first, second])
    assert inp == 100
    assert out == 25
    assert total == 125
