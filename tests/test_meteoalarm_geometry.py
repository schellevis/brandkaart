from pipeline import meteoalarm_geometry as mg

def test_convert_cap_polygon_wisselt_lat_lon_en_sluit():
    ring = mg.convert_cap_polygon("46.0,8.0 46.0,9.0 47.0,9.0")
    assert ring[0] == [8.0, 46.0]           # lon,lat
    assert ring[0] == ring[-1]              # gesloten
    assert len(ring) >= 4

def test_convert_cap_polygon_ongeldig_bereik():
    assert mg.convert_cap_polygon("200,8 46,9 47,9") is None

def test_convert_cap_polygon_te_weinig_punten():
    assert mg.convert_cap_polygon("46,8 46,8") is None

def test_polygons_to_geometry_multipolygon():
    geom = mg.polygons_to_geometry([
        "46,8 46,9 47,9 46,8",
        "40,1 40,2 41,2 40,1",
    ])
    assert geom["type"] == "MultiPolygon"
    assert len(geom["coordinates"]) == 2

def test_polygons_to_geometry_single_polygon():
    geom = mg.polygons_to_geometry(["46,8 46,9 47,9 46,8"])
    assert geom["type"] == "Polygon"

def _rec(zone=None, polygons=None):
    r = {"id": "x", "source_attrs": {}}
    if zone:
        r["source_attrs"]["zone"] = zone
    return r

def test_attach_inline_polygoon_wint():
    kept, skipped = mg.attach_geometry(
        [_rec()], {}, {}, polygons_by_id={"x": ["46,8 46,9 47,9 46,8"]}
    )
    assert skipped == 0
    assert kept[0]["geometry"]["type"] == "Polygon"
    assert "_polygons" not in kept[0]

def test_attach_emma_join():
    emma = {"DE304": {"type": "Polygon", "coordinates": [[[8, 50], [9, 50], [9, 51], [8, 50]]]}}
    kept, skipped = mg.attach_geometry([_rec(zone="EMMA_ID:DE304")], emma, {})
    assert skipped == 0
    assert kept[0]["geometry"] == emma["DE304"]

def test_attach_nuts_join():
    nuts = {"FR713": {"type": "Polygon", "coordinates": [[[4, 45], [5, 45], [5, 46], [4, 45]]]}}
    kept, skipped = mg.attach_geometry([_rec(zone="NUTS:FR713")], {}, nuts)
    assert kept[0]["geometry"] == nuts["FR713"]

def test_attach_onbekende_zone_overgeslagen():
    kept, skipped = mg.attach_geometry([_rec(zone="EMMA_ID:ONBEKEND")], {}, {})
    assert kept == [] and skipped == 1
