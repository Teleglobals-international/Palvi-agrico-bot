"""
B3 — Fast intent classifier on partial transcripts.

Matches farmer's speech against expected patterns at each conversation step.
Uses simple keyword/regex matching — no ML model needed.
If a confident match is found on a partial transcript, returns immediately
without waiting for STT to finalize.
"""
import re
import logging

logger = logging.getLogger(__name__)

# Expected answer patterns per conversation step
STEP_PATTERNS = {
    "ask_availability": {
        "yes": ["हो", "होय", "हा", "व्हय", "बोला", "सांगा", "वेळ", "हाय", "आहे", "yes", "ha", "ok"],
        "no": ["नाही", "नाय", "नको", "नंतर", "वेळ नाय", "busy"],
    },
    "ask_crop": {
        "cotton": ["कापूस", "कापस", "कपास", "cotton", "kapus"],
        "soybean": ["सोयाबीन", "सोया", "soybean", "soya"],
        "tur": ["तूर", "तुर", "tur", "toor"],
        "maize": ["मका", "मक्का", "maize", "makka"],
        "turmeric": ["हळद", "हल्दी", "turmeric", "halad"],
        "ginger": ["आलं", "आले", "ginger", "aale"],
    },
    "yes_no": {
        "yes": ["हो", "होय", "हा", "व्हय", "चालेल", "बरं", "पाठवा", "करा", "घ्यायचं", "yes", "ok"],
        "no": ["नाही", "नाय", "नको", "न्हाय", "नग", "राहू दे", "no", "nahi"],
    },
    "pest_name": {
        "pandhari_mashi": ["पांढरी माशी", "पांढरी", "माशी", "whitefly"],
        "mava": ["मावा", "mava", "aphid"],
        "tudtude": ["तुडतुडे", "tudtude", "jassid"],
        "bollworm": ["बोंड अळी", "बोंडअळी", "bollworm"],
    },
}


def classify_partial(text: str, step: str) -> dict | None:
    """
    Classify a partial/interim transcript against expected patterns for the step.

    Returns:
        {"intent": "crop", "value": "cotton", "confidence": "high"} or None
    """
    if not text or len(text.strip()) < 2:
        return None

    text_lower = text.lower().strip()

    # Determine which pattern set to use
    if step in ("ask_crop", "ask_crop_after_intro"):
        patterns = STEP_PATTERNS["ask_crop"]
        for crop, keywords in patterns.items():
            for kw in keywords:
                if kw in text or kw in text_lower:
                    logger.info(f"[CLASSIFIER] Matched crop '{crop}' from partial: '{text}'")
                    return {"intent": "crop", "value": crop, "confidence": "high"}

    elif step == "ask_availability":
        patterns = STEP_PATTERNS["ask_availability"]
        for intent, keywords in patterns.items():
            for kw in keywords:
                if kw in text or kw in text_lower:
                    logger.info(f"[CLASSIFIER] Matched availability '{intent}' from partial: '{text}'")
                    return {"intent": "availability", "value": intent, "confidence": "high"}

    elif step in ("ask_pest", "ask_fungal", "ask_growth", "confirm_order",
                  "pitch_pump", "cross_sell_pump", "ask_other_info"):
        patterns = STEP_PATTERNS["yes_no"]
        for intent, keywords in patterns.items():
            for kw in keywords:
                if kw in text or kw in text_lower:
                    logger.info(f"[CLASSIFIER] Matched yes/no '{intent}' from partial: '{text}'")
                    return {"intent": "yes_no", "value": intent, "confidence": "high"}

    elif step == "identify_pest":
        patterns = STEP_PATTERNS["pest_name"]
        for pest, keywords in patterns.items():
            for kw in keywords:
                if kw in text or kw in text_lower:
                    logger.info(f"[CLASSIFIER] Matched pest '{pest}' from partial: '{text}'")
                    return {"intent": "pest", "value": pest, "confidence": "high"}

    # Check for numeric patterns (acres, days)
    if step in ("ask_acres", "ask_days"):
        numbers = re.findall(r'\d+', text)
        if numbers:
            logger.info(f"[CLASSIFIER] Matched number '{numbers[0]}' from partial: '{text}'")
            return {"intent": "number", "value": numbers[0], "confidence": "high"}

    return None
