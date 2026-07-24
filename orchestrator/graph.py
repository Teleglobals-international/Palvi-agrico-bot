"""
Palvi Agrico — State Machine + Claude Fallback.

Hardcoded scripted questions for instant response (0ms TTS from cache).
Claude is only called when farmer asks off-script questions or gives
unexpected answers that need interpretation.
"""
import json
import logging
import boto3
from services.session_manager import SessionManager
from services.sarvam_tts import pre_cache_audio
from app.config import settings

logger = logging.getLogger(__name__)
session_manager = SessionManager()

# ═══════════════════════════════════════════════════════════════
# ALL SCRIPTED RESPONSES (pre-cached at startup = 0ms TTS)
# ═══════════════════════════════════════════════════════════════

GREETING = "नमस्कार सर, मी पाल्वी ॲग्रिको कंपनी पुणे मधून ॲग्री डॉक्टर पूजा बोलतेय. मी तुम्हासनी शेती संदर्भात म्हाइती देण्याकरिता हा कॉल केलाय. तुम्हासनी आत्ता बोलण्यासाठी पाच मिनिटं वेळ हाय का?"
NO_TIME_RESPONSE = "ठीक हाय सर, काय हरकत न्हाई. मी नंतर कॉल करते. येते!"
COMPANY_INTRO = "सर, आपली पाल्वी ॲग्रिको कंपनी शेतकऱ्यांना पीक लागवडीपासून ते काढणीपर्यंतची समदी म्हाइती अन् मार्गदर्शन देते."
COMPANY_INTRO_2 = "तसंच शेतीसाठी लागणारं समदं किटकनाशक, बुरशीनाशक, तणनाशक, ताडपत्री, स्प्रे पंप, अन् हार्डवेअरचं साहित्य आपल्याकडं उपलब्ध हाय."
ASK_CROP = "आता सध्या खरीप हंगाम चालू झालाय तर सर मले कळंल का तुम्ही कोणत्या पिकाची लागवड केलीया? त्या संदर्भात म्हाइती देण्यासाठीच मी हा कॉल केलाय."
NO_INPUT_RESPONSE = "सर, तुमचा आवाज नीट ऐकू आला नाय. जरा मोठ्यानं सांगा."
THANK_YOU = "शेवटी कॉलवर पाल्वी ॲग्रिकोला वेळ दिल्याबद्दल आभारी हाय सर. आपला दिवस शुभ जावो!"

# Scripted questions (one per step, all pre-cached)
Q_ACREAGE = "बरं सर, किती एकरात लागवड केलीया?"
Q_VARIETY = "बरं सर, कोणती जात लावलीया?"
Q_DAYS = "बरं सर, लागवडीला किती दिवस झाले?"
Q_WEATHER = "बरं सर, तुमच्या भागात पाऊस झाला का?"
Q_PEST = "बरं सर, पिकावर काही कीड किंवा रोग दिसतोय का?"
Q_WHICH_PEST = "बरं सर, कोणती कीड दिसतेय?"
Q_PEST_LEVEL = "बरं सर, किती प्रमाणात दिसतेय, कमी हाय का जास्त?"
Q_GROWTH = "बरं सर, पिकाची वाढ कशी दिसतेय, जोमदार हाय का?"
Q_FERTILIZER = "बरं सर, खतांचं नियोजन केलंय का आधी?"
Q_ORDER = "बरं सर, मग सायमिंट अन् साइज प्लस दोन्ही ठेवू का तुमच्याकडं? दोन्ही मिळून एक हजार एकोणसत्तर रुपये होत्यात."
Q_ADDRESS = "बरं सर, तुमचा पूर्ण पत्ता सांगा, पिन कोड अन् जवळचा लँडमार्क."
Q_PUMP = "सर, सध्या फवारणीसाठी कोणता स्प्रे पंप वापरतात?"
Q_PUMP_OFFER = "सर, आमच्याकडं मजबूत अन् टिकाऊ बॅटरी पंप उपलब्ध हायत. औषधाचा समान प्रसार होतो. नवीन पंप बघायचा हाय का?"
Q_OTHER_CROP = "सर, याच्या व्यतिरिक्त आणखी कोणत्या पिकाची म्हाइती हवी हाय का?"

