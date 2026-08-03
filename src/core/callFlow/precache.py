"""
Pre-caching logic for all scripted responses at startup.
"""
import re
import logging

from src.adapters.tts.sarvam_tts import pre_cache_audio
from src.core.callFlow.scripts import (
    ALL_SCRIPTED_TEXTS, COMPANY_INTRO, COMPANY_INTRO_2, ASK_CROP,
)

logger = logging.getLogger(__name__)


def _split_long_text(text: str) -> list:
    """Split long text into chunks at natural sentence boundaries."""
    sentences = re.split(r'(?<=\.)\s+|(?<=,)\s+(?=अन्)|(?<=,)\s+(?=तसंच)', text)

    result = []
    for s in sentences:
        if len(s) > 120:
            sub_parts = s.split(', ')
            current = ""
            for sp in sub_parts:
                if len(current) + len(sp) < 100:
                    current += (", " if current else "") + sp
                else:
                    if current:
                        result.append(current)
                    current = sp
            if current:
                result.append(current)
        else:
            result.append(s)

    return [r.strip() for r in result if r.strip()]


async def pre_cache_static_responses():
    """Pre-cache all scripted responses at startup."""
    logger.info("[GRAPH] Pre-caching all scripted responses...")
    for text in ALL_SCRIPTED_TEXTS:
        await pre_cache_audio(text)

    # Also cache combined intro
    full_intro = COMPANY_INTRO + " " + COMPANY_INTRO_2 + " " + ASK_CROP
    splits = _split_long_text(full_intro)
    for part in splits:
        await pre_cache_audio(part.strip())

    logger.info("[GRAPH] Pre-caching complete!")
