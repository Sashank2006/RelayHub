"""Tests for business trust scoring."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "code"))

import main as router  # noqa: E402


def _biz(verified=1, official="a.com", used="a.com", age=1307,
         dom_age=1019, reports=0, sent=100):
    return {
        "verified": verified,
        "official_domain": official,
        "domain_used_by_sender": used,
        "account_age_days": age,
        "domain_used_by_sender_age_days": dom_age,
        "user_reports_30d": reports,
        "messages_sent_30d": sent,
    }


def test_missing_business_is_neutral():
    assert router.business_risk(None, {}) == (0.0, 1.0)
    assert router.business_risk("business_x", {}) == (0.0, 0.0)


def test_healthy_verified_business_has_low_risk():
    risk, trust = router.business_risk("b", {"b": _biz()})
    assert risk < 0.5
    assert trust > 0.5


def test_unverified_young_business_is_risky():
    risk, _ = router.business_risk("b", {"b": _biz(verified=0, age=35, dom_age=10)})
    assert risk >= 0.5


def test_high_report_unverified_sender_scores_very_high():
    # Mirrors the real business_098 (Loan Verification Desk) profile.
    row = _biz(verified=0, official="", used="vl.gl", age=35, dom_age=10,
               reports=23, sent=1756)
    risk, trust = router.business_risk("b", {"b": row})
    assert risk >= 0.9
    assert trust == 0.0


def test_trust_is_clamped_to_zero():
    row = _biz(verified=0, official="a.com", used="b.com", age=20, dom_age=5,
               reports=500, sent=10)
    risk, trust = router.business_risk("b", {"b": row})
    assert risk >= 1.0
    assert trust == 0.0
