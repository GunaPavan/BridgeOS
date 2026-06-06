"""Multilingual stub for WhatsApp templates used by G1 (consent flow).

Full multi-template + multi-language rendering lands in Phase G4. This G1
file holds only the two strings the consent loop needs RIGHT NOW:

    - recruit_invite     (outbound: "Aarav needs a donor. Reply YES.")
    - recruit_ack_yes    (inbound webhook reply on YES)
    - recruit_ack_no     (inbound webhook reply on NO)
    - recruit_ack_other  (inbound webhook reply on anything else)

When G4 lands, this file is folded into a per-template translations table.
"""

from __future__ import annotations

from typing import Literal

LanguageCode = Literal["en", "hi", "te", "ta", "mr", "bn", "kn", "gu"]


# {donor_first}, {patient_name}, {patient_age}, {patient_bg}
RECRUIT_INVITE: dict[str, str] = {
    "en": (
        "Hi {donor_first}, {patient_name} (age {patient_age}, {patient_bg}) "
        "needs a committed donor for their Blood Bridge. You match. "
        "Reply YES to join the bridge, or NO to decline."
    ),
    "hi": (
        "नमस्ते {donor_first}, {patient_name} (उम्र {patient_age}, {patient_bg}) "
        "को अपने Blood Bridge के लिए एक प्रतिबद्ध दाता की आवश्यकता है। आप मेल खाते हैं। "
        "जुड़ने के लिए YES लिखें, या मना करने के लिए NO लिखें।"
    ),
    "te": (
        "నమస్కారం {donor_first}, {patient_name} (వయసు {patient_age}, {patient_bg}) "
        "వారి Blood Bridge కోసం ఒక నిబద్ధ దాత అవసరం. మీరు సరిపోతున్నారు. "
        "చేరడానికి YES అని, లేదా తిరస్కరించడానికి NO అని పంపండి."
    ),
    "ta": (
        "வணக்கம் {donor_first}, {patient_name} (வயது {patient_age}, {patient_bg}) "
        "க்கு Blood Bridge-க்கு ஒரு உறுதியான தானியருக்கான தேவை உள்ளது. "
        "சேருவதற்கு YES என்றும், மறுக்க NO என்றும் பதிலளிக்கவும்."
    ),
    "mr": (
        "नमस्कार {donor_first}, {patient_name} (वय {patient_age}, {patient_bg}) "
        "यांना त्यांच्या Blood Bridge साठी एक वचनबद्ध दाता हवा आहे. आपण योग्य आहात. "
        "सहभागी होण्यासाठी YES, नकार देण्यासाठी NO लिहा."
    ),
    "bn": (
        "নমস্কার {donor_first}, {patient_name} (বয়স {patient_age}, {patient_bg}) "
        "এর Blood Bridge এর জন্য একজন প্রতিশ্রুতিবদ্ধ দাতা প্রয়োজন। আপনি মিলে যান। "
        "যোগ দিতে YES, প্রত্যাখ্যান করতে NO লিখুন।"
    ),
    "kn": (
        "ನಮಸ್ಕಾರ {donor_first}, {patient_name} (ವಯಸ್ಸು {patient_age}, {patient_bg}) "
        "ಅವರ Blood Bridge ಗೆ ಒಬ್ಬ ಬದ್ಧ ದಾನಿ ಅಗತ್ಯ. ನೀವು ಹೊಂದಿಕೆಯಾಗುತ್ತೀರಿ. "
        "ಸೇರಲು YES, ನಿರಾಕರಿಸಲು NO ಎಂದು ಉತ್ತರಿಸಿ."
    ),
    "gu": (
        "નમસ્તે {donor_first}, {patient_name} (ઉંમર {patient_age}, {patient_bg}) "
        "ને તેમના Blood Bridge માટે પ્રતિબદ્ધ દાતા જોઈએ છે. તમે મેળ ખાઓ છો. "
        "જોડાવા YES, નકારવા NO લખો."
    ),
}


