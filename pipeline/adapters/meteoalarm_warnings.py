"""MeteoAlarm-waarschuwingen uit sleutelvrije Atom/CAP-feeds voor 8 landen.

De landbronnen draaien live vanuit :mod:`pipeline.run`, met afzonderlijke
resultaten en fallback per land. CAP-vrijetekst wordt niet gepubliceerd.
"""

from __future__ import annotations

import hashlib

# Niet-vertrouwde externe XML: uitsluitend defusedxml (XXE / billion-laughs).
import defusedxml.ElementTree as ET

from concurrent.futures import ThreadPoolExecutor

from .. import meteoalarm_geometry as _geo
from ..common import SourceResult, http_get, iso, normalize_iso, parse_iso, utcnow
from ..schema import make_record

ATOM_NS = "{http://www.w3.org/2005/Atom}"
CAP_NS = "{urn:oasis:names:tc:emergency:cap:1.2}"

COUNTRIES = {
    "nl": "netherlands", "be": "belgium", "lu": "luxembourg",
    "de": "germany", "at": "austria", "ch": "switzerland",
    "it": "italy", "fr": "france",
}
FEED_URL = "https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-{slug}"
FIRE_RELEVANT_TYPES = {5, 8}  # 5 = high-temperature, 8 = forest-fire
ATTRIBUTION = "EUMETNET – MeteoAlarm"

AWARENESS_LABELS = {5: "Hitte", 8: "Bosbrand"}
LEVEL_MAP = {2: ("yellow", 2), 3: ("orange", 3), 4: ("red", 4)}

# Goedkope Atom-voorfilter op de (Engelse) event-tekst; awareness_type in het
# CAP-bericht is de definitieve inhoudelijke filter.
_PREFILTER_KEYWORDS = ("fire", "forest", "heat", "temperature")


def parse_atom(xml: bytes) -> tuple[str | None, list[dict]]:
    root = ET.fromstring(xml)
    feed_updated = root.findtext(f"{ATOM_NS}updated")
    entries: list[dict] = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        cap_url = None
        for link in entry.findall(f"{ATOM_NS}link"):
            if link.get("type") == "application/cap+xml":
                cap_url = link.get("href")
                break
        if not cap_url:
            continue
        entries.append({
            "cap_url": cap_url,
            "event": (entry.findtext(f"{CAP_NS}event") or "").strip(),
            "identifier": entry.findtext(f"{CAP_NS}identifier"),
        })
    return feed_updated, entries


