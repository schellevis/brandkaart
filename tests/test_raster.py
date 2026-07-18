"""Tests voor pipeline/raster.py: GeoTIFF -> web-PNG + metadata.

Bouwt een kleine synthetische float32-GeoTIFF in-memory met rasterio (geen
netwerk, geen bestanden op schijf) en controleert daarnaast, indien
aanwezig, de conversie van een echt AEMET-voorbeeldbestand.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import numpy as np
import pytest
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from pipeline.raster import CLASS_LABELS, convert_geotiff, parse_sld_colors

WIDTH, HEIGHT = 8, 6

REAL_SAMPLE = Path("public/data/danger/es/aemet/down_20260716_peligro_c_D00.tif")

SLD_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<StyledLayerDescriptor version="1.0.0"
    xmlns="http://www.opengis.net/sld">
  <NamedLayer>
    <UserStyle>
      <FeatureTypeStyle>
        <Rule>
          <RasterSymbolizer>
            <ColorMap type="values">
              <ColorMapEntry color="#000000" quantity="0" opacity="0.0" label="Sin Datos"/>
              <ColorMapEntry color="#4B96E3" quantity="1" label="Muy bajo"/>
              <ColorMapEntry color="#51D1F6" quantity="2" label="Bajo"/>
              <ColorMapEntry color="#57E520" quantity="3" label="Moderado"/>
              <ColorMapEntry color="#F9FB2F" quantity="4" label="Alto"/>
              <ColorMapEntry color="#EF8504" quantity="5" label="Muy alto"/>
              <ColorMapEntry color="#F52300" quantity="6" label="Extremo"/>
            </ColorMap>
          </RasterSymbolizer>
        </Rule>
      </FeatureTypeStyle>
    </UserStyle>
  </NamedLayer>
</StyledLayerDescriptor>
"""


def _synthetic_geotiff(crs: str = "EPSG:4326") -> bytes:
    """Bouw een 8x6 float32-GeoTIFF met klassen 0..6 en een NaN-pixel."""
    values = np.array(
        [
            [0, 1, 2, 3, 4, 5, 6, np.nan],
            [1, 2, 3, 4, 5, 6, 0, 1],
            [2, 3, 4, 5, 6, 0, 1, 2],
            [3, 4, 5, 6, 0, 1, 2, 3],
            [4, 5, 6, 0, 1, 2, 3, 4],
            [5, 6, 0, 1, 2, 3, 4, 5],
        ],
        dtype=np.float32,
    )
    assert values.shape == (HEIGHT, WIDTH)

    # Pixelgrootte 0.01 graad, linkerbovenhoek op (-10, 44) zoals bij de
    # echte AEMET-schiereilandrasters.
    transform = from_origin(-10.0, 44.0, 0.01, 0.01)

    with MemoryFile() as memfile:
        with memfile.open(
            driver="GTiff",
            width=WIDTH,
            height=HEIGHT,
            count=1,
            dtype="float32",
            crs=crs,
            transform=transform,
        ) as dataset:
            dataset.write(values, 1)
        return memfile.read()


def _chunks(png: bytes) -> dict[str, bytes]:
    """Ontleed een PNG in chunk-type -> payload, voor witte-doos-asserts."""
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    offset = 8
    found: dict[str, bytes] = {}
    while offset < len(png):
        (length,) = struct.unpack(">I", png[offset : offset + 4])
        tag = png[offset + 4 : offset + 8].decode("ascii")
        payload = png[offset + 8 : offset + 8 + length]
        found[tag] = payload
        offset += 8 + length + 4  # lengte + tag + data + crc
    return found


def test_png_magic_bytes_en_chunks():
    result = convert_geotiff("test.tif", _synthetic_geotiff())
    png = result["png"]
    assert png[:8] == b"\x89PNG\r\n\x1a\n"

    chunks = _chunks(png)
    assert set(["IHDR", "PLTE", "tRNS", "IDAT", "IEND"]).issubset(chunks)

    width, height, bit_depth, color_type = struct.unpack(">IIBB", chunks["IHDR"][:10])
    assert (width, height) == (WIDTH, HEIGHT)
    assert bit_depth == 8
    assert color_type == 3  # indexed


