# SAARTHI field readiness: real logbook language, the parts catalogue, and speech on the node

> **Status:** built and tested (all tests passing; see the README for the count).
> - SAARTHI now reads real maintenance English. On 4,383 held-out entries from a real aircraft-engine logbook it extracts part, problem, cylinders, engine side and action, and links the part to the illustrated parts catalogue (IPC).
> - Voice input runs **on the NIRANTAR node** with an open-source recogniser, so no audio leaves a closed network.
> - What has not been done is a field trial with technicians' voices in a hangar. §5 is the protocol, and the tool for it is built.

---

## 1. What changed and why

| Before | Now |
|---|---|
| Voice through the browser's speech service (Chrome or Edge send the audio to the vendor's cloud) | Speech recognised on the node (Vosk/Kaldi, Apache 2.0); browser speech only in demo mode, never in secure mode |
| Part names from a hand-written lexicon of the synthetic fleet | Part vocabulary loaded from the fleet's **illustrated parts catalogue**, with technician-to-catalogue synonyms |
| Tested only on generated utterances (100% on its own benchmark, which says little about the field) | Tested on **6,169 real logbook entries** (University of North Dakota aviation program via MaintNet/AKGAM) with a held-out split |
| Tail numbers had to be said as letters ("F I B one zero seven") | The NATO alphabet and letter names also work ("foxtrot india bravo one oh seven", "eff eye bee …") |

---

## 2. Real logbook English (`saarthi/logbook.py`)

Entries look like this:

> `#2 & 3 ROCKER COVER GASKETS LEAKING, R/H ENG.` / `REMOVED & REPLACED ROCKER COVER GASKETS.`

SAARTHI turns them into:

- **part** `ROCKER COVER GASKET`, linked to catalogue part **75906** (gasket, rocker box cover);
- **problem** `leak`;
- **cylinders** `[2, 3]`;
- **engine** `R`;
- **action** `replace`.

It expands common shorthand (CYL, ENG, ASSY, R/H, R&R, INSP, CK and others) and copes with text the source cut mid-word. When a bare word such as "clamp" matches several catalogue entries in different assemblies, it asks which one rather than guessing.

**Evaluation** (`python -m nirantar logbook-eval`):
- The rules were developed on a fixed 30% of entries and scored once on the other 70%. The 60 entries read while designing are excluded from the test.
- The only labels available are GPT-4o extractions made by the AKGAM authors (a *silver* reference, not expert-validated).

| Held-out test, 4,383 entries | Agreement with the reference |
|---|---|
| Part, exact phrase | 81% |
| Part, same part noun | 91% |
| Problem category | 99% |
| Cylinders | 96% |
| Engine side | 98% |
| Corrective action | 95% |

The parts catalogue plus a small general glossary give 79.6% exact on parts by themselves. Part names learned from the development split add only about 1 point, so the vocabulary comes from the catalogue, as it should.

**Who is right when they disagree?** I judged twenty random test disagreements per field by hand (`data/lycoming/adjudication.json`):

| Field | SAARTHI right | Reference right | Neither or ambiguous |
|---|---|---|---|
| Part | 15 | 5 | 0 |
| Problem | 15 | 3 | 2 |
| Action | 13 | 5 | 2 |
| Cylinders | 12 | 8 | 0 |
| Engine side | 0 | 4 | 16 |

So the agreement figures understate accuracy. Engine side is mostly ambiguous in the text itself: "R/H BAFFLE" can mean the right engine's baffle or the right side of a baffle.

Patterns these samples exposed (number lists after a part name, "GROUND RUN" read as grinding, and others) are recorded but were **not** tuned on, so the figures stay held-out numbers.

**Catalogue links.** On an unseen sample of 30 entries, SAARTHI offered 22 links and 16 were correct. It abstained on 8. The errors are mostly airframe baffles: only the engine's catalogue was available, so they have no correct entry. A deployment loads the whole aircraft's catalogue.

The API is `POST /api/saarthi/logbook {"problem": ..., "action": ...}`, which returns the fields and catalogue candidates.

---

## 3. Speech on the node (`saarthi/asr.py`)

```bash
python -m nirantar serve --auth ... --asr-model en=models/vosk-model-small-en-in-0.4 [--asr-model hi=models/vosk-model-small-hi-0.22]
```

**How a recording flows:**
- The browser records the microphone at 16 kHz, through an AudioWorklet served by the node.
- It sends raw audio to `/api/saarthi/transcribe`, with the same login, role and forgery checks as every request, and a limit of about 60 s.
- The node decodes it with Vosk's native library, called directly through `ctypes`. The wheel's Python wrapper pulls in packages only needed for subtitles and downloads, which would not install offline.

**Two readings per recording:**
- *free*: the model's full English;
- *within SAARTHI's vocabulary*: about 540 words the model knows, from the lexicon, the catalogue, tail-number letters and numbers.

A restricted vocabulary is not automatically better, because it loses the model's word-order statistics. On the one real recording available here, free decoding was perfect and the restricted one turned "one oh" into "auto". So SAARTHI keeps whichever reading it can structure into more fields (free on a tie) and shows the other reading to the technician.

**Models.** No model is shipped in the repository. The unit obtains one from a verified source (Alpha Cephei's Indian-English small model, and the Hindi one for Hinglish), checks it, and includes it in the offline bundle:

```bash
python -m nirantar bundle --speech-model models/vosk-model-small-en-in-0.4 ...
```

The bundle installs the Vosk wheel (Windows and Linux) without its optional extras. `selftest` reports whether the speech engine loads.

**What was verified here:**
- The engine runs offline on a real speech sample (Vosk's own test recording, in `tests/data`), correctly, in 0.2 s.
- The full browser path was exercised with that recording as a fake microphone in headless Chromium: microphone → AudioWorklet → node → recogniser → parser, with the other reading shown.
- The development model was Alpha Cephei's small US-English model, found inside an npm package. It is not distributed.

---

## 4. Hinglish and Hindi

The English model does not know Hinglish words ("badal", "kharab", "aath" and others are listed as unknown by the console). Voice entry in Hinglish needs the Hindi model alongside the English one, and the language selector chooses between them. Typed Hinglish and Hindi work as before.

---

## 5. Field trial (the remaining step, needs a unit)

1. **Record.** 200+ real snag reports from at least 10 technicians, in the hangar and on the flight line, in English and Hinglish, saying what they would write. Save each as `NAME.wav` (16-bit mono) with `NAME.txt` holding what was said.
2. **Score the recogniser.** `python -m nirantar asr-trial FOLDER --asr-model en=...` gives the word error rate free and within the vocabulary, for each recording and overall.
3. **Score SAARTHI end to end.** Use the console's own log: how often an entry was signed with no field corrected (already recorded per entry as `edited_fields`), and the median time to log.
4. **Adapt the vocabulary.** Add the unit's words and synonyms (catalogue names, local usage) to the vocabulary, not the code. Then repeat.

Acceptance targets proposed (docs/05): over 90% of entries signed without manual correction, a median under 30 s, and zero silent errors (wrong values signed unchallenged).
