from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import geopandas as gpd
from pyproj import Transformer
from shapely.geometry import box, mapping

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent

# Centre of the study area (WGS 84)
CENTRE_LAT = 23.07
CENTRE_LON = 76.85

# Half-widths in degrees (≈0.1° ≈ 11 km → ~20 km envelope)
HALF_DEG_LAT = 0.10
HALF_DEG_LON = 0.10

# Target CRS
TARGET_EPSG = 32643

# Canonical sub-directories (Phase 1 relevant)
DIRECTORIES = [
    "data/01_raw",
    "data/02_interim",
    "data/03_composites",
    "data/04_labels",
    "data/05_patches",
    "notebooks",
    "scripts",
    "models",
    "outputs",
    "docs",
]

STUDY_AREA_PATH = "data/01_raw/study_area.geojson"

# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
log = logging.getLogger(__name__)


def create_directories(root: Path) -> None:
    """Create the project directory tree."""
    for d in DIRECTORIES:
        p = root / d
        p.mkdir(parents=True, exist_ok=True)
        log.info("DIR  %s", p)


def build_study_area_geojson(root: Path) -> Path:
    """
    Build a bounding-box polygon around Kothri Kalan, reproject to UTM 43N,
    and save as GeoJSON.
    """
    # 1. Build bounding box in geographic coords
    minx = CENTRE_LON - HALF_DEG_LON
    miny = CENTRE_LAT - HALF_DEG_LAT
    maxx = CENTRE_LON + HALF_DEG_LON
    maxy = CENTRE_LAT + HALF_DEG_LAT

    bbox_wgs84 = box(minx, miny, maxx, maxy)
    log.info("WGS 84 bounding box: %s", bbox_wgs84.bounds)

    gdf = gpd.GeoDataFrame(
        {
            "name": ["Kothri Kalan Study Area"],
            "description": [
                "~20 km × 20 km bounding polygon centred on Kothri Kalan, "
                "Sehore District, Madhya Pradesh, India.  Covers surrounding "
                "agricultural fields and Parvati/Kolar catchment water bodies."
            ],
            "centre_lat": [CENTRE_LAT],
            "centre_lon": [CENTRE_LON],
        },
        geometry=[bbox_wgs84],
        crs="EPSG:4326",
    )

    # 2. Reproject to target CRS
    gdf_utm = gdf.to_crs(epsg=TARGET_EPSG)
    log.info(
        "UTM 43N bounding box (m): %s",
        tuple(round(c, 2) for c in gdf_utm.total_bounds),
    )

    # 3. Compute approximate dimensions in metres
    bounds = gdf_utm.total_bounds
    width_m = bounds[2] - bounds[0]
    height_m = bounds[3] - bounds[1]
    log.info("Study area size: %.1f m × %.1f m (%.1f km × %.1f km)",
             width_m, height_m, width_m / 1000, height_m / 1000)

    # 4. Write GeoJSON
    out_path = root / STUDY_AREA_PATH
    gdf_utm.to_file(out_path, driver="GeoJSON")
    log.info("GEOJSON  %s", out_path)

    return out_path


def main() -> None:
    log.info("=" * 60)
    log.info("Phase 1 – Project Setup  |  Root: %s", PROJECT_ROOT)
    log.info("=" * 60)

    create_directories(PROJECT_ROOT)
    geojson_path = build_study_area_geojson(PROJECT_ROOT)

    # Pretty-print for verification
    with open(geojson_path) as f:
        geojson = json.load(f)
    log.info("Study-area GeoJSON preview:\n%s", json.dumps(geojson, indent=2)[:800])

    log.info("✅  Project setup complete.")


if __name__ == "__main__":
    main()
