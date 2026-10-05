"""SAARTHI lexicon: English, Hinglish (Roman) and Hindi (Devanagari) vocabulary.

Every phrase maps onto a closed set of values (part numbers, failure modes,
actions), so the extractor can only ever produce a value that exists in the
fleet schema. Devanagari entries include the loanword spellings that browser
speech recognition emits for hi-IN ("हाइड्रोलिक पंप लीक").

All phrases pass through ``normalise`` before matching, so entries here may be
written in any case and with or without nukta / chandrabindu.
"""
from __future__ import annotations

# ---------------------------------------------------------------- numbers

NUMBER_WORDS: dict[str, int] = {}
for _words, _v in [
    (("zero", "oh", "shunya", "sunya", "शून्य", "ज़ीरो", "जीरो"), 0),
    (("one", "ek", "एक", "वन"), 1),
    (("two", "do", "दो", "टू"), 2),
    (("three", "teen", "तीन", "थ्री"), 3),
    (("four", "char", "chaar", "चार", "फोर"), 4),
    (("five", "paanch", "panch", "पांच", "पाँच", "फाइव"), 5),
    (("six", "chhe", "chhah", "chah", "che", "छह", "छः", "छे", "सिक्स"), 6),
    (("seven", "saat", "sat", "सात", "सेवन"), 7),
    (("eight", "aath", "aat", "आठ", "एट"), 8),
    (("nine", "nau", "नौ", "नाइन"), 9),
    (("ten", "das", "दस", "टेन"), 10),
    (("eleven", "gyarah", "gyaarah", "ग्यारह"), 11),
    (("twelve", "barah", "baarah", "बारह"), 12),
    (("thirteen", "terah", "तेरह"), 13),
    (("fourteen", "chaudah", "चौदह"), 14),
    (("fifteen", "pandrah", "पंद्रह", "पन्द्रह"), 15),
    (("sixteen", "solah", "सोलह"), 16),
    (("seventeen", "satrah", "सत्रह"), 17),
    (("eighteen", "atharah", "अठारह"), 18),
    (("nineteen", "unnis", "उन्नीस"), 19),
    (("twenty", "bees", "बीस"), 20),
]:
    for _w in _words:
        NUMBER_WORDS[_w] = _v

ORDINALS = {
    1: ("first", "1st", "pehla", "pahla", "pehle", "pahle", "pehli", "पहला", "पहले", "पहली"),
    2: ("second", "2nd", "doosra", "dusra", "doosre", "dusre", "doosri", "dusri", "दूसरा", "दूसरे", "दूसरी"),
    3: ("third", "3rd", "teesra", "tisra", "teesre", "teesri", "तीसरा", "तीसरे", "तीसरी"),
    4: ("fourth", "4th", "chautha", "chauthe", "chauthi", "चौथा", "चौथे", "चौथी"),
}

SIDES = {
    1: ("left", "baayan", "bayan", "baaya", "baayen", "baen", "बायां", "बाएं", "बाया", "बाईं", "लेफ्ट"),
    2: ("right", "daayan", "dayan", "daaya", "daayen", "daen", "दायां", "दाएं", "दाया", "दाईं", "राइट"),
}

# ---------------------------------------------------------------- structure words

BASE_WORDS = ("b", "bee", "base", "बी", "बेस")
FLEET_WORDS = {
    "FighterH": ("fighter", "jet", "फाइटर", "लड़ाकू", "ladaku", "ladaaku"),
    "HeloU": ("helicopter", "heli", "helo", "chopper", "हेलीकॉप्टर", "हेलिकॉप्टर", "हेलीकाप्टर", "हेलो", "हेली"),
}
# two-letter tail prefixes as spoken letters ("F I", "एफ आई")
TAIL_PREFIX = {"FighterH": ("fi", "f i", "एफ आई", "एफआई"), "HeloU": ("he", "h e", "एच ई", "एचई")}
TAIL_WORDS = ("tail", "aircraft", "airframe", "jahaz", "jahaaz", "jahaj", "विमान", "जहाज", "टेल", "एयरक्राफ्ट")
NUMBER_MARKERS = ("number", "no", "num", "nambar", "numbar", "नंबर", "नम्बर")
CONNECTORS = ("ka", "ki", "ke", "का", "की", "के", "par", "pe", "पर", "पे", "mein", "me", "में", "the", "of", "on", "at")
POSITION_WORDS = ("position", "pos", "posn", "slot", "पोजीशन", "पोजिशन", "पोज़ीशन", "स्थान", "sthan")
ENGINE_WORDS = ("engine", "injan", "इंजन")
SERIAL_WORDS = ("serial", "sr", "sn", "s/n", "सीरियल", "सिरियल")

