#!/usr/bin/env python3
"""Génère et contrôle les brouillons de réponse sur les emails qui en reçoivent un.

Le modèle reçoit la qualification ATTENDUE (l'étiquette), pas celle produite par le
modèle de classification : on mesure ainsi la qualité du brouillon seule.

Contrôles automatiques : JSON valide, citations de FAQ valides, aucun nombre inventé,
signature présente (un texte tronqué n'a pas de signature).
Les brouillons sont aussi écrits dans un fichier Markdown pour une relecture humaine.

Usage : python3 eval/check_drafts.py
"""
import json
from datetime import datetime

from llm import ROOT, call_llm, check_draft, draft_messages, faq_for, load_env, load_faq, parse_draft


def main():
    env = load_env()
    model = env["LLM_PRIMARY_MODEL"]
    # JSON simple et non strict : en mode json_schema, Groq tronque le texte de qwen vers
    # 140 tokens tout en renvoyant un JSON valide (voir eval/model-selection.md).
    options = {"reasoning_effort": "none", "response_format": {"type": "json_object"}}
    faq = load_faq()

    labels = json.loads((ROOT / "data" / "emails_labels.json").read_text())
    targets = [l for l in labels if not l["expected_filtered"] and not l["expected_manual_review"]]
    emails = {}
    for f in (ROOT / "data" / "emails").glob("*.json"):
        e = json.loads(f.read_text())
        emails[e["message_id"]] = e

    runs = []
    for label in targets:
        mid, qualification = label["message_id"], label["expected"]
        entries = faq_for(qualification["category"], faq)
        result = call_llm("groq", model, draft_messages(emails[mid], qualification, entries), env, options)
        draft, error = (None, result["error"]) if result["error"] else parse_draft(result["content"])
        run = {"message_id": mid, "model": model, **result, "error": error, "draft": draft,
               "faq_provided": [e["id"] for e in entries]}
        if draft:
            run["checks"] = check_draft(draft, emails[mid], qualification, entries)
        runs.append(run)
        flags = ""
        if draft:
            c = run["checks"]
            flags = " ".join(filter(None, [
                f"citations invalides {c['invalid_citations']}" if c["invalid_citations"] else "",
                f"nombres non sourcés {c['unsupported_numbers']}" if c["unsupported_numbers"] else "",
                "signature absente (tronqué ?)" if c["missing_signature"] else "",
                f"non couvert : {len(draft['unanswered'])}" if draft["unanswered"] else "",
            ])) or "ok"
        print(f"{mid}  réponse {result['seconds']:4.1f}s  {flags if draft else 'ÉCHEC ' + error[:80]}")

    out_dir = ROOT / "eval" / "runs"
    out_dir.mkdir(exist_ok=True)
    stamp = f"{datetime.now():%Y%m%d-%H%M%S}"
    (out_dir / f"drafts-{stamp}.json").write_text(json.dumps(runs, ensure_ascii=False, indent=2))
    write_reading_file(out_dir / f"drafts-{stamp}.md", runs, emails, model)
    print(f"\nÀ relire : eval/runs/drafts-{stamp}.md\n")
    print_summary(runs)


def write_reading_file(path, runs, emails, model):
    lines = [f"# Brouillons générés par {model}", "",
             "Grille de relecture, pour chaque brouillon : **fidèle** (rien d'inventé), "
             "**complet** (toutes les demandes traitées ou signalées), **ton** (professionnel, sans engagement).", ""]
    for r in runs:
        e = emails[r["message_id"]]
        lines += [f"## {r['message_id']} — {e['subject']}", "", "**Email :**", "", "> " + e["body"].replace("\n", "\n> "), ""]
        if not r["draft"]:
            lines += [f"**ÉCHEC :** {r['error']}", ""]
            continue
        d, c = r["draft"], r["checks"]
        lines += ["**Brouillon :**", "", "```text", d["draft"], "```", "",
                  f"- FAQ fournies : {', '.join(r['faq_provided'])}",
                  f"- FAQ citées : {', '.join(d['faq_ids_used']) or 'aucune'}",
                  f"- Non couvert : {'; '.join(d['unanswered']) or 'rien'}",
                  f"- Citations invalides : {c['invalid_citations'] or 'aucune'}",
                  f"- Nombres non sourcés : {c['unsupported_numbers'] or 'aucun'}",
                  f"- Signature : {'absente' if c['missing_signature'] else 'présente'}", ""]
    path.write_text("\n".join(lines))


def print_summary(runs):
    ok = [r for r in runs if r["draft"]]
    n = len(runs)
    invalid = sum(bool(r["checks"]["invalid_citations"]) for r in ok)
    numbers = sum(bool(r["checks"]["unsupported_numbers"]) for r in ok)
    unanswered = sum(bool(r["draft"]["unanswered"]) for r in ok)
    unsigned = sum(r["checks"]["missing_signature"] for r in ok)
    usage = [r["usage"] for r in ok if r["usage"]]
    avg = lambda xs: round(sum(xs) / len(xs)) if xs else 0
    print("| Brouillons | JSON valide | Citations invalides | Nombres non sourcés | Sans signature | Avec points non couverts | Tokens entrée | Tokens sortie | Temps de réponse |")
    print("|---|---|---|---|---|---|---|---|---|")
    print(f"| {n} | {len(ok)}/{n} | {invalid} | {numbers} | {unsigned} | {unanswered} "
          f"| {avg([u.get('prompt_tokens', 0) for u in usage])} | {avg([u.get('completion_tokens', 0) for u in usage])} "
          f"| {sum(r['seconds'] for r in ok) / max(len(ok), 1):.1f} s |")


if __name__ == "__main__":
    main()
