"""Tests for historical evidence retrieval."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "code"))

import main as router  # noqa: E402


def _hist(message_id, text, sender=None, group=None, business=None,
          conv="group"):
    row = {
        "message_id": message_id,
        "conversation_type": conv,
        "sender_user_id": sender,
        "group_id": group,
        "business_id": business,
        "message_text": text,
    }
    return row


def test_no_history_returns_none():
    ctx = {"hist_idx": {"u_001": []}, "ev_idx": {}}
    out = router.find_evidence("u_001", "group", None, None, "u_002",
                               "hello world", "", "", ctx)
    assert out == "none"


def test_no_similarity_no_context_returns_none():
    ctx = {
        "hist_idx": {"u_001": [_hist("m1", "completely unrelated text",
                                     sender="u_099", group="g_other")]},
        "ev_idx": {},
    }
    out = router.find_evidence("u_001", "group", "g_x", None, "u_002",
                               "cricket match highlights tonight", "", "", ctx)
    assert out == "none"


def test_same_sender_clears_threshold():
    ctx = {
        "hist_idx": {"u_001": [_hist("m1", "selling a kurta set near gate 2",
                                     sender="u_048", group="g_005")]},
        "ev_idx": {},
    }
    out = router.find_evidence("u_001", "group", "g_005", None, "u_048",
                               "photos for the kurta set are attached", "", "", ctx)
    assert out == "m1"


def test_reply_engagement_bonus_helps():
    ctx = {
        "hist_idx": {"u_001": [_hist("m1", "some group chatter",
                                     sender="u_048", group="g_005")]},
        "ev_idx": {"m1": {"message_replied": 1, "message_opened": 1,
                          "message_reported": 0, "muted_after_message": 0}},
    }
    # Low text overlap, but same sender + replied bonus pushes over 0.35.
    out = router.find_evidence("u_001", "group", "g_005", None, "u_048",
                               "tanker water delivery timing", "", "", ctx)
    assert out == "m1"


def test_limit_is_respected():
    ctx = {
        "hist_idx": {"u_001": [
            _hist("m1", "selling a kurta set near gate 2", sender="u_048", group="g_005"),
            _hist("m2", "kurta set still available pickup gate 2", sender="u_048", group="g_005"),
            _hist("m3", "another kurta photo pickup near gate 2", sender="u_048", group="g_005"),
        ]},
        "ev_idx": {},
    }
    out = router.find_evidence("u_001", "group", "g_005", None, "u_048",
                               "photos of the kurta set are attached", "", "", ctx)
    ids = out.split(";")
    assert len(ids) <= 2
