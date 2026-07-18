import io, zipfile
from pipeline.places import ATTRIBUTION, build_payload, parse_cities

def _row(name, country, lat, lon, population):
    fields = ["1", name, name, "", str(lat), str(lon), "P", "PPL", country, "", "", "", "", "", str(population), "", "", "Europe/Test", "2026-01-01"]
    return "\t".join(fields)

def test_filtert_bbox_en_sorteert_op_inwoners():
    text = "\n".join([_row("Klein", "FR", 48, 2, 6000), _row("Groot", "ES", 40, -3, 900000), _row("Buiten", "US", 20, -80, 1000000)])
    assert parse_cities(text) == [["Groot", "ES", 40.0, -3.0, 900000], ["Klein", "FR", 48.0, 2.0, 6000]]

def test_payload_contract():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive: archive.writestr("cities5000.txt", _row("Teststad", "NL", 52, 5, 12345))
    payload = build_payload(buffer.getvalue(), "2026-07-17T00:00:00Z")
    assert payload == {"attribution": ATTRIBUTION, "generated": "2026-07-17T00:00:00Z", "places": [["Teststad", "NL", 52.0, 5.0, 12345]]}
