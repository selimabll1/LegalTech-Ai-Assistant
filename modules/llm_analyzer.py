"""Local LegalTech document analysis using the Ollama chat API.

The LLM extracts facts and proposes a classification. It does not calculate
the final risk/opportunity scores. Deterministic factual validation and scoring
are applied afterwards by separate modules.
"""

from __future__ import annotations

import json
import re
from typing import Any

import requests

from config import OLLAMA_MODEL, OLLAMA_URL


MAX_INPUT_CHARS = 12_000
REQUEST_TIMEOUT_SECONDS = 240
ANALYZER_VERSION = "legaltech_analyzer_v5"

EVENT_CODES = [
    "CONSTITUTION_SOCIETE",
    "SOUSCRIPTION_CAPITAL",
    "AUGMENTATION_CAPITAL",
    "DISSOLUTION",
    "LIQUIDATION",
    "CLOTURE_LIQUIDATION",
    "REDRESSEMENT_JUDICIAIRE",
    "FAILLITE",
    "CLOTURE_FAILLITE",
    "VENTE_FONDS_COMMERCE",
    "LOCATION_GERANCE",
    "VENTE_ENCHERES_SAISIE",
    "AVIS_CREANCIERS",
    "NOMINATION_DIRIGEANT",
    "NOMINATION_COMMISSAIRE",
    "CHANGEMENT_GOUVERNANCE",
    "CONVOCATION_AGO",
    "CONVOCATION_AGE",
    "CONSTITUTION_ASSOCIATION",
    "RECTIFICATIF",
    "AUTRE",
]

EVIDENCE_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "preuve_textuelle": {"type": "string"},
    },
    "required": ["description", "preuve_textuelle"],
}

ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "societe": {"type": "string"},
        "categorie": {"type": "string"},
        "type_evenement": {"type": "string"},
        "type_evenement_code": {
            "type": "string",
            "enum": EVENT_CODES,
        },
        "resume": {"type": "string"},
        "faits_extraits": {
            "type": "object",
            "properties": {
                "montants_originaux": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "dates_importantes": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "delais": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "parties_citees": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "decision_ou_action": {"type": "string"},
            },
            "required": [
                "montants_originaux",
                "dates_importantes",
                "delais",
                "parties_citees",
                "decision_ou_action",
            ],
        },
        "risques_detectes": {
            "type": "array",
            "items": EVIDENCE_ITEM_SCHEMA,
        },
        "opportunites_detectees": {
            "type": "array",
            "items": EVIDENCE_ITEM_SCHEMA,
            "maxItems": 1,
        },
        "action_recommandee": {"type": "string"},
        "niveau_confiance_llm": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
    },
    "required": [
        "societe",
        "categorie",
        "type_evenement",
        "type_evenement_code",
        "resume",
        "faits_extraits",
        "risques_detectes",
        "opportunites_detectees",
        "action_recommandee",
        "niveau_confiance_llm",
    ],
}


