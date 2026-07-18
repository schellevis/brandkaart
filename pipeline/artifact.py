"""Artefactbouw: staging, validatie en atomaire publicatie naar public/data."""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
from datetime import timedelta
from pathlib import Path

from . import PIPELINE_VERSION, SCHEMA_VERSION
from .checks import scan_artifact_files
from .common import SourceResult, gzip_bytes, iso, parse_iso, utcnow
from .schema import to_feature_collection

# Zonder valid_until in het vorige manifest mag een laag maximaal zo lang
# worden hergebruikt na de laatste geslaagde ingest.
REUSE_MAX_AGE = timedelta(hours=24)

# Statische bestandsindeling van de gepubliceerde bronlagen.
LAYER_FILES = {
    "firms": "detections.latest.geojson",
    "cems_rapid_mapping": "incidents.eu.latest.geojson",
    "aemet_warnings": "warnings.es.latest.geojson",
    "meteo_forets": "danger/fr/meteo-des-forets.latest.geojson",
    "aemet_danger": "danger/es/aemet.index.latest.geojson",
    "pla_alfa": "danger/es/cat/pla-alfa.latest.geojson",
    "galicia_irdi": "danger/es/gal/irdi.latest.geojson",
    "canarias_alerts": "measures/es/canarias-alerts.latest.geojson",
}

# MeteoAlarm-landlagen.
LAYER_FILES.update({
    f"meteoalarm_{cc}": f"warnings/eu/{cc}.latest.geojson"
    for cc in ("nl", "be", "lu", "de", "at", "ch", "it", "fr")
})

# Bronnen die technisch nooit in het publieke artefact/manifest mogen komen.
# Publicatie-akkoord voor alle bronnen (incl. MeteoAlarm) verkregen op
# 17 juli 2026; de blokkadeset is daarom leeg. Het mechanisme blijft bestaan
# zodat een bron desgewenst opnieuw geblokkeerd kan worden.
PUBLICATION_BLOCKED_SOURCES: frozenset[str] = frozenset()


class ArtifactError(Exception):
    """Validatie mislukt; er is niets gepubliceerd."""


def build(results: list[SourceResult], output_dir: Path, previous_dir: Path | None = None) -> dict:
    """Bouw het artefact in staging, valideer en publiceer atomair.

    Retourneert een rapport met per bestand de grootte. Bij een
    validatieovertreding blijft de bestaande output onaangeroerd.

    Voor een gefaalde bron wordt, indien `previous_dir` een eerder artefact
    bevat, de laatst gepubliceerde laag hergebruikt zolang die nog geldig
    is — zichtbaar gemarkeerd als `stale_reused` met de oorspronkelijke
    tijden, zodat oude data nooit ongemerkt als actueel verschijnt.
    """
    plain_files: dict[str, bytes] = {}
    manifest = {
        "built_at": iso(utcnow()),
        "pipeline_version": PIPELINE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "sources": {},
    }

    for result in results:
        if result.source in PUBLICATION_BLOCKED_SOURCES:
            continue
        entry = {
            "status": result.status,
            "last_attempt_at": manifest["built_at"],
            "last_success_at": manifest["built_at"] if result.status.startswith("ok") else None,
            "source_updated_at": result.source_updated_at,
            "valid_until": result.valid_until,
            "record_count": len(result.records),
            "attribution": result.attribution,
            "source_url": result.source_url,
            "notes": result.notes,
            "error": result.error,
            "coverage": result.coverage,
        }
        if result.files:
            entry["files"] = sorted(_published_path(path) for path in result.files)
        layer_path = LAYER_FILES.get(result.source)
        if layer_path and result.status.startswith("ok"):
            payload = json.dumps(
                to_feature_collection(result.records),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
            plain_files[layer_path] = payload
            entry["file"] = layer_path + ".gz"
            entry["sha256"] = hashlib.sha256(payload).hexdigest()
        elif layer_path and result.status == "failed" and previous_dir is not None:
            reused = _reuse_previous(result.source, layer_path, previous_dir, manifest["built_at"])
            if reused is not None:
                plain_files[layer_path] = reused["payload"]
                plain_files.update(reused["files"])
                entry["notes"] = entry["notes"] + reused["entry"].pop("notes")
                entry.update(reused["entry"])
        for path, data in result.files.items():
            plain_files[path] = data
        manifest["sources"][result.source] = entry

    manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8")

    violations = scan_artifact_files({**plain_files, "manifest.json": manifest_bytes})
    if violations:
        raise ArtifactError("validatie mislukt:\n" + "\n".join(violations))

    staging = output_dir.parent / (output_dir.name + ".staging")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    report: dict[str, int] = {}
    for path, data in plain_files.items():
        if path.endswith((".json", ".geojson")):
            data = gzip_bytes(data)
            path += ".gz"
        target = staging / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        report[path] = len(data)
    (staging / "manifest.json").write_bytes(manifest_bytes)
    report["manifest.json"] = len(manifest_bytes)

    # Publicatie pas nadat het volledige artefact gevalideerd en geschreven is.
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging.rename(output_dir)
    return report


def _reuse_previous(source: str, layer_path: str, previous_dir: Path, built_at: str):
    """Zoek een nog geldige laag van deze bron in het vorige artefact."""
    try:
        previous_manifest = json.loads((previous_dir / "manifest.json").read_text("utf-8"))
        previous = previous_manifest["sources"][source]
    except (OSError, ValueError, KeyError):
        return None
    if previous.get("status") not in ("ok", "ok_stale", "stale_reused"):
        return None

    valid_until = previous.get("valid_until")
    last_success = previous.get("last_success_at")
    if valid_until is not None:
        valid_until_dt = parse_iso(valid_until)
        built_at_dt = parse_iso(built_at)
        if valid_until_dt is None or built_at_dt is None or valid_until_dt < built_at_dt:
            return None
    else:
        last_success_dt = parse_iso(last_success)
        if last_success_dt is None or last_success_dt < utcnow() - REUSE_MAX_AGE:
            return None

    try:
        payload = gzip.decompress((previous_dir / (layer_path + ".gz")).read_bytes())
    except (OSError, gzip.BadGzipFile):
        return None

    extra_files: dict[str, bytes] = {}
    try:
        for path in previous.get("files", []):
            extra_files[path] = (previous_dir / path).read_bytes()
    except OSError:
        return None

    return {
        "payload": payload,
        "entry": {
            "status": "stale_reused",
            "last_success_at": last_success,
            "source_updated_at": previous.get("source_updated_at"),
            "valid_until": valid_until,
            "record_count": previous.get("record_count"),
            "file": layer_path + ".gz",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "files": list(previous.get("files", [])),
            "notes": [
                "bron faalde in deze run; laag hergebruikt uit het vorige artefact "
                "met de oorspronkelijke tijden"
            ],
        },
        "files": extra_files,
    }


def _published_path(path: str) -> str:
    return path + ".gz" if path.endswith((".json", ".geojson")) else path
