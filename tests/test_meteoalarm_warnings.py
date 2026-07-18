import gzip
import json

from pipeline.adapters import meteoalarm_warnings as ma
from pipeline.artifact import build
from pipeline.schema import ALLOWED_FIELDS

ATOM = b"""<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2">
  <updated>2026-07-17T06:00:00Z</updated>
  <entry>
    <cap:event>Yellow warning for heatwave</cap:event>
    <cap:identifier>2.49.0.0.56.0.BE.X.1</cap:identifier>
    <link type="application/cap+xml" href="https://feeds.example/cap/1"/>
  </entry>
  <entry>
    <cap:event>Orange thunderstorm warning</cap:event>
    <cap:identifier>2.49.0.0.56.0.BE.X.2</cap:identifier>
    <link type="application/cap+xml" href="https://feeds.example/cap/2"/>
  </entry>
  <entry>
    <cap:event>Red warning for forest fire</cap:event>
    <cap:identifier>2.49.0.0.56.0.BE.X.3</cap:identifier>
    <link type="application/cap+xml" href="https://feeds.example/cap/1"/>
  </entry>
</feed>"""

def test_parse_atom_extracts_updated_and_entries():
    updated, entries = ma.parse_atom(ATOM)
    assert updated == "2026-07-17T06:00:00Z"
    assert len(entries) == 3
    assert entries[0]["cap_url"] == "https://feeds.example/cap/1"
    assert entries[0]["event"] == "Yellow warning for heatwave"

def test_prefilter_keeps_fire_and_heat_deduped():
    _, entries = ma.parse_atom(ATOM)
    urls = ma.prefilter_cap_urls(entries)
    # heat (cap/1) en forest fire (ook cap/1) blijven, dedupe -> 1 url; onweer valt af
    assert urls == ["https://feeds.example/cap/1"]

CAP = b"""<?xml version="1.0"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>2.49.0.0.56.0.BE.X.1</identifier>
  <status>Actual</status>
  <msgType>Alert</msgType>
  <info>
    <language>nl-BE</language>
    <event>Gele waarschuwing voor hittegolf</event>
    <onset>2026-07-17T10:00:00+00:00</onset>
    <expires>2026-07-18T20:00:00+00:00</expires>
    <certainty>Likely</certainty>
    <urgency>Future</urgency>
    <severity>Moderate</severity>
    <web>https://kmi.be/warning/1</web>
    <parameter><valueName>awareness_level</valueName><value>2; yellow; Moderate</value></parameter>
    <parameter><valueName>awareness_type</valueName><value>5; high-temperature</value></parameter>
    <area>
      <areaDesc>Namen</areaDesc>
      <geocode><valueName>EMMA_ID</valueName><value>BE006</value></geocode>
      <geocode><valueName>NUTS2</valueName><value>BE35</value></geocode>
    </area>
  </info>
  <info>
    <language>en</language>
    <event>Yellow warning for heatwave</event>
    <onset>2026-07-17T10:00:00+00:00</onset>
    <expires>2026-07-18T20:00:00+00:00</expires>
    <certainty>Likely</certainty><urgency>Future</urgency><severity>Moderate</severity>
    <parameter><valueName>awareness_level</valueName><value>2; yellow; Moderate</value></parameter>
    <parameter><valueName>awareness_type</valueName><value>5; high-temperature</value></parameter>
    <area><areaDesc>Namur</areaDesc>
      <geocode><valueName>EMMA_ID</valueName><value>BE006</value></geocode></area>
  </info>
</alert>"""

def test_parse_cap_structuur():
    cap = ma.parse_cap(CAP)
    assert cap["identifier"] == "2.49.0.0.56.0.BE.X.1"
    assert cap["status"] == "Actual"
    assert len(cap["infos"]) == 2
    info_nl = cap["infos"][0]
    assert info_nl["awareness_type"] == 5
    assert info_nl["awareness_level"] == 2
    assert info_nl["areas"][0]["emma_id"] == "BE006"
    assert info_nl["areas"][0]["nuts"] == "BE35"
    assert info_nl["web"] == "https://kmi.be/warning/1"

