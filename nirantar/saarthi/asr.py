"""Speech recognition on the node, with no network (SAARTHI field mode).

Browser speech input (Chrome, Edge) sends the audio to the browser maker's
cloud, which is not acceptable on a closed network. Here audio is
recognised on the NIRANTAR node itself with Vosk (Kaldi), Apache 2.0:

* the engine is the ``vosk`` wheel's native library, called through
  ``ctypes`` (the wheel's Python wrapper pulls in packages only needed for
  subtitles and downloads, so it is not imported);
* the model is a folder the unit installs from a verified source (e.g. Alpha
  Cephei's ``vosk-model-small-en-in``); one model per language
  (``--asr-model en=PATH --asr-model hi=PATH``);
* recognition can be **restricted to the words SAARTHI understands** (tail
  numbers, part names from the parts catalogue, findings, actions, numbers).
  A small vocabulary is what makes speech in a noisy hangar usable. Words the
  model does not know are reported, not silently dropped.

``wer`` scores transcripts against references for field trials.
"""
from __future__ import annotations

import ctypes
import importlib.util
import json
import os
import re
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

SAMPLE_RATE = 16000


def _library_path() -> Path:
    spec = importlib.util.find_spec("vosk")       # locate the wheel without running its __init__
    if spec is None or not spec.submodule_search_locations:
        raise RuntimeError("the vosk package is not installed (offline bundle: wheels/vosk-*.whl)")
    d = Path(list(spec.submodule_search_locations)[0])
    name = {"win32": "libvosk.dll", "darwin": "libvosk.dyld"}.get(sys.platform, "libvosk.so")
    if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
        os.add_dll_directory(str(d))               # its MinGW runtime DLLs sit beside it
    return d / name


class _Lib:
    _lib = None
    _lock = threading.Lock()

    @classmethod
    def get(cls):
        with cls._lock:
            if cls._lib is None:
                lib = ctypes.CDLL(str(_library_path()))
                P, C, I, F = ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.c_float
                sig = {
                    "vosk_set_log_level": ([I], None), "vosk_model_new": ([C], P), "vosk_model_free": ([P], None),
                    "vosk_model_find_word": ([P, C], I), "vosk_recognizer_new": ([P, F], P),
                    "vosk_recognizer_new_grm": ([P, F, C], P), "vosk_recognizer_set_words": ([P, I], None),
                    "vosk_recognizer_accept_waveform": ([P, C, I], I), "vosk_recognizer_final_result": ([P], C),
                    "vosk_recognizer_free": ([P], None),
                }
                for name, (args, res) in sig.items():
                    fn = getattr(lib, name)
                    fn.argtypes, fn.restype = args, res
                lib.vosk_set_log_level(-1)
                cls._lib = lib
            return cls._lib


@dataclass
class Transcript:
    text: str
    words: list[dict]
    grammar: bool
    unknown_share: float


class VoskEngine:
    """One loaded model (thread-safe: each call makes its own recogniser)."""

    def __init__(self, model_dir: str | Path, lang: str = "en"):
        self.dir, self.lang = Path(model_dir), lang
        if not (self.dir / "am").exists() and not (self.dir / "conf").exists():
            raise FileNotFoundError(f"{self.dir} does not look like a Vosk model folder")
        self.lib = _Lib.get()
        self.model = self.lib.vosk_model_new(str(self.dir).encode())
        if not self.model:
            raise RuntimeError(f"could not load the speech model in {self.dir}")
        self.name = self.dir.name
        self._vocab = None

    def knows(self, word: str) -> bool:
        return self.lib.vosk_model_find_word(self.model, word.lower().encode()) >= 0

    def grammar(self, phrases) -> tuple[list[str], list[str]]:
        """(words the model knows, words it does not) from SAARTHI's vocabulary phrases."""
        words = sorted({w for p in phrases for w in re.findall(r"[a-z']+", str(p).lower())})
        known = [w for w in words if self.knows(w)]
        return known, [w for w in words if w not in set(known)]

    def transcribe(self, pcm16: bytes, rate: int = SAMPLE_RATE, grammar: list[str] | None = None) -> Transcript:
        """16-bit mono PCM in; text and per-word confidence out. With ``grammar``, only those words (or [unk])."""
        lib = self.lib
        if grammar:
            rec = lib.vosk_recognizer_new_grm(self.model, float(rate), json.dumps(sorted(set(grammar)) + ["[unk]"]).encode())
        else:
            rec = lib.vosk_recognizer_new(self.model, float(rate))
        try:
            lib.vosk_recognizer_set_words(rec, 1)
            step = 8000
            for i in range(0, len(pcm16), step):
                chunk = pcm16[i:i + step]
                lib.vosk_recognizer_accept_waveform(rec, chunk, len(chunk))
            out = json.loads(lib.vosk_recognizer_final_result(rec).decode("utf-8"))
        finally:
            lib.vosk_recognizer_free(rec)
        words = [{"word": w["word"], "conf": round(float(w.get("conf", 1.0)), 3),
                  "start": round(float(w.get("start", 0)), 2), "end": round(float(w.get("end", 0)), 2)}
                 for w in out.get("result", [])]
        unk = sum(w["word"] == "[unk]" for w in words) / max(len(words), 1)
        text = " ".join(w["word"] for w in words if w["word"] != "[unk]") or out.get("text", "")
        return Transcript(text, words, bool(grammar), round(unk, 3))


