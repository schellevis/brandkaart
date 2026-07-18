"""Controles vóór publicatie: PII, secrets en artefactintegriteit.

Alles in het artefact wordt als publiek behandeld. Deze controles draaien
op de staging-output; bij één overtreding wordt niets gepubliceerd.
"""

from __future__ import annotations

import json
import re

from .common import secret_values

EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Telefoonachtig: + of 00 gevolgd door 8+ cijfers (met separatoren). De
# lookbehind sluit voorafgaande woordtekens, punten en koppeltekens uit,
# zodat record-id's ("firms-…-0058-48…") en decimalen ("0.0058") geen
# valse treffers geven.
PHONE_PATTERN = re.compile(r"(?<![\w.\-])(?:\+|00)\d(?:[\s().-]?\d){7,}")


def scan_text(text: str, label: str) -> list[str]:
    """Controleer één tekstfragment; retourneert overtredingen (leeg = schoon)."""
    violations = []
    for match in EMAIL_PATTERN.finditer(text):
        violations.append(f"{label}: e-mailadres in output ({match.group()[:3]}…)")
    for match in PHONE_PATTERN.finditer(text):
        violations.append(f"{label}: telefoonachtig nummer in output ({match.group()[:6]}…)")
    return violations


def scan_json_strings(data: bytes, label: str) -> list[str]:
    """PII-scan over uitsluitend de stringwaarden van een JSON-document.

    Coördinaatarrays zijn getallen en geven anders valse telefoontreffers
    (cijferreeksen gescheiden door punten en komma's).
    """
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return [f"{label}: geen geldige JSON/UTF-8"]
    strings: list[str] = []
    _collect_strings(document, strings)
    return scan_text("\n".join(strings), label)


def _collect_strings(node, into: list[str]) -> None:
    if isinstance(node, str):
        into.append(node)
    elif isinstance(node, dict):
        for key, value in node.items():
            into.append(str(key))
            _collect_strings(value, into)
    elif isinstance(node, list):
        for value in node:
            _collect_strings(value, into)


def scan_secrets(data: bytes, label: str) -> list[str]:
    """Controleer dat geen bekende secretwaarde (uit de omgeving) in de output zit."""
    violations = []
    for value in secret_values():
        if value.encode("utf-8") in data:
            violations.append(f"{label}: secretwaarde uit omgeving aangetroffen in output")
    return violations


def scan_artifact_files(files: dict[str, bytes]) -> list[str]:
    """Draai alle controles over de volledige artefactinhoud."""
    violations = []
    for path, data in files.items():
        violations.extend(scan_secrets(data, path))
        if path.endswith((".json", ".geojson")):
            violations.extend(scan_json_strings(data, path))
        elif path.endswith((".csv", ".txt", ".html", ".js")):
            violations.extend(scan_text(data.decode("utf-8", errors="replace"), path))
    return violations