SYSTEM_PROMPT = """
Tu es un analyste LegalTech interne pour UGFS North Africa.

Ta mission est d'extraire les faits explicitement présents dans une annonce
juridique. Tu ne calcules jamais le score de risque ou d'opportunité : un moteur
de règles séparé le fera ensuite.

RÈGLES ABSOLUES
1. N'invente aucun fait, risque, opportunité, montant, nom, date ou conséquence.
2. Chaque risque et chaque opportunité explicite doit contenir une
   preuve_textuelle courte copiée depuis le texte source. Sans preuve explicite,
   ne retourne pas cet élément.
3. opportunites_detectees contient au maximum UNE opportunité explicite, choisie
   comme la plus concrète et la plus actionnable. Une liste vide reste correcte
   si le texte n'énonce aucune opportunité directe. Un moteur déterministe distinct
   ajoutera ensuite, lorsque les faits le permettent, une opportunité potentielle
   prudente sans la présenter comme une recommandation d'investissement.
4. Ne crée jamais de risques génériques tels que déséquilibre entre fondateurs,
   gouvernance supposée, manque de collaboration ou incertitude commerciale.
5. Préserve les montants exactement tels qu'ils apparaissent dans le champ
   montants_originaux. En Tunisie, les trois chiffres après la virgule ou le
   point représentent généralement les millimes : "23 000.000 DT" correspond
   à 23 000 dinars, et "1 000,000 dinars" correspond à 1 000 dinars. Ne
   transforme jamais ces montants en millions. Un parseur déterministe corrigera
   ensuite le résumé et contrôlera le calcul du capital.
6. Ne compte pas les fondateurs à partir d'une liste. Mentionne leurs noms sans
   annoncer un nombre, sauf si le texte donne explicitement ce nombre.
7. "Assemblée générale constitutive" appartient à la constitution d'une société.
   Ce n'est ni une AGO ni une AGE.
8. categorie doit être un libellé métier lisible, par exemple
   "Société communautaire régionale", jamais un code avec des underscores.
9. type_evenement doit être un libellé français lisible. type_evenement_code doit
   être exactement l'un des codes autorisés par le schéma.
10. L'action recommandée doit commencer par un verbe opérationnel : Vérifier,
    Analyser, Surveiller, Contacter, Escalader, Archiver, Examiner ou Confirmer.
    Elle doit préciser l'objet du contrôle et, si disponible, l'échéance. Une
    réponse d'un seul mot telle que "Examiner" ou "Contacter" est interdite.
11. niveau_confiance_llm mesure uniquement la confiance dans l'extraction et la
    classification, jamais la certitude juridique ni la justesse du score.
12. Réponds exclusivement avec un objet JSON conforme au schéma, en français.

TAXONOMIE DES CODES
- CONSTITUTION_SOCIETE : création/constitution d'une société, y compris une
  assemblée générale constitutive.
- SOUSCRIPTION_CAPITAL : souscription isolée sans indices suffisants de création.
- AUGMENTATION_CAPITAL : augmentation du capital d'une société existante.
- DISSOLUTION : dissolution sans détail suffisant sur la liquidation.
- LIQUIDATION : liquidation volontaire ou judiciaire en cours.
- CLOTURE_LIQUIDATION : fin/clôture des opérations de liquidation.
- REDRESSEMENT_JUDICIAIRE : procédure de redressement ou période d'observation.
- FAILLITE : ouverture ou état de faillite.
- CLOTURE_FAILLITE : clôture de faillite.
- VENTE_FONDS_COMMERCE : vente/cession/donation d'un fonds de commerce.
- LOCATION_GERANCE : location-gérance ou gérance libre.
- VENTE_ENCHERES_SAISIE : saisie et/ou vente aux enchères.
- AVIS_CREANCIERS : déclaration de créances ou appel aux créanciers.
- NOMINATION_DIRIGEANT : nomination d'un dirigeant ou administrateur.
- NOMINATION_COMMISSAIRE : nomination d'un commissaire aux comptes.
- CHANGEMENT_GOUVERNANCE : autre changement de gouvernance.
- CONVOCATION_AGO : uniquement une assemblée générale ordinaire explicite.
- CONVOCATION_AGE : uniquement une assemblée générale extraordinaire explicite.
- CONSTITUTION_ASSOCIATION : création d'une association/syndicat.
- RECTIFICATIF : correction ou rectificatif.
- AUTRE : aucun code précédent ne correspond clairement.
""".strip()


