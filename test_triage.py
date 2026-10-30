import json, subprocess, sys, threading, urllib.request
from http.server import HTTPServer
import triage

CASES = [json.loads(l) for l in open("data/messages.jsonl", encoding="utf-8")]


def test_jeu_de_messages():
    ko = []
    for c in CASES:
        r = triage.triage(c["message"], "rules")
        if (r["intent"], sorted(r["manquant"])) != (c["intent"], sorted(c["manquant"])):
            ko.append((c["message"][:50], r["intent"], r["manquant"], "attendu", c["intent"], c["manquant"]))
    score = 1 - len(ko) / len(CASES)
    print(f"\n{len(CASES) - len(ko)}/{len(CASES)} messages corrects ({score:.0%})")
    for k in ko:
        print("  KO", k)
    assert score >= 0.9


def test_jamais_envoye():
    assert all(triage.triage(c["message"], "rules")["statut"] == "brouillon_a_valider" for c in CASES)


def test_llm_en_panne_retombe_sur_les_regles(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("LLM_API_KEY", "x")
    monkeypatch.setenv("LLM_MODEL", "x")
    assert triage.triage("Quels sont vos horaires ?", "llm")["intent"] == "info"


def test_serveur():
    srv = HTTPServer(("127.0.0.1", 0), triage.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_port}"
    req = urllib.request.Request(url, json.dumps({"message": "Quels sont vos horaires ?"}).encode())
    assert json.load(urllib.request.urlopen(req))["intent"] == "info"
    try:
        urllib.request.urlopen(urllib.request.Request(url, b"{}"))
    except urllib.error.HTTPError as e:
        assert e.code == 400
    srv.shutdown()
