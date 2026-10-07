#!/usr/bin/env python3
"""Envoie des emails de test (data/emails/) au webhook du WF1.

Dans un vrai centre d'appel, c'est le CRM ou l'outil de ticketing qui appellerait
ce webhook à chaque nouvel email. Ce script joue ce rôle.

Usage :
  python3 scripts/send_email.py msg-001 msg-002     # emails choisis
  python3 scripts/send_email.py --all               # les 30 emails
  python3 scripts/send_email.py --test msg-001      # URL de test (workflow ouvert, « Execute workflow » cliqué)
  python3 scripts/send_email.py --run eval-1 --all  # marque les tickets comme appartenant à un test
"""
import argparse
import base64
import json
import pathlib
import re
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE_URL = "http://localhost:5678"


def load_env():
    env = {}
    for line in (ROOT / ".env").read_text().splitlines():
        m = re.match(r"^([A-Z0-9_]+)=(.*)$", line.strip())
        if m:
            env[m.group(1)] = m.group(2)
    return env


def load_email(message_id):
    path = ROOT / "data" / "emails" / f"email-{message_id.removeprefix('msg-')}.json"
    email = json.loads(path.read_text())
    attachments = []
    for attachment in email.pop("attachments", []):
        file = ROOT / "data" / attachment["path"]
        if not file.exists():
            print(f"  pièce jointe absente, ignorée : {attachment['path']}")
            continue
        attachments.append({"filename": attachment["filename"], "mime_type": "application/pdf",
                            "content_base64": base64.b64encode(file.read_bytes()).decode()})
    if attachments:
        email["attachments"] = attachments
    return email


def send(email, url, api_key):
    request = urllib.request.Request(url, json.dumps(email).encode(), {
        "Content-Type": "application/json",
        "X-Api-Key": api_key,
        "User-Agent": "ai-business-automation-n8n/0.1 (send_email)",
    })
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.load(response), round(time.time() - started, 1), None
    except urllib.error.HTTPError as e:
        return None, round(time.time() - started, 1), f"HTTP {e.code} : {e.read().decode()[:300]}"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ids", nargs="*", help="identifiants des emails, par exemple msg-001")
    parser.add_argument("--all", action="store_true", help="envoyer les 30 emails")
    parser.add_argument("--test", action="store_true", help="utiliser l'URL de test (webhook-test)")
    parser.add_argument("--run", default="", help="identifiant de série de test, enregistré dans test_run")
    args = parser.parse_args()

    ids = sorted(p.stem.replace("email-", "msg-") for p in (ROOT / "data" / "emails").glob("*.json")) if args.all else args.ids
    if not ids:
        parser.error("indiquer des identifiants d'emails ou --all")

    env = load_env()
    url = f"{BASE_URL}/{'webhook-test' if args.test else 'webhook'}/requests"
    results = []
    for mid in ids:
        email = load_email(mid)
        if args.run:
            email["test_run"] = args.run
        ticket, seconds, error = send(email, url, env["WEBHOOK_API_KEY"])
        if error:
            print(f"{mid}  {seconds:5.1f}s  ÉCHEC  {error}")
        else:
            print(f"{mid}  {seconds:5.1f}s  {ticket.get('status', ''):20s} {ticket.get('category', '') or '':12s} "
                  f"{ticket.get('priority', '') or '':7s} {ticket.get('team', '') or ''}")
        results.append({"message_id": mid, "seconds": seconds, "error": error, "ticket": ticket})
    return results


if __name__ == "__main__":
    main()