def _clamp_float(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return round(max(0.0, min(1.0, number)), 3)


def _as_clean_string(value: Any, default: str) -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[;\n]+", value)
        return [part.strip(" -•\t") for part in parts if part.strip(" -•\t")]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _normalize_for_match(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"[\W_]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def _evidence_matches_source(evidence: str, source_text: str) -> bool:
    evidence_norm = _normalize_for_match(evidence)
    source_norm = _normalize_for_match(source_text)
    return len(evidence_norm) >= 8 and evidence_norm in source_norm


def _normalize_evidence_items(
    value: Any,
    source_text: str,
) -> tuple[list[str], list[dict[str, str]]]:
    descriptions: list[str] = []
    supported_items: list[dict[str, str]] = []

    if not isinstance(value, list):
        return descriptions, supported_items

    for item in value:
        if not isinstance(item, dict):
            continue

        description = _as_clean_string(item.get("description"), "")
        evidence = _as_clean_string(item.get("preuve_textuelle"), "")

        if not description or not evidence:
            continue

        # Reject unsupported LLM interpretations.
        if not _evidence_matches_source(evidence, source_text):
            continue

        descriptions.append(description)
        supported_items.append(
            {
                "description": description,
                "preuve_textuelle": evidence,
            }
        )

    return descriptions, supported_items


def _extract_json_object(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    cleaned = re.sub(
        r"<think>.*?</think>",
        "",
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    ).strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("The model response does not contain a JSON object.")
        parsed = json.loads(cleaned[start : end + 1])

    if not isinstance(parsed, dict):
        raise ValueError("The model response JSON is not an object.")
    return parsed


def _fallback_analysis(reason: str, ocr_quality: float) -> dict[str, Any]:
    return {
        "societe": "À vérifier",
        "categorie": "À classifier manuellement",
        "type_evenement": "À classifier manuellement",
        "type_evenement_code": "AUTRE",
        "resume": "Analyse LLM indisponible ou JSON invalide.",
        "faits_extraits": {
            "montants_originaux": [],
            "dates_importantes": [],
            "delais": [],
            "parties_citees": [],
            "decision_ou_action": "À vérifier",
        },
        "risques_detectes": [],
        "opportunites_detectees": [],
        "risques_avec_preuves": [],
        "opportunites_avec_preuves": [],
        "action_recommandee": (
            "Vérifier manuellement le document et la disponibilité d'Ollama."
        ),
        "niveau_confiance_llm": 0.0,
        "ocr_quality": _clamp_float(ocr_quality, default=0.0),
        "json_valid": False,
        "llm_error": reason,
        "llm_model": OLLAMA_MODEL,
        "analyzer_version": ANALYZER_VERSION,
    }


def _normalize_analysis(
    raw: dict[str, Any],
    ocr_quality: float,
    source_text: str,
) -> dict[str, Any]:
    event_code = _as_clean_string(raw.get("type_evenement_code"), "AUTRE")
    if event_code not in EVENT_CODES:
        event_code = "AUTRE"

    risks, risks_with_evidence = _normalize_evidence_items(
        raw.get("risques_detectes"),
        source_text,
    )
    opportunities, opportunities_with_evidence = _normalize_evidence_items(
        raw.get("opportunites_detectees"),
        source_text,
    )

    facts = raw.get("faits_extraits")
    if not isinstance(facts, dict):
        facts = {}

    return {
        "societe": _as_clean_string(raw.get("societe"), "À vérifier"),
        "categorie": _as_clean_string(
            raw.get("categorie"),
            "À classifier manuellement",
        ),
        "type_evenement": _as_clean_string(
            raw.get("type_evenement"),
            "À classifier manuellement",
        ),
        "type_evenement_code": event_code,
        "resume": _as_clean_string(
            raw.get("resume"),
            "Résumé à vérifier manuellement.",
        ),
        "faits_extraits": {
            "montants_originaux": _as_string_list(
                facts.get("montants_originaux")
            ),
            "dates_importantes": _as_string_list(
                facts.get("dates_importantes")
            ),
            "delais": _as_string_list(facts.get("delais")),
            "parties_citees": _as_string_list(facts.get("parties_citees")),
            "decision_ou_action": _as_clean_string(
                facts.get("decision_ou_action"),
                "À vérifier",
            ),
        },
        "risques_detectes": risks,
        "opportunites_detectees": opportunities,
        "risques_avec_preuves": risks_with_evidence,
        "opportunites_avec_preuves": opportunities_with_evidence,
        "action_recommandee": _as_clean_string(
            raw.get("action_recommandee"),
            "Effectuer une revue humaine du document.",
        ),
        "niveau_confiance_llm": _clamp_float(
            raw.get("niveau_confiance_llm"),
            default=0.5,
        ),
        "ocr_quality": _clamp_float(ocr_quality, default=0.0),
        "json_valid": True,
        "llm_error": "",
        "llm_model": OLLAMA_MODEL,
        "analyzer_version": ANALYZER_VERSION,
    }


def analyze_legal_text(text: str, ocr_quality: float = 0.7) -> dict[str, Any]:
    """Analyze one legal announcement with the locally running Ollama model."""
    source_text = (text or "").strip()

    if len(source_text) < 30:
        return _fallback_analysis(
            "Extracted text is empty or too short.",
            ocr_quality,
        )

    truncated_text = source_text[:MAX_INPUT_CHARS]
    user_prompt = (
        "Analyse l'annonce juridique suivante. "
        "Retourne uniquement le JSON demandé.\n\n"
        f"TEXTE SOURCE:\n{truncated_text}"
    )

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "think": False,
        "format": ANALYSIS_SCHEMA,
        "options": {
            "temperature": 0.0,
            "seed": 42,
        },
    }

    try:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        body = response.json()

        message = body.get("message")
        if not isinstance(message, dict):
            raise ValueError("Ollama response is missing the 'message' object.")

        content = message.get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Ollama returned an empty message.")

        raw_analysis = _extract_json_object(content)
        return _normalize_analysis(
            raw_analysis,
            ocr_quality,
            truncated_text,
        )

    except requests.Timeout:
        return _fallback_analysis(
            f"Ollama request timed out after {REQUEST_TIMEOUT_SECONDS} seconds.",
            ocr_quality,
        )
    except requests.RequestException as exc:
        return _fallback_analysis(
            f"Ollama connection error: {exc}",
            ocr_quality,
        )
    except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        return _fallback_analysis(
            f"Invalid Ollama response: {exc}",
            ocr_quality,
        )
