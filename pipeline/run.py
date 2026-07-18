"""Pipeline-runner: alle bronnen, validatie en artefactbouw in één run.

Gebruik: uv run python -m pipeline.run [--output public/data]

Een falende bron blokkeert de andere bronnen niet; een validatiefout
(PII/secrets) blokkeert wél de volledige publicatie.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import meteoalarm_geometry
from .adapters import (
    aemet_danger, aemet_warnings, cems_rapid_mapping, effis_danger, firms,
    galicia_irdi, meteo_forets, meteoalarm_warnings, pla_alfa,
)
from .artifact import ArtifactError, build
from .common import SourceResult, redact
from .geometry import attach_geometry, load_departements

ADAPTERS = (
    firms,
    meteo_forets,
    aemet_warnings,
    aemet_danger,
    effis_danger,
    cems_rapid_mapping,
    pla_alfa,
    galicia_irdi,
)

DEPARTEMENTS_ASSET = Path("assets/departements.simplified.geojson.gz")
ARTIFACT_WARNING_BYTES = 5 * 1024 * 1024


def _attach_departements(result: SourceResult) -> None:
    """Koppel departementsgrenzen aan de Franse gevaarrecords."""
    if not DEPARTEMENTS_ASSET.exists():
        result.notes.append(f"{DEPARTEMENTS_ASSET} ontbreekt; records blijven zonder geometrie")
        return
    linked, missing = attach_geometry(result.records, load_departements(DEPARTEMENTS_ASSET))
    result.notes.append(f"geometrie gekoppeld: {linked} records, {missing} zonder match")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="public/data", type=Path)
    args = parser.parse_args(argv)

    results: list[SourceResult] = []
    for adapter in ADAPTERS:
        name = adapter.__name__.rsplit(".", 1)[-1]
        print(f"[bron] {name} ophalen…", flush=True)
        try:
            result = adapter.fetch()
        except Exception as exc:  # noqa: BLE001 — één bron mag de run niet breken
            result = SourceResult(source=name).fail(f"onverwachte fout: {exc}")
        if result.source == "meteo_forets" and result.status.startswith("ok"):
            _attach_departements(result)
        results.append(result)
        print(f"[bron] {name}: {result.status}, {len(result.records)} records")
        for note in result.notes:
            print(f"       - {note}")
        if result.error:
            print(f"       ! {result.error}")

    # MeteoAlarm-waarschuwingen (8 landen). De geometrie wordt binnen de adapter
    # gekoppeld; de zone-assets worden hier geladen en meegegeven.
    print("[bron] meteoalarm_warnings ophalen…", flush=True)
    try:
        emma = meteoalarm_geometry.load_zone_asset(
            meteoalarm_geometry.EMMA_ASSET_PATH, "emma_id"
        )
        nuts = meteoalarm_geometry.load_zone_asset(
            meteoalarm_geometry.NUTS_ASSET_PATH, "nuts_code"
        )
    except Exception as exc:  # noqa: BLE001 — corrupte assets mogen de run niet breken
        print(
            f"       ! geometrie-assets ontbreken ({redact(str(exc))}); "
            "records zonder match worden overgeslagen"
        )
        emma, nuts = {}, {}
    try:
        meteoalarm_results = meteoalarm_warnings.fetch_all(emma, nuts)
    except Exception as exc:  # noqa: BLE001 — onverwachte adapterfout blijft per bron zichtbaar
        meteoalarm_results = [
            SourceResult(source=f"meteoalarm_{country}").fail(
                f"onverwachte MeteoAlarm-fout: {exc}"
            )
            for country in meteoalarm_warnings.COUNTRIES
        ]
    for result in meteoalarm_results:
        results.append(result)
        print(f"[bron] {result.source}: {result.status}, {len(result.records)} records")
        for note in result.notes:
            print(f"       - {note}")
        if result.error:
            print(f"       ! {result.error}")

    try:
        # Het bestaande artefact dient als bron voor stale_reused-fallback.
        report = build(results, args.output, previous_dir=args.output)
    except ArtifactError as exc:
        print(f"\n[FOUT] {redact(str(exc))}", file=sys.stderr)
        print("[FOUT] Er is niets gepubliceerd.", file=sys.stderr)
        return 1

    print(f"\n[artefact] geschreven naar {args.output}/")
    total = 0
    for path, size in sorted(report.items()):
        total += size
        print(f"  {size / 1024:9.1f} kB  {path}")
    print(f"  {total / 1024:9.1f} kB  totaal")
    if total > ARTIFACT_WARNING_BYTES:
        print(
            f"[let op] artefact is groter dan de afgesproken waarschuwingsgrens "
            f"van {ARTIFACT_WARNING_BYTES / 1024 / 1024:.0f} MB",
            file=sys.stderr,
        )

    manifest = json.loads((args.output / "manifest.json").read_text("utf-8"))
    reused = [s for s, e in manifest["sources"].items() if e["status"] == "stale_reused"]
    failed = [
        s
        for s, e in manifest["sources"].items()
        if e["status"] == "failed" or (e["error"] and e["status"] != "stale_reused")
    ]
    skipped = [r.source for r in results if r.status == "skipped_no_key"]
    if reused:
        print(f"\n[let op] bron faalde, vorige laag hergebruikt (stale_reused): {', '.join(reused)}")
    if failed:
        print(f"[let op] mislukte bronnen (zichtbaar in manifest): {', '.join(failed)}")
    if skipped:
        print(f"[let op] overgeslagen zonder sleutel: {', '.join(skipped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
