#!/usr/bin/env python3
"""Évaluation de bout en bout : les 30 emails passent par le vrai WF1.

Chaque email est envoyé au webhook de production, marqué d'un identifiant de série
(test_run) : les tickets ne sont pas rattachés aux vrais tickets et ne déclenchent pas
d'alerte Slack. Le ticket renvoyé est comparé à l'étiquette. L'exécution n8n est relue
pour compter les relances et repérer une bascule vers le modèle de secours.

Les seuils de réussite sont ceux du cahier des charges (§ 13.4), fixés avant la mesure.

Usage : python3 eval/run_eval.py [--resume eval-AAAAMMJJ-HHMM | --report eval-AAAAMMJJ-HHMM]
--report relit les exécutions dans n8n et régénère le rapport, sans renvoyer les emails.
Chaque résultat est enregistré dès qu'il arrive : en cas d'arrêt, --resume reprend la série
là où elle s'est arrêtée.
Sorties : eval/results.md (versionné) et eval/runs/eval-*.json (résultats bruts).
"""
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "eval"))
from baseline_keywords import classify as baseline_classify  # noqa: E402
from send_email import load_email, load_env, send  # noqa: E402

N8N = "http://localhost:5678"
FIELDS = ["customer_name", "company", "email", "phone", "requested_date"]


def empty_to_none(value):
    return None if value in ("", None) else value


def same(field, got, expected):
    got, expected = empty_to_none(got), empty_to_none(expected)
    if got is None or expected is None:
        return got is None and expected is None
    if field == "phone":
        return re.sub(r"\D", "", str(got)) == re.sub(r"\D", "", str(expected))
    return str(got).strip().casefold() == str(expected).strip().casefold()


def execution_details(execution_id, api_key):
    """Nombre de relances et modèles utilisés, lus dans l'exécution n8n."""
    url = f"{N8N}/api/v1/executions/{execution_id}?includeData=true"
    request = urllib.request.Request(url, headers={"X-N8N-API-KEY": api_key})
    for _ in range(10):  # l'exécution est enregistrée juste après la réponse du webhook
        try:
            data = json.load(urllib.request.urlopen(request, timeout=30))
            run_data = data["data"]["resultData"]["runData"]
            if "Lire la qualification" not in run_data:
                raise KeyError("exécution pas encore enregistrée")
            groq_down = any(len((run.get("data") or {}).get("main") or []) > 1 and run["data"]["main"][1]
                            for n in ("Classifier (Groq)", "Rédiger (Groq)") for run in run_data.get(n, []))
            return {
                "groq_error": groq_down,
                "classification_attempts": len(run_data.get("Lire la qualification", [])),
                "fallback_used": any(n in run_data for n in ("Classifier (Gemini, secours)", "Rédiger (Gemini, secours)")),
            }
        except (urllib.error.HTTPError, KeyError):
            time.sleep(2)
    return {"classification_attempts": None, "fallback_used": None}


def score(email, label, ticket):
    filtered = ticket["status"] == "FILTERED"
    result = {"filtered_ok": filtered == label["expected_filtered"]}
    if label["expected_filtered"] or filtered:
        return result
    e = label["expected"]
    got_secondary = [s for s in (ticket.get("secondary_requests") or "").split(" | ") if s]
    result.update({
        "category_ok": ticket.get("category") == e["category"],
        "priority_ok": ticket.get("priority") == e["priority"],
        "team_ok": ticket.get("team") == label["expected_team"],
        "fields": {f: same(f, ticket.get(f), e[f]) for f in FIELDS},
        "ambiguous_ok": bool(ticket.get("ambiguous")) == e["ambiguous"],
        "secondary_ok": len(got_secondary) == len(e["secondary_requests"]),
        "inventions": [f for f in FIELDS if e[f] is None and empty_to_none(ticket.get(f)) is not None],
        "review_expected": label["expected_manual_review"],
        "review_got": ticket["status"] in ("NEEDS_MANUAL_REVIEW", "ERROR"),
        "baseline_ok": baseline_classify(email["subject"], email["body"]) == e["category"],
    })
    return result


def pct(numerator, denominator):
    return f"{numerator}/{denominator} ({numerator / denominator:.0%})" if denominator else "n/a"


