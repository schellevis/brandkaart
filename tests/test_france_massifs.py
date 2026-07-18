import json
from datetime import date
from pipeline.adapters import france_massifs

def test_alle_vijftien_departementen_expliciet_geconfigureerd():
    assert set(france_massifs.DEPARTMENTS)==set(france_massifs.SUPPORTED); assert len(france_massifs.SUPPORTED)==15
    for config in france_massifs.DEPARTMENTS.values(): assert config["decision_url"] and "levels" in config

def test_geen_generieke_niveaumapping(monkeypatch):
    monkeypatch.setattr(france_massifs,"http_get",lambda url:json.dumps({"massifs":{"x":[3,0]}}).encode())
    result=france_massifs.fetch(date(2026,7,17)); assert result.status=="ok"; assert len(result.records)==15
    by_dep={r["source_attrs"]["department"]:r for r in result.records}
    assert by_dep["13"]["restrictions_text"]=="Toegang verboden"; assert by_dep["13"]["source_attrs"]["publishable"] is True
    assert by_dep["11"]["restrictions_text"]==france_massifs.UNKNOWN; assert by_dep["11"]["source_attrs"]["publishable"] is False
    assert by_dep["83"]["restrictions_text"]=="Toegang wordt afgeraden"

def test_schema_afwijking_wordt_geen_nulmeting(monkeypatch):
    monkeypatch.setattr(france_massifs,"http_get",lambda url:b'{}'); result=france_massifs.fetch(date(2026,7,17)); assert result.status=="failed"; assert result.records==[]