# Product recommendations (pre-cached)
CYMINT_RECOMMENDATION = "सर, यासाठी आमच्याकडं सायमिंट हाय. चारशे मिली एक एकराला, दोनशे लिटर पाण्यात फवारा. रसशोषक किडी लगेच मरत्यात. तुमच्याकडं ठेवू का?"
SIZE_PLUS_RECOMMENDATION = "सर, वाढीसाठी आमचं साइज प्लस हाय. पाचशे मिली एक एकराला, दोनशे लिटर पाण्यात फवारा. मुळं मजबूत होत्यात अन् वाढ जोमदार होते. ठेवू का?"
BOTH_PRODUCTS = "सर, दोन्ही एकत्र फवारता येत्यात, काय साइड इफेक्ट नाय. दोन्हीची किंमत एक हजार एकोणसत्तर रुपये."

# Acknowledgments
ACK_GOOD = "बरं सर."
RE_ASK_CROP = "बरं सर, तर तुम्ही सध्या कोणतं पीक लावलंय शेतात?"

# ═══════════════════════════════════════════════════════════════
# FAQ — Pre-cached answers for common off-script questions (0ms)
# ═══════════════════════════════════════════════════════════════
FAQ_PUMP = "सर, आमच्याकडं बॅटरी अन् पेट्रोल दोन्ही पंप उपलब्ध हायत. मजबूत अन् टिकाऊ हायत."
FAQ_PRODUCTS = "सर, आमच्याकडं किटकनाशक, बुरशीनाशक, तणनाशक, पीकपोषक, स्प्रे पंप, अन् ताडपत्री उपलब्ध हाय."
FAQ_PRICE_CYMINT = "सर, सायमिंटची किंमत पाचशे चौतीस रुपये हाय एक एकराला."
FAQ_PRICE_SIZE = "सर, साइज प्लसची किंमत पाचशे पस्तीस रुपये हाय एक एकराला."
FAQ_TARPAULIN = "सर, आमच्याकडं धान्य अन् खत सुरक्षित ठेवायला मजबूत ताडपत्री उपलब्ध हाय."
FAQ_DELIVERY = "सर, ऑर्डर दिल्यावर तुमच्या पत्त्यावर डिलिव्हरी होते."
FAQ_OFF_TOPIC = "सर, मी फक्त शेती अन् आमच्या उत्पादनांबद्दल म्हाइती देऊ शकते."
FAQ_PUMP_CONFIRM = "बरं सर, पंपाची म्हाइती तुम्हासनी पाठवते."

# ═══════════════════════════════════════════════════════════════
# SCHEME — Lucky Draw Pitch & FAQs (pre-cached, short spoken)
# ═══════════════════════════════════════════════════════════════
SCHEME_PITCH = "सर, एक खास गोष्ट सांगायची हाय. आमची लकी ड्रॉ योजना चालू हाय. ट्रॅक्टर, दुचाकी अशी बक्षिसं जिंकता येत्यात. ऐकायचं हाय का?"
SCHEME_DETAILS = "सर, एक ते पंधरा ऑगस्ट खरेदी करा. तीन हजारांवर एक कूपन अन् चारशे रुपयांची भेट. साडेसात हजारांवर तीन कूपन अन् पंधराशे रुपयांची भेट. सोडत वीस ऑक्टोबरला दसऱ्याला."
SCHEME_GIFTS = "सर, बक्षिसं ऐका: ट्रॅक्टर, दोन दुचाक्या, तीन स्कूटर, चार पॉवर टिलर, पंप, ताडपत्र्या अन् कृषी किट. पंधरा हजार शेतकऱ्यांना हमखास भेट."
SCHEME_RULES = "सर, पंधरा ऑगस्टपूर्वी पूर्ण पेमेंट करा. कूपन बिलासोबत मिळते. कॅश ऑन डिलिव्हरी चालते पण कूपन पेमेंटनंतरच."
SCHEME_END = "सर, तर आत्ताच ऑर्डर दिली तर या योजनेचा लाभ मिळंल. काय ठेवू का तुमच्यासाठी?"

