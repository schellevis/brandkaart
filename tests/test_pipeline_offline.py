"""Netwerkloze end-to-end-run met synthetische adapterfixtures."""
import io, json, tarfile
from datetime import datetime, timezone

from pipeline import run
from pipeline.adapters import aemet_danger, aemet_warnings, cems_rapid_mapping, effis_danger, firms, galicia_irdi, meteo_forets, meteoalarm_warnings, pla_alfa

_EMPTY_ATOM = (b'<feed xmlns="http://www.w3.org/2005/Atom" '
              b'xmlns:cap="urn:oasis:names:tc:emergency:cap:1.2">'
              b'<updated>2026-07-17T00:00:00Z</updated></feed>')

def _tar(files):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as archive:
        for name, data in files.items():
            info = tarfile.TarInfo(name); info.size = len(data); archive.addfile(info, io.BytesIO(data))
    return out.getvalue()

def test_pipeline_volledig_offline(monkeypatch, tmp_path):
    today = datetime.now(timezone.utc).date(); stamp = f"{today.isoformat()}T12:00:00Z"; compact = today.strftime("%Y%m%d")
    csv_header = "latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,frp\n"
    csv_row = f"48.4,2.7,{today.isoformat()},1200,N20,VIIRS,n,4.2\n"
    monkeypatch.setenv("FIRMS_MAP_KEY", "synthetic-test-key")
    monkeypatch.setattr(firms, "http_get", lambda url: (csv_header + csv_row).encode())

    rows = "\n".join(f"{stamp};{i:02d};1;2;Departement {i:02d}" for i in range(1, 81))
    dataset = {"resources": [{"format": "csv", "url": "fixture://meteo.csv", "last_modified": stamp}]}
    monkeypatch.setattr(meteo_forets, "http_get_json", lambda url: dataset)
    monkeypatch.setattr(meteo_forets, "http_get", lambda url: ("date;num_dep;niveau_j1;niveau_j2;nom_dep\n" + rows).encode())

    feature = {"type":"Feature","geometry":{"type":"Polygon","coordinates":[[[-4,39],[-3,39],[-3,40],[-4,39]]]},"properties":{"COD_Z":"SYN001","Nombre_zona":"Synthetische zone","N_avisos":"1","Avis_ATTA":"[{'severity': 'Amarillo', 'descripcion': 'Hoge temperatuur'}]"}}
    warning_tar = _tar({f"r_D+0_{today.strftime('%Y%m%d')}120000_penbal_{compact}CEST_fixture.geojson": json.dumps({"type":"FeatureCollection","features":[feature]}).encode()})
    monkeypatch.setattr(aemet_warnings, "http_get", lambda url: b'<a href="https://fixture.invalid/warnings.tar.gz">download</a>' if url == aemet_warnings.PAGE_URL else warning_tar)

    danger_tar = _tar({f"down_{compact}_peligro_p_D00.tif": b"synthetic-geotiff"})
    monkeypatch.setattr(aemet_danger, "http_get", lambda *args, **kwargs: danger_tar)
    monkeypatch.setattr(aemet_danger, "convert_geotiff", lambda name, data, sld: {"png": b"\x89PNG\r\n\x1a\nsynthetic", "meta": {"name":name,"bounds":{"west":-10,"south":35,"east":5,"north":44},"width":1,"height":1,"crs":"EPSG:4326","classes":{"1":{"color":"#4b96e3","label":"zeer laag"}}}})

    monkeypatch.setattr(effis_danger, "http_get", lambda url, **kwargs: b"synthetic-png")
    monkeypatch.setattr(effis_danger, "_validate_png", lambda data: None)

    activation = {"code":"EMSRTEST","name":"Synthetic wildfire","category":"Wildfire","centroid":"POINT (2.7 48.4)","activationTime":stamp,"drmPhase":"Response","closed":False,"n_products":1}
    monkeypatch.setattr(cems_rapid_mapping, "http_get_json", lambda url: {"results":[activation],"next":None})

    pla_meta={"geometryType":"esriGeometryPolygon","maxRecordCount":2000,"fields":[{"name":x} for x in pla_alfa.EXPECTED_FIELDS],"editingInfo":{"dataLastEditDate":1784249224000}}
    pla_features={"type":"FeatureCollection","features":[{"type":"Feature","geometry":{"type":"Polygon","coordinates":[[[1,41],[2,41],[2,42],[1,41]]]},"properties":{"CODIMUNI":f"{i:06d}","NOMMUNI":f"Municipi {i}","CODICOMAR":"01","NOMCOMAR":"Comarca","PERIL_M":2}} for i in range(947)]}
    monkeypatch.setattr(pla_alfa,"http_get",lambda url:json.dumps(pla_features if "/query?" in url else pla_meta).encode())

    irdi_page="<p>Actualizado o Xoves, 16 de Xullo de 2026 ás 09:48</p>"
    levels=["Baixo","Moderado","Alto","Moi Alto","Extremo"]
    irdi_table="<table class='table-irdi-table'>"+"".join(f"<tr><td class='views-field-field-zona'>Concello {i}</td><td class='views-field-field-p50'>{levels[i%5]}</td></tr>" for i in range(313))+"</table>"
    geometry={"type":"Polygon","coordinates":[[[-8,42],[-7,42],[-7,43],[-8,42]]]}
    monkeypatch.setattr(galicia_irdi,"_request",lambda *a,**k:irdi_page.encode())
    monkeypatch.setattr(galicia_irdi,"_post_view",lambda day,page:irdi_table if page==0 else "")
    monkeypatch.setattr(galicia_irdi,"load",lambda:{f"Concello {i}":(f"{i:05d}",geometry) for i in range(313)})
    monkeypatch.setattr(run, "DEPARTEMENTS_ASSET", tmp_path / "niet-aanwezig.geojson.gz")
    monkeypatch.setattr(meteoalarm_warnings, "http_get", lambda url, **kwargs: _EMPTY_ATOM)

    output = tmp_path / "public" / "data"
    assert run.main(["--output", str(output)]) == 0
    manifest = json.loads((output / "manifest.json").read_text())
    expected = {"firms","meteo_forets","aemet_warnings","aemet_danger","effis_danger","cems_rapid_mapping","pla_alfa","galicia_irdi"}
    expected |= {f"meteoalarm_{cc}" for cc in ("nl","be","lu","de","at","ch","it","fr")}
    assert set(manifest["sources"]) == expected
    assert all(entry["status"].startswith("ok") for entry in manifest["sources"].values())
    assert (output / "detections.latest.geojson.gz").exists()
    assert (output / "danger/es/aemet" / f"down_{compact}_peligro_p_D00.png").exists()
    assert (output / "danger/eu/effis.index.latest.geojson.gz").exists()
    assert (output / "danger/es/cat/pla-alfa.latest.geojson.gz").exists()
    assert (output / "danger/es/gal/irdi.latest.geojson.gz").exists()
    assert manifest["sources"]["galicia_irdi"]["coverage"]["municipalities_expected"] == 313
