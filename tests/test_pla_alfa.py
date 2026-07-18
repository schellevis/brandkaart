import json
from pipeline.adapters import pla_alfa

def _metadata(): return {"geometryType":"esriGeometryPolygon","maxRecordCount":2000,"fields":[{"name":x} for x in pla_alfa.EXPECTED_FIELDS],"editingInfo":{"dataLastEditDate":1784249224000}}
def _collection(level=2,count=947): return {"type":"FeatureCollection","features":[{"type":"Feature","geometry":{"type":"Polygon","coordinates":[[[1,41],[2,41],[2,42],[1,41]]]},"properties":{"CODIMUNI":f"{i:06d}","NOMMUNI":f"Municipi {i}","CODICOMAR":"01","NOMCOMAR":"Comarca","PERIL_M":level}} for i in range(count)]}

def test_fetch_twee_dagen(monkeypatch):
    def get(url): return json.dumps(_collection() if "/query?" in url else _metadata()).encode()
    monkeypatch.setattr(pla_alfa,"http_get",get); result=pla_alfa.fetch()
    assert result.status=="ok"; assert len(result.records)==1894; assert result.records[0]["kind"]=="danger"; assert result.coverage["regions"]==["Catalonië"]

def test_niveau_buiten_contract_is_bronstoring(monkeypatch):
    monkeypatch.setattr(pla_alfa,"http_get",lambda url: json.dumps(_collection(5) if "/query?" in url else _metadata()).encode())
    result=pla_alfa.fetch(); assert result.status=="failed"; assert "niveau 5" in result.error

def test_onvolledige_response_is_geen_nulmeting():
    try: pla_alfa._validate_collection(_collection(count=20))
    except ValueError as exc: assert "verwacht circa 947" in str(exc)
    else: raise AssertionError("onvolledige bron werd geaccepteerd")
