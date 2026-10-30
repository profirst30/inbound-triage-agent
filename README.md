# Qualification des demandes entrantes

Un agent qui lit une demande client (garage, conciergerie, agence...), la classe, relève ce qui manque et prépare une réponse. **Il n'envoie jamais rien** : la sortie est un brouillon à valider par une personne.

```
$ python triage.py "Bonjour, je voudrais un rendez-vous pour une vidange, plutôt jeudi. 06 12 34 56 78"
{
  "intent": "rdv",
  "priorite": "normale",
  "champs": {"prestation": "vidange", "jour": "jeudi", "telephone": "06 12 34 56 78", ...},
  "manquant": ["immatriculation"],
  "brouillon": "Bonjour, merci pour votre demande de rendez-vous. Pour avancer, pouvez-vous nous indiquer l'immatriculation du véhicule ?",
  "statut": "brouillon_a_valider"
}
```

## Ce qu'il fait

- Cinq types de demande : `urgence`, `rdv`, `devis`, `info`, `autre`. Une urgence passe devant le reste et déclenche une alerte humaine.
- Champs extraits : prestation, immatriculation, jour, téléphone, e-mail.
- Champs obligatoires par type (un rendez-vous exige prestation, immatriculation, jour et un contact) ; ce qui manque est demandé dans le brouillon.
- Deux backends : `rules` (hors ligne, par défaut) et `llm` (API compatible OpenAI, variables `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`). Le LLM ne fait que classer et extraire ; manque, priorité et brouillon restent du code déterministe. Si le LLM échoue, on retombe sur les règles.

## Utilisation

```bash
python triage.py --serve 8000     # petit serveur HTTP, POST {"message": "..."}
python -m pytest -s               # tests + score sur data/messages.jsonl
```

Le workflow n8n `workflows/qualification-demandes.n8n.json` enchaîne : webhook, agent, branche urgence / brouillon à valider, réponse. À importer dans n8n (Import from file) ; l'URL de l'agent est `http://localhost:8000`, à adapter si n8n tourne dans Docker.

## Limites

- **Score : 25/27 sur `data/messages.jsonl`**. Les 27 messages sont fictifs et écrits par moi, avec les règles en tête : c'est un test de non-régression, pas un benchmark.
- Les deux échecs connus sont instructifs : une négation (« pas besoin de rendez-vous, juste un prix » classé `rdv`) et une demande implicite (« bruit étrange au freinage, pouvez-vous regarder ? » classé `autre`). Les règles s'arrêtent là ; c'est le cas d'usage du backend `llm`.
- Le backend `llm` n'est pas couvert par les tests (pas de clé en intégration) ; seul le repli sur les règles l'est.
- Le workflow n8n n'a pas été exécuté dans n8n : seuls ses liens internes ont été vérifiés.
- Pas d'envoi d'e-mail ni de CRM : c'est volontaire, la validation humaine est le point de passage.

## Licence

MIT
