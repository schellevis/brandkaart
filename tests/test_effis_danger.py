import json
import struct
from datetime import datetime, timezone

from pipeline.adapters import effis_danger as effis


def _png(width=effis.WIDTH, height=effis.HEIGHT):
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x06\x00\x00\x00"
        + b"crc!"
        + struct.pack(">I", 1)
        + b"IDATxcrc!"
        + struct.pack(">I", 0)
        + b"IENDcrc!"
    )


def test_fetch_publiceert_drie_complete_dagen(monkeypatch):
    seen = []
    monkeypatch.setattr(effis, "utcnow", lambda: datetime(2026, 7, 18, 8, tzinfo=timezone.utc))
    monkeypatch.setattr(effis, "http_get", lambda url, **kwargs: seen.append(url) or _png())

    result = effis.fetch()

    assert result.status == "ok"
    assert len(result.records) == 3
    assert len(result.files) == 6
    assert [r["source_attrs"]["day_offset"] for r in result.records] == [0, 1, 2]
    assert "TIME=2026-07-18" in seen[0]
    assert "TIME=2026-07-20" in seen[2]
    assert result.valid_until == "2026-07-21T00:00:00Z"


def test_raster_gebruikt_dezelfde_webmercatorprojectie_als_leaflet(monkeypatch):
    seen = []
    monkeypatch.setattr(effis, "utcnow", lambda: datetime(2026, 7, 18, 8, tzinfo=timezone.utc))
    monkeypatch.setattr(effis, "http_get", lambda url, **kwargs: seen.append(url) or _png())

    result = effis.fetch()
    meta = json.loads(result.files["danger/eu/effis/fwi-2026-07-18.json"])

    assert "SRS=EPSG%3A3857" in seen[0]
    assert "BBOX=-2782987" in seen[0]
    assert meta["crs"] == "EPSG:3857"
    assert meta["projected_bounds"]["north"] > 11_000_000


def test_onverwachte_of_onvolledige_png_faalt_hele_bron(monkeypatch):
    monkeypatch.setattr(effis, "utcnow", lambda: datetime(2026, 7, 18, 8, tzinfo=timezone.utc))
    responses = iter((_png(), _png(width=42)))
    monkeypatch.setattr(effis, "http_get", lambda url, **kwargs: next(responses))

    result = effis.fetch()

    assert result.status == "failed"
    assert result.records == []
    assert result.files == {}
    assert "D+1" in result.error
