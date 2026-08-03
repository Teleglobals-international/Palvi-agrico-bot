"""
Claude/Bedrock fallback — only for off-script / unexpected farmer inputs.
"""
import json
import logging
import asyncio
import boto3

from src.config.settings import settings

logger = logging.getLogger(__name__)

CLAUDE_SYSTEM = """तू पाल्वी ॲग्रिको कंपनीची ॲग्री डॉक्टर पूजा आहेस.
तुझी भाषा: शुद्ध मराठी (सोपी, विनम्र, व्यावसायिक). ग्रामीण बोली वापरू नकोस.
शेतकऱ्याने प्रश्न विचारला आहे. त्याचे उत्तर दे.
उत्तर 2-3 वाक्यांपेक्षा जास्त नको.
कधीही हिंदी, markdown, इंग्रजी वापरू नकोस. फक्त मराठी.

उत्पादने:
- सायमिंट: किटकनाशक, पांढरी माशी/मावा/तुडतुडे वर, चारशे मिली प्रती एकर, दोनशे लिटर पाणी, किंमत पाचशे चौतीस रुपये.
- साइज प्लस: पीकपोषक, समुद्री शैवाल अर्क, पाचशे मिली प्रती एकर, दोनशे लिटर पाणी, किंमत पाचशे पस्तीस रुपये.
- स्प्रे पंप: बॅटरी आणि पेट्रोल दोन्ही उपलब्ध. मजबूत, टिकाऊ, औषधाचा समान प्रसार.
- ताडपत्री: धान्य आणि खत सुरक्षित ठेवायला.
- तणनाशक, बुरशीनाशक: उपलब्ध आहे, विशिष्ट उत्पादनांची माहिती कॉलनंतर पाठवू.

सेवा: पीक लागवडीपासून काढणीपर्यंत मार्गदर्शन, शेती साहित्य डिलिव्हरी.
"""

_bedrock_client = None


def _get_bedrock_client():
    global _bedrock_client
    if _bedrock_client is None:
        _bedrock_client = boto3.client("bedrock-runtime", region_name=settings.AWS_REGION)
    return _bedrock_client


def _call_claude_sync(conversation_history: list) -> str:
    """Call Claude for off-script questions only."""
    try:
        bedrock = _get_bedrock_client()
        messages = []
        for turn in conversation_history[-6:]:  # Only last 6 turns for speed
            if turn["role"] == "farmer":
                messages.append({"role": "user", "content": turn["text"]})
            elif turn["role"] == "bot":
                messages.append({"role": "assistant", "content": turn["text"]})
        if not messages or messages[-1]["role"] != "user":
            messages.append({"role": "user", "content": "पुढे बोला"})

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 60,
            "temperature": 0.3,
            "system": CLAUDE_SYSTEM,
            "messages": messages,
        })

        response = bedrock.invoke_model(
            modelId="us.anthropic.claude-sonnet-4-6",
            body=body,
        )
        result = json.loads(response["body"].read())
        reply = result["content"][0]["text"].strip()
        logger.info(f"[CLAUDE] Reply: '{reply[:60]}'")
        return reply
    except Exception as e:
        logger.error(f"[CLAUDE] Error: {e}")
        return ""


async def call_claude(conversation_history: list) -> str:
    """Async wrapper for Claude call (runs in thread pool)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _call_claude_sync, conversation_history)
