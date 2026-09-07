from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKERS = ("gsk_", "BEGIN RSA PRIVATE KEY", "BEGIN OPENSSH PRIVATE KEY")


def test_tracked_files_have_no_secret_markers():
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    hits = []
    for rel in result.stdout.splitlines():
        path = ROOT / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in MARKERS:
            if marker in text:
                hits.append(f"{rel}: {marker}")
        if rel.endswith(".env.example"):
            assert "your_groq_api_key" in text
            assert "gsk_" not in text
    assert hits == []