def test_select_info_prefereert_nederlands():
    cap = ma.parse_cap(CAP)
    info = ma.select_info(cap, prefer=("nl", "en"))
    assert info["lang"] == "nl-BE"
    assert info["areas"][0]["desc"] == "Namen"

def test_parse_cap_onleesbaar_geeft_none():
    assert ma.parse_cap(b"<niet-geldig") is None

def test_area_key_voorkeursvolgorde():
    assert ma.area_key({"emma_id": "DE304", "nuts": "DEA2", "desc": "x", "polygons": []}) == "DE304"
    assert ma.area_key({"emma_id": None, "nuts": "FR713", "desc": "x", "polygons": []}) == "FR713"
    h = ma.area_key({"emma_id": None, "nuts": None, "desc": "Ticino", "polygons": ["46,8 46,9 47,9 46,8"]})
    assert h.startswith("h:") and len(h) > 4
    # deterministisch
    assert h == ma.area_key({"emma_id": None, "nuts": None, "desc": "Ticino", "polygons": ["46,8 46,9 47,9 46,8"]})

def test_build_records_hitte_record():
    cap = ma.parse_cap(CAP)
    records = ma.build_records(cap, "be", "2026-07-17T06:00:00Z")
    assert len(records) == 1
    r = records[0]
    assert r["kind"] == "warning"
    assert r["id"] == "be:2.49.0.0.56.0.BE.X.1:BE006"
    assert r["severity_source"] == "yellow"
    assert r["severity_normalized"] == 2
    assert r["area_text"] == "Namen"
    assert r["source_url"] == "https://kmi.be/warning/1"
    assert r["source_attrs"]["awareness_type"] == "Hitte"
    assert r["source_attrs"]["country"] == "be"
    assert r["source_attrs"]["zone"] == "EMMA_ID:BE006"
    assert "event" not in r["source_attrs"]  # geen CAP-vrijetekst
    assert r["attribution"] == ma.ATTRIBUTION
    assert set(r) <= ALLOWED_FIELDS
    assert "_polygons" not in r

def test_build_records_filtert_niet_relevante_types(monkeypatch):
    cap = ma.parse_cap(CAP)
    for info in cap["infos"]:
        info["awareness_type"] = 3  # onweer
    assert ma.build_records(cap, "be", "2026-07-17T06:00:00Z") == []

def _feed_with(cap_urls_events):
    entries = "".join(
        f'<entry><cap:event>{ev}</cap:event>'
        f'<cap:identifier>id-{i}</cap:identifier>'
        f'<link type="application/cap+xml" href="{url}"/></entry>'
        for i, (url, ev) in enumerate(cap_urls_events)
    )
    return (
        b'<feed xmlns="http://www.w3.org/2005/Atom" '
        b'xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2">'
        b'<updated>2026-07-17T06:00:00Z</updated>'
        + entries.encode() + b"</feed>"
    )

def test_fetch_country_ok(monkeypatch):
    feed = _feed_with([("https://cap/1", "Yellow warning for heatwave")])
    def fake_get(url, **kw):
        return feed if "legacy-atom" in url else CAP
    monkeypatch.setattr(ma, "http_get", fake_get)
    result = ma.fetch_country("be", {"BE006": {"type": "Polygon",
        "coordinates": [[[4, 50], [5, 50], [5, 51], [4, 50]]]}}, {})
    assert result.source == "meteoalarm_be"
    assert result.status == "ok"
    assert len(result.records) == 1
    assert result.source_updated_at == "2026-07-17T06:00:00Z"
    assert result.valid_until == "2026-07-18T20:00:00Z"
    assert "issued_at" not in result.records[0]

def test_fetch_country_lege_feed_is_ok(monkeypatch):
    feed = _feed_with([])
    monkeypatch.setattr(ma, "http_get", lambda url, **kw: feed)
    result = ma.fetch_country("nl", {}, {})
    assert result.status == "ok"
    assert result.records == []
    assert result.valid_until is None

