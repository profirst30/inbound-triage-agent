"""Qualifie une demande entrante (garage, conciergerie...) et prépare une réponse À VALIDER.

Rien n'est jamais envoyé : la sortie est un brouillon + la liste de ce qui manque.
Backends : "rules" (hors ligne, par défaut) ou "llm" (variables LLM_BASE_URL, LLM_API_KEY, LLM_MODEL).
Le LLM ne fait que classer et extraire ; manque d'infos, priorité et brouillon restent déterministes.

Usage : python triage.py "message"   |   python triage.py --serve [port]
"""
import json, os, re, sys, urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

INTENTS = ("urgence", "rdv", "devis", "info", "autre")
# Ordre = priorité : une panne l'emporte sur un rendez-vous, qui l'emporte sur un devis.
KEYWORDS = {
    "urgence": r"panne|ne d[ée]marre (plus|pas)|fum[ée]e|accident|remorqu|voyant (rouge|moteur)|freins? (l[âa]che|ne)|urgent",
    "rdv": r"rendez-vous|\brdv\b|cr[ée]neau|disponibilit|\bdispo|r[ée]server|prendre (un )?(rdv|rendez)|passer (au|à) garage",
    "devis": r"devis|tarif|\bprix\b|combien|co[uû]t",
    "info": r"horaires?|ouvert|ferm[ée]|adresse|o[uù] (se trouve|[êe]tes)|accept|paiement|parking",
}
SERVICES = r"vidange|plaquettes?|freins?|pneus?|contr[ôo]le technique|r[ée]vision|climatisation|clim|diagnostic|batterie|distribution|embrayage"
DAYS = r"lundi|mardi|mercredi|jeudi|vendredi|samedi|demain|apr[èe]s-demain|cette semaine|semaine prochaine|\d{1,2}/\d{1,2}|\d{1,2} (janvier|f[ée]vrier|mars|avril|mai|juin|juillet|ao[ûu]t|septembre|octobre|novembre|d[ée]cembre)"
PLATE = r"\b[A-Z]{2}-?\d{3}-?[A-Z]{2}\b"
PHONE = r"(?:\+33\s?|0)[1-9](?:[\s.]?\d{2}){4}"
EMAIL = r"[\w.+-]+@[\w-]+\.[\w.-]+"
# Champs exigés par type de demande ; "contact" = téléphone ou e-mail.
REQUIRED = {
    "urgence": ["telephone"],
    "rdv": ["prestation", "immatriculation", "jour", "contact"],
    "devis": ["prestation", "immatriculation", "contact"],
    "info": [],
    "autre": [],
}
LABELS = {"telephone": "un numéro de téléphone", "prestation": "la prestation souhaitée",
          "immatriculation": "l'immatriculation du véhicule", "jour": "le jour qui vous convient",
          "contact": "un numéro de téléphone ou une adresse e-mail"}


def _find(pattern, text, flags=re.I):
    m = re.search(pattern, text, flags)
    return m.group(0).strip() if m else None


def rules_extract(text):
    intent = next((k for k, p in KEYWORDS.items() if re.search(p, text, re.I)), "autre")
    fields = {
        "prestation": _find(SERVICES, text),
        "immatriculation": _find(PLATE, text.upper(), 0),
        "jour": _find(DAYS, text),
        "telephone": _find(PHONE, text),
        "email": _find(EMAIL, text),
    }
    return intent, fields


def llm_extract(text):
    """Classe et extrait via une API compatible OpenAI. Non couvert par les tests (pas de clé en CI)."""
    prompt = (f"Réponds en JSON strict : intent parmi {list(INTENTS)}, et fields avec les clés "
              "prestation, immatriculation, jour, telephone, email (null si absent). Message :\n" + text)
    body = json.dumps({"model": os.environ["LLM_MODEL"], "temperature": 0,
                       "response_format": {"type": "json_object"},
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(os.environ["LLM_BASE_URL"].rstrip("/") + "/chat/completions", body, {
        "Content-Type": "application/json", "Authorization": "Bearer " + os.environ["LLM_API_KEY"]})
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.loads(json.load(r)["choices"][0]["message"]["content"])
    if out.get("intent") not in INTENTS:
        raise ValueError("intent hors liste")
    return out["intent"], {k: out.get("fields", {}).get(k) for k in ("prestation", "immatriculation", "jour", "telephone", "email")}


def triage(text, backend=None):
    backend = backend or os.environ.get("TRIAGE_BACKEND", "rules")
    try:
        intent, fields = llm_extract(text) if backend == "llm" else rules_extract(text)
    except Exception:  # LLM indisponible ou sortie invalide : on retombe sur les règles
        intent, fields = rules_extract(text)
    fields["contact"] = fields["telephone"] or fields["email"]
    manquant = [f for f in REQUIRED[intent] if not fields.get(f)]
    return {
        "intent": intent,
        "priorite": "haute" if intent == "urgence" else "normale",
        "champs": {k: v for k, v in fields.items() if k != "contact"},
        "manquant": manquant,
        "brouillon": draft(intent, manquant),
        "statut": "brouillon_a_valider",  # jamais d'envoi automatique
    }


def draft(intent, manquant):
    if intent == "autre":
        return "Bonjour, merci pour votre message. Pouvez-vous préciser votre demande ? Nous revenons vers vous rapidement."
    if intent == "urgence":
        base = "Bonjour, nous avons bien reçu votre message et le traitons en priorité."
    elif intent == "info":
        return "Bonjour, merci pour votre message. [Réponse à compléter par l'équipe : horaires, adresse ou paiement.]"
    else:
        base = "Bonjour, merci pour votre demande de " + ("rendez-vous." if intent == "rdv" else "devis.")
    if manquant:
        return base + " Pour avancer, pouvez-vous nous indiquer " + ", ".join(LABELS[m] for m in manquant) + " ?"
    return base + " Nous revenons vers vous avec " + ("un créneau." if intent == "rdv" else "un devis.") + " [À valider avant envoi]"


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            text = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))["message"]
            code, out = 200, triage(text)
        except (ValueError, KeyError, TypeError):
            code, out = 400, {"erreur": 'corps attendu : {"message": "..."}'}
        body = json.dumps(out, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--serve"]:
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
        HTTPServer(("127.0.0.1", port), Handler).serve_forever()
    elif len(sys.argv) > 1:
        print(json.dumps(triage(" ".join(sys.argv[1:])), ensure_ascii=False, indent=2))
    else:
        sys.exit(__doc__)
