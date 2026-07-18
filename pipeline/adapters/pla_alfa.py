"""Pla Alfa: gemeentelijk gevaar in Catalonië voor vandaag en morgen.

Dit is een gevaarlaag (`danger/es/cat/`), geen maatregelenlaag: PERIL_M is
een bronrisiconiveau en bevat op zichzelf geen juridisch toegangsverbod.
"""
from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone
from urllib.parse import urlencode

from ..common import SourceResult, http_get, iso, utcnow
from ..schema import make_record

SOURCE_URL = "https://interior.gencat.cat/es/serveis/informacio-geografica/visors-i-aplicacions/pla-alfa/"
ATTRIBUTION = "Font: Generalitat de Catalunya. Departament d'Interior i Seguretat Pública (Pla Alfa)"
LAYERS = (
    (0, "https://services7.arcgis.com/ZCqVt1fRXwwK6GF4/arcgis/rest/services/Pla_Alfa_Municipal_Avui_FL_2_view/FeatureServer/0"),
    (1, "https://services7.arcgis.com/ZCqVt1fRXwwK6GF4/arcgis/rest/services/pla_alfa_municipal_dema_FL_VW/FeatureServer/5"),
)
EXPECTED_FIELDS = {"CODIMUNI", "NOMMUNI", "CODICOMAR", "NOMCOMAR", "PERIL_M"}
MIN_MUNICIPALITIES, MAX_MUNICIPALITIES = 900, 1000
LEVELS = {0: "nivell 0", 1: "nivell 1", 2: "nivell 2", 3: "nivell 3", 4: "nivell 4"}

def fetch() -> SourceResult:
    result = SourceResult(source="pla_alfa", attribution=ATTRIBUTION, source_url=SOURCE_URL,
        coverage={"countries":["ES"],"regions":["Catalonië"],"municipalities_expected":947,"days":[0,1],"kind":"danger","complete_within_region":True})
    fetched_at = iso(utcnow()); records=[]; newest=None; seen=set(); today=utcnow().date()
    try:
        for offset, base in LAYERS:
            metadata = json.loads(http_get(base + "?f=json").decode())
            _validate_metadata(metadata)
            query = base + "/query?" + urlencode({"where":"1=1","outFields":"CODIMUNI,NOMMUNI,CODICOMAR,NOMCOMAR,PERIL_M","returnGeometry":"true","outSR":"4326","f":"geojson"})
            collection = json.loads(http_get(query).decode())
            features = _validate_collection(collection)
            edit_ms = (metadata.get("editingInfo") or {}).get("dataLastEditDate")
            if edit_ms:
                updated = datetime.fromtimestamp(edit_ms/1000, timezone.utc)
                if newest is None or updated > newest: newest=updated
            target=today+timedelta(days=offset)
            for feature in features:
                props=feature["properties"]; code=str(props["CODIMUNI"]).strip(); key=(offset,code)
                if key in seen: continue
                seen.add(key); level=int(props["PERIL_M"])
                records.append(make_record(id=f"pla-alfa-{target.isoformat()}-{code}",source_id=code,kind="danger",authority="Generalitat de Catalunya — Pla Alfa",source_url=SOURCE_URL,geometry=feature["geometry"],area_text=str(props["NOMMUNI"]).strip(),severity_source=LEVELS[level],severity_normalized=level,certainty="official_danger_level",issued_at=iso(newest),valid_from=iso(datetime.combine(target,time.min,tzinfo=timezone.utc)),valid_to=iso(datetime.combine(target,time.max,tzinfo=timezone.utc)),fetched_at=fetched_at,expires_policy="hide_after_valid_to",attribution=ATTRIBUTION,raw_payload_ref=f"pla_alfa:d{offset}:{code}",source_attrs={"municipality_code":code,"comarca_code":str(props["CODICOMAR"]).strip(),"comarca":str(props["NOMCOMAR"]).strip(),"day_offset":offset}))
    except Exception as exc: return result.fail(f"schema/plausibiliteit Pla Alfa: {exc}")
    result.records=records; result.source_updated_at=iso(newest); result.valid_until=iso(datetime.combine(today+timedelta(days=1),time.max,tzinfo=timezone.utc)); result.status="ok"; return result

def _validate_metadata(meta):
    fields={f.get("name") for f in meta.get("fields",[])}
    if meta.get("geometryType") != "esriGeometryPolygon" or not EXPECTED_FIELDS <= fields: raise ValueError("onverwacht FeatureServer-schema")
    if int(meta.get("maxRecordCount") or 0) < MAX_MUNICIPALITIES: raise ValueError("recordlimiet te laag voor volledige dekking")

def _validate_collection(collection):
    if collection.get("type") != "FeatureCollection" or collection.get("exceededTransferLimit"): raise ValueError("onvolledige GeoJSON-response")
    features=collection.get("features") or []
    if not MIN_MUNICIPALITIES <= len(features) <= MAX_MUNICIPALITIES: raise ValueError(f"{len(features)} gemeenten, verwacht circa 947")
    codes=set()
    for f in features:
        p=f.get("properties") or {}; missing=EXPECTED_FIELDS-set(p)
        if missing or not f.get("geometry"): raise ValueError(f"feature mist velden/geometrie: {sorted(missing)}")
        try: level=int(p["PERIL_M"])
        except (TypeError,ValueError): raise ValueError("PERIL_M is niet numeriek") from None
        if level not in LEVELS: raise ValueError(f"onbekend PERIL_M-niveau {level}")
        code=str(p["CODIMUNI"]).strip()
        if not code or code in codes: raise ValueError("lege of dubbele gemeentecode")
        codes.add(code)
    return features