def report(runs, run_id, started, duration):
    scored = [r for r in runs if r.get("score") and "category_ok" in r["score"]]
    standard = [r for r in scored if r["difficulty"] != "difficile"]
    hard = [r for r in scored if r["difficulty"] == "difficile"]
    ok = lambda rs, key: sum(r["score"][key] for r in rs)
    fields_ok = sum(sum(r["score"]["fields"].values()) for r in scored)
    fields_total = len(scored) * len(FIELDS)
    expected_null = sum(1 for r in scored for f in FIELDS if r["label"]["expected"][f] is None)
    inventions = [(r["message_id"], f) for r in scored for f in r["score"]["inventions"]]
    sensitive = [r for r in scored if r["score"]["review_expected"]]
    missed = [r["message_id"] for r in sensitive if not r["score"]["review_got"]]
    over = [r["message_id"] for r in scored if r["score"]["review_got"] and not r["score"]["review_expected"]]
    first_try = [r for r in scored if r["details"].get("classification_attempts") == 1]
    errors = [r for r in runs if r.get("error")]

    cat_std = ok(standard, "category_ok") / len(standard) if standard else 0
    cat_hard = ok(hard, "category_ok") / len(hard) if hard else 0
    llm_cat = ok(scored, "category_ok")
    base_cat = ok(scored, "baseline_ok")
    verdict = lambda passed: "atteint" if passed else "**non atteint**"

    lines = [
        "# Résultats de l'évaluation", "",
        f"Série `{run_id}`, lancée le {started:%Y-%m-%d à %H:%M}, durée {duration / 60:.0f} min. "
        "Généré par `eval/run_eval.py`.", "",
        "Les 30 emails du jeu de test passent par le **vrai WF1** (webhook de production), "
        "et chaque ticket est comparé à son étiquette (`data/emails_labels.json`).", "",
        "## Seuils fixés avant la mesure (CDC § 13.4)", "",
        "| Métrique | Seuil | Mesure | Verdict |", "|---|---|---|---|",
        f"| Classification, cas standards | au moins 90 % | {pct(ok(standard, 'category_ok'), len(standard))} | {verdict(cat_std >= 0.9)} |",
        f"| Classification, cas difficiles | au moins 80 % | {pct(ok(hard, 'category_ok'), len(hard))} | {verdict(cat_hard >= 0.8)} |",
        f"| LLM contre baseline par mots-clés | écart nettement positif | {pct(llm_cat, len(scored))} contre {pct(base_cat, len(scored))} | {verdict(llm_cat - base_cat >= 0.15 * len(scored))} |",
        f"| JSON valide au premier essai | au moins 95 % | {pct(len(first_try), len(scored))} | {verdict(len(first_try) >= 0.95 * len(scored))} |",
        f"| Champs inventés | 0 visé | {len(inventions)} sur {expected_null} champs attendus vides | {verdict(not inventions)} |",
        f"| Cas sensibles envoyés en revue humaine | 100 % | {pct(len(sensitive) - len(missed), len(sensitive))} | {verdict(not missed)} |",
        "",
        "## Autres mesures", "",
        "| Mesure | Résultat |", "|---|---|",
        f"| Filtrage correct (réponses automatiques) | {pct(sum(r['score']['filtered_ok'] for r in runs if r.get('score')), len(runs))} |",
        f"| Priorité correcte | {pct(ok(scored, 'priority_ok'), len(scored))} |",
        f"| Équipe correcte | {pct(ok(scored, 'team_ok'), len(scored))} |",
        f"| Champs extraits exacts (nom, entreprise, email, téléphone, date) | {pct(fields_ok, fields_total)} |",
        f"| Nombre de demandes secondaires correct | {pct(ok(scored, 'secondary_ok'), len(scored))} |",
        f"| Ambiguïté correcte | {pct(ok(scored, 'ambiguous_ok'), len(scored))} |",
        f"| Revue humaine non nécessaire mais déclenchée | {len(over)} ({', '.join(over) or 'aucun'}) |",
        f"| Bascule vers le modèle de secours (quota de Groq dépassé) | {sum(bool(r['details'].get('groq_error')) for r in scored)} email(s), aucun ticket perdu |",
        f"| Échecs techniques (pas de ticket) | {len(errors)} |",
        f"| Temps moyen par email | {sum(r['seconds'] for r in runs) / len(runs):.0f} s |",
        "",
        "## Erreurs, email par email", "",
        "| Email | Difficulté | Écart |", "|---|---|---|",
    ]
    for r in runs:
        issues = []
        if r.get("error"):
            issues.append(f"échec technique : {r['error'][:80]}")
        s = r.get("score") or {}
        if s and not s.get("filtered_ok", True):
            issues.append("filtrage incorrect")
        if "category_ok" in s:
            e, t = r["label"]["expected"], r["ticket"]
            if not s["category_ok"]:
                issues.append(f"catégorie {t.get('category')} au lieu de {e['category']}")
            if not s["priority_ok"]:
                issues.append(f"priorité {t.get('priority')} au lieu de {e['priority']}")
            for f, good in s["fields"].items():
                if not good:
                    issues.append(f"{f} « {t.get(f) or 'vide'} » au lieu de « {e[f] or 'vide'} »")
            if not s["secondary_ok"]:
                issues.append("nombre de demandes secondaires")
            if not s["ambiguous_ok"]:
                issues.append("ambiguïté")
            if s["review_expected"] and not s["review_got"]:
                issues.append("**cas sensible non envoyé en revue**")
        if issues:
            lines.append(f"| {r['message_id']} | {r['difficulty']} | {' ; '.join(issues)} |")
    lines += ["",
              "## Limites", "",
              "- 30 emails : une erreur fait varier un taux de plus de 3 points. Ces chiffres sont une tendance.",
              "- 5 emails (001, 002, 004, 005, 021) ont servi au choix du modèle et à la mise au point du prompt : "
              "les résultats sont un peu optimistes sur eux.",
              "- La baseline par mots-clés a été écrite en connaissant les emails : elle est plutôt avantagée.",
              "- Une seule exécution : à `temperature: 0`, la variabilité est faible mais pas nulle.",
              ""]
    (ROOT / "eval" / "results.md").write_text("\n".join(lines))