# Scheme FAQ short answers (Marathwada accent)
FAQ_SCHEME_WHAT = "सर, ही आमची स्वातंत्र्य दिनाची योजना हाय. एक ते पंधरा ऑगस्ट खरेदी केल्यावर लकी ड्रॉ कूपन अन् हमखास भेट मिळते. ट्रॅक्टर, दुचाकी अशी बक्षिसं हायत."
FAQ_SCHEME_WHEN = "सर, ऑफर एक ऑगस्ट ते पंधरा ऑगस्ट हाय. लकी ड्रॉ वीस ऑक्टोबरला दसऱ्याला होणार हाय."
FAQ_SCHEME_HOW = "सर, पात्र उत्पादनं खरेदी करा अन् पूर्ण पेमेंट करा. कूपन मिळंल अन् लकी ड्रॉला पात्र व्हाल."
FAQ_SCHEME_GIFTS = SCHEME_GIFTS
FAQ_SCHEME_COD = "सर, कॅश ऑन डिलिव्हरी उपलब्ध हाय. पण लकी ड्रॉसाठी पूर्ण पेमेंट आधी झालं पाहिजे."
FAQ_SCHEME_COUPON = "सर, पूर्ण पेमेंटनंतर बिलासोबत कूपन मिळते. ते सांभाळून ठेवा, त्यावरूनच विजेता ठरतो."
FAQ_SCHEME_TRUST = "सर, ही पारदर्शक योजना हाय. जीएसटी बिल मिळते, कूपन अधिकृत हाय, अन् लकी ड्रॉ सार्वजनिक कार्यक्रमात काढला जातो."
FAQ_KIT = "सर, आमच्याकडं सोयाबीन, कापूस, केळी, डाळिंब, मिरची, टोमॅटो, मका, तूर, ऊस अशा पिकांसाठी संपूर्ण कृषी किट उपलब्ध हायत."
FAQ_OFFICE = "सर, आमचं ऑफिस पुणे, कल्याणी नगर, सेरेब्रम आयटी पार्कमध्ये हाय. गोदाम बी पुण्यात हाय."
FAQ_AUTHORIZED = "सर, आमची समदी उत्पादनं शासनमान्य अन् अधिकृत हायत. जीएसटी बिल मिळते."
FAQ_E_AGRI = "सर, आमचे ई-ॲग्री दुकान अन् अधिकृत प्रतिनिधी अनेक जिल्ह्यांत कार्यरत हायत. तुमच्या जिल्ह्यातल्या प्रतिनिधीशी संपर्क करून देतो."
FAQ_SERVICES = "सर, आमच्याकडं कृषी किट, ॲग्री डॉक्टर सेवा, माती परीक्षण, ड्रोन फवारणी, हवामान अंदाज, अन् मोबाईल ॲप उपलब्ध हाय."
FAQ_FINTECH = "सर, आमच्या ई-ॲग्री दुकानातून किसान क्रेडिट कार्ड, बँक खाते, आधार बँकिंग अशा सेवा बी उपलब्ध हायत."
FAQ_RESULT = "सर, आमची उत्पादनं दर्जेदार अन् अधिकृत हायत. योग्य वापर केल्यास चांगला रिझल्ट मिळतो, पण शंभर टक्के गॅरंटी कुणीच देऊ शकत नाय."
FAQ_RETAILER = "सर, आम्ही ई-ॲग्री दुकान अन् अधिकृत प्रतिनिधीमार्फत थेट शेतकऱ्यांना सेवा देतो. तांत्रिक सल्ला बी मिळतो."
FAQ_SOIL_TEST = "सर, आमच्याकडं माती परीक्षण सेवा हाय. चारशे रुपयांत प्रतिनिधी शेतावर येतो, नमुना घेतो अन् रिपोर्ट देतो."
FAQ_APP = "सर, आमची वेबसाइट अन् ॲंड्रॉइड ॲप उपलब्ध हाय. लिंक एसएमएसवर पाठवतो."
FAQ_CYTOBOOST = "सर, सोयाबीन अन् कापसाच्या वाढीसाठी आमचं सायटोबूस्ट उपलब्ध हाय. हे ग्रोथ रेग्युलेटर हाय, जोमदार वाढ होते."
FAQ_STATES = "सर, ही योजना महाराष्ट्र, मध्य प्रदेश, राजस्थान, ओडिशा, झारखंड, छत्तीसगड, उत्तर प्रदेश अन् कर्नाटक या राज्यांत लागू हाय."
FAQ_ASSURED_GIFT = "सर, पात्र खरेदीनंतर सात दिवसांत हमखास भेट तुमच्या पत्त्यावर पोस्ट किंवा कुरिअरने पाठवली जाते."

