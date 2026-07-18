"""AEMET-brandgevaar: sleutelvrije GeoTIFF-tarball, D+0 t/m D+7.

De adapter valideert het archief, neemt per dag/gebied een metadatarecord
op en zet de eerste dagen om naar compacte web-PNG's met de officiële
SLD-legendakleuren plus een bounds/legenda-JSON (zie pipeline/raster.py).
"""

from __future__ import annotations

import io
import json
import re
import tarfile
from datetime import datetime, timedelta, timezone

from ..common import SourceResult, http_get, iso, utcnow
from ..raster import convert_geotiff
from ..schema import make_record

DOWNLOAD_URL = "https://www.aemet.es/es/api-eltiempo/incendios/download"
PAGE_URL = "https://www.aemet.es/es/eltiempo/prediccion/incendios"
ATTRIBUTION = "© AEMET"

AREA_LABELS = {"p": "schiereiland en Balearen", "c": "Canarische Eilanden"}
# D+0 t/m D+2 gaan als web-PNG (~68 kB per dag) plus bounds/legenda-JSON mee
# in het artefact; de ruwe GeoTIFFs (5,6 MB per schiereilanddag) nooit.
CONVERT_MAX_DAY_OFFSET = 2
MODEL_STALE_AFTER = timedelta(hours=30)

# Waargenomen naamconventie: down_20260714_peligro_p_D00.tif
# (uitgiftedatum, gebied p/c, doeldag D00..D07).
NAME_PATTERN = re.compile(
    r"down_(?P<issued>\d{8})_peligro_(?P<area>[pc])_D(?P<day>\d{2})\.tiff?$",
    re.IGNORECASE,
)


def fetch() -> SourceResult:
    result = SourceResult(source="aemet_danger", attribution=ATTRIBUTION, source_url=PAGE_URL)
    try:
        archive = http_get(DOWNLOAD_URL, timeout=120)
    except Exception as exc:  # noqa: BLE001
        return result.fail(str(exc))

    fetched_at = iso(utcnow())
    records: list[dict] = []
    newest_issue: datetime | None = None
    tiff_count = 0
    converted = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:*") as tar:
            members = {
                m.name.rsplit("/", 1)[-1]: m for m in tar.getmembers() if m.isfile()
            }
            for name, member in members.items():
                if not name.lower().endswith((".tif", ".tiff")):
                    continue
                tiff_count += 1
                parsed = _parse_name(name)
                if parsed is None:
                    result.notes.append(f"onherkende of niet-ondersteunde bestandsnaam: {name}")
                    continue
                area, issued, day_offset = parsed
                if newest_issue is None or issued > newest_issue:
                    newest_issue = issued
                target = issued + timedelta(days=day_offset)
                artifact_file = None
                if day_offset <= CONVERT_MAX_DAY_OFFSET:
                    handle = tar.extractfile(member)
                    if handle is not None:
                        stem = name.rsplit(".", 1)[0]
                        sld_member = members.get(f"{stem}.sld")
                        sld = tar.extractfile(sld_member).read() if sld_member else None
                        try:
                            conversion = convert_geotiff(name, handle.read(), sld)
                        except Exception as exc:  # noqa: BLE001
                            result.notes.append(f"conversie mislukt voor {name}: {exc}")
                        else:
                            artifact_file = f"danger/es/aemet/{stem}.png"
                            result.files[artifact_file] = conversion["png"]
                            result.files[f"danger/es/aemet/{stem}.json"] = json.dumps(
                                conversion["meta"], ensure_ascii=False
                            ).encode("utf-8")
                            converted += 1
                records.append(
                    _record(
                        name, area, issued, day_offset, target, member.size, fetched_at,
                        artifact_file,
                    )
                )
    except tarfile.TarError as exc:
        return result.fail(f"archief onleesbaar: {exc}")

    if tiff_count == 0:
        return result.fail("archief bevat geen GeoTIFF-bestanden")

    result.records = records
    result.notes.append(
        f"{tiff_count} GeoTIFFs in archief, {converted} omgezet naar web-PNG "
        f"(D+0..D+{CONVERT_MAX_DAY_OFFSET})"
    )
    result.source_updated_at = iso(newest_issue)
    if newest_issue:
        result.valid_until = iso(newest_issue + timedelta(days=8))
    result.status = "ok"
    if newest_issue and utcnow() - newest_issue > MODEL_STALE_AFTER:
        result.status = "ok_stale"
        result.notes.append("modelrun is ouder dan 30 uur")
    return result


def _parse_name(name: str):
    match = NAME_PATTERN.search(name)
    if not match:
        return None
    try:
        issued = datetime.strptime(match.group("issued"), "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    day = int(match.group("day") or 0)
    if day > 7:
        return None
    return match.group("area").lower(), issued, day


def _record(name, area, issued, day_offset, target, size, fetched_at, artifact_file=None) -> dict:
    source_attrs = {"file": name, "bytes": size, "day_offset": day_offset, "area": area}
    if artifact_file:
        source_attrs["png"] = artifact_file
        source_attrs["meta"] = artifact_file.rsplit(".", 1)[0] + ".json"
    return make_record(
        id=f"aemet-ipif-{area}-{issued.date().isoformat()}-d{day_offset}",
        kind="danger",
        authority="AEMET",
        source_url=PAGE_URL,
        geometry=None,  # rasterlaag; verwijzing via source_attrs.file
        area_text=AREA_LABELS.get(area, area),
        severity_source="rasterklassen 0-6 (AEMET IPIF)",
        certainty="forecast",
        issued_at=iso(issued),
        valid_from=iso(target),
        valid_to=iso(target + timedelta(days=1)),
        fetched_at=fetched_at,
        expires_policy="hide_after_valid_to",
        attribution=ATTRIBUTION,
        raw_payload_ref=f"aemet_danger:{name}",
        source_attrs=source_attrs,
    )