# ---------------------------------------------------------------- parts (per part number)

PART_PHRASES: dict[str, tuple[str, ...]] = {
    "FH-FP-01": ("engine fuel pump", "fuel pump", "fuel ka pump", "eendhan pump", "indhan pump",
                 "फ्यूल पंप", "ईंधन पंप", "इंधन पंप"),
    "FH-OP-02": ("engine oil pump", "oil pump", "oil ka pump", "tel pump", "ऑयल पंप", "आयल पंप", "तेल पंप",
                 "lube pump"),
    "FH-HP-03": ("hydraulic pump", "hydraulics pump", "hydraulic ka pump", "हाइड्रोलिक पंप", "हाइड्रॉलिक पंप"),
    "FH-AC-04": ("flight control actuator", "control actuator", "actuator", "एक्चुएटर", "एक्टुएटर",
                 "कंट्रोल एक्चुएटर"),
    "FH-RD-05": ("radar transmitter", "radar", "रडार", "राडार", "रडार ट्रांसमीटर"),
    "FH-MF-06": ("multi function display", "multifunction display", "mfd", "display", "screen",
                 "डिस्प्ले", "स्क्रीन", "एमएफडी"),
    "FH-GN-07": ("ac generator", "generator", "alternator", "जनरेटर", "जेनरेटर", "अल्टरनेटर"),
    "FH-CT-08": ("ecs cooling turbine", "cooling turbine", "ecs turbine", "ecs", "turbine",
                 "कूलिंग टरबाइन", "टरबाइन", "टर्बाइन"),
    "FH-BR-09": ("wheel brake unit", "wheel brake", "brake unit", "brake", "brakes", "ब्रेक"),
    "HU-SW-01": ("swashplate assembly", "swashplate", "swash plate", "स्वाशप्लेट", "स्वॉश प्लेट", "स्वाश प्लेट"),
    "HU-GB-02": ("accessory gearbox", "gearbox", "gear box", "गियरबॉक्स", "गियर बॉक्स", "गियरबाक्स"),
    "HU-FC-03": ("fuel control unit", "fuel control", "fcu", "फ्यूल कंट्रोल", "ईंधन नियंत्रण"),
    "HU-HP-04": ("hydraulic pump", "hydraulics pump", "hydraulic ka pump", "हाइड्रोलिक पंप", "हाइड्रॉलिक पंप"),
    "HU-AV-05": ("autopilot computer", "autopilot", "auto pilot", "ऑटोपायलट", "ऑटो पायलट"),
    "HU-ST-06": ("starter generator", "starter", "generator", "स्टार्टर", "जनरेटर", "जेनरेटर"),
    "HU-DA-07": ("lead lag damper", "lead-lag damper", "damper", "डैम्पर", "डैंपर", "डम्पर"),
}
# a bare head noun that names several parts: ask which one
PART_HEADS = {"pump": ("pump", "pumps", "पंप", "पम्प")}

# ---------------------------------------------------------------- failure modes

MODE_PHRASES: dict[str, tuple[str, ...]] = {
    "pressure_low": ("low pressure", "pressure low", "pressure kam", "kam pressure", "pressure drop",
                     "pressure dropping", "pressure gir", "प्रेशर कम", "कम प्रेशर", "दबाव कम", "कम दबाव", "प्रेशर ड्रॉप"),
    "leak": ("leak", "leaking", "leakage", "seepage", "tapak", "tapakna", "tapak raha", "लीक", "लीकेज", "रिसाव",
             "टपक"),
    "contamination": ("contamination", "contaminated", "dirty", "ganda", "gandagi", "particles in fuel",
                      "कंटैमिनेशन", "गंदा", "गंदगी", "मिलावट"),
    "chip_detected": ("chip detected", "chip detector", "chip light", "chips", "chip", "metal particles",
                      "चिप डिटेक्टर", "चिप"),
    "corrosion": ("corrosion", "corroded", "rust", "rusted", "jung", "zang", "कोरोजन", "करोजन", "जंग", "ज़ंग"),
    "bite_fail": ("bite fail", "bite failure", "bit fail", "bite", "self test fail", "built in test",
                  "test fail", "बाइट फेल", "बाइट", "टेस्ट फेल"),
    "intermittent": ("intermittent", "kabhi kabhi", "on off", "aata jaata", "flicker", "flickering",
                     "इंटरमिटेंट", "कभी कभी", "आता जाता"),
    "no_output": ("no output", "output nahi", "dead", "not working", "kaam nahi", "nahi chal",
                  "आउटपुट नहीं", "काम नहीं", "नहीं चल", "डेड"),
    "overheat": ("overheat", "overheating", "over heat", "over temperature", "temperature high", "high temp",
                 "garam", "bahut garam", "ओवरहीट", "गरम", "गर्म", "ज्यादा गरम"),
    "bearing_wear": ("bearing wear", "bearing noise", "bearing", "बेयरिंग"),
    "erosion": ("erosion", "eroded", "sand erosion", "sand damage", "इरोजन", "क्षरण"),
    "wear": ("wear", "worn", "worn out", "wear out", "ghisa", "ghis gaya", "ghisav", "घिसा", "घिस", "घिसाव",
             "वियर"),
    "crack": ("crack", "cracked", "darar", "toota", "टूटा", "दरार", "क्रैक"),
    "flow_error": ("flow error", "flow fault", "fuel flow", "flow galat", "flow", "फ्लो एरर", "फ्लो"),
}

