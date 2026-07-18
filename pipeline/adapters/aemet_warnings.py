"""AEMET-waarschuwingen: sleutelvrije GeoJSON-tarball.

De officiële waarschuwingspagina bevat een downloadlink met wisselende
timestamp; de adapter ontdekt die link per run. Het archief bevat
daagse overzichten (r_D+0..r_D+2, per gebied penbal/can) en uurbestanden
(av_hh_*). Het prototype gebruikt de dagbestanden.

Zoneproperties per feature: per fenomeen een stringified detail-lijst
(`Avis_{FFPP}`, bv. Avis_ATTA voor hitte, Avis_TOTO voor onweer) met daarin
een letterlijke `severity`-tekst (Amarillo/Naranja/Rojo), plus numerieke
rangordevelden (`Nivel_{FFPP}`, `Av_mayor`), `COD_Z`, `Nombre_zona` en
`N_avisos`.

Kleurmapping (onderzoek 17 juli 2026 tegen Plan Meteoalerta + live data):
het numerieke veld is een prioriteits-/rangorde, LAGER = ernstiger
(2=naranja en 3=amarillo direct geverifieerd; 1=rojo afgeleid). Verde-zones
worden niet als feature geëxporteerd. Daarom is de tekstuele severity in de
aviso-details leidend en dient het numerieke veld alleen als fallback.
"""

from __future__ import annotations

import ast
import io
import json
import re
import tarfile

from ..common import SourceResult, http_get, iso, utcnow
from ..schema import make_record

PAGE_URL = "https://www.aemet.es/es/eltiempo/prediccion/avisos"
ATTRIBUTION = "© AEMET"

DAILY_FILE_PATTERN = re.compile(
    r"^r_D\+(?P<day>\d)_(?P<stamp>\d{14})_(?P<area>penbal|can)_(?P<target>\d{8})"
)
AREA_LABELS = {"penbal": "schiereiland en Balearen", "can": "Canarische Eilanden"}

# Normalisatie uitsluitend voor kaartkleur/sortering; bronwoord blijft leidend.
SEVERITY_WORDS = {"amarillo": 2, "naranja": 3, "rojo": 4}
# Numerieke rangorde als fallback wanneer geen tekstuele severity aanwezig is:
# lager getal = ernstiger (1=rojo is afgeleid, niet direct waargenomen).
NIVEL_RANK_FALLBACK = {1: "rojo", 2: "naranja", 3: "amarillo"}
MAX_PHENOMENA = 5


