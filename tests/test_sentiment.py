from pia.analysis.sentiment import score_text


def test_positive():
    label, score = score_text("This food is excellent and my dog loves it")
    assert label == "positive"
    assert score > 0


def test_negative():
    label, score = score_text("Terrible quality, worst bag I have bought")
    assert label == "negative"
    assert score < 0


def test_empty_neutral():
    label, score = score_text("")
    assert label == "neutral"
    assert score == 0.0