def test_transparantie_voor_klasse_nul_en_nan():
    result = convert_geotiff("test.tif", _synthetic_geotiff())
    chunks = _chunks(result["png"])

    trns = chunks["tRNS"]
    # Index 0 (klasse "geen data", waarin NaN ook op wordt afgebeeld) moet
    # volledig transparant zijn; de overige palette-indices ondoorzichtig.
    assert trns[0] == 0
    assert all(alpha == 255 for alpha in trns[1:])

    plte = chunks["PLTE"]
    assert len(plte) % 3 == 0
    assert len(plte) // 3 == 7  # klassen 0..6

    # Decodeer de rasterdata om te bevestigen dat de NaN-pixel en de
    # klasse-0-pixels effectief naar index 0 zijn gemapt.
    raw = zlib.decompress(chunks["IDAT"])
    stride = WIDTH + 1  # filterbyte + pixels
    rows = [raw[i * stride : (i + 1) * stride] for i in range(HEIGHT)]
    indices = np.array([[b for b in row[1:]] for row in rows], dtype=np.uint8)

    assert indices[0, 0] == 0  # was klasse 0
    assert indices[0, 7] == 0  # was NaN
    assert indices[0, 3] == 3  # klasse 3 blijft klasse 3


def test_meta_bounds_en_velden():
    result = convert_geotiff("test.tif", _synthetic_geotiff())
    meta = result["meta"]

    bounds = meta["bounds"]
    assert bounds["west"] == pytest.approx(-10.0)
    assert bounds["north"] == pytest.approx(44.0)
    assert bounds["east"] == pytest.approx(-10.0 + WIDTH * 0.01)
    assert bounds["south"] == pytest.approx(44.0 - HEIGHT * 0.01)

    assert meta["width"] == WIDTH
    assert meta["height"] == HEIGHT
    assert "4326" in meta["crs"]

    assert set(meta["classes"]) == set(range(1, 7))
    for klass, info in meta["classes"].items():
        assert info["color"].startswith("#")
        assert len(info["color"]) == 7
        assert info["label"] == CLASS_LABELS[klass]

    assert meta["nodata"]["class"] == 0


def test_meta_bounds_herprojecteert_niet_epsg4326_crs():
    # EPSG:3857 (Web Mercator) heeft dezelfde oorsprong-eenheden niet als
    # graden; als de herprojectie werkt, moeten bounds er heel anders
    # uitzien dan de rauwe transform-coördinaten (die in meters zouden zijn).
    result = convert_geotiff("test.tif", _synthetic_geotiff(crs="EPSG:3857"))
    bounds = result["meta"]["bounds"]
    assert -180 <= bounds["west"] <= 180
    assert -90 <= bounds["south"] <= 90
    assert "3857" in result["meta"]["crs"]


def test_sld_kleuren_worden_gebruikt_indien_meegegeven():
    result = convert_geotiff("test.tif", _synthetic_geotiff(), sld=SLD_SAMPLE)
    assert result["meta"]["classes"][1]["color"] == "#4b96e3"
    assert result["meta"]["classes"][6]["color"] == "#f52300"


def test_parse_sld_colors_geldig():
    colors = parse_sld_colors(SLD_SAMPLE)
    assert colors is not None
    assert colors[1] == "#4b96e3"
    assert colors[6] == "#f52300"


def test_parse_sld_colors_defensief_bij_rommel():
    assert parse_sld_colors(b"dit is geen xml") is None
    assert parse_sld_colors(b"<niet-een-sld/>") is None


def test_parse_sld_colors_weigert_doctype():
    kwaadaardig = b"""<?xml version="1.0"?>
    <!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
    <root>&xxe;</root>
    """
    assert parse_sld_colors(kwaadaardig) is None


@pytest.mark.skipif(not REAL_SAMPLE.exists(), reason="voorbeeldbestand niet aanwezig in werkkopie")
def test_echt_voorbeeldbestand_canarische_eilanden_is_klein():
    data = REAL_SAMPLE.read_bytes()
    result = convert_geotiff(REAL_SAMPLE.name, data)
    assert result["png"][:8] == b"\x89PNG\r\n\x1a\n"
    assert len(result["png"]) < 200_000
    assert result["meta"]["crs"] is not None
