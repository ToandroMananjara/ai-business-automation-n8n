"""Baseline sans IA : classification de la catégorie par mots-clés.

Point de comparaison de l'évaluation. Si le LLM ne fait pas nettement mieux que ces
quelques règles, c'est le prompt ou les données qu'il faut revoir.

Limite à connaître : ces règles ont été écrites en connaissant les 30 emails de test.
La baseline est donc plutôt avantagée, ce qui rend la comparaison prudente : un écart
en faveur du LLM n'en est que plus significatif.
"""
import re

# Ordre de priorité identique à celui du LLM (primary_intent_order) : la première
# catégorie dont un mot-clé est trouvé l'emporte.
RULES = [
    ("CANDIDATURE", ["candidature", "mon cv", "curriculum", "poste de", "recrutez"]),
    ("RECLAMATION", ["inadmissible", "pas normal", "explications", "réclamation", "plainte",
                     "contester", "déçu", "inacceptable", "ne vient pas", "pas venu"]),
    ("RENDEZ_VOUS", ["rendez-vous", "passer", "venir", "intervention", "devis", "rappeler",
                     "envoyer quelqu'un", "décaler", "installer", "remplacer", "entretien",
                     "come", "appointment"]),
    ("SUIVI", ["où en est", "relance", "confirmation", "dossier", "devis signé", "copie",
               "duplicata", "mes rendez-vous"]),
    ("INFORMATION", ["intervenez", "horaires", "samedi", "certifiés", "frais", "merci",
                     "garantie", "zone"]),
]


def classify(subject, body):
    text = f"{subject} {body}".lower()
    text = re.sub(r"<[^>]+>", " ", text)
    for category, keywords in RULES:
        if any(keyword in text for keyword in keywords):
            return category
    return "AUTRE"
