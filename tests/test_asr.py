"""SAARTHI voice input on the node: spoken letters, scoring, the transcribe endpoint, and (if installed) Vosk."""
import importlib.util
import json
import os
import threading
import urllib.error
import urllib.request
import wave
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from nirantar.saarthi.asr import wer
from nirantar.saarthi.extract import Extractor, spoken_letters

DIGITS = Path(__file__).parent / "data" / "vosk_digits.wav"
SAID = "one zero zero zero one nine oh two one oh zero one eight zero three"


def test_word_error_rate():
    assert wer("number two hydraulic pump leak", "number two hydraulic pump leak") == (0, 5)
    assert wer("number two hydraulic pump leak", "number to hydraulic pump") == (2, 5)


def test_spoken_tail_numbers(world):
    assert spoken_letters("foxtrot india bravo one oh seven") == "f i b one zero seven"
    x = Extractor(world)
    for said in ("foxtrot india bravo one zero seven number two hydraulic pump leak removed and replaced",
                 "eff eye bee one oh seven second hydraulic pump leak replaced"):
        f = {k: v["value"] for k, v in x.extract(said).as_dict()["fields"].items()}
        assert (f["tail"], f["part"], f["mode"]) == ("FI-B1-07", "FH-HP-03", "leak")


class FakeSpeech:
    def info(self):
        return {"available": True, "engine": "fake", "languages": {"en": {"model": "fake", "grammar_words": 3,
                                                                          "unknown_words": []}}}

    def transcribe(self, pcm, lang, rate, restrict=True, score=None):
        cands = ["fi b one zero seven hydraulic pump leak", "five be one zero seven hydraulic pump lake"]
        best = max(cands, key=score)
        return {"text": best, "free_text": cands[1], "restricted_text": cands[0], "chosen": "restricted",
                "words": [], "lang": lang, "model": "fake", "bytes": len(pcm), "rate": rate}


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    from nirantar.pipeline import Config, run
    from nirantar.ui.server import Console, make_handler
    out = tmp_path_factory.mktemp("results")
    run(Config(history_days=730, n_seeds=2, mrv_seeds=2, top_k=2, out_dir=str(out)), log=lambda *_: None)
    c = Console(out, asr_models={"en": "fake"})
    c._speech = FakeSpeech()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(c))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def post_audio(url, data, ctype="audio/l16; rate=16000", headers=None):
    req = urllib.request.Request(url + "/api/saarthi/transcribe?lang=en", data=data, method="POST",
                                 headers={"X-Nirantar": "1", "Content-Type": ctype, **(headers or {})})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_transcribe_endpoint_picks_what_saarthi_can_structure(server):
    opts = json.loads(urllib.request.urlopen(server + "/api/saarthi/options").read())
    assert opts["asr"]["available"]
    code, r = post_audio(server, b"\x00\x00" * 16000)
    assert code == 200 and r["text"].startswith("fi b one zero seven") and r["rate"] == 16000
    assert post_audio(server, b"\x00" * 10, "application/json")[0] == 415
    assert post_audio(server, b"\x00" * 10, headers={"X-Nirantar": "0"})[0] == 403
    try:                                            # refused before the body is read: 413, or the pipe closes
        assert post_audio(server, b"\x00\x00" * 1_100_000)[0] == 413
    except urllib.error.URLError as e:
        assert "pipe" in str(e.reason).lower() or "reset" in str(e.reason).lower()


MODEL = os.environ.get("NIRANTAR_TEST_ASR_MODEL")


@pytest.mark.skipif(not MODEL or importlib.util.find_spec("vosk") is None,
                    reason="set NIRANTAR_TEST_ASR_MODEL to a Vosk model folder (and install vosk) to run")
def test_vosk_on_real_speech():
    from nirantar.saarthi.asr import VoskEngine, wav_pcm16
    e = VoskEngine(MODEL)
    pcm, rate = wav_pcm16(DIGITS)
    t = e.transcribe(pcm, rate)
    assert wer(SAID, t.text)[0] <= 1
    with wave.open(str(DIGITS)) as w:
        assert w.getframerate() == rate


def test_logbook_endpoint(server):
    req = urllib.request.Request(server + "/api/saarthi/logbook", method="POST",
                                 data=json.dumps({"problem": "#3 ROCKER COVER GASKET LEAKING, L/H ENG.",
                                                  "action": "REMOVED & REPLACED GASKET."}).encode(),
                                 headers={"X-Nirantar": "1", "Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req).read())
    assert (r["part"], r["cylinders"], r["engine"], r["action"]) == ("ROCKER COVER GASKET", [3], "L", "replace")
    assert r["ipc"][0]["pn"] == "75906"