class SpeechService:
    """The node's recognisers by language, plus the domain grammar built from SAARTHI's vocabulary."""

    def __init__(self, models: dict[str, str | Path], phrases: list[str] | None = None):
        self.engines = {lang: VoskEngine(path, lang) for lang, path in models.items()}
        self.phrases = list(phrases or [])
        self.grammars = {lang: e.grammar(self.phrases) for lang, e in self.engines.items()}

    def info(self) -> dict:
        return {"available": bool(self.engines), "engine": "vosk (on this node)",
                "languages": {lang: {"model": e.name, "grammar_words": len(self.grammars[lang][0]),
                                     "unknown_words": self.grammars[lang][1][:40]}
                              for lang, e in self.engines.items()}}

    def transcribe(self, pcm16: bytes, lang: str, rate: int = SAMPLE_RATE, restrict: bool = True,
                   score=None) -> dict:
        """Decode freely and, if ``restrict``, also within SAARTHI's vocabulary. A restricted vocabulary has no
        word-order statistics, so it is not always better: keep the transcript ``score(text)`` (how many fields
        SAARTHI can structure from it) rates higher, the free one on a tie. Both are returned."""
        e = self.engines.get(lang) or next(iter(self.engines.values()))
        free = e.transcribe(pcm16, rate, None)
        known = self.grammars[e.lang][0]
        res = {"lang": e.lang, "model": e.name, "free_text": free.text, "restricted_text": None, "chosen": "free",
               "text": free.text, "words": free.words}
        if restrict and known:
            g = e.transcribe(pcm16, rate, known)
            res["restricted_text"], res["unknown_share"] = g.text, g.unknown_share
            if score is not None and g.text and score(g.text) > score(free.text):
                res.update(chosen="restricted", text=g.text, words=g.words)
        return res


def wav_pcm16(path: str | Path) -> tuple[bytes, int]:
    import wave
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2 or w.getnchannels() != 1:
            raise ValueError("expected 16-bit mono WAV")
        return w.readframes(w.getnframes()), w.getframerate()


def wer(ref: str, hyp: str) -> tuple[int, int]:
    """(word edits, reference words): word error rate = edits / words."""
    r, h = ref.lower().split(), hyp.lower().split()
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (r[i - 1] != h[j - 1]))
            prev, d[j] = d[j], cur
    return d[len(h)], len(r)


def field_trial(service: SpeechService, folder: str | Path, lang: str = "en") -> dict:
    """Score recordings ``NAME.wav`` against ``NAME.txt`` (what was said): word error rate with and
    without the domain vocabulary."""
    out = {"files": 0, "free": [0, 0], "restricted": [0, 0], "items": []}
    for wav in sorted(Path(folder).glob("*.wav")):
        ref_path = wav.with_suffix(".txt")
        if not ref_path.exists():
            continue
        pcm, rate = wav_pcm16(wav)
        ref = ref_path.read_text(encoding="utf-8").strip()
        e = service.engines.get(lang) or next(iter(service.engines.values()))
        free = e.transcribe(pcm, rate).text
        restricted = e.transcribe(pcm, rate, service.grammars[e.lang][0]).text
        for key, hyp in (("free", free), ("restricted", restricted)):
            ed, n = wer(ref, hyp)
            out[key][0] += ed
            out[key][1] += n
        out["files"] += 1
        out["items"].append({"file": wav.name, "reference": ref, "free": free, "restricted": restricted})
    for key in ("free", "restricted"):
        ed, n = out[key]
        out[key] = {"word_errors": ed, "words": n, "wer": round(ed / n, 3) if n else None}
    return out


def domain_phrases(world=None, ipc_vocab=None) -> list[str]:
    """Everything SAARTHI understands, as words a recogniser may output."""
    from nirantar.saarthi import lexicon as L
    from nirantar.saarthi.extract import SPOKEN_LETTERS
    out = ["zero one two three four five six seven eight nine oh ten first second third fourth number position",
           "left right engine serial tail aircraft base removed replaced installed inspected checked tightened",
           "cleaned repaired leak leaking crack cracked loose missing broken worn no output found and with on of"]
    out += list(SPOKEN_LETTERS) + list(SPOKEN_LETTERS.values())
    for name, v in vars(L).items():                  # every word list in the lexicon (its constants only)
        if not name.isupper():
            continue
        if isinstance(v, (tuple, list)):
            out += [x for x in v if isinstance(x, str)]
        elif isinstance(v, dict):
            for k, x in v.items():
                out += [k] if isinstance(k, str) else []
                out += [y for y in (x if isinstance(x, (tuple, list)) else [x]) if isinstance(y, str)]
    if world is not None:
        out += [p.name for p in world.pns.values()] + [m for ms in world.failure_modes.values() for m in ms]
        out += [t["id"].replace("-", " ") for t in world.tails]
    if ipc_vocab is not None:
        out += sorted(ipc_vocab.heads | ipc_vocab.qualifiers)
    return out