def prefilter_cap_urls(entries: list[dict]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        event = entry["event"].lower()
        if not any(word in event for word in _PREFILTER_KEYWORDS):
            continue
        url = entry["cap_url"]
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _first_int(value: str | None) -> int | None:
    """'5; high-temperature' -> 5; '2; yellow; Moderate' -> 2."""
    if not value:
        return None
    head = value.split(";", 1)[0].strip()
    return int(head) if head.isdigit() else None


def _parameters(info: ET.Element) -> dict[str, str]:
    params: dict[str, str] = {}
    for param in info.findall(f"{CAP_NS}parameter"):
        name = param.findtext(f"{CAP_NS}valueName")
        value = param.findtext(f"{CAP_NS}value")
        if name is not None:
            params[name.strip()] = (value or "").strip()
    return params


def _parse_area(area: ET.Element) -> dict:
    emma_id = None
    nuts = None
    for geocode in area.findall(f"{CAP_NS}geocode"):
        name = (geocode.findtext(f"{CAP_NS}valueName") or "").strip()
        value = (geocode.findtext(f"{CAP_NS}value") or "").strip()
        if name == "EMMA_ID":
            emma_id = value
        elif name.startswith("NUTS"):
            nuts = value
    polygons = [
        (poly.text or "").strip()
        for poly in area.findall(f"{CAP_NS}polygon")
        if (poly.text or "").strip()
    ]
    return {
        "desc": (area.findtext(f"{CAP_NS}areaDesc") or "").strip(),
        "emma_id": emma_id,
        "nuts": nuts,
        "polygons": polygons,
    }


def parse_cap(xml: bytes) -> dict | None:
    try:
        root = ET.fromstring(xml)  # defusedxml: weigert XXE/entity-aanvallen
    except Exception:  # noqa: BLE001 — onleesbaar of vijandig CAP faalt veilig als None
        return None
    references = (root.findtext(f"{CAP_NS}references") or "").split()
    infos: list[dict] = []
    for info in root.findall(f"{CAP_NS}info"):
        params = _parameters(info)
        infos.append({
            "lang": (info.findtext(f"{CAP_NS}language") or "").strip(),
            "event": (info.findtext(f"{CAP_NS}event") or "").strip(),
            "onset": info.findtext(f"{CAP_NS}onset"),
            "effective": info.findtext(f"{CAP_NS}effective"),
            "expires": info.findtext(f"{CAP_NS}expires"),
            "sent": root.findtext(f"{CAP_NS}sent"),
            "certainty": (info.findtext(f"{CAP_NS}certainty") or "").strip(),
            "urgency": (info.findtext(f"{CAP_NS}urgency") or "").strip(),
            "severity": (info.findtext(f"{CAP_NS}severity") or "").strip(),
            "web": (info.findtext(f"{CAP_NS}web") or "").strip() or None,
            "awareness_type": _first_int(params.get("awareness_type")),
            "awareness_level": _first_int(params.get("awareness_level")),
            "areas": [_parse_area(a) for a in info.findall(f"{CAP_NS}area")],
        })
    return {
        "identifier": (root.findtext(f"{CAP_NS}identifier") or "").strip(),
        "status": (root.findtext(f"{CAP_NS}status") or "").strip(),
        "msg_type": (root.findtext(f"{CAP_NS}msgType") or "").strip(),
        "references": references,
        "infos": infos,
    }


def select_info(cap: dict, prefer: tuple[str, ...] = ("nl", "en")) -> dict | None:
    infos = cap.get("infos") or []
    if not infos:
        return None
    for wanted in prefer:
        for info in infos:
            primary = info["lang"].split("-", 1)[0].lower()
            if primary == wanted:
                return info
    return infos[0]


def area_key(area: dict) -> str:
    if area.get("emma_id"):
        return area["emma_id"]
    if area.get("nuts"):
        return area["nuts"]
    basis = area.get("desc", "").strip().lower() + "|" + "|".join(area.get("polygons", []))
    return "h:" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]


def _zone_ref(area: dict) -> str | None:
    if area.get("emma_id"):
        return f"EMMA_ID:{area['emma_id']}"
    if area.get("nuts"):
        return f"NUTS:{area['nuts']}"
    return None


def build_records(
    cap: dict,
    country: str,
    fetched_at: str,
    polygons_by_id: dict[str, list[str]] | None = None,
) -> list[dict]:
    if cap.get("status") != "Actual":
        return []
    if cap.get("msg_type") not in {"Alert", "Update"}:
        return []
    info = select_info(cap, prefer=("nl", "en"))
    if info is None:
        return []
    awareness_type = info["awareness_type"]
    if awareness_type not in FIRE_RELEVANT_TYPES:
        return []
    level = info["awareness_level"]
    if level not in LEVEL_MAP:
        return []
    severity_source, severity_normalized = LEVEL_MAP[level]
    identifier = cap["identifier"]

    records: list[dict] = []
    for area in info["areas"]:
        source_attrs = {
            "country": country,
            "awareness_type": AWARENESS_LABELS[awareness_type],
            "urgency": info["urgency"] or None,
            "severity": info["severity"] or None,
            "msg_type": cap.get("msg_type") or None,
        }
        zone = _zone_ref(area)
        if zone:
            source_attrs["zone"] = zone
        record_id = f"{country}:{identifier}:{area_key(area)}"
        record = make_record(
            id=record_id,
            source_id=identifier,
            kind="warning",
            authority=ATTRIBUTION,
            source_url=info["web"] or FEED_URL.format(slug=COUNTRIES[country]),
            geometry=None,  # gezet in Task 5 (join of inline)
            area_text=area["desc"] or None,
            severity_source=severity_source,
            severity_normalized=severity_normalized,
            certainty=info["certainty"] or None,
            issued_at=normalize_iso(info["sent"]),
            valid_from=normalize_iso(info["onset"] or info["effective"]),
            valid_to=normalize_iso(info["expires"]),
            fetched_at=fetched_at,
            expires_policy="hide_after_valid_to",
            attribution=ATTRIBUTION,
            raw_payload_ref=f"meteoalarm:{country}:{identifier}",
            source_attrs={k: v for k, v in source_attrs.items() if v is not None},
        )
        if polygons_by_id is not None and area["polygons"]:
            polygons_by_id[record_id] = area["polygons"]
        records.append(record)
    return records


