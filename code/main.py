"""
Message Notification Router - HackerRank Orchestrate (Aug 2026)

Deterministic, multimodal, personalized routing engine for WhatsApp-style
messages. For every incoming message it decides:
  - notify : interrupt now
  - digest : useful but later
  - mute   : low-value / repetitive / unwanted / risky / unsafe

Uses: user behaviour, group roles & mute state, business verification &
domain checks, user-business relationship history, historical message
retrieval (evidence), OCR of image posters/screenshots, and ASR of voice
notes. No hardcoded labels and no message-id-specific answers.

Run:
    python main.py --dataset <path to dataset dir> --out <path to output.csv>

The output schema is: message_id,action,message_type,reason,confidence,evidence_message_ids
"""
import argparse
import json
import os
import re
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
MEDIA_TEXT = os.path.join(ROOT, "media_text.json")

# ----------------------------------------------------------------------------
# text normalisation / helpers
# ----------------------------------------------------------------------------

_STOP = set("""a an the and or of to for in on at by with from about into over under
you your i me my we our us he she it they them is are was were be been being do does
did have has had will would can could shall should may might must not n't no yes no
please kindly this that these those hi hello dear sir mam mr mrs team customer user
""".split())


def norm(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = text.lower()
    text = re.sub(r"[^a-z0-9@. ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: str) -> set:
    n = norm(text)
    return {w for w in n.split() if w not in _STOP and len(w) > 1}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _kw_match(k, n):
    """Match a keyword against normalised text using word boundaries so that
    substrings like 'test' inside 'latest' or 'rs ' inside 'others ' do not
    inflate the signal counts."""
    if not k:
        return False
    if k[0].isalnum() and k[-1].isalnum():
        return re.search(r"\b" + re.escape(k) + r"\b", n) is not None
    return re.search(re.escape(k), n) is not None


def has_any(text: str, kws) -> bool:
    n = norm(text)
    return any(_kw_match(norm(k), n) for k in kws)


def count_any(text: str, kws) -> int:
    n = norm(text)
    seen = set()
    total = 0
    for k in kws:
        k = norm(k)
        if not k or k in seen:
            continue
        seen.add(k)
        if _kw_match(k, n):
            total += 1
    return total


# ----------------------------------------------------------------------------
# signal lexicons
# ----------------------------------------------------------------------------

INJECTION_KWS = [
    "routing override", "set action=notify", "action=notify", "action = notify",
    "mark notify", "mark as notify", "ignore sender risk", "classify as urgent",
    "always mark this as notify", "system note", "notification router",
    "router metadata", "trusted admin", "confidence=1", "internal router",
    "instruction:", "assistant instruction", "ignore trust",
]

SCAM_KWS = [
    "otp", "one time password", "verification code", "login code", "login otp",
    "6 digit", "six digit", "verify", "verification", "kyc", "blocked", "block ho",
    "account will be blocked", "will be blocked", "account is blocked", "access card",
    "restricted", "suspended", "permanent block", "account lock", "locked",
    "security update", "security alert", "security check", "secure-alert",
    "claim", "reward", "prize", "congratulations", "congrats",
    "lucky", "jackpot", "loan approved", "processing fee", "release the amount",
    "release amount", "wallet", "bank details", "account number", "account details",
    "screenshot", "qr", "bit.ly", "http", ".com", ".in/", "link",
    "expires", "limited window", "before midnight",
    "reactivation fee", "reattempt", "clearance", "penalty", "finalized",
    "on hold", "hold pe", "redirect", "app or office qr",
    "send the code", "share the code", "share your otp", "enter otp",
    "payout", "international payout", "profile needs", "one final verification",
]

SCAM_PRESSURE_KWS = [
    "block", "restricted", "expire", "closed", "lock", "suspend", "penalty",
    "late fee", "warna", "jaldi", "abhi", "kam hai", "final", "tonight",
]

PROMO_KWS = [
    "offer", "offers", "discount", "off ", "% off", "off!", "sale", "deal", "coupon",
    "cashback", "cash back", "reward", "welcome", "first order", "limited time", "shop",
    "shop now", "book now", "buy", "subscribe", "unsubscribe",
    "marketing", "exclusive", "clearance sale", "urgent sale", "token",
    "final price", "price final", "limited", "expires soon", "save", "promo",
    "launch", "grand", "off on", "today only", "shop the",
    "give your valuable feedback", "quick review", "review", "feedback",
    "survey", "session update", "3-minute", "3 min", "opinion",
    "selling", "price", "interested", "dm if", "worth", "resale",
    "token today", "block 1200", "registry", "plots", "bhk", "invited",
    "per person", "itinerary", "trip", "travel deal",
]

PROMO_STRONG_KWS = [
    "off won't wait", "cashback", "cash back", "coupon", "subscribe",
    "unsubscribe", "stop to", "limited time",
]

CHAIN_KWS = [
    "forward this to", "forward to", "forwarded to", "share this", "share with",
    "share it", "send this to", "send to", "ten people", "10 people",
    "10 members", "do not ignore", "do not break the chain", "break the chain",
    "chain", "positive energy", "blessing", "blessings", "blessed",
    "before sunset", "before night", "before midnight", "good luck", "luck changes",
    "fwd as received", "as received", "read till end", "elders",
    "bhagwan", "sabki", "sabko", "positive",
]

URGENT_KWS = [
    "call me now", "call now", "call me urgently", "urgently", "urgent",
    "asap", "immediately", "right away", "now", "right now", "today",
    "tonight", "before 5 pm", "before 6 pm", "before 6:00", "by 6 pm",
    "in 10 minutes", "in the next 10", "next ten minutes", "10 min",
    "closes in", "in 10 mins", "minutes", "minute",
    "leaving in", "leaves in", "leaves at", "closes at", "closes today",
    "closes this evening", "before the portal locks", "deadline",
    "failing", "incident bridge", "incident", "escalation", "escalates",
    "alert threshold", "stay online", "now ", "immediately", "asap",
    "jaldi", "abhi", "time kam", "band hone", "tanker", "aa gaya",
    "aagaya", "nikalna", "padega", "moved to", "gate closes",
    "moving in", "before the window", "window closes", "expire",
    "today", "tomorrow", "reach by", "please reach", "by 340",
    "by 6 pm today", "today only", "must be", "confirm in",
    "pick up", "collect", "retrieve", "submit", "confirm", "send the",
]

NEGATION_KWS = [
    "no urgency", "nothing urgent", "no rush", "no pressure", "nothing blocking",
    "no need to reply", "no need to respond", "not urgent", "whenever convenient",
    "if you get time", "read after market", "read later", "nothing for tonight",
    "kal baat", "koi urgency nahi", "clear nahi hai", "baad me",
]

EVENT_KWS = [
    "maintenance", "tanker", "water", "fire alarm", "school", "circular",
    "field trip", "class", "meeting", "sync", "incident", "pickup", "trip",
    "schedule", "appointment", "clinic", "lift", "studio", "rehearsal",
    "potluck", "registration", "forms", "internship", "alumni", "gate",
    "tower b", "service lift", "repair", "driver", "courier", "pickup code",
    "delivery", "order ending", "return pickup", "rollback", "deployment",
    "review slides", "lab", "exam", "fee receipt", "bus list", "consent",
    "test", "bridge", "payments failing", "route", "airport", "booking",
    "movie", "market", "stock", "nifty", "earnings", "match", "highlights",
]

PERSONAL_KWS = [
    "hi", "hey", "hello", "call me", "dinner", "lunch", "food", "home",
    "reach", "arrived", "okay", "ok", "can you", "would you", "are you",
    "did you", "just", "little", "chat", "talk", "family", "beta",
]

GREETING_KWS = [
    "good morning", "good evening", "good afternoon", "good night",
    "have a good day", "smile", "bless", "good day", "welcome", "namaste",
]

PAYMENT_KWS = [
    "payment due", "pay", "paid", "fee", "charges", "charge", "maintenance",
    "clearance amount", "amount", "late fee", "receipt", "bill", "renewal",
    "upi", "refund", "payout", "loan", "token amount", "rs ",
]

# ----------------------------------------------------------------------------
# contextual tables
# ----------------------------------------------------------------------------

def load_context(dataset_dir):
    ctx = {}
    ctx["users"] = pd.read_csv(os.path.join(dataset_dir, "users.csv"))
    ctx["groups"] = pd.read_csv(os.path.join(dataset_dir, "groups.csv"))
    ctx["group_members"] = pd.read_csv(os.path.join(dataset_dir, "group_members.csv"))
    ctx["business"] = pd.read_csv(os.path.join(dataset_dir, "business_accounts.csv"))
    ctx["user_business"] = pd.read_csv(os.path.join(dataset_dir, "user_business_history.csv"))
    ctx["history"] = pd.read_csv(os.path.join(dataset_dir, "message_history.csv"))
    ctx["events"] = pd.read_csv(os.path.join(dataset_dir, "message_events.csv"))

    gm = ctx["group_members"]
    ctx["gm_idx"] = {(g, u): r for (g, u), r in
                     gm.set_index(["group_id", "user_id"]).iterrows()}

    biz = ctx["business"]
    ctx["biz_idx"] = {r["business_id"]: r for _, r in biz.iterrows()}

    ub = ctx["user_business"]
    ctx["ub_idx"] = {(r["user_id"], r["business_id"]): r for _, r in ub.iterrows()}

    ev = ctx["events"]
    ctx["ev_idx"] = {r["message_id"]: r for _, r in ev.iterrows()}

    # per-user index of historical messages for retrieval
    hist_idx = {}
    for _, r in ctx["history"].iterrows():
        uid = r["user_id"]
        hist_idx.setdefault(uid, []).append(r)
    ctx["hist_idx"] = hist_idx

    # (user, business) pairs where the user dismissed and/or muted a prior message
    dismissed_biz = set()
    ev_idx = ctx["ev_idx"]
    for uid, rows in hist_idx.items():
        for r in rows:
            bid = r.get("business_id")
            if isinstance(bid, str) and bid:
                ev = ev_idx.get(r["message_id"])
                if ev is not None:
                    _muted = int(ev.get("muted_after_message") or 0) == 1
                    _dismissed = int(ev.get("notification_dismissed") or 0) == 1
                    _opened = int(ev.get("message_opened") or 0)
                    if _muted or (_dismissed and not _opened):
                        dismissed_biz.add((uid, bid))
    ctx["dismissed_biz"] = dismissed_biz
    return ctx


def load_media_text():
    """OCR (images) and ASR (voice) results cached by main.py's preprocess step."""
    if os.path.exists(MEDIA_TEXT):
        with open(MEDIA_TEXT, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ----------------------------------------------------------------------------
# business trust
# ----------------------------------------------------------------------------

def business_risk(bid, biz_idx):
    if not isinstance(bid, str) or not bid:
        return 0.0, 1.0
    b = biz_idx.get(bid)
    if b is None:
        return 0.0, 0.0
    verified = int(b.get("verified") or 0)
    official = _safe_str(b.get("official_domain"))
    used = _safe_str(b.get("domain_used_by_sender"))
    age = float(b.get("account_age_days") or 0)
    dom_age = float(b.get("domain_used_by_sender_age_days") or 0)
    reports = float(b.get("user_reports_30d") or 0)
    sent = float(b.get("messages_sent_30d") or 0)

    mismatch = bool(official) and bool(used) and official != used
    risk = 0.0
    if verified == 0:
        risk += 0.35
    if mismatch:
        risk += 0.35
    if age < 60:
        risk += 0.25
    if dom_age < 60:
        risk += 0.15
    if reports >= 10 and sent > 0:
        risk += min(0.35, reports / max(sent, 1) * 100 * 0.5)
    trust = 1.0 - min(1.0, risk)
    return risk, trust


# ----------------------------------------------------------------------------
# content signals
# ----------------------------------------------------------------------------

def _safe_str(x):
    if x is None:
        return ""
    if isinstance(x, float) and x != x:  # NaN
        return ""
    return str(x)


def content_signals(text, image_text, voice_text, forwarded_count):
    text = _safe_str(text)
    image_text = _safe_str(image_text)
    voice_text = _safe_str(voice_text)
    full = " ".join(x for x in [text, image_text, voice_text] if x)
    n = norm(full)
    s = {
        "text": full,
        "injection": count_any(full, INJECTION_KWS),
        "scam": count_any(full, SCAM_KWS),
        "pressure": count_any(full, SCAM_PRESSURE_KWS),
        "promo": count_any(full, PROMO_KWS),
        "promo_strong": count_any(full, PROMO_STRONG_KWS),
        "pct_off": bool(re.search(r"\b\d{1,3}\s?off\b", norm(full))),
        "chain": count_any(full, CHAIN_KWS),
        "urgent": count_any(full, URGENT_KWS),
        "negation": count_any(full, NEGATION_KWS),
        "event": count_any(full, EVENT_KWS),
        "personal": count_any(full, PERSONAL_KWS),
        "greeting": count_any(full, GREETING_KWS),
        "payment": count_any(full, PAYMENT_KWS),
        "fwd": int(forwarded_count or 0),
        "has_link": bool(re.search(r"(http|bit\.ly|\.com|\.in[/ ]|\.co|\.org|\.net)", n)),
        "has_qr": bool(re.search(r"qr|scan", n)),
    }
    return s


# ----------------------------------------------------------------------------
# evidence retrieval
# ----------------------------------------------------------------------------

def find_evidence(user_id, conv_type, group_id, business_id, sender_user_id,
                  text, image_text, voice_text, ctx, limit=2):
    hist = ctx.get("hist_idx", {}).get(user_id, [])
    if not hist:
        return "none"
    full = " ".join(_safe_str(x) for x in [text, image_text, voice_text] if _safe_str(x))
    tset = tokens(full)
    scored = []
    for h in hist:
        ht = h["message_text"] or ""
        hset = tokens(ht)
        sim = jaccard(tset, hset)
        same_biz = h.get("business_id") and h["business_id"] == business_id
        same_sender = h.get("sender_user_id") and h["sender_user_id"] == sender_user_id
        same_group = h.get("group_id") and h["group_id"] == group_id
        same_conv = h.get("conversation_type") == conv_type
        base = sim
        if same_biz:
            base += 0.45
        if same_sender:
            base += 0.4
        if same_group:
            base += 0.3
        if same_conv:
            base += 0.05
        if base <= 0:
            continue
        # engagement bonus
        ev = ctx.get("ev_idx", {}).get(h["message_id"])
        if ev is not None:
            if ev.get("message_replied"):
                base += 0.15
            if ev.get("message_opened"):
                base += 0.05
            if ev.get("message_reported"):
                base += 0.2
            if ev.get("muted_after_message"):
                base += 0.1
        scored.append((base, h["message_id"]))
    scored.sort(key=lambda x: -x[0])
    scored = [m for sc, m in scored[:limit] if sc >= 0.35]
    if not scored:
        return "none"
    return ";".join(scored)


# ----------------------------------------------------------------------------
# routing decision
# ----------------------------------------------------------------------------

def _conf(base, *mods):
    c = base
    for m in mods:
        c += m
    return max(0.5, min(0.98, round(c, 2)))


def decide(msg, sig, ctx):
    uid = msg["user_id"]
    conv = msg["conversation_type"]
    gid = msg.get("group_id")
    bid = msg.get("business_id")
    sender = msg.get("sender_user_id")

    # ---- personalized context ----
    b_risk, b_trust = business_risk(bid, ctx["biz_idx"])
    ub = ctx["ub_idx"].get((uid, bid)) if isinstance(bid, str) and bid else None
    opted_out = False
    allows_promo = None
    dismissed_marketing = False
    if ub is not None:
        po = ub.get("promotions_opted_out_at")
        if po is None:
            opted_out = False
        elif isinstance(po, float) and po != po:  # NaN
            opted_out = False
        else:
            opted_out = str(po).strip() not in ("", "nan", "None", "NaT")
        allows_promo = int(ub.get("allows_promotions") or 0) == 1
        try:
            dismissed_marketing = float(ub.get("messages_dismissed_30d") or 0) >= 5
        except (TypeError, ValueError):
            pass

    gm = None
    if gid and uid:
        gm = ctx["gm_idx"].get((gid, uid))
    group_muted = False
    role = None
    if gm is not None and isinstance(gm, dict):
        role = str(gm.get("role") or "")
        group_muted = int(gm.get("group_muted_by_user") or 0) == 1
    elif gm is not None:
        role = str(gm["role"] if "role" in gm.index else "")
        gm_row = dict(gm)
        group_muted = int(gm_row.get("group_muted_by_user") or 0) == 1

    # sender admin in this group
    sender_admin = False
    if gid and sender:
        gm_s = ctx["gm_idx"].get((gid, sender))
        if gm_s is not None:
            if isinstance(gm_s, dict):
                sender_admin = str(gm_s.get("role") or "") == "admin"
            else:
                sender_admin = str(dict(gm_s).get("role") or "") == "admin"

    direct_mention = bool(re.search(r"@" + re.escape(uid), str(msg.get("message_text") or "")))

    t = sig["text"]
    n = norm(t)
    n_text = norm(str(msg.get("message_text") or ""))
    negated = sig["negation"] >= 1
    # time-bound same-day action phrases
    timebound = bool(re.search(
        r"(by 6 ?pm|by 5 ?pm|before 6 ?pm|before 5 ?pm|in 10 min|leaving in|leaves in|"
        r"closes at|closes in|closes today|today at|tonight|before midnight|before the|"
        r"reach by|by \d{1,2}(:\d{2})? ?(am|pm)|before \d{1,2} ?(am|pm)|in the next \d+|"
        r"for the next \d+|expires|only till|till 7 ?pm|by 340|from gate 2|side entrance|"
        r"10 min me|5 baje tak|baje tak|today before|before evening|before \d{1,2} ?pm|"
        r"\btoday\b|by tomorrow|tomorrow morning|tomorrow evening|tomorrow at|this evening)", n))
    action_now = bool(re.search(
        r"(collect|confirm|call|move|submit|pick ?up|retrieve|reach|pay|send|share|"
        r"come|join|check|release|fill|complete|leave|open|blocked|hold|hold |stay online|"
        r"hata|nikal|le aao|kar do|jao|bring|close|attend|watch|move)", n))

    strong_work = bool(re.search(
        r"(stay online|incident|escalat|payments failing|build is failing|alert threshold|"
        r"client meeting|in 20 minutes|next ten minutes|in the next ten|"
        r"come online now|failed jobs|rollback)", n))

    # genuine sensitive asks (identity / money), with negation handling so that
    # "no payment or OTP is required" or "don't post screenshots" is not a scam.
    sensitive_ask = bool(re.search(
        r"(share (your )?(otp|code|password|pin)|send (the )?(otp|code)|"
        r"enter (otp|code)|verify (the )?(otp|code)|"
        r"(confirm|re-?enter|type).{0,20}(password|otp|code|pin)|"
        r"(reply|text|message).{0,20}(otp|code)|(otp|code|pin).{0,25}(received|we sent|just sent)|"
        r"(send|share|post) screenshot|screenshot here|"
        r"bank details|account number|account details|credit card|debit card|card details|"
        r"upi (id|number|pin)|send your|share your)", n))
    if sensitive_ask and re.search(r"(don'?t|do not|never|no need|avoid|unless|not (post|send|share))", n):
        sensitive_ask = False
    hinglish_ask = bool(re.search(
        r"(otp|code|verification).{0,25}(batao|bhejo|daalo|daal do|karo|kar do|do na)|"
        r"(batao|bhejo|daalo|karo).{0,25}(otp|code|verification)", n))
    qr_pay = bool(re.search(
        r"(scan|qr).{0,40}(pay|amount|clearance|fee)|(pay|amount).{0,40}(qr|scan)", n))
    pay_text = bool(re.search(
        r"(payment|pay|due|fee|receipt|clearance|upi|bill|charge)", n_text))

    # ---------- 1) prompt injection -> mute scam ----------
    if sig["injection"] > 0:
        return ("mute", "scam",
                "The message tries to override the router or asks for sensitive data under false urgency.",
                _conf(0.93, 0.02 * sig["injection"]))

    # ---------- 2) risky business + sensitive ask -> mute scam ----------
    if isinstance(bid, str) and b_risk >= 0.5 and \
            (sensitive_ask or hinglish_ask or qr_pay or sig["scam"] >= 3):
        return ("mute", "scam",
                "The sender account shows risk signals (verification/domain mismatch) and the message requests sensitive actions.",
                _conf(0.9, 0.03 * min(sig["scam"], 3)))

    # ---------- 2b) unverified, high-report sender with no real engagement -> mute spam ----------
    if isinstance(bid, str) and b_risk >= 0.9:
        _b = ctx["biz_idx"].get(bid)
        _verified = int(_b.get("verified") or 0) if _b is not None else 0
        _reports = float(_b.get("user_reports_30d") or 0) if _b is not None else 0
        _why = _safe_str(ub.get("why_user_knows_account")) if ub is not None else ""
        _opened = int(ub.get("messages_opened_30d") or 0) if ub is not None else 0
        _active_rel = re.search(
            r"(order|delivery|purchase|bought|booking|appointment|consult|"
            r"subscription|membership|payment due|refund)", _why)
        if _verified == 0 and _reports >= 15 and not _active_rel and _opened == 0:
            return ("mute", "spam",
                    "Unverified sender account with heavy user reports and no opened or active engagement.",
                    _conf(0.9))


    # ---------- 3) strong scam content -> mute scam ----------
    if (sensitive_ask or hinglish_ask or qr_pay) or sig["scam"] >= 4 or \
            (sig["scam"] >= 2 and sig["has_link"]) or \
            (sig["scam"] >= 3 and sig["pressure"] >= 1):
        return ("mute", "scam",
                "The message uses urgency or asks for verification details, OTP, or payment, indicating a scam.",
                _conf(0.87, 0.02 * min(sig["scam"], 4)))

    # ---------- 4) chain forwards / high-fwd blessing & health tips -> mute ----------
    if sig["chain"] >= 1 and (sig["greeting"] >= 1 or "share" in n or "forward" in n
                              or sig["fwd"] >= 6 or "positive" in n):
        return ("mute", "forward",
                "Chain forward or repeated forwarded content that the user usually ignores.",
                _conf(0.82, 0.02 * min(sig["fwd"], 6)))
    if sig["fwd"] >= 8 and (sig["greeting"] >= 1 or "health" in n or "bless" in n):
        return ("mute", "forward",
                "Repeated forwarded greetings or health tips the user typically ignores.",
                _conf(0.82, 0.01 * min(sig["fwd"], 6)))

    # ---------- 5) promotion personalization ----------
    statement_msg = "statement" in n
    promo_hits = sig["promo"] >= 2 or sig["promo_strong"] >= 1 or sig["pct_off"] or \
        (isinstance(bid, str) and ub is not None and "subscri" in n)
    # group admin notices can contain incidental promo words ("offer letter"),
    # so exclude same-day admin deadlines from the promotion branch.
    admin_deadline = bool(sender_admin) and timebound and sig["urgent"] >= 1 and sig["event"] >= 1
    is_promo = (promo_hits if conv == "business" else
                (sig["promo"] >= 2 or sig["promo_strong"] >= 1 or sig["pct_off"])) \
        and not statement_msg and not admin_deadline
    if is_promo:
        if (uid, bid) in ctx.get("dismissed_biz", set()) or opted_out or dismissed_marketing or group_muted:
            return ("mute", "promotion",
                    "The user has opted out of, muted, dismissed, or repeatedly ignored similar marketing messages.",
                    _conf(0.8, 0.02 if opted_out or group_muted else 0.0))
        return ("digest", "promotion",
                "The message is promotional but matches a topic or business the user has engaged with.",
                _conf(0.72, 0.03 if allows_promo else -0.02))

    # ---------- 5c) continuation of an active sales thread in a group ----------
    if conv == "group" and sender and not (sig["urgent"] >= 1 or direct_mention or timebound):
        _thread_promo = False
        for _h in ctx["hist_idx"].get(uid, []):
            if str(_h.get("sender_user_id") or "") == str(sender) and \
                    str(_h.get("group_id") or "") == str(gid):
                if re.search(r"(selling|for sale|sale|price|available|discount|kurta|price is final)",
                             norm(str(_h.get("message_text") or ""))):
                    _thread_promo = True
                    break
        if _thread_promo and (sig["promo"] >= 1 or sig["event"] >= 1):
            if group_muted:
                return ("mute", "promotion",
                        "The user muted this group; a follow-up to an active sales thread.",
                        _conf(0.8))
            return ("digest", "promotion",
                    "A follow-up message in an active local sales thread the user may be interested in.",
                    _conf(0.72))


    # ---------- 5b) legitimate payment reminder from trusted admin -> notify ----------
    if pay_text and timebound and not sig["has_link"] and not negated and not strong_work:
        if conv == "group" and (sender_admin or sig["event"] >= 1):
            return ("notify", "payment",
                    "A trusted group admin sent a legitimate payment reminder with a same-day deadline.",
                    _conf(0.7))

    # ---------- 6) urgent / direct mention / time-bound action -> notify ----------
    urgent_ok = (direct_mention or sig["urgent"] >= 2) and not negated
    if (urgent_ok or strong_work) and (timebound or action_now) and not negated:
        if sig["event"] >= sig["urgent"] and sig["event"] >= 1 \
                and not direct_mention and not strong_work:
            return ("notify", "event",
                    "A trusted contact sent a same-day operational update that the user likely needs now.",
                    _conf(0.8, 0.02 if direct_mention else 0.0))
        return ("notify", "urgent",
                "The message is from a trusted context and contains a direct, time-sensitive request.",
                _conf(0.8, 0.03 if direct_mention else 0.0))

    # ---------- 7) same-day actionable event (non-business) -> notify ----------
    if conv != "business" and sig["event"] >= 2 and timebound and action_now and not negated:
        return ("notify", "event",
                "A group or sender shared a same-day update that requires the user's attention now.",
                _conf(0.76, 0.02 if direct_mention else 0.0))

    # ---------- 7b) admin school circulars (text or OCR) -> notify ----------
    _all_txt = n + " " + norm(str(sig.get("image_text", ""))) + " " + norm(str(sig.get("voice_text", "")))
    if sender_admin and re.search(r"(circular|consent form|permission slip|field trip)", _all_txt):
        return ("notify", "event",
                "A school or admin circular requires the user to review and act.",
                _conf(0.75))

    # ---------- 8) business updates ----------
    if conv == "business":
        why = _safe_str(ub.get("why_user_knows_account")) if ub is not None else ""
        today_text = bool(re.search(r"(today|tonight|tomorrow|this evening|scheduled)", n))
        active_kind = bool(re.search(
            r"(order|delivery|ride|booking|pickup|return|appointment|refill)", why))
        active_now = today_text or bool(re.search(
            r"(today|booked|confirmed|expected|pending|active|scheduled)", why))
        if ub is not None and active_kind and active_now:
            if re.search(r"(appointment|ride|booking|pickup|refill)", why):
                return ("notify", "event",
                        "A verified business sent a reminder matching the user's recent booking or pickup.",
                        _conf(0.75))
            return ("notify", "business_update",
                    "A verified business sent an update matching the user's recent order or delivery.",
                    _conf(0.72))
        return ("digest", "business_update",
                "A verified business sent a legitimate but non-urgent update.",
                _conf(0.72, 0.03 if b_trust > 0.9 else -0.02))

    # ---------- 10) group / personal falls back to digest ----------
    if sig["greeting"] >= 1:
        return ("digest", "greeting",
                "The message is a harmless greeting that can be read later.",
                _conf(0.72))
    if sig["event"] >= 1:
        return ("digest", "event",
                "The message is useful group information, but not urgent enough to interrupt the user.",
                _conf(0.7))
    if sig["payment"] >= 1:
        return ("digest", "payment",
                "The message is a legitimate but non-urgent payment reminder.",
                _conf(0.68))
    if sig["fwd"] >= 2:
        return ("digest", "forward",
                "A forwarded message with no urgent action or safety risk.",
                _conf(0.68))
    return ("digest", "personal",
            "The sender is trusted, but the message has no urgent action or safety relevance.",
            _conf(0.7))


# ----------------------------------------------------------------------------
# pipeline
# ----------------------------------------------------------------------------

def build_evidence(msg, sig, ctx):
    return find_evidence(
        msg["user_id"], msg["conversation_type"], msg.get("group_id"),
        msg.get("business_id"), msg.get("sender_user_id"),
        msg.get("message_text") or "", sig.get("image_text", ""),
        sig.get("voice_text", ""), ctx)


def route(msg, ctx, media):
    img_txt = ""
    vo_txt = ""
    mid = msg.get("media_id")
    if msg.get("media_type") == "image" and mid:
        img_txt = media.get("images", {}).get(mid, "")
    if msg.get("media_type") == "voice" and mid:
        vo_txt = media.get("voice", {}).get(mid, "")

    sig = content_signals(msg.get("message_text") or "", img_txt, vo_txt,
                          msg.get("forwarded_count"))
    sig["image_text"] = img_txt
    sig["voice_text"] = vo_txt
    action, mtype, reason, confidence = decide(msg, sig, ctx)
    evidence = build_evidence(msg, sig, ctx)
    return {
        "message_id": msg["message_id"],
        "action": action,
        "message_type": mtype,
        "reason": reason,
        "confidence": confidence,
        "evidence_message_ids": evidence,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=os.path.join(ROOT, "..", "dataset"))
    ap.add_argument("--out", default=os.path.join(ROOT, "..", "dataset", "output.csv"))
    args = ap.parse_args()

    dataset_dir = args.dataset
    msgs = pd.read_csv(os.path.join(dataset_dir, "messages.csv"))
    ctx = load_context(dataset_dir)
    media = load_media_text()

    rows = []
    for _, m in msgs.iterrows():
        try:
            rows.append(route(m, ctx, media))
        except Exception as e:  # defensive: never leave a row blank
            rows.append({
                "message_id": m["message_id"], "action": "digest",
                "message_type": "unknown", "reason": "Fallback decision.",
                "confidence": 0.5, "evidence_message_ids": "none"})
            print(f"[warn] {m['message_id']}: {e}", file=sys.stderr)

    out = pd.DataFrame(rows, columns=[
        "message_id", "action", "message_type", "reason",
        "confidence", "evidence_message_ids"])
    out.to_csv(args.out, index=False)
    print(f"Wrote {len(out)} rows to {args.out}")
    print(out[["message_id", "action", "message_type", "confidence"]].to_string(index=False))


if __name__ == "__main__":
    main()
