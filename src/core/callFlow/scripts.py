"""
All scripted text constants for the Palvi Agrico call flow.

These are pre-cached at startup for 0ms TTS latency.
"""

# ═══════════════════════════════════════════════════════════════
# ALL SCRIPTED RESPONSES (pre-cached at startup = 0ms TTS)
# ═══════════════════════════════════════════════════════════════

GREETING = "नमस्कार सर... मी पाल्वी ॲग्रिको कंपनी पुणे मधून ॲग्री डॉक्टर पूजा बोलतेय. सर... आमची स्वातंत्र्य दिनानिमित्त एक भव्य लकी ड्रॉ योजना चालू आहे. यामध्ये ट्रॅक्टर, दुचाकी, स्कूटर अशी मोठी बक्षिसे जिंकता येतात. सर, तुम्हाला याबद्दल सविस्तर सांगू का? फक्त दोन मिनिटं लागतील."
NO_TIME_RESPONSE = "ठीक आहे सर, काही हरकत नाही. मी नंतर कॉल करते. धन्यवाद!"
COMPANY_INTRO = "सर, आपली पाल्वी ॲग्रिको कंपनी शेतकऱ्यांना पीक लागवडीपासून ते काढणीपर्यंतची संपूर्ण माहिती आणि मार्गदर्शन देते."
COMPANY_INTRO_2 = "तसेच शेतीसाठी लागणारे सर्व किटकनाशक, बुरशीनाशक, तणनाशक, ताडपत्री, स्प्रे पंप, आणि हार्डवेअरचे साहित्य आमच्याकडे उपलब्ध आहे."
ASK_CROP = "आता सध्या खरीप हंगाम चालू झाला आहे तर सर, मला सांगाल का तुम्ही कोणत्या पिकाची लागवड केली आहे? त्या संदर्भात माहिती देण्यासाठीच मी हा कॉल केला आहे."
NO_INPUT_RESPONSE = "सर, तुमचा आवाज नीट ऐकू आला नाही. जरा मोठ्याने सांगा."
THANK_YOU = "कॉलवर पाल्वी ॲग्रिकोला वेळ दिल्याबद्दल खूप धन्यवाद सर. आपला दिवस शुभ जावो!"

# Scripted questions (one per step, all pre-cached) — varied acknowledgments
Q_ACREAGE = "समजलं सर, किती एकरात लागवड केली आहे?"
Q_VARIETY = "ठीक आहे सर, कोणती जात लावली आहे?"
Q_DAYS = "कळलं सर, लागवडीला किती दिवस झाले?"
Q_WEATHER = "छान सर, तुमच्या भागात पाऊस झाला का?"
Q_PEST = "समजलं सर, पिकावर काही कीड किंवा रोग दिसतोय का?"
Q_WHICH_PEST = "कळलं सर, कोणती कीड दिसतेय?"
Q_PEST_LEVEL = "ठीक सर, किती प्रमाणात दिसतेय, कमी आहे का जास्त?"
Q_GROWTH = "समजलं सर, पिकाची वाढ कशी दिसतेय, जोमदार आहे का?"
Q_FERTILIZER = "छान सर, खतांचे नियोजन केले आहे का आधी?"
Q_ORDER = "ठीक आहे सर, मग सायमिंट आणि साइज प्लस दोन्ही ठेवू का तुमच्याकडे? दोन्ही मिळून एक हजार एकोणसत्तर रुपये होतात."
Q_ADDRESS = "कळलं सर, तुमचा पूर्ण पत्ता सांगा, पिन कोड आणि जवळचा लँडमार्क."
Q_PUMP = "सर, सध्या फवारणीसाठी कोणता स्प्रे पंप वापरतात?"
Q_PUMP_OFFER = "सर, आमच्याकडे मजबूत आणि टिकाऊ बॅटरी पंप उपलब्ध आहेत. औषधाचा समान प्रसार होतो. नवीन पंप बघायचा आहे का?"
Q_OTHER_CROP = "सर, याच्या व्यतिरिक्त आणखी कोणत्या पिकाची माहिती हवी आहे का?"

# Acknowledgments
ACK_GOOD = "समजलं सर."
RE_ASK_CROP = "ठीक आहे सर, तर तुम्ही सध्या कोणते पीक लावले आहे शेतात?"


def get_responses(dialect: str) -> dict:
    """Get canned responses keyed by step name."""
    return {
        "greet": GREETING,
        "no_time": NO_TIME_RESPONSE,
        "no_input": NO_INPUT_RESPONSE,
        "not_understood": "सर, जरा नीट समजलं नाय. पुन्हा सांगा.",
        "thank_you": THANK_YOU,
        "off_topic": "सर, मी फक्त शेती अन् आमच्या उत्पादनांबद्दल म्हाइती देऊ शकते.",
    }


# ═══════════════════════════════════════════════════════════════
# ALL SCRIPTED TEXTS — aggregated for pre-caching at startup
# ═══════════════════════════════════════════════════════════════
from src.core.productKnowledge.products import (
    CYMINT_RECOMMENDATION, SIZE_PLUS_RECOMMENDATION, BOTH_PRODUCTS,
    FAQ_PUMP, FAQ_PRODUCTS, FAQ_PRICE_CYMINT, FAQ_PRICE_SIZE,
    FAQ_TARPAULIN, FAQ_DELIVERY, FAQ_OFF_TOPIC, FAQ_PUMP_CONFIRM,
    FAQ_KIT, FAQ_OFFICE, FAQ_AUTHORIZED, FAQ_E_AGRI, FAQ_SERVICES,
    FAQ_FINTECH, FAQ_RESULT, FAQ_RETAILER, FAQ_SOIL_TEST, FAQ_APP,
    FAQ_CYTOBOOST,
)
from src.core.offerEngine.scheme import (
    SCHEME_PITCH, SCHEME_DETAILS, SCHEME_GIFTS, SCHEME_RULES, SCHEME_END,
    FAQ_SCHEME_WHAT, FAQ_SCHEME_WHEN, FAQ_SCHEME_HOW,
    FAQ_SCHEME_COD, FAQ_SCHEME_COUPON, FAQ_SCHEME_TRUST,
    FAQ_ASSURED_GIFT, FAQ_SCHEME_STATES,
)

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
    FAQ_SOIL_TEST, FAQ_APP, FAQ_CYTOBOOST, FAQ_SCHEME_STATES, FAQ_ASSURED_GIFT,
]