NEGATION_BEFORE = ("no", "not", "koi", "bina", "without", "nil", "कोई", "बिना", "नो")
NEGATION_AFTER = ("clean", "ok", "okay", "theek", "thik", "normal", "negative", "nil", "nahi", "nahin",
                  "साफ", "ठीक", "नार्मल", "नॉर्मल", "नहीं", "निल")

# ---------------------------------------------------------------- actions

ACTION_PHRASES: dict[str, tuple[str, ...]] = {
    "replaced": ("replaced", "replace", "replace kiya", "changed", "change kiya", "swapped", "badla",
                 "badal diya", "badal di", "naya lagaya", "बदला", "बदल दिया", "बदल दी", "रिप्लेस", "चेंज"),
    "removed": ("removed", "remove kiya", "taken off", "nikala", "nikal diya", "utara", "utaar diya",
                "निकाला", "निकाल दिया", "उतारा", "रिमूव"),
    "sent_for_repair": ("sent for repair", "repair ke liye bheja", "repair ko bheja", "sent to brd",
                        "bhej diya", "bheja", "रिपेयर के लिए भेजा", "भेज दिया", "भेजा"),
    "rectified_in_situ": ("rectified", "fixed", "repaired on aircraft", "theek kiya", "thik kiya",
                          "sahi kiya", "ठीक किया", "सही किया", "ठीक कर दिया"),
    "inspected": ("inspected", "checked", "check kiya", "dekha", "jaanch", "jaanch ki", "जांच", "जाँच", "चेक किया"),
    "deferred": ("deferred", "defer", "carried forward", "baad mein", "बाद में", "डेफर"),
}

ACTION_LABELS = {
    "reported": "Reported only",
    "inspected": "Inspected",
    "rectified_in_situ": "Rectified on aircraft",
    "removed": "Removed",
    "replaced": "Replaced from stores",
    "sent_for_repair": "Sent for repair",
    "deferred": "Deferred (needs supervisor)",
}

ACTION_HINGLISH = {
    "reported": "report kiya", "inspected": "jaanch ki", "rectified_in_situ": "theek kiya",
    "removed": "nikala", "replaced": "badla", "sent_for_repair": "repair ke liye bheja",
    "deferred": "defer kiya",
}

MODE_LABELS = {
    "pressure_low": "Low pressure", "leak": "Leak", "contamination": "Contamination",
    "chip_detected": "Chip detected", "corrosion": "Corrosion", "bite_fail": "BITE fail",
    "intermittent": "Intermittent", "no_output": "No output", "overheat": "Overheat",
    "bearing_wear": "Bearing wear", "erosion": "Erosion", "wear": "Wear", "crack": "Crack",
    "flow_error": "Flow error",
}

# Words that mark a Roman-script sentence as Hinglish rather than English.
HINGLISH_MARKERS = ("ka", "ki", "ke", "hai", "hain", "diya", "kiya", "gaya", "mein", "nahi", "pe", "par",
                    "raha", "rahi", "aur", "ko", "se", "badla", "nikala", "bheja", "theek", "wala")

FILLERS = ("haan", "toh", "to", "matlab", "uh", "um", "accha", "acha", "ji", "sir", "okay so", "हाँ", "तो")
