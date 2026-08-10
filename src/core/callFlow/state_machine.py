"""
Palvi Agrico — State Machine + Claude Fallback.

Hardcoded scripted questions for instant response (0ms TTS from cache).
Claude is only called when farmer asks off-script questions or gives
unexpected answers that need interpretation.
"""
import logging

from src.infra.db.session_manager import SessionManager
from src.core.callFlow.scripts import (
    GREETING, NO_TIME_RESPONSE, COMPANY_INTRO, COMPANY_INTRO_2, ASK_CROP,
    THANK_YOU, Q_ACREAGE, Q_VARIETY, Q_DAYS, Q_WEATHER,
    Q_PEST, Q_WHICH_PEST, Q_PEST_LEVEL, Q_GROWTH, Q_FERTILIZER,
    Q_ORDER, Q_ADDRESS, Q_PUMP, Q_PUMP_OFFER, Q_OTHER_CROP,
    RE_ASK_CROP,
)
from src.core.productKnowledge.products import (
    CYMINT_RECOMMENDATION, SIZE_PLUS_RECOMMENDATION, BOTH_PRODUCTS,
    FAQ_PUMP_CONFIRM,
)
from src.core.offerEngine.scheme import (
    SCHEME_PITCH, SCHEME_DETAILS, SCHEME_GIFTS, SCHEME_RULES, SCHEME_END,
)
from src.core.productKnowledge.faq_matcher import try_faq
from src.adapters.llm.claude import call_claude

logger = logging.getLogger(__name__)
session_manager = SessionManager()

# Yes/No detection
YES_WORDS = ["हो", "होय", "हा", "चालेल", "ठीक", "नक्की", "व्हय", "बरं",
             "yes", "ha", "ho", "ok", "sure", "करा", "पाठवा", "द्या", "ठेवा"]
NO_WORDS = ["नाही", "नको", "नाय", "न्हाय", "no", "nahi", "nako", "नग",
            "नंतर", "राहू दे", "नाई", "नहीं"]


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _is_yes(text):
    return any(w in text.lower() for w in YES_WORDS)


def _is_no(text):
    return any(w in text.lower() for w in NO_WORDS)


def _is_question(text):
    """Detect if farmer is asking a question (off-script) rather than answering."""
    text_lower = text.lower().strip()
    # Explicit answers — never treat as questions
    answer_patterns = ["नाही", "नको", "हो", "नाय", "ठीक", "बरं", "कोणताच नाही",
                       "कोणतीच नाही", "काही नाही", "माहीत नाही"]
    if any(text_lower == p or text_lower.startswith(p + " ") for p in answer_patterns):
        return False
    # Short question words (even 1-3 words) that are clearly questions
    short_questions = ["काय", "काय म्हणाला", "काय म्हणालात", "काय सांगितलं",
                       "कशाबद्दल", "कोणत्या", "का", "कसं", "कधी", "कुठे",
                       "पुन्हा सांगा", "नीट ऐकू आलं नाही", "कळलं नाही",
                       "समजलं नाही", "परत सांगा"]
    if any(text_lower == q or text_lower.startswith(q) for q in short_questions):
        logger.info(f"[QUESTION DETECTED] Short question: '{text[:40]}'")
        return True
    # Short responses (1-3 words) that aren't in short_questions — treat as answers
    if len(text.split()) <= 3:
        return False
    # Question indicators in Marathi
    q_indicators = ["काय", "कसं", "कोणत", "का ", "कधी", "कुठ", "का?",
                    "सांगा", "माहिती", "किंमत", "price", "rate", "उपलब्ध",
                    "विचारतोय", "सांगू शकाल", "आहेत का", "हवी", "हवं",
                    "द्या ना", "बोला", "?", "कसे", "कसा", "कोणत्या सुविधा",
                    "कोणते उत्पादन", "कोणत्या सेवा", "आहेत", "बद्दल"]
    if any(w in text_lower for w in q_indicators):
        logger.info(f"[QUESTION DETECTED] '{text[:40]}' matched question indicator")
        return True
    # Only flag as question if very long (>8 words)
    if len(text.split()) > 8:
        return True
    return False


