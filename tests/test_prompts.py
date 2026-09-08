from datetime import datetime

from pia.agent.prompts import SYSTEM_PROMPT


def test_static_prefix_has_no_timestamps():
    assert "You are a Petbarn catalog assistant" in SYSTEM_PROMPT
    now = datetime.now().isoformat()
    assert now[:10] not in SYSTEM_PROMPT
    assert "chat_id" not in SYSTEM_PROMPT
    assert "never from memory of earlier tool JSON" in SYSTEM_PROMPT
    assert "Never append a snapshot" in SYSTEM_PROMPT
    assert "sort_by and species" in SYSTEM_PROMPT