# Add FAQ texts to pre-cache list
ALL_SCRIPTED_TEXTS = [
    GREETING, NO_TIME_RESPONSE, COMPANY_INTRO, COMPANY_INTRO_2, ASK_CROP,
    NO_INPUT_RESPONSE, THANK_YOU, Q_ACREAGE, Q_VARIETY, Q_DAYS, Q_WEATHER,
    Q_PEST, Q_WHICH_PEST, Q_PEST_LEVEL, Q_GROWTH, Q_FERTILIZER, Q_ORDER,
    Q_ADDRESS, Q_PUMP, Q_PUMP_OFFER, Q_OTHER_CROP,
    CYMINT_RECOMMENDATION, SIZE_PLUS_RECOMMENDATION, BOTH_PRODUCTS, ACK_GOOD,
    RE_ASK_CROP, FAQ_PUMP, FAQ_PRODUCTS, FAQ_PRICE_CYMINT, FAQ_PRICE_SIZE,
    FAQ_TARPAULIN, FAQ_DELIVERY, FAQ_OFF_TOPIC, FAQ_PUMP_CONFIRM,
    SCHEME_PITCH, SCHEME_DETAILS, SCHEME_GIFTS, SCHEME_RULES, SCHEME_END,
    FAQ_SCHEME_WHAT, FAQ_SCHEME_WHEN, FAQ_SCHEME_HOW, FAQ_SCHEME_COD,
    FAQ_SCHEME_COUPON, FAQ_SCHEME_TRUST, FAQ_KIT, FAQ_OFFICE, FAQ_AUTHORIZED,
    FAQ_E_AGRI, FAQ_SERVICES, FAQ_FINTECH, FAQ_RESULT, FAQ_RETAILER,
    FAQ_SOIL_TEST, FAQ_APP, FAQ_CYTOBOOST, FAQ_STATES, FAQ_ASSURED_GIFT,
]