# ═══════════════════════════════════════════════════════════════
# STATE MACHINE — process_turn
# ═══════════════════════════════════════════════════════════════

async def process_turn(user_text: str, session: dict) -> str:
    """
    State machine for the Lucky Draw pitch-first call flow.

    Primary flow: Greeting → Lucky Draw Details → Gifts → Rules → Ask Order → Address → Thank You
    Secondary: If farmer asks about products/crops → FAQ answers, then returns to scheme flow.
    """
    step = session.get("step", "greet")
    logger.info(f"[GRAPH] Step={step}, Input='{user_text[:40]}'")

    if "conversation" not in session:
        session["conversation"] = []

    # ── GREET ─────────────────────────────────────────────────
    if step == "greet":
        session["step"] = "ask_availability"
        session["conversation"].append({"role": "bot", "text": GREETING})
        session_manager.update(session["call_sid"], session)
        return GREETING

    # ── ASK AVAILABILITY ──────────────────────────────────────
    if step == "ask_availability":
        session["conversation"].append({"role": "farmer", "text": user_text})
        if _is_no(user_text):
            session["step"] = "done"
            session["should_close"] = True
            session_manager.update(session["call_sid"], session)
            return NO_TIME_RESPONSE

        # Go directly to scheme details (Lucky Draw is the main pitch)
        session["step"] = "scheme_details"
        from src.core.offerEngine.scheme import SCHEME_DETAILS
        session["conversation"].append({"role": "bot", "text": SCHEME_DETAILS})
        session_manager.update(session["call_sid"], session)
        return SCHEME_DETAILS

    # ── SCHEME DETAILS → GIFTS ────────────────────────────────
    if step == "scheme_details":
        session["conversation"].append({"role": "farmer", "text": user_text})
        if _is_no(user_text):
            session["step"] = "done"
            session["should_close"] = True
            session["conversation"].append({"role": "bot", "text": THANK_YOU})
            session_manager.update(session["call_sid"], session)
            return THANK_YOU
        if _is_question(user_text):
            faq = try_faq(user_text)
            reply = faq if faq else await call_claude(session["conversation"])
            if reply:
                session["conversation"].append({"role": "bot", "text": reply})
                session_manager.update(session["call_sid"], session)
                return reply
        session["step"] = "scheme_gifts"
        from src.core.offerEngine.scheme import SCHEME_GIFTS
        session["conversation"].append({"role": "bot", "text": SCHEME_GIFTS})
        session_manager.update(session["call_sid"], session)
        return SCHEME_GIFTS

    # ── SCHEME GIFTS → RULES ─────────────────────────────────
    if step == "scheme_gifts":
        session["conversation"].append({"role": "farmer", "text": user_text})
        if _is_no(user_text):
            session["step"] = "done"
            session["should_close"] = True
            session["conversation"].append({"role": "bot", "text": THANK_YOU})
            session_manager.update(session["call_sid"], session)
            return THANK_YOU
        if _is_question(user_text):
            faq = try_faq(user_text)
            reply = faq if faq else await call_claude(session["conversation"])
            if reply:
                session["conversation"].append({"role": "bot", "text": reply})
                session_manager.update(session["call_sid"], session)
                return reply
        session["step"] = "scheme_rules"
        from src.core.offerEngine.scheme import SCHEME_RULES
        session["conversation"].append({"role": "bot", "text": SCHEME_RULES})
        session_manager.update(session["call_sid"], session)
        return SCHEME_RULES

    # ── SCHEME RULES → ASK ORDER ──────────────────────────────
    if step == "scheme_rules":
        session["conversation"].append({"role": "farmer", "text": user_text})
        if _is_no(user_text):
            session["step"] = "done"
            session["should_close"] = True
            session["conversation"].append({"role": "bot", "text": THANK_YOU})
            session_manager.update(session["call_sid"], session)
            return THANK_YOU
        if _is_question(user_text):
            faq = try_faq(user_text)
            reply = faq if faq else await call_claude(session["conversation"])
            if reply:
                session["conversation"].append({"role": "bot", "text": reply})
                session_manager.update(session["call_sid"], session)
                return reply
        session["step"] = "scheme_end"
        from src.core.offerEngine.scheme import SCHEME_END
        session["conversation"].append({"role": "bot", "text": SCHEME_END})
        session_manager.update(session["call_sid"], session)
        return SCHEME_END

    # ── SCHEME END → ORDER OR DONE ────────────────────────────
    if step == "scheme_end":
        session["conversation"].append({"role": "farmer", "text": user_text})
        if _is_question(user_text):
            faq = try_faq(user_text)
            reply = faq if faq else await call_claude(session["conversation"])
            if reply:
                session["conversation"].append({"role": "bot", "text": reply})
                session_manager.update(session["call_sid"], session)
                return reply
        if _is_yes(user_text):
            # Farmer wants to order → ask address
            session["step"] = "ask_address"
            session["conversation"].append({"role": "bot", "text": Q_ADDRESS})
            session_manager.update(session["call_sid"], session)
            return Q_ADDRESS
        # Farmer said no or unclear → thank and end
        session["step"] = "done"
        session["should_close"] = True
        session["conversation"].append({"role": "bot", "text": THANK_YOU})
        session_manager.update(session["call_sid"], session)
        return THANK_YOU

    # ── ASK ADDRESS ───────────────────────────────────────────
    if step == "ask_address":
        session["conversation"].append({"role": "farmer", "text": user_text})
        if _is_question(user_text):
            faq = try_faq(user_text)
            reply = faq if faq else await call_claude(session["conversation"])
            if reply:
                session["conversation"].append({"role": "bot", "text": reply})
                session_manager.update(session["call_sid"], session)
                return reply
        session["address"] = user_text
        session["step"] = "ask_crop"
        # After address, ask about crop for product recommendation
        session["conversation"].append({"role": "bot", "text": ASK_CROP})
        session_manager.update(session["call_sid"], session)
        return ASK_CROP

    # ── ASK CROP ──────────────────────────────────────────────
    if step == "ask_crop":
        session["conversation"].append({"role": "farmer", "text": user_text})
        if _is_question(user_text):
            faq = try_faq(user_text)
            if faq:
                reply = faq + " तर सर, तुम्ही कोणतं पीक लावलंय?"
            else:
                reply = await call_claude(session["conversation"])
                if reply:
                    reply = reply + " तर सर, तुम्ही कोणतं पीक लावलंय?"
                else:
                    reply = RE_ASK_CROP
            session["conversation"].append({"role": "bot", "text": reply})
            session_manager.update(session["call_sid"], session)
            return reply
        generic = ["ठीक", "ok", "बरं", "हो", "ओके", "अच्छा"]
        if any(user_text.strip().lower() == g for g in generic) or len(user_text.strip()) <= 3:
            session["conversation"].append({"role": "bot", "text": RE_ASK_CROP})
            session_manager.update(session["call_sid"], session)
            return RE_ASK_CROP
        session["crop"] = user_text
        session["step"] = "recommend_product"
        # Recommend products based on crop
        from src.core.productKnowledge.products import CYMINT_RECOMMENDATION
        session["conversation"].append({"role": "bot", "text": CYMINT_RECOMMENDATION})
        session_manager.update(session["call_sid"], session)
        return CYMINT_RECOMMENDATION

    # ── RECOMMEND PRODUCT → CONFIRM ORDER ─────────────────────
    if step == "recommend_product":
        session["conversation"].append({"role": "farmer", "text": user_text})
        if _is_question(user_text):
            faq = try_faq(user_text)
            reply = faq if faq else await call_claude(session["conversation"])
            if reply:
                session["conversation"].append({"role": "bot", "text": reply})
                session_manager.update(session["call_sid"], session)
                return reply
        # End call with thank you regardless
        session["step"] = "done"
        session["should_close"] = True
        session["conversation"].append({"role": "bot", "text": THANK_YOU})
        session_manager.update(session["call_sid"], session)
        return THANK_YOU

    # ── DONE ──────────────────────────────────────────────────
    if step == "done":
        session["should_close"] = True
        return THANK_YOU

    return THANK_YOU
