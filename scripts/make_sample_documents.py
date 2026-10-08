#!/usr/bin/env python3
"""Génère les documents fictifs du WF2 (CV et factures) et leurs étiquettes.

Formats produits, pour tester chaque chemin du WF2 :
- PDF contenant du texte (cas le plus courant) ;
- DOCX (Word) ;
- PDF scanné : une image, sans texte extractible.

Outils : python-docx, et deux commandes intégrées à macOS (cupsfilter pour texte -> PDF,
sips pour PDF -> image -> PDF). Toutes les données sont fictives.

Usage : python3 scripts/make_sample_documents.py
"""
import json
import pathlib
import subprocess
import tempfile

import docx

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

CVS = [
    {
        "file": "cv/cv-lucas-martin.pdf", "format": "pdf",
        "text": """LUCAS MARTIN
Téléconseiller
lucas.martin@example.com - 06 39 98 64 20 - Lyon

EXPÉRIENCE
Janvier 2024 - Décembre 2025 : Téléconseiller, Exemple Relation Client SARL
  Accueil téléphonique, prise de rendez-vous pour des artisans, suivi des demandes.
Janvier 2023 - Décembre 2023 : Conseiller prise de rendez-vous, Cabinet Exemple

FORMATION
2022 : BTS Négociation et digitalisation de la relation client (NDRC)

COMPÉTENCES
Accueil téléphonique, prise de rendez-vous, Excel, CRM HubSpot""",
        "expected": {"name": "Lucas Martin", "email": "lucas.martin@example.com", "phone": "06 39 98 64 20",
                     "experience_years": 3.0, "skills_min": 3},
        "expected_status": "PENDING_REVIEW", "trap": "Cas standard, PDF texte. 24 + 12 mois = 3,0 ans, calculés par le code.",
    },
    {
        "file": "cv/cv-ines-robert.docx", "format": "docx",
        "text": """INÈS ROBERT
Étudiante en relation client
ines.robert@example.fr - 06 39 98 72 41

FORMATION
2024 - 2026 : BTS NDRC (en cours)

EXPÉRIENCE
Avril 2025 - Septembre 2025 : Assistante commerciale (stage), Exemple Immobilier

COMPÉTENCES
Relation client, prospection téléphonique, Word, Excel""",
        "expected": {"name": "Inès Robert", "email": "ines.robert@example.fr", "phone": "06 39 98 72 41",
                     "experience_years": 0.5, "skills_min": 3},
        "expected_status": "PENDING_REVIEW", "trap": "Format DOCX : texte lu après décompression du fichier. Stage de 6 mois = 0,5 an.",
    },
    {
        "file": "cv/cv-amelie-bernard.pdf", "format": "pdf",
        "text": """AMÉLIE BERNARD
Chargée de suivi client
amelie.bernard@example.org - 04 65 71 40 18

EXPÉRIENCE PROFESSIONNELLE
Mars 2019 - Février 2024 : Chargée de suivi client, Exemple Énergie
  Suivi des dossiers d'intervention, gestion des réclamations, relances.
Septembre 2016 - Février 2019 : Téléconseillère, Exemple Télécom

FORMATION
2016 : Licence professionnelle Commerce

COMPÉTENCES
Gestion des réclamations, suivi de dossiers, Salesforce, Excel""",
        "expected": {"name": "Amélie Bernard", "email": "amelie.bernard@example.org", "phone": "04 65 71 40 18",
                     "experience_years": 7.5, "skills_min": 3},
        "expected_status": "PENDING_REVIEW", "trap": "Deux expériences : 60 + 30 mois = 7,5 ans.",
    },
    {
        "file": "cv/cv-karim-said-scan.pdf", "format": "scan",
        "text": """KARIM SAÏD
Technicien d'intervention
karim.said@example.com - 06 39 98 11 07

EXPÉRIENCE
2018 - 2025 : Technicien chauffagiste, Exemple Services""",
        "expected": None,
        "expected_status": "NEEDS_MANUAL_REVIEW", "trap": "PDF scanné (image) : aucun texte extractible, revue humaine sans appel au LLM.",
    },
    {
        "file": "cv/cv-julien-moreau.docx", "format": "docx",
        "text": """JULIEN MOREAU
Technicien SAV
Téléphone : 06 39 98 35 62

EXPÉRIENCE
Juin 2020 - Mai 2023 : Technicien SAV, Exemple Chauffage

COMPÉTENCES
Diagnostic de pannes, relation client, planification""",
        "expected": {"name": "Julien Moreau", "email": None, "phone": "06 39 98 35 62",
                     "experience_years": 3.0, "skills_min": 2},
        "expected_status": "NEEDS_MANUAL_REVIEW", "trap": "Aucun email dans le CV : email null (rien d'inventé), revue humaine.",
    },
]

