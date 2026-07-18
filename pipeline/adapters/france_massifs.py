"""Voorwerk Franse massieven; bewust niet opgenomen in de publicatierunner.

Niveaucodes worden uitsluitend via DEPARTMENTS per departement geïnterpreteerd.
Een onbekende code wordt nooit generiek omgerekend en is `publishable=False`.
"""
from __future__ import annotations
import json
from datetime import datetime,time,timezone
from ..common import SourceResult,http_get,iso,utcnow
from ..schema import make_record

ATTRIBUTION="Source : Préfectures / Entente Valabre / Météo-France — risque-prevention-incendie.fr"
BASE="https://www.risque-prevention-incendie.fr"
UNKNOWN="Onbekend voor dit departement — niet tonen"
SUPPORTED=("04","06","07","11","13","17","20","26","30","34","42","66","81","83","84")

def _unknown(dep): return {"name":dep,"decision_url":f"{BASE}/{dep}/","levels":{},"note":UNKNOWN}
DEPARTMENTS={dep:_unknown(dep) for dep in SUPPORTED}
DEPARTMENTS.update({
 "13":{"name":"Bouches-du-Rhône","decision_url":f"{BASE}/13/","levels":{1:"Toegang toegestaan",2:"Toegang toegestaan",3:"Toegang verboden",4:"Toegang verboden"},"note":"Lokale uitzonderingen staan in het prefecturale besluit."},
 "66":{"name":"Pyrénées-Orientales","decision_url":f"{BASE}/66/","levels":{3:"Toegang verboden"},"note":"Niveaus 1 en 2 nog niet juridisch vastgelegd in deze adapter."},
 "83":{"name":"Var","decision_url":f"{BASE}/83/","levels":{3:"Toegang wordt afgeraden",4:"Toegang verboden buiten de in het prefecturale besluit genoemde uitzonderingsgebieden",5:"Toegang volledig verboden"},"note":"Niveaus 1 en 2 nog niet juridisch vastgelegd in deze adapter."},
})

def fetch(day=None):
    day=day or utcnow().date(); fetched=iso(utcnow()); result=SourceResult(source="france_massifs",attribution=ATTRIBUTION,source_url=BASE,coverage={"countries":["FR"],"departments":list(SUPPORTED),"kind":"measure","publication_enabled":False,"reason":"betekenis niveaucodes en geometrie nog niet voor ieder departement vastgesteld"});records=[];failures=[]
    for dep in SUPPORTED:
        url=f"{BASE}/static/{dep}/import_data/{day:%Y%m%d}.json"
        try: payload=json.loads(http_get(url).decode())
        except Exception as exc: failures.append(f"{dep}: {exc}");continue
        massifs=payload.get("massifs") if isinstance(payload,dict) else None
        if not isinstance(massifs,dict) or not massifs: failures.append(f"{dep}: massifs-schema ontbreekt");continue
        config=DEPARTMENTS[dep]
        for massif_id,value in massifs.items():
            if not isinstance(value,list) or not value: failures.append(f"{dep}/{massif_id}: ongeldige niveauwaarde");continue
            try:level=int(value[0])
            except (TypeError,ValueError): failures.append(f"{dep}/{massif_id}: niet-numeriek niveau");continue
            meaning=config["levels"].get(level,UNKNOWN);publishable=level in config["levels"]
            records.append(make_record(id=f"fr-massif-{day.isoformat()}-{dep}-{massif_id}",source_id=str(massif_id),kind="measure",authority=f"Préfecture {config['name']}",source_url=config["decision_url"],geometry=None,area_text=f"Massif {massif_id} — département {dep}",severity_source=f"niveau {level} (codering département {dep})",certainty="official_daily_measure",valid_from=iso(datetime.combine(day,time.min,tzinfo=timezone.utc)),valid_to=iso(datetime.combine(day,time.max,tzinfo=timezone.utc)),fetched_at=fetched,expires_policy="hide_after_valid_to",restrictions_text=meaning,attribution=ATTRIBUTION,raw_payload_ref=f"france_massifs:{dep}:{day:%Y%m%d}:{massif_id}",source_attrs={"department":dep,"massif_id":str(massif_id),"level_code":level,"publishable":publishable,"decision_url":config["decision_url"]}))
    result.records=records;result.source_updated_at=f"{day.isoformat()}T00:00:00Z";result.valid_until=iso(datetime.combine(day,time.max,tzinfo=timezone.utc));result.notes=["Voorwerk-ingest; niet publiceren zonder geometrie en complete departementale betekenistabel",*failures];result.status="ok" if records else "failed";result.error=None if records else "geen departementale data beschikbaar";return result