MAX_WORKERS = 6
CAP_TIMEOUT = 20
CAP_RETRIES = 2


def _fetch_one_cap(url: str) -> dict | None:
    """Haal en parse een CAP-bericht. Gooit door bij netwerkfout."""
    raw = http_get(url, timeout=CAP_TIMEOUT, retries=CAP_RETRIES)
    return parse_cap(raw)


def fetch_country(country: str, emma_zones: dict, nuts_zones: dict) -> SourceResult:
    source = f"meteoalarm_{country}"
    result = SourceResult(source=source, attribution=ATTRIBUTION,
                          source_url=FEED_URL.format(slug=COUNTRIES[country]))
    try:
        atom = http_get(result.source_url)
    except Exception as exc:  # noqa: BLE001
        return result.fail(f"feed ophalen mislukt: {exc}")
    try:
        feed_updated, entries = parse_atom(atom)
    except Exception as exc:  # noqa: BLE001
        return result.fail(f"feed onleesbaar: {exc}")

    urls = prefilter_cap_urls(entries)
    fetched_at = iso(utcnow())
    caps: list[dict] = []
    try:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            for cap in pool.map(_fetch_one_cap, urls):
                if cap is None:
                    return result.fail("onleesbaar CAP-bericht; land onvolledig")
                caps.append(cap)
    except Exception as exc:  # noqa: BLE001 — volledigheid leidend
        return result.fail(f"CAP ophalen mislukt: {exc}")

    # References zijn sender,identifier,sent-triplets; onderdruk de vervangen
    # identifier wanneer die ook in deze feedrun voorkomt.
    referenced: set[str] = set()
    for cap in caps:
        for reference in cap["references"]:
            parts = reference.split(",")
            if len(parts) >= 2 and parts[1]:
                referenced.add(parts[1])

    records: list[dict] = []
    polygons_by_id: dict[str, list[str]] = {}
    for cap in caps:
        if cap["identifier"] in referenced:
            continue
        records.extend(build_records(cap, country, fetched_at, polygons_by_id))

    kept, skipped = _geo.attach_geometry(
        records, emma_zones, nuts_zones, polygons_by_id=polygons_by_id
    )
    if skipped:
        result.notes.append(f"{skipped} record(s) zonder geometrie overgeslagen")
        return result.fail(
            "landlaag onvolledig: relevante waarschuwing zonder geometrie"
        )

    result.records = kept
    result.source_updated_at = normalize_iso(feed_updated)
    valid_tos = [parsed for r in kept if (parsed := parse_iso(r.get("valid_to"))) is not None]
    result.valid_until = iso(max(valid_tos)) if valid_tos else None
    result.status = "ok"
    return result


def fetch_all(emma_zones: dict | None = None, nuts_zones: dict | None = None) -> list[SourceResult]:
    emma_zones = emma_zones or {}
    nuts_zones = nuts_zones or {}
    results: list[SourceResult] = []
    for country in COUNTRIES:
        try:
            result = fetch_country(country, emma_zones, nuts_zones)
        except Exception as exc:  # noqa: BLE001 — één land mag de run niet breken
            result = SourceResult(
                source=f"meteoalarm_{country}",
                attribution=ATTRIBUTION,
                source_url=FEED_URL.format(slug=COUNTRIES[country]),
            ).fail(f"onverwachte landfout: {exc}")
        results.append(result)
    return results
