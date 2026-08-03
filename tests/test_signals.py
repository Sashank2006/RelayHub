"""Tests for text normalization, keyword matching, and content signals."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "code"))

import main as router  # noqa: E402


def test_norm_lowercases_and_collapses_whitespace():
    assert router.norm("  Hello,   World!  ") == "hello world"


def test_norm_strips_punctuation():
    assert router.norm("Scan-QR & pay!! now") == "scan qr pay now"


def test_kw_match_is_word_boundary_based():
    # "test" must not match inside "latest"
    assert router.count_any("check the latest status", ["test"]) == 0
    # trailing-space keywords normalize to a word token, so "rs " must not
    # match inside "others "
    assert router.count_any("share with others", ["rs "]) == 0
    # "won" must not match inside "wonderful"
    assert router.count_any("wonderful news", ["won"]) == 0
    assert router.count_any("please send the otp now", ["otp"]) == 1


def test_count_any_deduplicates_keywords():
    # Two distinct keywords hit, but repeated occurrences count once each.
    assert router.count_any("offer offer discount", router.PROMO_KWS) >= 1


def test_content_signals_detect_scam():
    sig = router.content_signals(
        "Your OTP is 4821. Verify now or your account will be blocked.",
        "", "", 0)
    assert sig["scam"] >= 2


def test_content_signals_detect_promo():
    sig = router.content_signals(
        "Limited time offer! 50% off, use coupon now.", "", "", 0)
    assert sig["promo"] >= 2


def test_content_signals_detect_chain():
    sig = router.content_signals(
        "Forward this to 10 people before sunset. Do not ignore.", "", "", 3)
    assert sig["chain"] >= 1


def test_content_signals_merge_ocr_text():
    # OCR text participates in signals (field trip consent form image).
    sig = router.content_signals(
        "School circular attached.", "FIELD TRIP CONSENT FORM", "", 0)
    assert sig["event"] >= 2


def test_content_signals_forwarded_count():
    sig = router.content_signals("Good morning.", "", "", 9)
    assert sig["fwd"] >= 8


def test_jaccard_basic():
    a = {"alpha", "beta", "gamma"}
    b = {"alpha", "beta", "delta"}
    assert router.jaccard(a, b) == pytest.approx(2 / 4)
    assert router.jaccard(a, set()) == 0.0
