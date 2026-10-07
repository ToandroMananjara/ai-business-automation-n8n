#!/usr/bin/env python3
"""Comparaison rapide des modèles candidats sur quelques emails représentatifs.

Ce n'est pas l'évaluation finale : avec 5 emails, ce test sert à écarter un modèle
clairement moins bon ou trop gourmand en tokens, pas à départager finement.

Usage : python3 eval/compare_models.py [filtre]
Exemple : python3 eval/compare_models.py json_object  (seulement les variantes dont le nom contient « json_object »)
Les résultats bruts sont écrits dans eval/runs/ (ignoré par git).
"""
import json
import sys
import time
from datetime import datetime

from llm import (ROOT, apply_business_rules, call_llm, classification_messages, load_env, output_schema,
                 parse_output, score)

EMAILS = ["msg-001", "msg-002", "msg-004", "msg-005", "msg-021"]

STRICT_JSON = {"type": "json_schema", "json_schema": output_schema()}
SIMPLE_JSON = {"type": "json_object"}
# (fournisseur, modèle, nom de la variante, options)
MODELS = [
    ("groq", "openai/gpt-oss-20b", "gpt-oss-20b json_schema", {"reasoning_effort": "low", "response_format": STRICT_JSON}),
    ("groq", "openai/gpt-oss-120b", "gpt-oss-120b json_schema", {"reasoning_effort": "low", "response_format": STRICT_JSON}),
    ("groq", "qwen/qwen3.8-27b", "qwen3.8-27b json_schema", {"reasoning_effort": "none", "response_format": STRICT_JSON}),
    ("gemini", "gemini-3.1-flash-lite", "gemini-3.1-flash-lite json_schema", {"response_format": STRICT_JSON}),
    # Variantes retenues : JSON simple, car le mode json_schema de Groq tronque les textes longs de qwen.
    ("groq", "qwen/qwen3.8-27b", "qwen3.8-27b json_object", {"reasoning_effort": "none", "response_format": SIMPLE_JSON}),
    ("gemini", "gemini-3.1-flash-lite", "gemini-3.1-flash-lite json_object", {"response_format": SIMPLE_JSON}),
]


def main():
    env = load_env()
    labels = {l["message_id"]: l for l in json.loads((ROOT / "data" / "emails_labels.json").read_text())}
    emails = {}
    for f in (ROOT / "data" / "emails").glob("*.json"):
        e = json.loads(f.read_text())
        emails[e["message_id"]] = e

    selected = [m for m in MODELS if len(sys.argv) < 2 or sys.argv[1] in m[2]]
    runs = []
    for provider, model, variant, options in selected:
        for mid in EMAILS:
            result = call_llm(provider, model, classification_messages(emails[mid]), env, options)
            output, parse_error = (None, result["error"]) if result["error"] else parse_output(result["content"])
            run = {"provider": provider, "model": variant, "message_id": mid, **result,
                   "parse_error": parse_error, "output": output}
            if output:
                run["score_llm"] = score(output, labels[mid]["expected"])
                run["final"] = apply_business_rules(output, emails[mid])
                run["score"] = score(run["final"], labels[mid]["expected"])
            runs.append(run)
            status = "ok" if output else f"ÉCHEC ({parse_error[:60]})"
            wait = result.get("quota_wait_seconds") or 0
            print(f"{variant:34s} {mid}  réponse {result['seconds']:5.1f}s  attente quota {wait:4.1f}s  {status}")
            if provider == "gemini":
                time.sleep(4)  # quota par minute plus serré sur l'offre gratuite

    out_dir = ROOT / "eval" / "runs"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"compare-{datetime.now():%Y%m%d-%H%M%S}.json"
    out_file.write_text(json.dumps(runs, ensure_ascii=False, indent=2))
    print(f"\nRésultats bruts : {out_file.relative_to(ROOT)}\n")
    print_summary(runs)


def print_summary(runs):
    print("Notes après règles du code (filet des 48 heures). Temps de réponse du modèle, hors attente de quota.\n")
    print("| Modèle | JSON valide | Catégorie | Priorité (LLM seul) | Priorité (après code) | Champs exacts | Inventions | Demandes secondaires | Tokens entrée | Tokens sortie (dont raisonnement) | Temps de réponse moyen |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for model in dict.fromkeys(r["model"] for r in runs):
        rs = [r for r in runs if r["model"] == model]
        ok = [r for r in rs if r.get("output")]
        n = len(rs)
        cat = sum(r["score"]["fields"]["category"] for r in ok)
        pri = sum(r["score"]["fields"]["priority"] for r in ok)
        pri_llm = sum(r["score_llm"]["fields"]["priority"] for r in ok)
        fields = sum(sum(r["score"]["fields"].values()) for r in ok)
        inventions = sum(len(r["score"]["inventions"]) for r in ok)
        secondary = sum(r["score"]["secondary_count_ok"] for r in ok)
        usage = [r["usage"] for r in ok if r["usage"]]
        avg = lambda xs: round(sum(xs) / len(xs)) if xs else 0
        prompt_t = avg([u.get("prompt_tokens", 0) for u in usage])
        completion_t = avg([u.get("completion_tokens", 0) for u in usage])
        reasoning_t = avg([(u.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0 for u in usage])
        seconds = sum(r["seconds"] for r in ok) / len(ok) if ok else 0
        print(f"| {model} | {len(ok)}/{n} | {cat}/{n} | {pri_llm}/{n} | {pri}/{n} | {fields}/{n * 8} | {inventions} | {secondary}/{n} "
              f"| {prompt_t} | {completion_t} ({reasoning_t}) | {seconds:.1f} s |")


if __name__ == "__main__":
    main()