def _try_faq(text: str) -> str | None:
    """Try to match farmer's question to a pre-cached FAQ answer. Returns None if no match."""
    t = text.lower()
    # Scheme / Offer / Lucky draw related
    if "योजना" in t or "scheme" in t or "ऑफर" in t or "offer" in t or "लकी" in t or "ड्रॉ" in t:
        if "बक्षीस" in t or "बक्षिस" in t or "gift" in t or "prize" in t:
            return FAQ_SCHEME_GIFTS
        if "कधी" in t or "तारीख" in t or "date" in t:
            return FAQ_SCHEME_WHEN
        if "कसं" in t or "कसा" in t or "how" in t or "सहभागी" in t:
            return FAQ_SCHEME_HOW
        if "cod" in t or "कॅश" in t or "cash" in t:
            return FAQ_SCHEME_COD
        if "कूपन" in t or "coupon" in t:
            return FAQ_SCHEME_COUPON
        if "विश्वास" in t or "trust" in t or "खरं" in t:
            return FAQ_SCHEME_TRUST
        return FAQ_SCHEME_WHAT
    # Kit related
    if "किट" in t or "kit" in t:
        return FAQ_KIT
    # Office / address of company
    if "ऑफिस" in t or "office" in t or "कार्यालय" in t or "गोदाम" in t:
        return FAQ_OFFICE
    # Authorized / government approved
    if "अधिकृत" in t or "authorized" in t or "शासनमान्य" in t or "परवाना" in t:
        return FAQ_AUTHORIZED
    # E-agri dukaan / representative
    if "दुकान" in t or "प्रतिनिधी" in t or "representative" in t:
        return FAQ_E_AGRI
    # Services
    if "सेवा" in t or "service" in t:
        if "फिनटेक" in t or "बँक" in t or "कर्ज" in t or "क्रेडिट" in t:
            return FAQ_FINTECH
        return FAQ_SERVICES
    # Result / guarantee
    if "रिझल्ट" in t or "result" in t or "गॅरंटी" in t or "guarantee" in t or "हमी" in t:
        return FAQ_RESULT
    # Retailer / why no local shop
    if "रिटेलर" in t or "retailer" in t or "दुकानदार" in t:
        return FAQ_RETAILER
    # Soil testing
    if "माती" in t or "soil" in t or "परीक्षण" in t:
        return FAQ_SOIL_TEST
    # App / website
    if "ॲप" in t or "app" in t or "वेबसाइट" in t or "website" in t:
        return FAQ_APP
    # CytoBoost / growth
    if "सायटोबूस्ट" in t or "cytoboost" in t or "gibberellic" in t:
        return FAQ_CYTOBOOST
    # States / which states
    if "राज्य" in t or "state" in t or "महाराष्ट्राबाहेर" in t:
        return FAQ_STATES
    # Assured gift delivery
    if "हमखास" in t or "assured" in t or ("भेट" in t and ("कधी" in t or "कशी" in t)):
        return FAQ_ASSURED_GIFT
    # Pump related
    if "पंप" in t or "pump" in t or "स्प्रे" in t:
        return FAQ_PUMP
    # Products / what do you have
    if ("उत्पादन" in t or "product" in t or ("उपलब्ध" in t and "कोणत" in t) or
            "हार्डवेअर" in t or "साहित्य" in t):
        return FAQ_PRODUCTS
    # Tarpaulin
    if "ताडपत्री" in t or "tarpaulin" in t:
        return FAQ_TARPAULIN
    # Price
    if "किंमत" in t or "price" in t or "rate" in t or "रेट" in t:
        if "साइज" in t or "size" in t:
            return FAQ_PRICE_SIZE
        return FAQ_PRICE_CYMINT
    # Delivery
    if "डिलिव्हरी" in t or "delivery" in t:
        return FAQ_DELIVERY
    return None

# Yes/No detection
YES_WORDS = ["हो", "होय", "हा", "चालेल", "ठीक", "नक्की", "व्हय", "बरं",
             "yes", "ha", "ho", "ok", "sure", "करा", "पाठवा", "द्या", "ठेवा"]
NO_WORDS = ["नाही", "नको", "नाय", "न्हाय", "no", "nahi", "nako", "नग",
            "नंतर", "राहू दे", "नाई", "नहीं"]


# ═══════════════════════════════════════════════════════════════
# CLAUDE — only for off-script / unexpected inputs
# ═══════════════════════════════════════════════════════════════

