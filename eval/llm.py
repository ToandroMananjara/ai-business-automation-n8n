"""Outils communs aux scripts d'évaluation : appel des LLM, préparation des emails, notation.

La préparation de l'email (normalisation, message envoyé au modèle) reproduit ce que
fera le WF1 dans n8n, pour que les résultats mesurés ici valent pour le workflow.
"""
import html
import json
import pathlib
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
RULES = json.loads((ROOT / "config" / "business_rules.json").read_text())

# Cloudflare, devant l'API de Groq, refuse les requêtes sans User-Agent explicite
# (erreur 403, « error code: 1010 »).
USER_AGENT = "ai-business-automation-n8n/0.1 (eval)"

PROVIDERS = {
    "groq": ("https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "GEMINI_API_KEY"),
}

WEEKDAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
          "septembre", "octobre", "novembre", "décembre"]
CALENDAR_DAYS = 14

FIELDS = ["category", "priority", "customer_name", "company", "email", "phone", "requested_date", "ambiguous"]


def load_env():
    env = {}
    for line in (ROOT / ".env").read_text().splitlines():
        m = re.match(r"^([A-Z0-9_]+)=(.*)$", line.strip())
        if m:
            env[m.group(1)] = m.group(2)
    return env


def system_prompt():
    """Le prompt de classification, avec les listes de valeurs tirées de la configuration."""
    text = (ROOT / "prompts" / "classify_extract.md").read_text()
    for key in ("categories", "priorities", "primary_intent_order"):
        text = text.replace("{{" + key + "}}", ", ".join(f"`{v}`" for v in RULES[key]))
    return text


def output_schema():
    """Schéma JSON strict de la sortie attendue."""
    nullable = {"type": ["string", "null"]}
    return {
        "name": "email_qualification",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": RULES["categories"]},
                "priority": {"type": "string", "enum": RULES["priorities"]},
                "customer_name": nullable,
                "company": nullable,
                "email": nullable,
                "phone": nullable,
                "requested_date": nullable,
                "secondary_requests": {"type": "array", "items": {"type": "string"}},
                "summary": {"type": "string"},
                "ambiguous": {"type": "boolean"},
            },
            "required": ["category", "priority", "customer_name", "company", "email", "phone",
                         "requested_date", "secondary_requests", "summary", "ambiguous"],
            "additionalProperties": False,
        },
    }


def normalize_body(body):
    """Texte brut : HTML retiré, signature d'envoi mobile retirée, espaces normalisés."""
    text = re.sub(r"(?i)<br\s*/?>|</div>|</p>", "\n", body)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"(?im)^--\s*\n(envoyé depuis|sent from).*$", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def calendar(received):
    """Les jours qui suivent la réception, pour que le modèle lise une date au lieu de la calculer."""
    lines = []
    for offset in range(CALENDAR_DAYS + 1):
        day = received.date() + timedelta(days=offset)
        label = "aujourd'hui" if offset == 0 else "demain" if offset == 1 else ""
        lines.append(f"- {WEEKDAYS[day.weekday()]} {day.day} {MONTHS[day.month - 1]} = {day.isoformat()}"
                     + (f" ({label})" if label else ""))
    return "\n".join(lines)


def user_message(email):
    received = datetime.fromisoformat(email["received_at"])
    return (
        f"Date de réception : {email['received_at']} ({WEEKDAYS[received.weekday()]})\n"
        f"Calendrier des jours suivants :\n{calendar(received)}\n"
        f"Expéditeur : {email['sender']}\n"
        f"Objet : {email['subject']}\n"
        f"Message :\n{normalize_body(email['body'])}"
    )


