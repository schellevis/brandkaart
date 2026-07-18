import json

import pipeline.artifact as artifact
from pipeline.artifact import PUBLICATION_BLOCKED_SOURCES, build
from pipeline.common import SourceResult


def _meteoalarm_result():
    r = SourceResult(source="meteoalarm_de", status="ok", attribution="EUMETNET – MeteoAlarm")
    r.records = [{
        "id": "de:x:DE304", "kind": "warning", "authority": "EUMETNET – MeteoAlarm",
        "attribution": "EUMETNET – MeteoAlarm", "fetched_at": "2026-07-17T06:00:00Z",
        "geometry": {"type": "Point", "coordinates": [8, 50]},
    }]
    return r


def test_publicatiegate_is_leeg():
    # Publicatie-akkoord voor alle bronnen (17 juli 2026): niets geblokkeerd.
    assert PUBLICATION_BLOCKED_SOURCES == frozenset()


def test_meteoalarm_wordt_gepubliceerd(tmp_path):
    output = tmp_path / "public" / "data"
    build([_meteoalarm_result()], output)
    manifest = json.loads((output / "manifest.json").read_text())
    assert "meteoalarm_de" in manifest["sources"]
    assert (output / "warnings" / "eu" / "de.latest.geojson.gz").exists()


def test_gate_mechanisme_werkt_nog(tmp_path, monkeypatch):
    # Zet een bron alsnog op geblokkeerd: die mag dan niet in het artefact komen.
    monkeypatch.setattr(artifact, "PUBLICATION_BLOCKED_SOURCES", frozenset({"meteoalarm_de"}))
    output = tmp_path / "public" / "data"
    build([_meteoalarm_result()], output)
    manifest = json.loads((output / "manifest.json").read_text())
    assert "meteoalarm_de" not in manifest["sources"]
    assert not (output / "warnings" / "eu" / "de.latest.geojson.gz").exists()