CLAUDE_SYSTEM = """तू पाल्वी ॲग्रिको कंपनीची ॲग्री डॉक्टर पूजा आहेस.
तुझी भाषा: मराठवाडा बोली.
शेतकऱ्याने प्रश्न विचारला आहे. त्याचं उत्तर दे आणि शेवटी स्क्रिप्टच्या पुढच्या प्रश्नावर परत ये.
उत्तर 2-3 वाक्यांपेक्षा जास्त नको.
कधीही हिंदी, markdown, इंग्रजी वापरू नकोस. फक्त मराठवाडा बोली.

उत्पादने:
- सायमिंट: किटकनाशक, पांढरी माशी/मावा/तुडतुडे वर, चारशे मिली प्रती एकर, दोनशे लिटर पाणी, किंमत पाचशे चौतीस रुपये.
- साइज प्लस: पीकपोषक, समुद्री शैवाल अर्क, पाचशे मिली प्रती एकर, दोनशे लिटर पाणी, किंमत पाचशे पस्तीस रुपये.
- स्प्रे पंप: बॅटरी अन् पेट्रोल दोन्ही उपलब्ध. मजबूत, टिकाऊ, औषधाचा समान प्रसार.
- ताडपत्री: धान्य अन् खत सुरक्षित ठेवायला.
- तणनाशक, बुरशीनाशक: उपलब्ध हाय, विशिष्ट उत्पादनांची म्हाइती कॉलनंतर पाठवू.

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


async def _call_claude(conversation_history: list) -> str:
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _call_claude_sync, conversation_history)


# ═══════════════════════════════════════════════════════════════
# PRE-CACHING
# ═══════════════════════════════════════════════════════════════

async def pre_cache_static_responses():
    """Pre-cache all scripted responses at startup."""
    logger.info("[GRAPH] Pre-caching all scripted responses...")
    for text in ALL_SCRIPTED_TEXTS:
        await pre_cache_audio(text)

    # Also cache combined intro
    full_intro = COMPANY_INTRO + " " + COMPANY_INTRO_2 + " " + ASK_CROP
    from routes.twilio_routes import _split_long_text
    splits = _split_long_text(full_intro)
    for part in splits:
        await pre_cache_audio(part.strip())

    logger.info("[GRAPH] Pre-caching complete!")


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _is_yes(text):
    return any(w in text.lower() for w in YES_WORDS)


def _is_no(text):
    return any(w in text.lower() for w in NO_WORDS)


def _is_question(text):
    """Detect if farmer is asking a question (off-script) rather than answering."""
    text_lower = text.lower()
    # Short responses are always answers, not questions
    if len(text.split()) <= 3:
        return False
    # Explicit answers — never treat as questions
    answer_patterns = ["नाही", "नको", "हो", "नाय", "ठीक", "बरं", "कोणताच नाही",
                       "कोणतीच नाही", "काही नाही", "माहीत नाही"]
    if any(text_lower.strip() == p or text_lower.strip().startswith(p + " ") for p in answer_patterns):
        return False
    # Question indicators in Marathi
    q_indicators = ["काय", "कसं", "कोणत", "का ", "कधी", "कुठ", "का?",
                    "सांगा", "माहिती", "किंमत", "price", "rate", "उपलब्ध",
                    "विचारतोय", "सांगू शकाल", "आहेत का", "हवी", "हवं",
                    "द्या ना", "बोला", "?", "कसे", "कसा", "कोणत्या सुविधा",
                    "कोणते उत्पादन", "कोणत्या सेवा", "आहेत"]
    # If text contains a question word/phrase, it's a question
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
            faq = _try_faq(user_text)
            if faq:
                reply = faq + " तर सर, तुम्ही कोणतं पीक लावलंय?"
            else:
                # Fall back to Claude
                reply = await _call_claude(session["conversation"])
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
            faq = _try_faq(user_text)
            reply = faq if faq else await _call_claude(session["conversation"])
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
            faq = _try_faq(user_text)
            reply = faq if faq else await _call_claude(session["conversation"])
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
            faq = _try_faq(user_text)
            reply = faq if faq else await _call_claude(session["conversation"])
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
            faq = _try_faq(user_text)
            reply = faq if faq else await _call_claude(session["conversation"])
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
            faq = _try_faq(user_text)
            reply = faq if faq else await _call_claude(session["conversation"])
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
            faq = _try_faq(user_text)
            reply = faq if faq else await _call_claude(session["conversation"])
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
            reply = await _call_claude(session["conversation"])
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
            faq = _try_faq(user_text)
            reply = faq if faq else await _call_claude(session["conversation"])
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
            faq = _try_faq(user_text)
            reply = faq if faq else await _call_claude(session["conversation"])
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
            faq = _try_faq(user_text)
            reply = faq if faq else await _call_claude(session["conversation"])
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
            faq = _try_faq(user_text)
            reply = faq if faq else await _call_claude(session["conversation"])
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
            faq = _try_faq(user_text)
            reply = faq if faq else await _call_claude(session["conversation"])
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
            faq = _try_faq(user_text)
            reply = faq if faq else await _call_claude(session["conversation"])
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


def get_responses(dialect: str) -> dict:
    """Compatibility function for twilio_routes."""
    return {
        "greet": GREETING,
        "no_time": NO_TIME_RESPONSE,
        "no_input": NO_INPUT_RESPONSE,
        "not_understood": "सर, जरा नीट समजलं नाय. पुन्हा सांगा.",
        "thank_you": THANK_YOU,
        "off_topic": "सर, मी फक्त शेती अन् आमच्या उत्पादनांबद्दल म्हाइती देऊ शकते.",
    }
