"""G4 — multilingual WhatsApp template store.

Single source of truth for the 4 outbound templates (slot_reminder,
recruit_invite, thank_you, swap_request) × 8 supported languages (en, hi,
te, ta, mr, bn, kn, gu) = 32 hand-authored strings.

Fallback chain on render:
    requested language → English → first non-empty body in the dict

If the requested language has no hand-authored string AND English is set
(it always is), we fall back to English and the caller can re-render via
the Care Agent LLM if it wants real semantic translation.

The webhook YES/NO intent parser already understands tokens in all 8
languages (`app/utils/intent.py`), so end-to-end the consent flow is
fully localised.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


LanguageCode = Literal["en", "hi", "te", "ta", "mr", "bn", "kn", "gu"]

ALL_LANGUAGES: tuple[LanguageCode, ...] = (
    "en", "hi", "te", "ta", "mr", "bn", "kn", "gu",
)


@dataclass(frozen=True)
class TemplateDef:
    key: str
    label: str
    requires_bridge: bool
    bodies: dict[str, str]


# ----- the templates -----

# Variables available to all templates:
#   {donor_name}, {donor_first}
# If requires_bridge=True, also:
#   {patient_name}, {patient_age}, {patient_blood_group}

SLOT_REMINDER: dict[str, str] = {
    "en": (
        "Hi {donor_first}, you're scheduled to donate for {patient_name}'s "
        "Blood Bridge on the next transfusion cycle. Reply YES to confirm or "
        "NO if you can't make it."
    ),
    "hi": (
        "नमस्ते {donor_first}, आप {patient_name} के Blood Bridge के लिए अगले "
        "transfusion cycle में रक्तदान करने वाले हैं। पुष्टि के लिए YES, "
        "नहीं आ सकते तो NO लिखें।"
    ),
    "te": (
        "నమస్కారం {donor_first}, మీరు {patient_name} యొక్క Blood Bridge కోసం "
        "తదుపరి transfusion cycle లో రక్తదానం చేయాలి. నిర్ధారించడానికి YES, "
        "రాలేకపోతే NO అని పంపండి."
    ),
    "ta": (
        "வணக்கம் {donor_first}, அடுத்த transfusion cycle-ல் {patient_name} இன் "
        "Blood Bridge-க்காக நீங்கள் இரத்த தானம் செய்ய திட்டமிடப்பட்டுள்ளீர்கள். "
        "உறுதிப்படுத்த YES, வர முடியாவிட்டால் NO என பதிலளிக்கவும்."
    ),
    "mr": (
        "नमस्कार {donor_first}, पुढच्या transfusion cycle मध्ये {patient_name} च्या "
        "Blood Bridge साठी आपण रक्तदान करणार आहात. पुष्टी देण्यासाठी YES, "
        "येऊ शकत नसाल तर NO लिहा."
    ),
    "bn": (
        "নমস্কার {donor_first}, পরবর্তী transfusion cycle-এ {patient_name} এর "
        "Blood Bridge এর জন্য আপনি রক্তদান করার কথা। নিশ্চিত করতে YES, "
        "আসতে না পারলে NO লিখুন।"
    ),
    "kn": (
        "ನಮಸ್ಕಾರ {donor_first}, ಮುಂದಿನ transfusion cycle ನಲ್ಲಿ {patient_name} "
        "ಅವರ Blood Bridge ಗಾಗಿ ನೀವು ರಕ್ತದಾನ ಮಾಡಲು ನಿಗದಿಯಾಗಿದೆ. "
        "ದೃಢೀಕರಿಸಲು YES, ಬರಲು ಸಾಧ್ಯವಾಗದಿದ್ದರೆ NO ಎಂದು ಉತ್ತರಿಸಿ."
    ),
    "gu": (
        "નમસ્તે {donor_first}, આગામી transfusion cycle માં {patient_name} ના "
        "Blood Bridge માટે તમારે રક્તદાન કરવાનું છે. ખાતરી માટે YES, "
        "ન આવી શકો તો NO લખો."
    ),
}


RECRUIT_INVITE: dict[str, str] = {
    "en": (
        "Hi {donor_first}, {patient_name} (age {patient_age}, "
        "{patient_blood_group}) needs a committed donor for their Blood "
        "Bridge. You match. Reply YES to join the bridge, or NO to decline."
    ),
    "hi": (
        "नमस्ते {donor_first}, {patient_name} (उम्र {patient_age}, "
        "{patient_blood_group}) को अपने Blood Bridge के लिए एक प्रतिबद्ध दाता की "
        "आवश्यकता है। आप मेल खाते हैं। जुड़ने के लिए YES लिखें, या मना करने के लिए NO लिखें।"
    ),
    "te": (
        "నమస్కారం {donor_first}, {patient_name} (వయసు {patient_age}, "
        "{patient_blood_group}) వారి Blood Bridge కోసం ఒక నిబద్ధ దాత అవసరం. "
        "మీరు సరిపోతున్నారు. చేరడానికి YES అని, లేదా తిరస్కరించడానికి NO అని పంపండి."
    ),
    "ta": (
        "வணக்கம் {donor_first}, {patient_name} (வயது {patient_age}, "
        "{patient_blood_group}) க்கு Blood Bridge-க்கு ஒரு உறுதியான தானியருக்கான தேவை உள்ளது. "
        "சேருவதற்கு YES என்றும், மறுக்க NO என்றும் பதிலளிக்கவும்."
    ),
    "mr": (
        "नमस्कार {donor_first}, {patient_name} (वय {patient_age}, "
        "{patient_blood_group}) यांना त्यांच्या Blood Bridge साठी एक वचनबद्ध दाता हवा आहे. "
        "आपण योग्य आहात. सहभागी होण्यासाठी YES, नकार देण्यासाठी NO लिहा."
    ),
    "bn": (
        "নমস্কার {donor_first}, {patient_name} (বয়স {patient_age}, "
        "{patient_blood_group}) এর Blood Bridge এর জন্য একজন প্রতিশ্রুতিবদ্ধ দাতা প্রয়োজন। "
        "আপনি মিলে যান। যোগ দিতে YES, প্রত্যাখ্যান করতে NO লিখুন।"
    ),
    "kn": (
        "ನಮಸ್ಕಾರ {donor_first}, {patient_name} (ವಯಸ್ಸು {patient_age}, "
        "{patient_blood_group}) ಅವರ Blood Bridge ಗೆ ಒಬ್ಬ ಬದ್ಧ ದಾನಿ ಅಗತ್ಯ. "
        "ನೀವು ಹೊಂದಿಕೆಯಾಗುತ್ತೀರಿ. ಸೇರಲು YES, ನಿರಾಕರಿಸಲು NO ಎಂದು ಉತ್ತರಿಸಿ."
    ),
    "gu": (
        "નમસ્તે {donor_first}, {patient_name} (ઉંમર {patient_age}, "
        "{patient_blood_group}) ને તેમના Blood Bridge માટે પ્રતિબદ્ધ દાતા જોઈએ છે. "
        "તમે મેળ ખાઓ છો. જોડાવા YES, નકારવા NO લખો."
    ),
}


THANK_YOU: dict[str, str] = {
    "en": (
        "Thank you {donor_first} for donating today — {patient_name}'s "
        "treatment continues because of you. 🙏"
    ),
    "hi": (
        "धन्यवाद {donor_first}, आज रक्तदान करने के लिए — आपकी वजह से "
        "{patient_name} का इलाज जारी है। 🙏"
    ),
    "te": (
        "ధన్యవాదాలు {donor_first}, ఈరోజు రక్తదానం చేసినందుకు — మీ వల్ల "
        "{patient_name} యొక్క చికిత్స కొనసాగుతుంది. 🙏"
    ),
    "ta": (
        "நன்றி {donor_first}, இன்று இரத்த தானம் செய்ததற்காக — உங்களால் "
        "{patient_name} இன் சிகிச்சை தொடர்கிறது. 🙏"
    ),
    "mr": (
        "धन्यवाद {donor_first}, आज रक्तदान केल्याबद्दल — आपल्यामुळे "
        "{patient_name} चे उपचार चालू आहेत. 🙏"
    ),
    "bn": (
        "ধন্যবাদ {donor_first}, আজ রক্তদান করার জন্য — আপনার কারণে "
        "{patient_name} এর চিকিৎসা চলছে। 🙏"
    ),
    "kn": (
        "ಧನ್ಯವಾದಗಳು {donor_first}, ಇಂದು ರಕ್ತದಾನ ಮಾಡಿದ್ದಕ್ಕೆ — ನಿಮ್ಮಿಂದಾಗಿ "
        "{patient_name} ರ ಚಿಕಿತ್ಸೆ ಮುಂದುವರಿಯುತ್ತಿದೆ. 🙏"
    ),
    "gu": (
        "આભાર {donor_first}, આજે રક્તદાન કરવા બદલ — તમારા કારણે "
        "{patient_name} ની સારવાર ચાલુ છે. 🙏"
    ),
}


# ----- G5: caregiver-recipient templates -----
# Variables: {caregiver_first}, {patient_name}, {added_donor_name},
#            {active_donor_count}, {next_transfusion_date}

RECRUIT_SUCCESS_CAREGIVER: dict[str, str] = {
    "en": (
        "Hi {caregiver_first}, good news — {patient_name}'s Blood Bridge is "
        "fully covered. {added_donor_name} just joined, bringing the cohort "
        "to {active_donor_count} active donors."
    ),
    "hi": (
        "नमस्ते {caregiver_first}, अच्छी खबर — {patient_name} का Blood Bridge "
        "पूरी तरह से कवर है। {added_donor_name} अभी जुड़े हैं, और cohort में "
        "अब {active_donor_count} सक्रिय दाता हैं।"
    ),
    "te": (
        "నమస్కారం {caregiver_first}, మంచి వార్త — {patient_name} యొక్క Blood Bridge "
        "పూర్తిగా కవర్ చేయబడింది. {added_donor_name} ఇప్పుడే చేరారు, "
        "cohort లో మొత్తం {active_donor_count} క్రియాశీల దాతలు."
    ),
    "ta": (
        "வணக்கம் {caregiver_first}, நல்ல செய்தி — {patient_name} இன் Blood Bridge "
        "முழுமையாக நிரப்பப்பட்டுள்ளது. {added_donor_name} இப்போதே சேர்ந்துள்ளார், "
        "cohort-ல் இப்போது {active_donor_count} செயலில் உள்ள தானியர்கள்."
    ),
    "mr": (
        "नमस्कार {caregiver_first}, चांगली बातमी — {patient_name} चा Blood Bridge "
        "पूर्णपणे कव्हर आहे. {added_donor_name} नुकतेच सामील झाले आहेत, "
        "cohort मध्ये आता {active_donor_count} सक्रिय दाता आहेत."
    ),
    "bn": (
        "নমস্কার {caregiver_first}, ভালো খবর — {patient_name} এর Blood Bridge "
        "সম্পূর্ণ কভার্ড। {added_donor_name} এইমাত্র যোগ দিয়েছেন, এবং cohort-এ "
        "এখন {active_donor_count} জন সক্রিয় দাতা।"
    ),
    "kn": (
        "ನಮಸ್ಕಾರ {caregiver_first}, ಒಳ್ಳೆಯ ಸುದ್ದಿ — {patient_name} ರ Blood Bridge "
        "ಸಂಪೂರ್ಣವಾಗಿ ಕವರ್ ಆಗಿದೆ. {added_donor_name} ಈಗ ಸೇರಿಕೊಂಡಿದ್ದಾರೆ, "
        "cohort ನಲ್ಲಿ ಈಗ {active_donor_count} ಸಕ್ರಿಯ ದಾನಿಗಳಿದ್ದಾರೆ."
    ),
    "gu": (
        "નમસ્તે {caregiver_first}, સારા સમાચાર — {patient_name} નો Blood Bridge "
        "સંપૂર્ણ રીતે કવર છે. {added_donor_name} હમણાં જ જોડાયા છે, અને cohort માં "
        "હવે {active_donor_count} સક્રિય દાતા છે."
    ),
}


BRIDGE_COVERED_CAREGIVER: dict[str, str] = {
    "en": (
        "Hi {caregiver_first}, {patient_name}'s Blood Bridge is healthy — "
        "{active_donor_count} active donors are committed for the next "
        "transfusion cycle."
    ),
    "hi": (
        "नमस्ते {caregiver_first}, {patient_name} का Blood Bridge स्वस्थ है — "
        "अगले transfusion cycle के लिए {active_donor_count} सक्रिय दाता प्रतिबद्ध हैं।"
    ),
    "te": (
        "నమస్కారం {caregiver_first}, {patient_name} యొక్క Blood Bridge ఆరోగ్యంగా ఉంది — "
        "తదుపరి transfusion cycle కోసం {active_donor_count} క్రియాశీల దాతలు నిబద్ధులు."
    ),
    "ta": (
        "வணக்கம் {caregiver_first}, {patient_name} இன் Blood Bridge ஆரோக்கியமாக உள்ளது — "
        "அடுத்த transfusion cycle-க்காக {active_donor_count} செயலில் உள்ள தானியர்கள் உறுதியளித்துள்ளனர்."
    ),
    "mr": (
        "नमस्कार {caregiver_first}, {patient_name} चा Blood Bridge निरोगी आहे — "
        "पुढच्या transfusion cycle साठी {active_donor_count} सक्रिय दाता वचनबद्ध आहेत."
    ),
    "bn": (
        "নমস্কার {caregiver_first}, {patient_name} এর Blood Bridge সুস্থ — "
        "পরবর্তী transfusion cycle এর জন্য {active_donor_count} জন সক্রিয় দাতা প্রতিশ্রুতিবদ্ধ।"
    ),
    "kn": (
        "ನಮಸ್ಕಾರ {caregiver_first}, {patient_name} ರ Blood Bridge ಆರೋಗ್ಯಕರವಾಗಿದೆ — "
        "ಮುಂದಿನ transfusion cycle ಗಾಗಿ {active_donor_count} ಸಕ್ರಿಯ ದಾನಿಗಳು ಬದ್ಧರಾಗಿದ್ದಾರೆ."
    ),
    "gu": (
        "નમસ્તે {caregiver_first}, {patient_name} નો Blood Bridge સ્વસ્થ છે — "
        "આગામી transfusion cycle માટે {active_donor_count} સક્રિય દાતા પ્રતિબદ્ધ છે."
    ),
}


TRANSFUSION_CONFIRMED_CAREGIVER: dict[str, str] = {
    "en": (
        "Hi {caregiver_first}, {patient_name}'s next transfusion is confirmed for "
        "{next_transfusion_date}. {added_donor_name} will be donating that day."
    ),
    "hi": (
        "नमस्ते {caregiver_first}, {patient_name} का अगला transfusion "
        "{next_transfusion_date} को निर्धारित है। उस दिन {added_donor_name} रक्तदान करेंगे।"
    ),
    "te": (
        "నమస్కారం {caregiver_first}, {patient_name} యొక్క తదుపరి transfusion "
        "{next_transfusion_date} న నిర్ధారించబడింది. ఆ రోజు {added_donor_name} రక్తదానం చేస్తారు."
    ),
    "ta": (
        "வணக்கம் {caregiver_first}, {patient_name} இன் அடுத்த transfusion "
        "{next_transfusion_date} அன்று உறுதிசெய்யப்பட்டுள்ளது. அன்று {added_donor_name} இரத்த தானம் செய்வார்."
    ),
    "mr": (
        "नमस्कार {caregiver_first}, {patient_name} चे पुढचे transfusion "
        "{next_transfusion_date} रोजी निश्चित आहे. त्या दिवशी {added_donor_name} रक्तदान करतील."
    ),
    "bn": (
        "নমস্কার {caregiver_first}, {patient_name} এর পরবর্তী transfusion "
        "{next_transfusion_date} তারিখে নিশ্চিত করা হয়েছে। সেদিন {added_donor_name} রক্তদান করবেন।"
    ),
    "kn": (
        "ನಮಸ್ಕಾರ {caregiver_first}, {patient_name} ರ ಮುಂದಿನ transfusion "
        "{next_transfusion_date} ರಂದು ದೃಢೀಕರಿಸಲಾಗಿದೆ. ಆ ದಿನ {added_donor_name} ರಕ್ತದಾನ ಮಾಡುತ್ತಾರೆ."
    ),
    "gu": (
        "નમસ્તે {caregiver_first}, {patient_name} નું આગામી transfusion "
        "{next_transfusion_date} ના રોજ નક્કી છે. તે દિવસે {added_donor_name} રક્તદાન કરશે."
    ),
}


FINAL_ASK_SOFT: dict[str, str] = {
    # Tier 3 — full pool broadcast including the `inactive_limited_despite_calls`
    # cohort. Tone is deliberately apologetic / soft because we're reaching out
    # to donors we'd normally protect from over-outreach. Last resort before
    # external escalation (eRaktKosh + ICMR RDRI).
    "en": (
        "Hi {donor_first} — we know we haven't been in touch for a while. "
        "{patient_name} really needs a donor for their transfusion on "
        "{slot_date} and you're a match. If you can help, please reply YES. "
        "No pressure — say NO if you can't. (ref {slot_ref})"
    ),
    "hi": (
        "नमस्ते {donor_first} — हम जानते हैं कि काफी समय से संपर्क नहीं हुआ। "
        "{patient_name} को {slot_date} के transfusion के लिए वास्तव में दाता की "
        "ज़रूरत है और आप मेल खाते हैं। यदि मदद कर सकें तो YES लिखें, अगर नहीं तो NO। "
        "(ref {slot_ref})"
    ),
    "te": (
        "నమస్కారం {donor_first} — చాలా రోజులుగా సంప్రదించలేకపోయాము. "
        "{patient_name} కి {slot_date} నాటి transfusion కోసం దాత అవసరం, మీరు సరిపోతారు. "
        "సహాయపడగలిగితే YES అని, లేకపోతే NO అని పంపండి. (ref {slot_ref})"
    ),
    "ta": (
        "வணக்கம் {donor_first} — நீண்ட நாட்களாக தொடர்பு கொள்ளவில்லை. "
        "{patient_name} க்கு {slot_date} அன்று transfusion-க்காக ஒரு தானியர் "
        "தேவை, நீங்கள் பொருந்துகிறீர்கள். உதவ முடிந்தால் YES, இல்லையெனில் NO. "
        "(ref {slot_ref})"
    ),
    "mr": (
        "नमस्कार {donor_first} — बऱ्याच दिवसांपासून संपर्क झाला नाही. "
        "{patient_name} ला {slot_date} रोजी transfusion साठी दात्याची गरज आहे आणि "
        "आपण मेळ खाता. मदत करू शकलात तर YES, नाहीतर NO. (ref {slot_ref})"
    ),
    "bn": (
        "নমস্কার {donor_first} — অনেক দিন যোগাযোগ হয়নি। "
        "{patient_name} এর {slot_date} তারিখের transfusion এর জন্য একজন দাতা "
        "দরকার, আপনি মিলছেন। সাহায্য করতে পারলে YES, না পারলে NO। (ref {slot_ref})"
    ),
    "kn": (
        "ನಮಸ್ಕಾರ {donor_first} — ತುಂಬಾ ದಿನಗಳಿಂದ ಸಂಪರ್ಕವಾಗಿಲ್ಲ. "
        "{patient_name} ಗೆ {slot_date} ರಂದು transfusion ಗಾಗಿ ದಾನಿ ಬೇಕು, "
        "ನೀವು ಹೊಂದಾಣಿಕೆ. ಸಹಾಯ ಮಾಡಲು ಸಾಧ್ಯವಾದರೆ YES, ಇಲ್ಲದಿದ್ದರೆ NO. "
        "(ref {slot_ref})"
    ),
    "gu": (
        "નમસ્તે {donor_first} — ઘણા સમયથી સંપર્ક નથી થયો. "
        "{patient_name} ને {slot_date} ના રોજ transfusion માટે દાતા જોઈએ છે અને "
        "તમે મેળ ખાઓ છો. મદદ કરી શકો તો YES, ન કરી શકો તો NO. (ref {slot_ref})"
    ),
}


URGENT_SLOT_ALERT: dict[str, str] = {
    # Alert Allocator Tier 1/2 — stronger language than slot_reminder because
    # the allocator only fires it when the patient's transfusion gap is short.
    # Carries a slot reference so the webhook can correlate YES/NO back to the
    # right wave + slot when the donor replies.
    "en": (
        "URGENT — {donor_first}, {patient_name} needs a donor for their "
        "transfusion on {slot_date}. You're a perfect match. Reply YES to "
        "confirm or NO if you can't make it. (ref {slot_ref})"
    ),
    "hi": (
        "अत्यावश्यक — {donor_first}, {patient_name} को {slot_date} के "
        "transfusion के लिए दाता चाहिए। आप एकदम सही मेल हैं। पुष्टि के लिए "
        "YES, नहीं आ सकते तो NO लिखें। (ref {slot_ref})"
    ),
    "te": (
        "అత్యవసరం — {donor_first}, {patient_name} కి {slot_date} నాడు "
        "transfusion కోసం దాత అవసరం. మీరు సరిగ్గా సరిపోతారు. నిర్ధారించడానికి "
        "YES, రాలేకపోతే NO అని పంపండి. (ref {slot_ref})"
    ),
    "ta": (
        "அவசரம் — {donor_first}, {patient_name} க்கு {slot_date} அன்று "
        "transfusion-க்காக ஒரு தானியர் தேவை. நீங்கள் சரியான பொருத்தம். "
        "உறுதிப்படுத்த YES, வர முடியாவிட்டால் NO என பதிலளிக்கவும். (ref {slot_ref})"
    ),
    "mr": (
        "अत्यावश्यक — {donor_first}, {patient_name} ला {slot_date} रोजी "
        "transfusion साठी दाता हवा आहे. आपण योग्य मेळ आहात. पुष्टी देण्यासाठी "
        "YES, येऊ शकत नसाल तर NO लिहा. (ref {slot_ref})"
    ),
    "bn": (
        "জরুরি — {donor_first}, {patient_name} এর {slot_date} তারিখে "
        "transfusion এর জন্য একজন দাতা প্রয়োজন। আপনি সঠিক মিল। নিশ্চিত করতে "
        "YES, আসতে না পারলে NO লিখুন। (ref {slot_ref})"
    ),
    "kn": (
        "ತುರ್ತು — {donor_first}, {patient_name} ಗೆ {slot_date} ರಂದು "
        "transfusion ಗಾಗಿ ದಾನಿ ಅಗತ್ಯವಿದೆ. ನೀವು ಸರಿಯಾದ ಹೊಂದಾಣಿಕೆ. ದೃಢೀಕರಿಸಲು "
        "YES, ಬರಲು ಸಾಧ್ಯವಾಗದಿದ್ದರೆ NO ಎಂದು ಉತ್ತರಿಸಿ. (ref {slot_ref})"
    ),
    "gu": (
        "તાત્કાલિક — {donor_first}, {patient_name} ને {slot_date} ના રોજ "
        "transfusion માટે દાતા જોઈએ છે. તમે યોગ્ય મેળ છો. ખાતરી માટે YES, "
        "ન આવી શકો તો NO લખો. (ref {slot_ref})"
    ),
}


# ---------------------------------------------------------------------------
# Phase B — automation engine follow-ups
# ---------------------------------------------------------------------------

# Sent by ``auto_pending_nudge`` to donors whose ping has been PENDING for
# longer than the configured threshold. Softer + shorter than the original
# ask — designed to feel like a friendly check-in, not a second pitch.
PENDING_PING_NUDGE: dict[str, str] = {
    "en": (
        "Hi {donor_first}, still hoping to hear back about {patient_name}'s "
        "slot on {slot_date}. A quick YES or NO works — no pressure either way."
    ),
    "hi": (
        "नमस्ते {donor_first}, {patient_name} के {slot_date} वाले slot के "
        "बारे में आपके जवाब का इंतज़ार है। बस YES या NO लिखें — कोई दबाव नहीं।"
    ),
    "te": (
        "నమస్కారం {donor_first}, {patient_name} యొక్క {slot_date} నాటి slot "
        "గురించి మీ స్పందన కోసం ఎదురుచూస్తున్నాం. కేవలం YES లేదా NO అని "
        "పంపండి — ఎటువంటి ఒత్తిడి లేదు."
    ),
    "ta": (
        "வணக்கம் {donor_first}, {patient_name} இன் {slot_date} slot குறித்து "
        "உங்கள் பதிலுக்காக காத்திருக்கிறோம். YES அல்லது NO என மட்டும் "
        "பதிலளிக்கவும் — அழுத்தம் இல்லை."
    ),
    "mr": (
        "नमस्कार {donor_first}, {patient_name} च्या {slot_date} च्या slot "
        "बद्दल आपल्या उत्तराची वाट पाहत आहोत. फक्त YES किंवा NO लिहा — "
        "कोणताही दबाव नाही."
    ),
    "bn": (
        "নমস্কার {donor_first}, {patient_name} এর {slot_date} এর slot "
        "সম্পর্কে আপনার উত্তরের জন্য অপেক্ষা করছি। শুধু YES বা NO লিখুন — "
        "কোনো চাপ নেই।"
    ),
    "kn": (
        "ನಮಸ್ಕಾರ {donor_first}, {patient_name} ರ {slot_date} slot ಬಗ್ಗೆ ನಿಮ್ಮ "
        "ಉತ್ತರಕ್ಕಾಗಿ ಕಾಯುತ್ತಿದ್ದೇವೆ. ಕೇವಲ YES ಅಥವಾ NO ಎಂದು ಉತ್ತರಿಸಿ — "
        "ಯಾವುದೇ ಒತ್ತಡವಿಲ್ಲ."
    ),
    "gu": (
        "નમસ્તે {donor_first}, {patient_name} ના {slot_date} ના slot વિશે "
        "તમારા જવાબની રાહ જોઈ રહ્યા છીએ. ફક્ત YES કે NO લખો — કોઈ દબાણ નથી."
    ),
}


# Day-before commitment reminder for donors who already said YES. Sent by
# ``auto_pre_donation_reminder`` exactly once per ping.
PRE_DONATION_REMINDER: dict[str, str] = {
    "en": (
        "Hi {donor_first}, gentle reminder — you've committed to donate for "
        "{patient_name} at {hospital} on {slot_date}. Thank you for showing "
        "up for the Blood Bridge 🩸"
    ),
    "hi": (
        "नमस्ते {donor_first}, यह एक हल्का याद दिलाना है — आपने {patient_name} "
        "के लिए {slot_date} को {hospital} में रक्तदान करने का वादा किया है। "
        "Blood Bridge के लिए धन्यवाद 🩸"
    ),
    "te": (
        "నమస్కారం {donor_first}, మృదువైన గుర్తింపు — మీరు {slot_date} నాడు "
        "{hospital} లో {patient_name} కోసం రక్తదానం చేయడానికి అంగీకరించారు. "
        "Blood Bridge కోసం ధన్యవాదాలు 🩸"
    ),
    "ta": (
        "வணக்கம் {donor_first}, மென்மையான நினைவூட்டல் — நீங்கள் {slot_date} "
        "அன்று {hospital}-ல் {patient_name}-க்காக இரத்த தானம் செய்ய ஒப்புக் "
        "கொண்டுள்ளீர்கள். Blood Bridge-க்கு நன்றி 🩸"
    ),
    "mr": (
        "नमस्कार {donor_first}, सौम्य आठवण — आपण {slot_date} रोजी {hospital} "
        "मध्ये {patient_name} साठी रक्तदान करण्याचे वचन दिले आहे. "
        "Blood Bridge साठी धन्यवाद 🩸"
    ),
    "bn": (
        "নমস্কার {donor_first}, একটি নরম মনে করিয়ে দেওয়া — আপনি {slot_date} "
        "তারিখে {hospital}-এ {patient_name} এর জন্য রক্তদান করার প্রতিশ্রুতি "
        "দিয়েছেন। Blood Bridge-এর জন্য ধন্যবাদ 🩸"
    ),
    "kn": (
        "ನಮಸ್ಕಾರ {donor_first}, ಮೃದು ನೆನಪು — ನೀವು {slot_date} ರಂದು {hospital} "
        "ನಲ್ಲಿ {patient_name} ಗಾಗಿ ರಕ್ತದಾನ ಮಾಡಲು ಒಪ್ಪಿಕೊಂಡಿದ್ದೀರಿ. "
        "Blood Bridge ಗಾಗಿ ಧನ್ಯವಾದಗಳು 🩸"
    ),
    "gu": (
        "નમસ્તે {donor_first}, હળવી યાદ — તમે {slot_date} ના રોજ {hospital} માં "
        "{patient_name} માટે રક્તદાન કરવાનું વચન આપ્યું છે. Blood Bridge "
        "માટે આભાર 🩸"
    ),
}


# Post-donation appreciation. Sent by ``auto_post_donation_thank_you`` once
# per ping after the donation is recorded. Includes the donor's next
# eligible date so they know exactly when they can help again.
POST_DONATION_THANK_YOU: dict[str, str] = {
    "en": (
        "Thank you {donor_first}! Your donation supports {patient_name}'s "
        "Blood Bridge. You're eligible to donate again on "
        "{next_eligible_date}. 🩸"
    ),
    "hi": (
        "धन्यवाद {donor_first}! आपका रक्तदान {patient_name} के Blood Bridge "
        "में मदद करता है। आप {next_eligible_date} को फिर रक्तदान कर सकते हैं। 🩸"
    ),
    "te": (
        "ధన్యవాదాలు {donor_first}! మీ రక్తదానం {patient_name} యొక్క Blood "
        "Bridge కు మద్దతుగా నిలుస్తుంది. మీరు {next_eligible_date} నాడు "
        "మళ్లీ రక్తదానం చేయవచ్చు. 🩸"
    ),
    "ta": (
        "நன்றி {donor_first}! உங்கள் இரத்த தானம் {patient_name} இன் Blood "
        "Bridge-க்கு உதவுகிறது. நீங்கள் {next_eligible_date} அன்று மீண்டும் "
        "தானம் செய்யத் தகுதியுடையவர். 🩸"
    ),
    "mr": (
        "धन्यवाद {donor_first}! आपले रक्तदान {patient_name} च्या Blood Bridge "
        "ला साथ देते. आपण {next_eligible_date} रोजी पुन्हा रक्तदान करू "
        "शकता. 🩸"
    ),
    "bn": (
        "ধন্যবাদ {donor_first}! আপনার রক্তদান {patient_name} এর Blood Bridge "
        "কে সাহায্য করে। আপনি {next_eligible_date} তারিখে আবার রক্তদান "
        "করতে পারবেন। 🩸"
    ),
    "kn": (
        "ಧನ್ಯವಾದಗಳು {donor_first}! ನಿಮ್ಮ ರಕ್ತದಾನ {patient_name} ರ Blood "
        "Bridge ಗೆ ಸಹಾಯ ಮಾಡುತ್ತದೆ. ನೀವು {next_eligible_date} ರಂದು ಮತ್ತೆ "
        "ರಕ್ತದಾನ ಮಾಡಬಹುದು. 🩸"
    ),
    "gu": (
        "આભાર {donor_first}! તમારું રક્તદાન {patient_name} ના Blood Bridge ને "
        "મદદ કરે છે. તમે {next_eligible_date} ના રોજ ફરી રક્તદાન કરી શકો છો. 🩸"
    ),
}


SWAP_REQUEST: dict[str, str] = {
    "en": (
        "Hi {donor_first}, can you swap your slot with another donor in "
        "{patient_name}'s Blood Bridge? Reply with a date that works for you."
    ),
    "hi": (
        "नमस्ते {donor_first}, क्या आप {patient_name} के Blood Bridge में किसी "
        "और दाता के साथ अपना slot बदल सकते हैं? कृपया एक उपयुक्त तारीख भेजें।"
    ),
    "te": (
        "నమస్కారం {donor_first}, మీరు {patient_name} యొక్క Blood Bridge లో మరో "
        "దాతతో మీ slot మార్చుకోగలరా? మీకు అనుకూలమైన తేదీని పంపండి."
    ),
    "ta": (
        "வணக்கம் {donor_first}, {patient_name} இன் Blood Bridge-ல் வேறு "
        "தானியருடன் உங்கள் slot-ஐ மாற்ற முடியுமா? உங்களுக்கு ஏற்ற தேதியை அனுப்பவும்."
    ),
    "mr": (
        "नमस्कार {donor_first}, आपण {patient_name} च्या Blood Bridge मध्ये दुसऱ्या "
        "दात्यासोबत आपला slot बदलू शकता का? आपल्यासाठी सोयीस्कर तारीख पाठवा."
    ),
    "bn": (
        "নমস্কার {donor_first}, আপনি কি {patient_name} এর Blood Bridge-এ অন্য "
        "দাতার সাথে আপনার slot বদল করতে পারবেন? আপনার সুবিধাজনক তারিখ পাঠান।"
    ),
    "kn": (
        "ನಮಸ್ಕಾರ {donor_first}, ನೀವು {patient_name} ರ Blood Bridge ನಲ್ಲಿ ಬೇರೆ "
        "ದಾನಿಯ ಜೊತೆ ನಿಮ್ಮ slot ಬದಲಾಯಿಸಬಹುದೇ? ನಿಮಗೆ ಸೂಕ್ತ ದಿನಾಂಕ ಕಳುಹಿಸಿ."
    ),
    "gu": (
        "નમસ્તે {donor_first}, શું તમે {patient_name} ના Blood Bridge માં બીજા "
        "દાતા સાથે તમારો slot બદલી શકો છો? તમારા માટે અનુકૂળ તારીખ મોકલો."
    ),
}


_DEFINITIONS: list[TemplateDef] = [
    TemplateDef(
        key="slot_reminder",
        label="Slot reminder",
        requires_bridge=True,
        bodies=SLOT_REMINDER,
    ),
    TemplateDef(
        key="recruit_invite",
        label="Recruit invite",
        requires_bridge=True,
        bodies=RECRUIT_INVITE,
    ),
    TemplateDef(
        key="thank_you",
        label="Thank you",
        requires_bridge=True,
        bodies=THANK_YOU,
    ),
    TemplateDef(
        key="swap_request",
        label="Swap request",
        requires_bridge=True,
        bodies=SWAP_REQUEST,
    ),
    TemplateDef(
        key="urgent_slot_alert",
        label="Urgent slot alert (Alert Allocator)",
        requires_bridge=True,
        bodies=URGENT_SLOT_ALERT,
    ),
    TemplateDef(
        key="final_ask_soft",
        label="Final ask — soft tone (Tier 3 broadcast)",
        requires_bridge=True,
        bodies=FINAL_ASK_SOFT,
    ),
    # Automation engine follow-ups
    TemplateDef(
        key="pending_ping_nudge",
        label="Pending ping nudge (4h+ no reply)",
        requires_bridge=True,
        bodies=PENDING_PING_NUDGE,
    ),
    TemplateDef(
        key="pre_donation_reminder",
        label="Pre-donation reminder (day before)",
        requires_bridge=True,
        bodies=PRE_DONATION_REMINDER,
    ),
    TemplateDef(
        key="post_donation_thank_you",
        label="Post-donation thank you",
        requires_bridge=True,
        bodies=POST_DONATION_THANK_YOU,
    ),
    # G5: caregiver-recipient templates. requires_bridge=True so the renderer
    # has patient + cohort context.
    TemplateDef(
        key="recruit_success_caregiver",
        label="Caregiver: recruit success",
        requires_bridge=True,
        bodies=RECRUIT_SUCCESS_CAREGIVER,
    ),
    TemplateDef(
        key="bridge_covered_caregiver",
        label="Caregiver: bridge covered",
        requires_bridge=True,
        bodies=BRIDGE_COVERED_CAREGIVER,
    ),
    TemplateDef(
        key="transfusion_confirmed_caregiver",
        label="Caregiver: transfusion confirmed",
        requires_bridge=True,
        bodies=TRANSFUSION_CONFIRMED_CAREGIVER,
    ),
]


# Convenience set so the API + caregiver-grouping logic can tell caregiver
# templates apart from donor templates without sniffing the key string.
CAREGIVER_TEMPLATE_KEYS: frozenset[str] = frozenset(
    {"recruit_success_caregiver", "bridge_covered_caregiver", "transfusion_confirmed_caregiver"}
)


def all_templates() -> list[TemplateDef]:
    return list(_DEFINITIONS)


def get_template(key: str) -> Optional[TemplateDef]:
    for t in _DEFINITIONS:
        if t.key == key:
            return t
    return None


def supported_languages(template: TemplateDef) -> list[str]:
    """Languages with a hand-authored body for this template."""
    return [l for l in ALL_LANGUAGES if l in template.bodies and template.bodies[l]]


def resolve_language(template: TemplateDef, requested: str) -> tuple[str, bool]:
    """Pick the actual language string we'll render, with English fallback.

    Returns (language_used, was_fallback).
    """
    if requested in template.bodies and template.bodies[requested]:
        return requested, False
    if "en" in template.bodies and template.bodies["en"]:
        return "en", True
    # Final fallback — first available body (template should always have at least one)
    for l, body in template.bodies.items():
        if body:
            return l, True
    raise ValueError(f"Template {template.key} has no bodies")


@dataclass(frozen=True)
class RenderedTemplate:
    body: str
    language_used: str
    was_fallback: bool


def render(
    key: str,
    *,
    language: str,
    # Donor-recipient vars (used by slot_reminder, recruit_invite, etc.)
    donor_first: str = "",
    donor_name: str = "",
    patient_name: str = "",
    patient_age: int = 0,
    patient_blood_group: str = "",
    # G5 caregiver-recipient vars (used by *_caregiver templates)
    caregiver_first: str = "",
    added_donor_name: str = "",
    active_donor_count: int = 0,
    next_transfusion_date: str = "",
    # G6 swap-recipient vars (used by swap_* templates)
    from_donor_first: str = "",
    from_donor_name: str = "",
    to_donor_first: str = "",
    to_donor_name: str = "",
    from_slot_date: str = "",
    to_slot_date: str = "",
    requested_name: str = "",
    ambiguous_options: str = "",
    # Alert Allocator urgent_slot_alert vars
    slot_date: str = "",
    slot_ref: str = "",
    # Phase B automation follow-up vars
    hospital: str = "",
    next_eligible_date: str = "",
) -> RenderedTemplate:
    """Render a template into a final string, with fallback to English."""
    template = get_template(key)
    if template is None:
        raise ValueError(f"Unknown template key '{key}'")

    lang_used, was_fallback = resolve_language(template, language)
    raw = template.bodies[lang_used]

    try:
        body = raw.format(
            donor_first=donor_first,
            donor_name=donor_name,
            patient_name=patient_name,
            patient_age=patient_age,
            patient_blood_group=patient_blood_group,
            caregiver_first=caregiver_first,
            added_donor_name=added_donor_name,
            active_donor_count=active_donor_count,
            next_transfusion_date=next_transfusion_date,
            from_donor_first=from_donor_first,
            from_donor_name=from_donor_name,
            to_donor_first=to_donor_first,
            to_donor_name=to_donor_name,
            from_slot_date=from_slot_date,
            to_slot_date=to_slot_date,
            requested_name=requested_name,
            ambiguous_options=ambiguous_options,
            slot_date=slot_date,
            slot_ref=slot_ref,
            hospital=hospital,
            next_eligible_date=next_eligible_date,
        )
    except KeyError as missing:
        raise ValueError(
            f"Template {key} requires variable {missing} not provided"
        ) from None

    return RenderedTemplate(
        body=body,
        language_used=lang_used,
        was_fallback=was_fallback,
    )


# ----- G6: swap state machine templates -----
# (Defined AFTER `render` so the file reads top-down for readability. Hand-
# authored in en/hi/te. Other languages fall back to English via
# resolve_language(); the swap copy is short so this is acceptable for v0.)

SWAP_REQUEST_INBOUND: dict[str, str] = {
    "en": (
        "Hi {to_donor_first}, {from_donor_name} would like to swap slots with you "
        "in {patient_name}'s Blood Bridge. They donate on {from_slot_date} and "
        "you donate on {to_slot_date}. Reply YES to accept the swap or NO to keep "
        "your current slot."
    ),
    "hi": (
        "नमस्ते {to_donor_first}, {from_donor_name} {patient_name} के Blood Bridge में "
        "आपके साथ slot बदलना चाहते हैं। वे {from_slot_date} को रक्तदान करते हैं और आप "
        "{to_slot_date} को। स्वीकार करने के लिए YES, मना करने के लिए NO लिखें।"
    ),
    "te": (
        "నమస్కారం {to_donor_first}, {from_donor_name} {patient_name} యొక్క Blood Bridge లో "
        "మీతో slot మార్చుకోవాలనుకుంటున్నారు. వారు {from_slot_date} న రక్తదానం చేస్తారు, "
        "మీరు {to_slot_date} న. అంగీకరించడానికి YES, తిరస్కరించడానికి NO అని పంపండి."
    ),
}

SWAP_CONFIRMED: dict[str, str] = {
    "en": (
        "Swap confirmed for {patient_name}'s bridge. {from_donor_name} now donates on "
        "{to_slot_date}; {to_donor_name} now donates on {from_slot_date}."
    ),
    "hi": (
        "{patient_name} के bridge के लिए swap confirmed। {from_donor_name} अब "
        "{to_slot_date} को रक्तदान करेंगे; {to_donor_name} अब {from_slot_date} को।"
    ),
    "te": (
        "{patient_name} యొక్క bridge కోసం swap నిర్ధారించబడింది. {from_donor_name} ఇప్పుడు "
        "{to_slot_date} న రక్తదానం చేస్తారు; {to_donor_name} ఇప్పుడు {from_slot_date} న."
    ),
}

SWAP_REJECTED_TO_REQUESTER: dict[str, str] = {
    "en": (
        "Hi {from_donor_first}, {to_donor_name} couldn't swap on those dates. "
        "Your slot on {from_slot_date} stays as-is for {patient_name}'s bridge."
    ),
    "hi": (
        "नमस्ते {from_donor_first}, {to_donor_name} इन तारीखों पर swap नहीं कर सके। "
        "{patient_name} के bridge के लिए {from_slot_date} पर आपका slot वैसा ही रहेगा।"
    ),
    "te": (
        "నమస్కారం {from_donor_first}, {to_donor_name} ఆ తేదీలలో swap చేయలేకపోయారు. "
        "{patient_name} యొక్క bridge కోసం {from_slot_date} న మీ slot అలాగే ఉంటుంది."
    ),
}

SWAP_UNKNOWN_DONOR: dict[str, str] = {
    "en": (
        "Hi {from_donor_first}, we couldn't find a donor matching \"{requested_name}\" "
        "on {patient_name}'s bridge. Reply: swap with <full name> on <date>."
    ),
    "hi": (
        "नमस्ते {from_donor_first}, हमें {patient_name} के bridge पर \"{requested_name}\" "
        "नाम का कोई दाता नहीं मिला। इस तरह लिखें: swap with <पूरा नाम> on <तारीख>।"
    ),
    "te": (
        "నమస్కారం {from_donor_first}, {patient_name} యొక్క bridge లో \"{requested_name}\" "
        "పేరుతో దాత కనుగొనబడలేదు. ఇలా పంపండి: swap with <పూర్తి పేరు> on <తేదీ>."
    ),
}

SWAP_AMBIGUOUS: dict[str, str] = {
    "en": (
        "Hi {from_donor_first}, multiple donors match \"{requested_name}\" on "
        "{patient_name}'s bridge: {ambiguous_options}. Reply with the full name."
    ),
    "hi": (
        "नमस्ते {from_donor_first}, {patient_name} के bridge पर \"{requested_name}\" "
        "नाम से कई दाता मेल खाते हैं: {ambiguous_options}। कृपया पूरा नाम लिखें।"
    ),
    "te": (
        "నమస్కారం {from_donor_first}, {patient_name} యొక్క bridge లో \"{requested_name}\" "
        "తో అనేక దాతలు సరిపోతున్నారు: {ambiguous_options}. దయచేసి పూర్తి పేరు పంపండి."
    ),
}

_DEFINITIONS.extend([
    TemplateDef(
        key="swap_request_inbound",
        label="Swap: notify target donor",
        requires_bridge=True,
        bodies=SWAP_REQUEST_INBOUND,
    ),
    TemplateDef(
        key="swap_confirmed",
        label="Swap: confirmed (to both)",
        requires_bridge=True,
        bodies=SWAP_CONFIRMED,
    ),
    TemplateDef(
        key="swap_rejected_to_requester",
        label="Swap: rejected (to requester)",
        requires_bridge=True,
        bodies=SWAP_REJECTED_TO_REQUESTER,
    ),
    TemplateDef(
        key="swap_unknown_donor",
        label="Swap: unknown target donor",
        requires_bridge=True,
        bodies=SWAP_UNKNOWN_DONOR,
    ),
    TemplateDef(
        key="swap_ambiguous",
        label="Swap: ambiguous target donor",
        requires_bridge=True,
        bodies=SWAP_AMBIGUOUS,
    ),
])

SWAP_TEMPLATE_KEYS: frozenset[str] = frozenset(
    {"swap_request_inbound", "swap_confirmed", "swap_rejected_to_requester",
     "swap_unknown_donor", "swap_ambiguous"}
)
