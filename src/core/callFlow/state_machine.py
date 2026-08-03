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
    State machine for the call script.
    Hardcoded questions = instant (pre-cached TTS).
    Claude only called for off-script farmer questions.
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

        session["step"] = "ask_crop"
        full_intro = COMPANY_INTRO + " " + COMPANY_INTRO_2 + " " + ASK_CROP
        session["conversation"].append({"role": "bot", "text": full_intro})
        session_manager.update(session["call_sid"], session)
        return full_intro

    # ── ASK CROP ──────────────────────────────────────────────
    if step == "ask_crop":
        session["conversation"].append({"role": "farmer", "text": user_text})
        # Check if farmer asked a question instead of answering
        if _is_question(user_text):
            # Try FAQ first (instant, pre-cached)
            faq = try_faq(user_text)
            if faq:
                reply = faq + " तर सर, तुम्ही कोणतं पीक लावलंय?"
            else:
                # Fall back to Claude
                reply = await call_claude(session["conversation"])
                if reply:
                    reply = reply + " तर सर, तुम्ही कोणतं पीक लावलंय?"
                else:
                    reply = RE_ASK_CROP
            session["conversation"].append({"role": "bot", "text": reply})
            session_manager.update(session["call_sid"], session)
            return reply
        # If farmer said something very generic like "ठीक आहे", "ok", "बरं"
        # without giving a crop name, re-ask
        generic = ["ठीक", "ok", "बरं", "हो", "ओके", "अच्छा"]
        if any(user_text.strip().lower() == g for g in generic) or len(user_text.strip()) <= 3:
            session["conversation"].append({"role": "bot", "text": RE_ASK_CROP})
            session_manager.update(session["call_sid"], session)
            return RE_ASK_CROP
        # Store crop and move to acreage
        session["crop"] = user_text
        session["step"] = "ask_acreage"
        session["conversation"].append({"role": "bot", "text": Q_ACREAGE})
        session_manager.update(session["call_sid"], session)
        return Q_ACREAGE

    # ── ASK ACREAGE ───────────────────────────────────────────
    if step == "ask_acreage":
        session["conversation"].append({"role": "farmer", "text": user_text})
        if _is_question(user_text):
            faq = try_faq(user_text)
            reply = faq if faq else await call_claude(session["conversation"])
            if reply:
                session["conversation"].append({"role": "bot", "text": reply})
                session_manager.update(session["call_sid"], session)
                return reply
        session["acreage"] = user_text
        session["step"] = "ask_variety"
        session["conversation"].append({"role": "bot", "text": Q_VARIETY})
        session_manager.update(session["call_sid"], session)
        return Q_VARIETY

    # ── ASK VARIETY ───────────────────────────────────────────
    if step == "ask_variety":
        session["conversation"].append({"role": "farmer", "text": user_text})
        if _is_question(user_text):
            faq = try_faq(user_text)
            reply = faq if faq else await call_claude(session["conversation"])
            if reply:
                session["conversation"].append({"role": "bot", "text": reply})
                session_manager.update(session["call_sid"], session)
                return reply
        session["variety"] = user_text
        session["step"] = "ask_days"
        session["conversation"].append({"role": "bot", "text": Q_DAYS})
        session_manager.update(session["call_sid"], session)
        return Q_DAYS

    # ── ASK DAYS ──────────────────────────────────────────────
    if step == "ask_days":
        session["conversation"].append({"role": "farmer", "text": user_text})
        if _is_question(user_text):
            faq = try_faq(user_text)
            reply = faq if faq else await call_claude(session["conversation"])
            if reply:
                session["conversation"].append({"role": "bot", "text": reply})
                session_manager.update(session["call_sid"], session)
                return reply
        session["days"] = user_text
        session["step"] = "ask_weather"
        session["conversation"].append({"role": "bot", "text": Q_WEATHER})
        session_manager.update(session["call_sid"], session)
        return Q_WEATHER

    # ── ASK WEATHER ───────────────────────────────────────────
    if step == "ask_weather":
        session["conversation"].append({"role": "farmer", "text": user_text})
        if _is_question(user_text):
            faq = try_faq(user_text)
            reply = faq if faq else await call_claude(session["conversation"])
            if reply:
                session["conversation"].append({"role": "bot", "text": reply})
                session_manager.update(session["call_sid"], session)
                return reply
        session["weather"] = user_text
        session["step"] = "ask_pest"
        session["conversation"].append({"role": "bot", "text": Q_PEST})
        session_manager.update(session["call_sid"], session)
        return Q_PEST

    # ── ASK PEST ──────────────────────────────────────────────
    if step == "ask_pest":
        session["conversation"].append({"role": "farmer", "text": user_text})
        if _is_question(user_text):
            faq = try_faq(user_text)
            reply = faq if faq else await call_claude(session["conversation"])
            if reply:
                session["conversation"].append({"role": "bot", "text": reply})
                session_manager.update(session["call_sid"], session)
                return reply
        if _is_no(user_text):
            # No pest → ask about growth directly
            session["step"] = "ask_growth"
            session["conversation"].append({"role": "bot", "text": Q_GROWTH})
            session_manager.update(session["call_sid"], session)
            return Q_GROWTH
        # Yes pest → ask which pest
        session["step"] = "ask_which_pest"
        session["conversation"].append({"role": "bot", "text": Q_WHICH_PEST})
        session_manager.update(session["call_sid"], session)
        return Q_WHICH_PEST

    # ── ASK WHICH PEST ────────────────────────────────────────
    if step == "ask_which_pest":
        session["conversation"].append({"role": "farmer", "text": user_text})
        if _is_question(user_text):
            faq = try_faq(user_text)
            reply = faq if faq else await call_claude(session["conversation"])
            if reply:
                session["conversation"].append({"role": "bot", "text": reply})
                session_manager.update(session["call_sid"], session)
                return reply
        session["pest"] = user_text
        session["step"] = "ask_pest_level"
        session["conversation"].append({"role": "bot", "text": Q_PEST_LEVEL})
        session_manager.update(session["call_sid"], session)
        return Q_PEST_LEVEL

    # ── ASK PEST LEVEL → RECOMMEND CYMINT ─────────────────────
    if step == "ask_pest_level":
        session["conversation"].append({"role": "farmer", "text": user_text})
        session["step"] = "after_cymint"
        session["conversation"].append({"role": "bot", "text": CYMINT_RECOMMENDATION})
        session_manager.update(session["call_sid"], session)
        return CYMINT_RECOMMENDATION

    # ── AFTER CYMINT → ASK GROWTH ─────────────────────────────
    if step == "after_cymint":
        session["conversation"].append({"role": "farmer", "text": user_text})
        if _is_question(user_text):
            reply = await call_claude(session["conversation"])
            if reply:
                session["conversation"].append({"role": "bot", "text": reply})
                session_manager.update(session["call_sid"], session)
                return reply
        session["step"] = "ask_growth"
        session["conversation"].append({"role": "bot", "text": Q_GROWTH})
        session_manager.update(session["call_sid"], session)
        return Q_GROWTH

    # ── ASK GROWTH → SIZE PLUS ────────────────────────────────
    if step == "ask_growth":
        session["conversation"].append({"role": "farmer", "text": user_text})
        if _is_no(user_text) or "नाय" in user_text or "कमी" in user_text or "नाही" in user_text:
            # Growth is bad → recommend Size Plus
            session["step"] = "after_size_plus"
            session["conversation"].append({"role": "bot", "text": SIZE_PLUS_RECOMMENDATION})
            session_manager.update(session["call_sid"], session)
            return SIZE_PLUS_RECOMMENDATION
        # Growth is good → skip to both products
        session["step"] = "both_products"
        session["conversation"].append({"role": "bot", "text": BOTH_PRODUCTS})
        session_manager.update(session["call_sid"], session)
        return BOTH_PRODUCTS

    # ── AFTER SIZE PLUS → BOTH PRODUCTS ───────────────────────
    if step == "after_size_plus":
        session["conversation"].append({"role": "farmer", "text": user_text})
        session["step"] = "both_products"
        session["conversation"].append({"role": "bot", "text": BOTH_PRODUCTS})
        session_manager.update(session["call_sid"], session)
        return BOTH_PRODUCTS

    # ── BOTH PRODUCTS → FERTILIZER ────────────────────────────
    if step == "both_products":
        session["conversation"].append({"role": "farmer", "text": user_text})
        if _is_question(user_text):
            faq = try_faq(user_text)
            reply = faq if faq else await call_claude(session["conversation"])
            if reply:
                session["conversation"].append({"role": "bot", "text": reply})
                session_manager.update(session["call_sid"], session)
                return reply
        session["step"] = "ask_fertilizer"
        session["conversation"].append({"role": "bot", "text": Q_FERTILIZER})
        session_manager.update(session["call_sid"], session)
        return Q_FERTILIZER

    # ── FERTILIZER → ORDER ────────────────────────────────────
    if step == "ask_fertilizer":
        session["conversation"].append({"role": "farmer", "text": user_text})
        session["step"] = "ask_order"
        session["conversation"].append({"role": "bot", "text": Q_ORDER})
        session_manager.update(session["call_sid"], session)
        return Q_ORDER

    # ── ORDER CONFIRMATION ────────────────────────────────────
    if step == "ask_order":
        session["conversation"].append({"role": "farmer", "text": user_text})
        if _is_no(user_text):
            # Skip to pump cross-sell
            session["step"] = "ask_pump"
            session["conversation"].append({"role": "bot", "text": Q_PUMP})
            session_manager.update(session["call_sid"], session)
            return Q_PUMP
        # Yes → ask address
        session["step"] = "ask_address"
        session["conversation"].append({"role": "bot", "text": Q_ADDRESS})
        session_manager.update(session["call_sid"], session)
        return Q_ADDRESS

    # ── ASK ADDRESS ───────────────────────────────────────────
    if step == "ask_address":
        session["conversation"].append({"role": "farmer", "text": user_text})
        session["address"] = user_text
        session["step"] = "ask_pump"
        session["conversation"].append({"role": "bot", "text": Q_PUMP})
        session_manager.update(session["call_sid"], session)
        return Q_PUMP

    # ── ASK PUMP ──────────────────────────────────────────────
    if step == "ask_pump":
        session["conversation"].append({"role": "farmer", "text": user_text})
        if _is_question(user_text):
            faq = try_faq(user_text)
            reply = faq if faq else await call_claude(session["conversation"])
            if reply:
                session["conversation"].append({"role": "bot", "text": reply})
                session_manager.update(session["call_sid"], session)
                return reply
        # Regardless of what they say about current pump, offer ours
        session["step"] = "pump_offer"
        session["conversation"].append({"role": "bot", "text": Q_PUMP_OFFER})
        session_manager.update(session["call_sid"], session)
        return Q_PUMP_OFFER

    # ── PUMP OFFER → handle farmer's interest ─────────────────
    if step == "pump_offer":
        session["conversation"].append({"role": "farmer", "text": user_text})
        if _is_yes(user_text):
            # Farmer interested — give brief confirmation and move on
            session["conversation"].append({"role": "bot", "text": FAQ_PUMP_CONFIRM})
            session["step"] = "ask_other_crop"
            session_manager.update(session["call_sid"], session)
            return FAQ_PUMP_CONFIRM
        if _is_question(user_text):
            faq = try_faq(user_text)
            reply = faq if faq else await call_claude(session["conversation"])
            if reply:
                session["conversation"].append({"role": "bot", "text": reply})
                session_manager.update(session["call_sid"], session)
                return reply
        # Farmer said no or anything else → move on
        session["step"] = "ask_other_crop"
        session["conversation"].append({"role": "bot", "text": Q_OTHER_CROP})
        session_manager.update(session["call_sid"], session)
        return Q_OTHER_CROP

    # ── OTHER CROP → SCHEME PITCH ───────────────────────────
    if step == "ask_other_crop":
        session["conversation"].append({"role": "farmer", "text": user_text})
        # Only restart if farmer explicitly says yes with a clear affirmative
        explicit_yes = ["हो", "होय", "हा", "व्हय", "सांगा", "हवी"]
        if any(w in user_text.lower().split() for w in explicit_yes) and "नाही" not in user_text.lower():
            # Restart from crop question
            session["step"] = "ask_crop"
            session["conversation"].append({"role": "bot", "text": ASK_CROP})
            session_manager.update(session["call_sid"], session)
            return ASK_CROP
        # Offer scheme before ending
        session["step"] = "scheme_pitch"
        session["conversation"].append({"role": "bot", "text": SCHEME_PITCH})
        session_manager.update(session["call_sid"], session)
        return SCHEME_PITCH

    # ── SCHEME PITCH ──────────────────────────────────────────
    if step == "scheme_pitch":
        session["conversation"].append({"role": "farmer", "text": user_text})
        if _is_no(user_text):
            # Not interested → end call
            session["step"] = "done"
            session["should_close"] = True
            session["conversation"].append({"role": "bot", "text": THANK_YOU})
            session_manager.update(session["call_sid"], session)
            return THANK_YOU
        # If yes OR unclear (farmer didn't say no) → give details
        session["step"] = "scheme_details"
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
        session["conversation"].append({"role": "bot", "text": SCHEME_RULES})
        session_manager.update(session["call_sid"], session)
        return SCHEME_RULES

    # ── SCHEME RULES → END ────────────────────────────────────
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
        session["conversation"].append({"role": "bot", "text": SCHEME_END})
        session_manager.update(session["call_sid"], session)
        return SCHEME_END

    # ── SCHEME END → DONE ─────────────────────────────────────
    if step == "scheme_end":
        session["conversation"].append({"role": "farmer", "text": user_text})
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