def main():
    env = load_env()
    labels = {l["message_id"]: l for l in json.loads((ROOT / "data" / "emails_labels.json").read_text())}
    ids = sorted(labels)
    out = ROOT / "eval" / "runs"
    out.mkdir(exist_ok=True)
    if len(sys.argv) == 3 and sys.argv[1] == "--report":
        run_id = sys.argv[2]
        runs = json.loads((out / f"{run_id}.json").read_text())
        for run in runs:
            if run.get("ticket") and run["ticket"].get("status") != "FILTERED":
                run["details"] = execution_details(run["ticket"]["execution_id"], env["N8N_API_KEY"])
        (out / f"{run_id}.json").write_text(json.dumps(runs, ensure_ascii=False, indent=2))
        report(runs, run_id, datetime.strptime(run_id, "eval-%Y%m%d-%H%M"), sum(r["seconds"] for r in runs))
        print("Rapport régénéré : eval/results.md")
        return
    if len(sys.argv) == 3 and sys.argv[1] == "--resume":
        run_id = sys.argv[2]
        runs = json.loads((out / f"{run_id}.json").read_text())
    else:
        run_id = f"eval-{datetime.now():%Y%m%d-%H%M}"
        runs = []
    done = {r["message_id"] for r in runs}
    started = datetime.now()
    for mid in ids:
        if mid in done:
            continue
        email = load_email(mid)
        email["test_run"] = run_id
        ticket, seconds, error = send(email, f"{N8N}/webhook/requests", env["WEBHOOK_API_KEY"])
        if error and "timed out" in str(error):
            error = f"délai dépassé : {error}"
        run = {"message_id": mid, "difficulty": labels[mid]["difficulty"], "label": labels[mid],
               "seconds": seconds, "error": error, "ticket": ticket}
        if ticket:
            run["score"] = score(email, labels[mid], ticket)
            run["details"] = execution_details(ticket["execution_id"], env["N8N_API_KEY"])
            # La baseline n'est pas le système évalué : son échec n'est pas un écart du WF1.
            status = "ok" if all(v for k, v in run["score"].items() if k.endswith("_ok") and k != "baseline_ok") else "écart"
        else:
            run["details"] = {"classification_attempts": None, "fallback_used": None}
            status = "ÉCHEC"
        print(f"{mid}  {seconds:5.1f}s  {status}", flush=True)
        runs.append(run)
        (out / f"{run_id}.json").write_text(json.dumps(runs, ensure_ascii=False, indent=2))   # après chaque email

    report(runs, run_id, started, (datetime.now() - started).total_seconds())
    print(f"\nRapport : eval/results.md   Résultats bruts : eval/runs/{run_id}.json")


if __name__ == "__main__":
    main()
