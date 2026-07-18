"""Bouw het vereenvoudigde officiële Xunta-asset met 313 gemeentegrenzen."""
from __future__ import annotations
import gzip,json
from pathlib import Path
from .common import http_get
from .geometry import simplify_geometry

SOURCE_URL="https://ideg.xunta.gal/servizos/rest/services/LimitesAdministrativos/LimitesAdministrativos/MapServer/16/query?where=1%3D1&outFields=CODCONC%2CCONCELLO%2CPROVINCIA&returnGeometry=true&outSR=4326&f=geojson"
ATTRIBUTION="Fonte: Instituto de Estudos do Territorio, Xunta de Galicia — CC BY-SA 4.0"
ASSET_PATH=Path(__file__).resolve().parent.parent/"assets"/"galicia-municipios.simplified.geojson.gz"

def build_asset(target=ASSET_PATH,tolerance=.002):
    source=json.loads(http_get(SOURCE_URL).decode()); features=[]
    if len(source.get("features",[])) != 313: raise ValueError("gemeentegrensbron bevat niet exact 313 gemeenten")
    for f in source["features"]:
        p=f.get("properties") or {}; code=str(p.get("CODCONC") or "").zfill(5); name=str(p.get("CONCELLO") or "").strip()
        if not code or not name: raise ValueError("gemeentegrens mist code of naam")
        features.append({"type":"Feature","geometry":simplify_geometry(f["geometry"],tolerance),"properties":{"municipality_code":code,"name":name}})
    data=json.dumps({"type":"FeatureCollection","features":features},ensure_ascii=False,separators=(",",":")).encode(); target=Path(target); target.parent.mkdir(parents=True,exist_ok=True); target.write_bytes(gzip.compress(data,mtime=0)); return {"features":len(features),"bytes":target.stat().st_size,"source_url":SOURCE_URL}

def load(path=ASSET_PATH):
    data=json.loads(gzip.decompress(Path(path).read_bytes())); return {f["properties"]["name"]:(f["properties"]["municipality_code"],f["geometry"]) for f in data["features"]}

if __name__=="__main__": print(json.dumps(build_asset(),indent=2))