def fetch() -> SourceResult:
    result = SourceResult(source="aemet_warnings", attribution=ATTRIBUTION, source_url=PAGE_URL)
    try:
        page = http_get(PAGE_URL).decode("utf-8", errors="replace")
        archive_url = _discover_archive_url(page)
        if archive_url is None:
            return result.fail("geen tar.gz-downloadlink gevonden op de waarschuwingspagina")
        archive = http_get(archive_url)
    except Exception as exc:  # noqa: BLE001
        return result.fail(str(exc))

    fetched_at = iso(utcnow())
    records: dict[str, dict] = {}
    daily_files = 0
    hourly_files = 0
    max_target = None
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as tar:
            for member in tar.getmembers():
                if not member.isfile():
                    continue
                name = member.name.rsplit("/", 1)[-1]
                if name.startswith("av_hh"):
                    hourly_files += 1
                    continue
                match = DAILY_FILE_PATTERN.match(name)
                if not match:
                    continue
                daily_files += 1
                handle = tar.extractfile(member)
                if handle is None:
                    continue
                try:
                    collection = json.loads(handle.read().decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    result.notes.append(f"onleesbare JSON in {name}")
                    continue
                target = match.group("target")
                if max_target is None or target > max_target:
                    max_target = target
                for feature in collection.get("features", []):
                    record = _normalize_feature(feature, match, name, fetched_at)
                    if record is not None:
                        records[record["id"]] = record
    except tarfile.TarError as exc:
        return result.fail(f"archief onleesbaar: {exc}")

    if daily_files == 0:
        return result.fail(
            f"geen dagbestanden (r_D+N) herkend in archief ({hourly_files} uurbestanden gezien)"
        )

    result.records = list(records.values())
    result.notes.append(
        f"{daily_files} dagbestanden en {hourly_files} uurbestanden in archief; "
        "uurbestanden nog ongebruikt"
    )
    fallback = sum(1 for r in records.values() if r.get("certainty") == "afgeleid_van_rangorde")
    if fallback:
        result.notes.append(
            f"{fallback} records zonder tekstuele severity; kleur afgeleid van numerieke rangorde"
        )
    result.source_updated_at = fetched_at
    if max_target:
        result.valid_until = (
            f"{max_target[:4]}-{max_target[4:6]}-{max_target[6:8]}T23:59:59Z"
        )
    result.status = "ok"
    return result


def _discover_archive_url(page: str) -> str | None:
    matches = re.findall(r"""["']([^"']+\.tar(?:\.gz)?)["']""", page)
    for match in matches:
        if match.startswith("//"):
            return "https:" + match
        if match.startswith("http"):
            return match
        if match.startswith("/"):
            return "https://www.aemet.es" + match
    return None


def _normalize_feature(feature: dict, match: re.Match, filename: str, fetched_at: str):
    props = feature.get("properties") or {}
    zone_code = str(props.get("COD_Z", "")).strip()
    if not zone_code:
        return None
    severity, certainty, phenomena = _extract_severity(props)
    if severity is None:
        return None
    target = match.group("target")
    target_date = f"{target[:4]}-{target[4:6]}-{target[6:8]}"

    source_attrs = {
        "area": AREA_LABELS.get(match.group("area"), match.group("area")),
        "day_offset": int(match.group("day")),
        "n_avisos": str(props.get("N_avisos", "")),
        "issued_stamp": match.group("stamp"),
    }
    if phenomena:
        source_attrs["phenomena"] = phenomena

    return make_record(
        id=f"aemet-{target_date}-{zone_code}",
        source_id=zone_code,
        kind="warning",
        authority="AEMET",
        source_url=PAGE_URL,
        geometry=feature.get("geometry"),
        area_text=_clean_text(props.get("Nombre_zona")),
        severity_source=severity,
        severity_normalized=SEVERITY_WORDS.get(severity),
        certainty=certainty,
        valid_from=f"{target_date}T00:00:00Z",
        valid_to=f"{target_date}T23:59:59Z",
        fetched_at=fetched_at,
        expires_policy="hide_after_valid_to",
        attribution=ATTRIBUTION,
        raw_payload_ref=f"aemet_warnings:{filename}",
        source_attrs=source_attrs,
    )


def _extract_severity(props: dict):
    """Bepaal de zone-severity uit de aviso-details van alle fenomenen.

    Retourneert (severity, certainty, fenomeenbeschrijvingen). De tekstuele
    `severity` uit de Avis_*-detail-lijsten is leidend; alleen zonder tekst
    valt de functie terug op de numerieke rangorde (lager = ernstiger).
    """
    words: list[str] = []
    phenomena: list[str] = []
    for key, value in props.items():
        if not key.startswith("Avis_") or value in (None, ""):
            continue
        try:
            entries = ast.literal_eval(str(value))
        except (ValueError, SyntaxError):
            continue
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            word = str(entry.get("severity", "")).strip().lower()
            if word in SEVERITY_WORDS:
                words.append(word)
            description = _clean_text(entry.get("descripcion"))
            if description and len(phenomena) < MAX_PHENOMENA:
                phenomena.append(description[:100])
    if words:
        return max(words, key=SEVERITY_WORDS.__getitem__), "aviso", phenomena

    # Fallback: numerieke rangorde over alle Nivel_*-velden en Av_mayor.
    levels = []
    for key, value in props.items():
        if key == "Av_mayor" or key.startswith("Nivel_"):
            try:
                levels.append(int(str(value).strip()))
            except (TypeError, ValueError):
                continue
    ranked = [level for level in levels if level in NIVEL_RANK_FALLBACK]
    if not ranked:
        return None, None, phenomena
    return NIVEL_RANK_FALLBACK[min(ranked)], "afgeleid_van_rangorde", phenomena


def _clean_text(value) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text[:300] or None