def test_fetch_country_cap_uitval_laat_land_falen(monkeypatch):
    feed = _feed_with([("https://cap/1", "Red warning for forest fire")])
    def fake_get(url, **kw):
        if "legacy-atom" in url:
            return feed
        raise OSError("cap onbereikbaar")
    monkeypatch.setattr(ma, "http_get", fake_get)
    result = ma.fetch_country("at", {}, {})
    assert result.status == "failed"
    assert result.error


def _cap_variant(identifier, msg_type="Alert", references=""):
    xml = CAP.replace(
        b"<identifier>2.49.0.0.56.0.BE.X.1</identifier>",
        f"<identifier>{identifier}</identifier>".encode(),
    ).replace(b"<msgType>Alert</msgType>", f"<msgType>{msg_type}</msgType>".encode())
    if references:
        xml = xml.replace(b"<info>", f"<references>{references}</references><info>".encode(), 1)
    return xml


def test_alert_wordt_door_update_reference_vervangen(monkeypatch):
    old_id = "2.49.0.0.56.0.BE.X.OLD"
    new_id = "2.49.0.0.56.0.BE.X.NEW"
    feed = _feed_with([
        ("https://cap/old", "Yellow warning for heatwave"),
        ("https://cap/new", "Yellow warning for heatwave"),
    ])
    caps = {
        "https://cap/old": _cap_variant(old_id),
        "https://cap/new": _cap_variant(
            new_id, "Update", f"sender.example,{old_id},2026-07-17T05:00:00Z"
        ),
    }
    monkeypatch.setattr(
        ma, "http_get", lambda url, **kw: feed if "legacy-atom" in url else caps[url]
    )
    zones = {"BE006": {"type": "Polygon", "coordinates": [[[4, 50], [5, 50], [5, 51], [4, 50]]]}}
    result = ma.fetch_country("be", zones, {})
    assert result.status == "ok"
    assert [record["source_id"] for record in result.records] == [new_id]


def test_cancel_wordt_niet_gepubliceerd():
    cap = ma.parse_cap(_cap_variant("cancel-id", "Cancel"))
    assert ma.build_records(cap, "be", "2026-07-17T06:00:00Z") == []


def test_ontbrekende_geometrie_laat_land_falen(monkeypatch):
    feed = _feed_with([("https://cap/1", "Yellow warning for heatwave")])
    monkeypatch.setattr(
        ma, "http_get", lambda url, **kw: feed if "legacy-atom" in url else CAP
    )
    result = ma.fetch_country("be", {}, {})
    assert result.status == "failed"
    assert "onvolledig" in result.error
    assert result.records == []


def test_gepubliceerd_record_bevat_geen_tijdelijk_polygoonveld(monkeypatch, tmp_path):
    feed = _feed_with([("https://cap/1", "Yellow warning for heatwave")])
    monkeypatch.setattr(
        ma, "http_get", lambda url, **kw: feed if "legacy-atom" in url else CAP
    )
    zones = {"BE006": {"type": "Polygon", "coordinates": [[[4, 50], [5, 50], [5, 51], [4, 50]]]}}
    result = ma.fetch_country("be", zones, {})
    output = tmp_path / "data"
    build([result], output)
    collection = json.loads(gzip.decompress((output / "warnings/eu/be.latest.geojson.gz").read_bytes()))
    assert all("_polygons" not in feature["properties"] for feature in collection["features"])

def test_fetch_all_geeft_acht_bronnen(monkeypatch):
    monkeypatch.setattr(ma, "http_get", lambda url, **kw: _feed_with([]))
    results = ma.fetch_all()
    assert [r.source for r in results] == [f"meteoalarm_{c}" for c in ma.COUNTRIES]
    assert all(r.status == "ok" for r in results)


def test_fetch_all_isoleert_een_onverwachte_landfout(monkeypatch):
    def fake_fetch(country, emma, nuts):
        if country == "be":
            raise ValueError("synthetische fout")
        return ma.SourceResult(source=f"meteoalarm_{country}", status="ok")

    monkeypatch.setattr(ma, "fetch_country", fake_fetch)
    results = ma.fetch_all()
    by_source = {result.source: result for result in results}
    assert by_source["meteoalarm_be"].status == "failed"
    assert by_source["meteoalarm_nl"].status == "ok"
