"""
Auto-detect dialect from the farmer's spoken response.

Analyzes speech text for regional Marathi dialect markers.
NOTE: STT may transcribe Marathi dialect words as Hindi approximations
depending on the speech model. We match both native Marathi
and Hindi-transcribed versions.

- Marathwada: व्हय, हाय, तुमास्नी, नाय, बरं, की, etc.
- Vidarbha: हाये, तुमाले, ना, न्हाय, हायेत, ले, etc.
- Standard: default if no regional markers detected
"""
import logging

logger = logging.getLogger(__name__)

# Marathwada dialect markers
# Includes both native Marathi spelling AND Hindi transcription variants
MARATHWADA_MARKERS = [
    # Native Marathi
    "व्हय", "हाय", "तुमास्नी", "नाय", "बरं हाय", "सांगा की",
    "हायत", "करतोय", "बोला की", "काय बा", "घ्यायचं हाय",
    "लागतंय", "मारलं", "केलं", "गेलं", "आलं", "बसलो",
    "जातोय", "येतोय", "करा की", "द्या की", "मिळालं",
    "हाय की", "सांगतो की",
    # Hindi transcription variants (how STT may hear Marathwada Marathi)
    "वही", "वहय", "है की", "बोलो की", "करो की", "दो की",
    "है बा", "काय बा", "बोला की", "बरा है",
]

# Vidarbha dialect markers
VIDARBHA_MARKERS = [
    # Native Marathi
    "हाये", "तुमाले", "हायेत", "नाय ना", "सांगा ना",
    "पिकाले", "मले", "तुमच्याले", "आमाले", "कराना",
    "बोला ना", "द्या ना", "घ्या ना", "चाललंय",
    "हाये ना", "करतोय ना", "ना बा", "काय ना",
    # Hindi transcription variants (how Twilio hears Vidarbha Marathi)
    "है ये", "बोलो ना", "करो ना", "दो ना", "है ना",
    "को", "मुझको", "तुमको", "हमको", "चल रहा",
]

# Strong markers — single match = high confidence detection
STRONG_MARATHWADA = ["व्हय", "वही", "वहय", "हाय की", "बोला की", "तुमास्नी", "है की"]
STRONG_VIDARBHA = ["हाये", "है ये", "तुमाले", "मले", "पिकाले", "आमाले", "बोला ना"]


def detect_dialect_from_speech(text: str) -> str | None:
    """
    Detect dialect from spoken text by looking for regional markers.

    Returns:
        "marathwada", "vidarbha", or None if no clear markers found
    """
    if not text or len(text.strip()) < 2:
        return None

    text_lower = text.lower().strip()

    # Check strong markers first (high confidence, single match enough)
    for marker in STRONG_MARATHWADA:
        if marker in text:
            logger.info(f"[DIALECT] Strong marathwada marker: '{marker}' in '{text}'")
            return "marathwada"

    for marker in STRONG_VIDARBHA:
        if marker in text:
            logger.info(f"[DIALECT] Strong vidarbha marker: '{marker}' in '{text}'")
            return "vidarbha"

    # Score-based detection for weaker signals
    marathwada_score = 0
    vidarbha_score = 0

    for marker in MARATHWADA_MARKERS:
        if marker in text or marker in text_lower:
            marathwada_score += 1

    for marker in VIDARBHA_MARKERS:
        if marker in text or marker in text_lower:
            vidarbha_score += 1

    if marathwada_score > vidarbha_score and marathwada_score >= 1:
        logger.info(f"[DIALECT] Detected marathwada (score={marathwada_score}) from: '{text}'")
        return "marathwada"
    elif vidarbha_score > marathwada_score and vidarbha_score >= 1:
        logger.info(f"[DIALECT] Detected vidarbha (score={vidarbha_score}) from: '{text}'")
        return "vidarbha"

    return None