# {donor_first}, {patient_name}
RECRUIT_ACK_YES: dict[str, str] = {
    "en": "Thank you {donor_first}! You're now on {patient_name}'s bridge. A coordinator will message you with the next slot.",
    "hi": "धन्यवाद {donor_first}! आप अब {patient_name} के bridge पर हैं। एक coordinator आपको अगले slot के बारे में बताएगा।",
    "te": "ధన్యవాదాలు {donor_first}! మీరు ఇప్పుడు {patient_name} యొక్క bridge లో ఉన్నారు. తదుపరి slot గురించి coordinator మీకు తెలియజేస్తారు.",
    "ta": "நன்றி {donor_first}! நீங்கள் இப்போது {patient_name} இன் bridge-ல் இருக்கிறீர்கள். அடுத்த slot பற்றி coordinator உங்களுக்கு தெரிவிப்பார்.",
    "mr": "धन्यवाद {donor_first}! आपण आता {patient_name} च्या bridge वर आहात. एक coordinator आपल्याला पुढील slot बद्दल कळवेल.",
    "bn": "ধন্যবাদ {donor_first}! আপনি এখন {patient_name} এর bridge-এ আছেন। একজন coordinator আপনাকে পরবর্তী slot সম্পর্কে জানাবেন।",
    "kn": "ಧನ್ಯವಾದಗಳು {donor_first}! ನೀವು ಈಗ {patient_name} ರ bridge ಮೇಲೆ ಇದ್ದೀರಿ. ಮುಂದಿನ slot ಬಗ್ಗೆ coordinator ತಿಳಿಸುತ್ತಾರೆ.",
    "gu": "આભાર {donor_first}! તમે હવે {patient_name} ના bridge પર છો. આગામી slot વિશે coordinator તમને જણાવશે.",
}

# {donor_first}
RECRUIT_ACK_NO: dict[str, str] = {
    "en": "Understood {donor_first} — thank you for replying. We won't contact you for this bridge.",
    "hi": "समझ गए {donor_first} — जवाब देने के लिए धन्यवाद। हम इस bridge के लिए आपसे संपर्क नहीं करेंगे।",
    "te": "అర్థమైంది {donor_first} — ప్రతిస్పందించినందుకు ధన్యవాదాలు. ఈ bridge కోసం మిమ్మల్ని సంప్రదించము.",
    "ta": "புரிந்தது {donor_first} — பதிலளித்ததற்கு நன்றி. இந்த bridge-க்காக உங்களைத் தொடர்பு கொள்ள மாட்டோம்.",
    "mr": "समजले {donor_first} — उत्तर दिल्याबद्दल धन्यवाद. आम्ही या bridge साठी आपल्याशी संपर्क करणार नाही.",
    "bn": "বুঝেছি {donor_first} — উত্তর দেওয়ার জন্য ধন্যবাদ। আমরা এই bridge এর জন্য আপনার সাথে যোগাযোগ করব না।",
    "kn": "ಅರ್ಥವಾಯಿತು {donor_first} — ಉತ್ತರಿಸಿದ್ದಕ್ಕೆ ಧನ್ಯವಾದಗಳು. ಈ bridge ಗಾಗಿ ನಾವು ನಿಮ್ಮನ್ನು ಸಂಪರ್ಕಿಸುವುದಿಲ್ಲ.",
    "gu": "સમજાયું {donor_first} — જવાબ આપવા બદલ આભાર. અમે આ bridge માટે તમારો સંપર્ક નહીં કરીએ.",
}

# {donor_first}
RECRUIT_ACK_OTHER: dict[str, str] = {
    "en": "Hi {donor_first} — please reply YES to join or NO to decline.",
    "hi": "नमस्ते {donor_first} — कृपया जुड़ने के लिए YES या मना करने के लिए NO लिखें।",
    "te": "నమస్కారం {donor_first} — దయచేసి చేరడానికి YES, తిరస్కరించడానికి NO అని పంపండి.",
    "ta": "வணக்கம் {donor_first} — சேருவதற்கு YES, மறுக்க NO என பதிலளிக்கவும்.",
    "mr": "नमस्कार {donor_first} — कृपया सहभागी होण्यासाठी YES किंवा नकार देण्यासाठी NO लिहा.",
    "bn": "নমস্কার {donor_first} — অনুগ্রহ করে যোগ দিতে YES বা প্রত্যাখ্যান করতে NO লিখুন।",
    "kn": "ನಮಸ್ಕಾರ {donor_first} — ಸೇರಲು YES ಅಥವಾ ನಿರಾಕರಿಸಲು NO ಎಂದು ಉತ್ತರಿಸಿ.",
    "gu": "નમસ્તે {donor_first} — કૃપા કરી જોડાવા YES અથવા નકારવા NO લખો.",
}


def render_recruit_invite(
    lang: str, donor_first: str, patient_name: str, patient_age: int, patient_bg: str
) -> str:
    body = RECRUIT_INVITE.get(lang) or RECRUIT_INVITE["en"]
    return body.format(
        donor_first=donor_first,
        patient_name=patient_name,
        patient_age=patient_age,
        patient_bg=patient_bg,
    )


def render_ack(intent: str, lang: str, donor_first: str, patient_name: str = "") -> str:
    """Pick the right ack table by intent ('accept' / 'decline' / 'other')."""
    table = {
        "accept": RECRUIT_ACK_YES,
        "decline": RECRUIT_ACK_NO,
        "other": RECRUIT_ACK_OTHER,
    }.get(intent, RECRUIT_ACK_OTHER)
    body = table.get(lang) or table["en"]
    return body.format(donor_first=donor_first, patient_name=patient_name)
