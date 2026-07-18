"""Gedeelde hulpfuncties: HTTP-ophalen, tijd en broncontracten."""

from __future__ import annotations

import gzip
import io
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

USER_AGENT = "brandkaart-prototype/0.1 (+https://github.com/; open source recon prototype)"
DEFAULT_TIMEOUT = 60


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str | None) -> datetime | None:
    """Parseer een ISO-tijd naar een tijdzonebewuste UTC-datetime."""
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_iso(value: str | None) -> str | None:
    """Normaliseer een ISO-tijd met offset naar de manifestvorm UTC-``Z``."""
    return iso(parse_iso(value))


def redact(text: str) -> str:
    """Verwijder bekende secretwaarden uit tekst voordat die gelogd wordt.

    Secrets staan alleen in omgevingsvariabelen (later: GitHub Actions
    Secrets). Alles wat op een secret-naam lijkt wordt op waarde gefilterd,
    zodat een URL of foutmelding nooit een sleutel lekt.
    """
    for value in secret_values():
        if value:
            text = text.replace(value, "***")
    return text


def secret_values() -> list[str]:
    pattern = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD)", re.IGNORECASE)
    return [
        value
        for name, value in os.environ.items()
        if pattern.search(name) and value and len(value) >= 8
    ]


def http_get(url: str, timeout: int = DEFAULT_TIMEOUT, retries: int = 1) -> bytes:
    """Haal een URL op met nette User-Agent; fouten worden geredigeerd."""
    last_error: Exception | None = None
    for _ in range(retries + 1):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    data = gzip.decompress(data)
                return data
        except (urllib.error.URLError, OSError, TimeoutError) as exc:  # noqa: PERF203
            last_error = exc
    raise SourceError(redact(f"ophalen mislukt: {last_error}")) from None


def http_get_json(url: str, timeout: int = DEFAULT_TIMEOUT):
    return json.loads(http_get(url, timeout=timeout).decode("utf-8"))


class SourceError(Exception):
    """Bronfout met reeds geredigeerde boodschap."""


@dataclass
class SourceResult:
    """Uitkomst van één bronadapter binnen een pipeline-run."""

    source: str
    status: str = "failed"  # ok | ok_stale | skipped_no_key | failed
    records: list[dict] = field(default_factory=list)
    source_updated_at: str | None = None
    valid_until: str | None = None
    attribution: str = ""
    source_url: str = ""
    notes: list[str] = field(default_factory=list)
    error: str | None = None
    # Extra bestanden (bv. rasters): artefactpad -> bytes.
    files: dict[str, bytes] = field(default_factory=dict)
    # Expliciete geografische/productdekking voor een latere dekkingskaart.
    coverage: dict = field(default_factory=dict)

    def fail(self, message: str) -> "SourceResult":
        self.status = "failed"
        self.error = redact(message)
        self.records = []
        self.files = {}
        return self


def parse_wkt_point(wkt: str) -> dict | None:
    match = re.match(r"\s*POINT\s*\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s*\)", wkt or "")
    if not match:
        return None
    try:
        coordinates = [float(match.group(1)), float(match.group(2))]
    except ValueError:
        return None
    return {"type": "Point", "coordinates": coordinates}


def gzip_bytes(data: bytes) -> bytes:
    buffer = io.BytesIO()
    # mtime=0 houdt de output deterministisch voor gelijke input.
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as handle:
        handle.write(data)
    return buffer.getvalue()
