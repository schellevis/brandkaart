"""AEMET-brandgevaar: GeoTIFF-rasters omzetten naar compacte web-PNG's.

De AEMET-tarball bevat per dag en
gebied een ongecomprimeerde float32-GeoTIFF van enkele MB. Die volledige
raster in het statische artefact meenemen is te duur. Dit module rendert de
klassen (0..6) daarom naar een klein indexed-palette PNG (7 kleuren, met
transparantie voor "geen data") plus een metadatarecord met de geografische
bounds en de gebruikte legenda. De frontend rekt het PNG vervolgens over die
bounds uit.

Bewuste vereenvoudiging: alleen de vier hoekcoördinaten van het raster worden
naar EPSG:4326 herprojecteerd (indien nodig); de pixels zelf blijven in het
oorspronkelijke grid staan. Voor de AEMET-brongegevens is dit onschadelijk
omdat ze al in EPSG:4326 worden aangeleverd (zelf geverifieerd op de
voorbeeldbestanden), maar bij een bron met een sterk vervormende projectie
(bijv. een lokale UTM-zone met een niet-rechthoekig raster) zou dit de kaart
lichtjes laten "schuiven" doordat een gereprojecteerde bounding box niet meer
precies overeenkomt met een simpele rechthoekige pixelrek. Voor dit MVP is
dat een acceptabele afweging tegen het alternatief (volledige reprojectie
met resampling, wat extra dependencies en rekentijd kost).
"""

from __future__ import annotations

import struct
import zlib
import defusedxml.ElementTree as ET

import numpy as np
from rasterio.crs import CRS
from rasterio.io import MemoryFile
from rasterio.warp import transform_bounds

# Nederlandse klasselabels voor de AEMET-rasterklassen.
# ("0 geen data, 1 zeer laag, 2 laag, 3 matig, 4 hoog, 5 zeer hoog, 6 extreem").
CLASS_LABELS: dict[int, str] = {
    0: "geen data",
    1: "zeer laag",
    2: "laag",
    3: "matig",
    4: "hoog",
    5: "zeer hoog",
    6: "extreem",
}

# Fallback-legenda voor klassen 1..6, gebruikt wanneer geen (bruikbare) SLD is
# meegegeven. Kleuren zijn 1-op-1 overgenomen uit een echt AEMET-SLD-bestand
# (down_20260716_peligro_p_D00.sld, zelf gedownload op 17 juli 2026 via
# https://www.aemet.es/es/api-eltiempo/incendios/download) en zijn dus geen
# eigen benadering maar de officiële AEMET-kleuren op de peildatum.
FALLBACK_COLORS: dict[int, str] = {
    1: "#4b96e3",  # zeer laag
    2: "#51d1f6",  # laag
    3: "#57e520",  # matig
    4: "#f9fb2f",  # hoog
    5: "#ef8504",  # zeer hoog
    6: "#f52300",  # extreem
}

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_COLOR_TYPE_INDEXED = 3


def convert_geotiff(name: str, data: bytes, sld: bytes | None = None) -> dict:
    """Zet één AEMET-GeoTIFF om naar een web-PNG plus metadata.

    Retourneert {"png": bytes, "meta": dict} waarbij meta bevat: bounds
    (west/south/east/north in EPSG:4326), width, height, crs (origineel,
    als string), classes (mapping klasse 1..6 -> {"color": "#rrggbb",
    "label": str}) en nodata (afhandeling van klasse 0 / NaN).

    `data` is de ruwe GeoTIFF-bytes; `sld` is de optionele bijbehorende
    SLD-stijl uit dezelfde AEMET-tarball. Als die aanwezig en bruikbaar is,
    worden de klassekleuren daaruit gehaald; anders geldt FALLBACK_COLORS.
    """
    with MemoryFile(data) as memfile, memfile.open() as dataset:
        band = dataset.read(1).astype(np.float64)
        crs = dataset.crs
        transform = dataset.transform  # noqa: F841 -- bewust niet gebruikt, zie moduledocstring
        width = dataset.width
        height = dataset.height
        nodata = dataset.nodata
        bounds = dataset.bounds

    nodata_mask = np.isnan(band)
    if nodata is not None and not np.isnan(nodata):
        nodata_mask |= band == nodata

    classes = np.rint(np.where(nodata_mask, 0.0, band)).astype(np.int16)
    classes = np.clip(classes, 0, 6)
    classes[nodata_mask] = 0
    classes[band == 0] = 0

    sld_colors = parse_sld_colors(sld) if sld else None
    palette_hex: dict[int, str] = dict(FALLBACK_COLORS)
    if sld_colors:
        palette_hex.update({k: v for k, v in sld_colors.items() if 1 <= k <= 6})

    png_bytes = _encode_indexed_png(classes.astype(np.uint8), palette_hex)

    west, south, east, north = _bounds_to_wgs84(bounds, crs)

    meta = {
        "name": name,
        "bounds": {"west": west, "south": south, "east": east, "north": north},
        "width": width,
        "height": height,
        "crs": crs.to_string() if crs else None,
        "classes": {
            klass: {"color": palette_hex[klass], "label": CLASS_LABELS[klass]}
            for klass in range(1, 7)
        },
        "nodata": {
            # Klasse 0 en NaN-pixels worden identiek behandeld: volledig
            # transparant via de tRNS-chunk van het PNG (alpha 0 op index 0).
            "class": 0,
            "label": CLASS_LABELS[0],
            "source_value": None if nodata is None else float(nodata),
            "handling": "klasse 0 en NaN-pixels zijn volledig transparant (index 0, alpha 0)",
        },
    }

    return {"png": png_bytes, "meta": meta}