def call_llm(provider, model, email, env, options=None, max_attempts=3):
    """Appelle le modèle. Retourne un dict : contenu brut, usage, durée, erreur éventuelle."""
    url, key_name = PROVIDERS[provider]
    body = {
        "model": model,
        "temperature": 0,
        "max_completion_tokens": 1500,
        "messages": [
            {"role": "system", "content": system_prompt()},
            {"role": "user", "content": user_message(email)},
        ],
        **(options or {}),
    }
    headers = {
        "Authorization": f"Bearer {env[key_name]}",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    for attempt in range(1, max_attempts + 1):
        started = time.time()
        request = urllib.request.Request(url, json.dumps(body).encode(), headers)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.load(response)
                seconds = round(time.time() - started, 2)
                waited = wait_for_quota(response.headers)
            return {
                "content": data["choices"][0]["message"].get("content") or "",
                "usage": data.get("usage", {}),
                "seconds": seconds,
                "quota_wait_seconds": waited,
                "error": None,
            }
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:300]
            if e.code in (429, 503) and attempt < max_attempts:
                time.sleep(float(e.headers.get("retry-after") or 5 * attempt))
                continue
            return {"content": "", "usage": {}, "seconds": round(time.time() - started, 2),
                    "error": f"HTTP {e.code}: {detail}"}
        except Exception as e:  # timeout, réseau
            if attempt < max_attempts:
                continue
            return {"content": "", "usage": {}, "seconds": round(time.time() - started, 2), "error": str(e)}


def wait_for_quota(headers, minimum_tokens=4000):
    """Respecte le quota de tokens par minute de Groq (en-têtes x-ratelimit-*)."""
    remaining = headers.get("x-ratelimit-remaining-tokens")
    reset = headers.get("x-ratelimit-reset-tokens")
    if remaining is None or reset is None or int(remaining) >= minimum_tokens:
        return 0.0
    seconds = 0.0
    for value, unit in re.findall(r"([\d.]+)(ms|s|m)", reset):
        seconds += float(value) * {"ms": 0.001, "s": 1, "m": 60}[unit]
    time.sleep(seconds + 0.5)
    return round(seconds + 0.5, 1)


def parse_output(content):
    """Retourne (objet, None) ou (None, raison) si le contenu n'est pas un JSON exploitable."""
    text = content.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return None, f"JSON invalide : {e}"
    missing = [f for f in FIELDS + ["secondary_requests", "summary"] if f not in data]
    if missing:
        return None, f"champs manquants : {missing}"
    return data, None


def apply_business_rules(output, email):
    """Règles déterministes appliquées après le LLM, comme dans le node Code du WF1.

    Échéance proche (clé deadline_escalation de la configuration, 48 heures) : la priorité
    monte au moins au niveau fixé, quoi qu'ait répondu le modèle (filet de sécurité sur un
    calcul de dates).
    """
    rule = RULES["deadline_escalation"]
    order = RULES["priorities"]  # du plus urgent au moins urgent
    result = dict(output)
    date = result.get("requested_date")
    if not date or result.get("priority") not in order:
        return result
    if order.index(result["priority"]) <= order.index(rule["min_priority"]):
        return result
    received = datetime.fromisoformat(email["received_at"])
    try:
        requested = datetime.fromisoformat(date).replace(tzinfo=received.tzinfo)
    except ValueError:
        return result
    if requested - received < timedelta(hours=rule["within_hours"]):
        result["priority"] = rule["min_priority"]
    return result


def _same(field, got, expected):
    if expected is None or got is None:
        return got is None and expected is None
    if field == "phone":
        return re.sub(r"\D", "", str(got)) == re.sub(r"\D", "", str(expected))
    if isinstance(expected, str):
        return str(got).strip().casefold() == expected.strip().casefold()
    return got == expected


def score(output, expected):
    """Compare une sortie à l'étiquette. Le téléphone est comparé chiffres seulement."""
    fields = {f: _same(f, output.get(f), expected[f]) for f in FIELDS}
    inventions = [f for f in FIELDS if expected[f] is None and output.get(f) is not None]
    secondary_ok = len(output.get("secondary_requests") or []) == len(expected["secondary_requests"])
    return {"fields": fields, "inventions": inventions, "secondary_count_ok": secondary_ok}
