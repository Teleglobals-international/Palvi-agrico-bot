"""
FAQ matcher — matches farmer questions to pre-cached FAQ answers.

Returns None if no match found (triggers Claude fallback).
"""
from src.core.productKnowledge.products import (
    FAQ_PUMP, FAQ_PRODUCTS, FAQ_PRICE_CYMINT, FAQ_PRICE_SIZE,
    FAQ_TARPAULIN, FAQ_DELIVERY, FAQ_KIT, FAQ_OFFICE, FAQ_AUTHORIZED,
    FAQ_E_AGRI, FAQ_SERVICES, FAQ_FINTECH, FAQ_RESULT, FAQ_RETAILER,
    FAQ_SOIL_TEST, FAQ_APP, FAQ_CYTOBOOST,
)
from src.core.offerEngine.scheme import (
    FAQ_SCHEME_WHAT, FAQ_SCHEME_WHEN, FAQ_SCHEME_HOW, FAQ_SCHEME_GIFTS,
    FAQ_SCHEME_COD, FAQ_SCHEME_COUPON, FAQ_SCHEME_TRUST,
    FAQ_SCHEME_MULTIPLE_COUPONS, FAQ_SCHEME_TAX, FAQ_SCHEME_CANCEL,
    FAQ_SCHEME_STATES, FAQ_SCHEME_PRODUCTS, FAQ_SCHEME_WHY_NOW,
    FAQ_ASSURED_GIFT,
)


def try_faq(text: str) -> str | None:
    """Try to match farmer's question to a pre-cached FAQ answer. Returns None if no match."""
    t = text.lower()

    # Scheme / Offer / Lucky draw related
    if "योजना" in t or "scheme" in t or "ऑफर" in t or "offer" in t or "लकी" in t or "ड्रॉ" in t:
        if "बक्षीस" in t or "बक्षिस" in t or "gift" in t or "prize" in t:
            return FAQ_SCHEME_GIFTS
        if "कधी" in t or "तारीख" in t or "date" in t or "कालावधी" in t:
            return FAQ_SCHEME_WHEN
        if "कसं" in t or "कसा" in t or "how" in t or "सहभागी" in t or "लाभ घे" in t:
            return FAQ_SCHEME_HOW
        if "cod" in t or "कॅश" in t or "cash" in t:
            return FAQ_SCHEME_COD
        if "कूपन" in t or "coupon" in t:
            if "अनेक" in t or "जास्त" in t or "एकापेक्षा" in t or "multiple" in t or "किती" in t:
                return FAQ_SCHEME_MULTIPLE_COUPONS
            return FAQ_SCHEME_COUPON
        if "विश्वास" in t or "trust" in t or "खरं" in t or "पारदर्शक" in t:
            return FAQ_SCHEME_TRUST
        if "टॅक्स" in t or "tax" in t or "जीएसटी" in t or "gst" in t or "टीडीएस" in t or "tds" in t:
            return FAQ_SCHEME_TAX
        if "रद्द" in t or "cancel" in t or "परत" in t or "return" in t or "रिफंड" in t or "refund" in t:
            return FAQ_SCHEME_CANCEL
        if "राज्य" in t or "state" in t or "कुठे" in t or "where" in t:
            return FAQ_SCHEME_STATES
        if "उत्पादन" in t or "product" in t or "काय काय" in t or "कोणत" in t:
            return FAQ_SCHEME_PRODUCTS
        if "का" in t and ("आता" in t or "आत्ता" in t or "लगेच" in t):
            return FAQ_SCHEME_WHY_NOW
        return FAQ_SCHEME_WHAT

    # Multiple coupons (outside scheme context too)
    if ("कूपन" in t or "coupon" in t) and ("अनेक" in t or "जास्त" in t or "multiple" in t or "किती" in t):
        return FAQ_SCHEME_MULTIPLE_COUPONS

    # Tax on prizes (outside scheme context)
    if ("टॅक्स" in t or "tax" in t or "टीडीएस" in t or "tds" in t) and ("बक्षीस" in t or "बक्षिस" in t or "prize" in t):
        return FAQ_SCHEME_TAX

    # Cancellation / return
    if "रद्द" in t or "cancel" in t or ("परत" in t and "माल" in t) or "रिफंड" in t or "refund" in t:
        return FAQ_SCHEME_CANCEL

    # States where scheme applies
    if ("राज्य" in t or "state" in t) and ("कोणत" in t or "किती" in t or "कुठे" in t):
        return FAQ_SCHEME_STATES

    # Why participate now / urgency
    if ("का" in t or "why" in t) and ("आता" in t or "आत्ता" in t or "now" in t):
        return FAQ_SCHEME_WHY_NOW

    # Assured gift delivery
    if "हमखास" in t or "assured" in t or ("भेट" in t and ("कधी" in t or "कशी" in t or "मिळेल" in t)):
        return FAQ_ASSURED_GIFT

    # Soil testing
    if "माती" in t or "soil" in t or "परीक्षण" in t:
        return FAQ_SOIL_TEST

    # App / website
    if "ॲप" in t or "app" in t or "वेबसाइट" in t or "website" in t:
        return FAQ_APP

    # FinTech / banking services
    if "फिनटेक" in t or "बँक" in t or "कर्ज" in t or "क्रेडिट" in t or "विमा" in t:
        return FAQ_FINTECH

    # E-agri dukaan / representative
    if "दुकान" in t or "प्रतिनिधी" in t or "representative" in t or "ई-ॲग्री" in t:
        return FAQ_E_AGRI

    # Retailer / why no local shop
    if "रिटेलर" in t or "retailer" in t or "दुकानदार" in t:
        return FAQ_RETAILER

    # Services
    if "सेवा" in t or "service" in t:
        return FAQ_SERVICES

    # Result / guarantee
    if "रिझल्ट" in t or "result" in t or "गॅरंटी" in t or "guarantee" in t or "हमी" in t:
        return FAQ_RESULT

    # CytoBoost / growth regulator
    if "सायटोबूस्ट" in t or "cytoboost" in t or "gibberellic" in t or "जिबरेलिक" in t:
        return FAQ_CYTOBOOST

    # Kit related
    if "किट" in t or "kit" in t:
        return FAQ_KIT

    # Office / address of company
    if "ऑफिस" in t or "office" in t or "कार्यालय" in t or "गोदाम" in t:
        return FAQ_OFFICE

    # Authorized / government approved
    if "अधिकृत" in t or "authorized" in t or "शासनमान्य" in t or "परवाना" in t:
        return FAQ_AUTHORIZED

    # Tarpaulin
    if "ताडपत्री" in t or "tarpaulin" in t:
        return FAQ_TARPAULIN

    # Pump related
    if "पंप" in t or "pump" in t or "स्प्रे" in t:
        return FAQ_PUMP

    # Products / what do you have
    if ("उत्पादन" in t or "product" in t or ("उपलब्ध" in t and "कोणत" in t) or
            "हार्डवेअर" in t or "साहित्य" in t):
        return FAQ_PRODUCTS

    # Price
    if "किंमत" in t or "price" in t or "rate" in t or "रेट" in t:
        if "साइज" in t or "size" in t:
            return FAQ_PRICE_SIZE
        return FAQ_PRICE_CYMINT

    # Delivery
    if "डिलिव्हरी" in t or "delivery" in t:
        return FAQ_DELIVERY

    return None
