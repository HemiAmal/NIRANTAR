"""Hand-written SAARTHI gold set: phrasing written independently of the generator.

Written before the extractor was run on it. First run: 32/36 utterances and
156/160 fields right; one parser bug was then fixed ("two no output" read as a
position) and two labels here were corrected where the schema made SAARTHI's
answer the right one (marked with comments).

Each case: (utterance, expected fields). ``None`` means SAARTHI should leave the
field open and ask (it must not guess). Fields not listed are not scored.
"""

GOLD = [
    # English, clean
    ("FI-B2-04 radar transmitter BITE failure, removed", dict(tail="FI-B2-04", part="FH-RD-05", position=1, mode="bite_fail", action="removed")),
    # "crack" is not a recorded failure mode of rotor-family parts in the schema: SAARTHI must ask
    ("HE-B3-09 lead-lag damper no. 2 cracked, replaced", dict(tail="HE-B3-09", part="HU-DA-07", position=2, mode=None, action="replaced")),
    ("On FI-B1-12 the left wheel brake is worn out. Replaced it.", dict(tail="FI-B1-12", part="FH-BR-09", position=1, mode="wear", action="replaced")),
    ("FI B2 16, ECS cooling turbine overheating, sent for repair", dict(tail="FI-B2-16", part="FH-CT-08", position=1, mode="overheat", action="sent_for_repair")),
    ("HE B4 07 autopilot intermittent, checked", dict(tail="HE-B4-07", part="HU-AV-05", position=1, mode="intermittent", action="inspected")),
    ("helicopter B4 number 3, fuel control unit flow error", dict(tail="HE-B4-03", part="HU-FC-03", position=None, mode="flow_error", action="reported")),
    ("HE B1 02 starter generator two no output, removed and sent for repair", dict(tail="HE-B1-02", part="HU-ST-06", position=2, mode="no_output", action="sent_for_repair")),
    ("fighter B2 tail 8 AC generator right side overheat", dict(tail="FI-B2-08", part="FH-GN-07", position=2, mode="overheat", action="reported")),
    ("FI B1 11 oil pump position 1 chip light came on, oil pump removed", dict(tail="FI-B1-11", part="FH-OP-02", position=1, mode="chip_detected", action="removed")),
    ("FI B1 03 MFD flickering, fixed", dict(tail="FI-B1-03", part="FH-MF-06", position=1, mode="intermittent", action="rectified_in_situ")),
    # English, spoken style (numbers as words, no punctuation)
    ("f i b two one five hydraulic pump number one low pressure", dict(tail="FI-B2-15", part="FH-HP-03", position=1, mode="pressure_low")),
    ("h e b three zero six swashplate corrosion found deferred", dict(tail="HE-B3-06", part="HU-SW-01", position=1, mode="corrosion", action="deferred")),
    ("fighter base two number nineteen actuator leaking", dict(tail="FI-B2-19", part="FH-AC-04", position=1, mode="leak")),
    ("jet b one tail twenty brakes worn", dict(tail="FI-B1-20", part="FH-BR-09", position=None, mode="wear")),
    # Hinglish
    ("FI B1 09 ka hydraulic pump do number leak kar raha hai, badal diya", dict(tail="FI-B1-09", part="FH-HP-03", position=2, mode="leak", action="replaced")),
    ("B2 ka 5 number fighter, radar ka bite fail aa raha hai", dict(tail="FI-B2-05", part="FH-RD-05", position=1, mode="bite_fail", action="reported")),
    ("heli B3 ka 1 number, damper teen ghis gaya, nikal diya", dict(tail="HE-B3-01", part="HU-DA-07", position=3, mode="wear", action="removed")),
    ("chopper B4 2 number gearbox mein corrosion mila, repair ke liye bheja", dict(tail="HE-B4-02", part="HU-GB-02", position=1, mode="corrosion", action="sent_for_repair")),
    ("FI B2 10 pehla generator kaam nahi kar raha", dict(tail="FI-B2-10", part="FH-GN-07", position=1, mode="no_output")),
    ("FI B1 14 fuel pump number 2, fuel ganda tha, contamination, check kiya", dict(tail="FI-B1-14", part="FH-FP-01", position=2, mode="contamination", action="inspected")),
    ("HE B1 08 autopilot kabhi kabhi band ho jata hai", dict(tail="HE-B1-08", part="HU-AV-05", position=1, mode="intermittent")),
    ("fighter B1 ka das number, ecs turbine garam ho raha hai, theek kiya", dict(tail="FI-B1-10", part="FH-CT-08", position=1, mode="overheat", action="rectified_in_situ")),
    # Hindi (Devanagari, as hi-IN speech recognition writes it)
    ("एफ आई बी टू जीरो वन रडार बाइट फेल", dict(tail="FI-B2-01", part="FH-RD-05", position=1, mode="bite_fail")),
    ("एच ई बी थ्री जीरो फाइव डैम्पर नंबर दो में दरार, बदल दिया", dict(tail="HE-B3-05", part="HU-DA-07", position=2, mode=None, action="replaced")),
    ("फाइटर बी 1 नंबर 13 का बायां ब्रेक घिस गया", dict(tail="FI-B1-13", part="FH-BR-09", position=1, mode="wear")),
    ("हेलीकॉप्टर बी 4 नंबर 9 गियरबॉक्स में जंग, जांच की", dict(tail="HE-B4-09", part="HU-GB-02", position=1, mode="corrosion", action="inspected")),
    ("बी 2 का 7 नंबर फाइटर, दूसरा ऑयल पंप प्रेशर कम, निकाल दिया", dict(tail="FI-B2-07", part="FH-OP-02", position=2, mode="pressure_low", action="removed")),
    ("एफ आई बी वन सिक्स, एक्चुएटर लीक", dict(tail="FI-B1-06", part="FH-AC-04", position=1, mode="leak")),
    ("हेलो बी 3 नंबर 2 स्टार्टर पहला ओवरहीट", dict(tail="HE-B3-02", part="HU-ST-06", position=1, mode="overheat")),
    # must ask rather than guess
    ("B1 05 pump leaking", dict(tail=None, part=None, mode="leak")),
    ("fuel pump leak", dict(tail=None, part="FH-FP-01", position=None)),     # only the fighter has a fuel pump
    ("FI B1 07 hydraulic pump leak", dict(tail="FI-B1-07", part="FH-HP-03", position=None, mode="leak")),
    ("FI B1 32 radar bite fail", dict(tail=None, part="FH-RD-05", mode="bite_fail")),
    ("FI B1 07 oil pump 1, chip detector clean, no leak", dict(tail="FI-B1-07", part="FH-OP-02", position=1, mode=None)),
    ("HE B3 02 swashplate crack nahi hai, corrosion hai", dict(tail="HE-B3-02", part="HU-SW-01", mode="corrosion")),
    ("FI B2 03 brake 3 worn", dict(tail="FI-B2-03", part="FH-BR-09", position=None, mode="wear")),
]