def parse_sld_colors(sld: bytes) -> dict[int, str] | None:
    """Haal klasse -> kleur (``#rrggbb``) uit een AEMET SLD-stijlbestand.

    AEMET-SLD's bevatten een ``<ColorMap type="values">`` met per klasse een
    ``<ColorMapEntry color="#RRGGBB" quantity="N" .../>``. Deze functie is
    defensief: bij onparseerbare XML, een ontbrekende/lege ColorMap of
    ongeldige kleurwaarden wordt None geretourneerd zodat de aanroeper op de
    fallback-legenda kan terugvallen.

    Veiligheid: SLD's komen van een externe bron en worden daarom uitsluitend
    met defusedxml verwerkt.
    """
    try:
        root = ET.fromstring(sld)
    except Exception:  # noqa: BLE001 — onleesbare of vijandige XML geeft fallback
        return None

    colors: dict[int, str] = {}
    for entry in root.iter():
        # Namespace-onafhankelijk matchen: SLD gebruikt doorgaans de
        # standaard-namespace, maar we willen niet breken op varianten.
        tag = entry.tag.rsplit("}", 1)[-1]
        if tag != "ColorMapEntry":
            continue
        quantity_raw = entry.get("quantity")
        color_raw = entry.get("color")
        if quantity_raw is None or color_raw is None:
            continue
        try:
            klass = int(float(quantity_raw))
        except ValueError:
            continue
        color = color_raw.strip().lower()
        if len(color) != 7 or not color.startswith("#"):
            continue
        try:
            int(color[1:], 16)
        except ValueError:
            continue
        colors[klass] = color

    return colors or None


def _bounds_to_wgs84(bounds, crs) -> tuple[float, float, float, float]:
    """Herprojecteer alleen de hoekcoördinaten van bounds naar EPSG:4326.

    Zie moduledocstring voor de beperkingen van deze aanpak (pixels zelf
    worden niet herprojecteerd).
    """
    if crs is None or crs == CRS.from_epsg(4326):
        return bounds.left, bounds.bottom, bounds.right, bounds.top
    return transform_bounds(crs, CRS.from_epsg(4326), bounds.left, bounds.bottom, bounds.right, bounds.top)


def _encode_indexed_png(classes: np.ndarray, palette_hex: dict[int, str]) -> bytes:
    """Schrijf een indexed-palette PNG (PLTE + tRNS) zonder Pillow.

    `classes` bevat per pixel een waarde 0..6 (uint8); index 0 is altijd
    volledig transparant, klassen 1..6 krijgen hun legendakleur.
    """
    height, width = classes.shape

    palette = [(0, 0, 0)]  # index 0: kleur is irrelevant, alpha is 0
    alpha = [0]
    for klass in range(1, 7):
        palette.append(_hex_to_rgb(palette_hex[klass]))
        alpha.append(255)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, _COLOR_TYPE_INDEXED, 0, 0, 0)
    plte = b"".join(struct.pack(">BBB", r, g, b) for r, g, b in palette)
    trns = bytes(alpha)

    # Elke scanline krijgt filterbyte 0 (geen filter) gevolgd door 1 byte per
    # pixel (de palette-index). Dat houdt de encoder simpel; zlib comprimeert
    # de herhaling in de rasterdata daarna prima.
    scanlines = np.zeros((height, width + 1), dtype=np.uint8)
    scanlines[:, 1:] = classes
    idat = zlib.compress(scanlines.tobytes(), level=9)

    return _PNG_SIGNATURE + b"".join(
        [
            _png_chunk(b"IHDR", ihdr),
            _png_chunk(b"PLTE", plte),
            _png_chunk(b"tRNS", trns),
            _png_chunk(b"IDAT", idat),
            _png_chunk(b"IEND", b""),
        ]
    )


def _png_chunk(tag: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload))


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