INVOICES = [
    {
        "file": "invoices/facture-F-2026-0142.pdf",
        "text": """FOURNITURES EXEMPLE SAS
12 rue de l'Exemple, 69003 Lyon

FACTURE N° F-2026-0142
Date : 30/09/2026
Échéance : 30/10/2026

Désignation                         Montant HT
Raccords cuivre et vannes           1 000,00 EUR

Total HT          1 000,00 EUR
TVA 20 %            200,00 EUR
Total TTC         1 200,00 EUR""",
        "expected": {"supplier": "Fournitures Exemple SAS", "invoice_number": "F-2026-0142", "invoice_date": "2026-09-30",
                     "due_date": "2026-10-30", "amount_excl_tax": 1000.00, "tax_amount": 200.00,
                     "amount_incl_tax": 1200.00, "currency": "EUR"},
        "expected_status": "PENDING_REVIEW", "trap": "Cas standard.",
    },
    {
        "file": "invoices/facture-F-2026-0157.pdf",
        "text": """ÉLECTRICITÉ PRO EXEMPLE
FACTURE F-2026-0157 du 02/10/2026
À régler avant le 01/11/2026

Câbles et disjoncteurs     845,50 EUR HT
TVA (20 %)                  169,10 EUR
Net à payer TTC           1 014,60 EUR""",
        "expected": {"supplier": "Électricité Pro Exemple", "invoice_number": "F-2026-0157", "invoice_date": "2026-10-02",
                     "due_date": "2026-11-01", "amount_excl_tax": 845.50, "tax_amount": 169.10,
                     "amount_incl_tax": 1014.60, "currency": "EUR"},
        "expected_status": "PENDING_REVIEW", "trap": "Mise en page différente, montants avec centimes.",
    },
    {
        "file": "invoices/facture-FA-889.pdf",
        "text": """PLOMBERIE DÉPÔT EXEMPLE
Facture FA-889
Date de facture : 05/10/2026
Date d'échéance : 20/10/2026

Total HT        312,40 EUR
TVA 10 %         31,24 EUR
Total TTC       353,64 EUR""",
        "expected": {"supplier": "Plomberie Dépôt Exemple", "invoice_number": "FA-889", "invoice_date": "2026-10-05",
                     "due_date": "2026-10-20", "amount_excl_tax": 312.40, "tax_amount": 31.24,
                     "amount_incl_tax": 353.64, "currency": "EUR"},
        "expected_status": "NEEDS_MANUAL_REVIEW",
        "trap": "Total faux : 312,40 + 31,24 = 343,64 et non 353,64. Le LLM doit recopier les montants tels quels ; le contrôle du code doit détecter l'erreur.",
    },
    {
        "file": "invoices/facture-CD-2026-77.pdf",
        "text": """CHAUFFAGE DISTRIBUTION EXEMPLE
FACTURE N° CD-2026-77
Émise le 15 septembre 2026 - Paiement à 30 jours, soit le 15 octobre 2026

Chaudière gaz à condensation       2 450,00 €
Total hors taxes                   2 450,00 €
TVA 5,5 %                            134,75 €
TOTAL TTC                          2 584,75 €""",
        "expected": {"supplier": "Chauffage Distribution Exemple", "invoice_number": "CD-2026-77", "invoice_date": "2026-09-15",
                     "due_date": "2026-10-15", "amount_excl_tax": 2450.00, "tax_amount": 134.75,
                     "amount_incl_tax": 2584.75, "currency": "EUR"},
        "expected_status": "PENDING_REVIEW", "trap": "Dates en toutes lettres, symbole € au lieu de EUR, espaces dans les milliers.",
    },
    {
        "file": "invoices/facture-X-12.pdf",
        "text": """OUTILLAGE EXEMPLE SARL
Facture X-12
Date : 01/10/2026
Échéance : 01/09/2026

Total HT     150,00 EUR
TVA 20 %      30,00 EUR
Total TTC    180,00 EUR""",
        "expected": {"supplier": "Outillage Exemple SARL", "invoice_number": "X-12", "invoice_date": "2026-10-01",
                     "due_date": "2026-09-01", "amount_excl_tax": 150.00, "tax_amount": 30.00,
                     "amount_incl_tax": 180.00, "currency": "EUR"},
        "expected_status": "NEEDS_MANUAL_REVIEW",
        "trap": "Échéance antérieure à la date de facture : le LLM doit recopier, le contrôle du code doit rejeter.",
    },
]


def text_pdf(text, out):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(text)
    with open(out, "wb") as pdf:
        subprocess.run(["cupsfilter", f.name], stdout=pdf, stderr=subprocess.DEVNULL, check=True)


def scanned_pdf(text, out):
    """Texte -> PDF -> image PNG -> PDF : le PDF final ne contient qu'une image."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        text_pdf(text, tmp / "page.pdf")
        subprocess.run(["sips", "-s", "format", "png", str(tmp / "page.pdf"), "--out", str(tmp / "page.png")],
                       stdout=subprocess.DEVNULL, check=True)
        subprocess.run(["sips", "-s", "format", "pdf", str(tmp / "page.png"), "--out", str(out)],
                       stdout=subprocess.DEVNULL, check=True)


def word(text, out):
    document = docx.Document()
    for line in text.split("\n"):
        document.add_paragraph(line)
    document.save(out)


def main():
    labels = []
    for kind, items in (("cv", CVS), ("invoice", INVOICES)):
        for item in items:
            out = DATA / item["file"]
            out.parent.mkdir(parents=True, exist_ok=True)
            fmt = item.get("format", "pdf")
            {"pdf": text_pdf, "scan": scanned_pdf, "docx": word}[fmt](item["text"], out)
            labels.append({"file": item["file"], "document_type": kind, "format": fmt,
                           "expected": item["expected"], "expected_status": item["expected_status"],
                           "trap": item["trap"]})
            print(f"{item['file']:40s} {fmt}")
    (DATA / "documents_labels.json").write_text(json.dumps(labels, ensure_ascii=False, indent=2) + "\n")
    print(f"{len(labels)} documents, étiquettes dans data/documents_labels.json")


if __name__ == "__main__":
    main()
