#!/usr/bin/env python3
"""Envoie les documents de test (data/cv, data/invoices) au webhook du WF2 et compare
chaque résultat à son étiquette (data/documents_labels.json).

Usage :
  python3 scripts/send_document.py --all                     # les 10 documents
  python3 scripts/send_document.py cv/cv-lucas-martin.pdf    # un document
  python3 scripts/send_document.py --run docs-1 --all        # marqué comme série de test
"""
import argparse
import base64
import json
import pathlib
import re

from send_email import ROOT, load_env, send

URL = "http://localhost:5678/webhook/documents"


def same(got, expected):
    if expected is None:
        return got in (None, "")
    if isinstance(expected, float):
        try:
            return abs(float(got) - expected) < 0.01
        except (TypeError, ValueError):
            return False
    if isinstance(expected, str) and re.fullmatch(r"[\d ]+", expected):
        return re.sub(r"\D", "", str(got)) == re.sub(r"\D", "", expected)
    return str(got).strip().casefold() == str(expected).strip().casefold()


def compare(label, row):
    gaps = []
    if row.get("status") != label["expected_status"]:
        gaps.append(f"statut {row.get('status')} au lieu de {label['expected_status']}")
    for field, expected in (label["expected"] or {}).items():
        if field == "skills_min":
            count = len([s for s in str(row.get("skills", "")).split(",") if s.strip()])
            if count < expected:
                gaps.append(f"{count} compétences au lieu d'au moins {expected}")
        elif not same(row.get(field), expected):
            gaps.append(f"{field} « {row.get(field)} » au lieu de « {expected} »")
    return gaps


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="*", help="chemins relatifs à data/, par exemple cv/cv-lucas-martin.pdf")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--run", default="", help="identifiant de série de test")
    args = parser.parse_args()

    labels = {l["file"]: l for l in json.loads((ROOT / "data" / "documents_labels.json").read_text())}
    files = list(labels) if args.all else args.files
    env = load_env()
    ok = 0
    for path in files:
        label = labels[path]
        payload = {"document_type": label["document_type"], "filename": pathlib.Path(path).name,
                   "content_base64": base64.b64encode((ROOT / "data" / path).read_bytes()).decode(),
                   "test_run": args.run}
        row, seconds, error = send(payload, URL, env["WEBHOOK_API_KEY"])
        if error:
            print(f"{path:38s} {seconds:5.1f}s  ÉCHEC  {error}")
            continue
        gaps = compare(label, row)
        ok += not gaps
        print(f"{path:38s} {seconds:5.1f}s  {row.get('status', ''):20s} {'conforme' if not gaps else 'ÉCART : ' + ' ; '.join(gaps)}")
        if row.get("review_reason"):
            print(f"{'':45s} raison : {row['review_reason']}")
    print(f"\n{ok}/{len(files)} documents conformes à leur étiquette")


if __name__ == "__main__":
    main()
