from __future__ import annotations

import logging
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

PROJECT_ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
TARGET_EPSG = 32643
LABELS_REL = "data/04_labels/labels.geojson"

CLASS_DEFINITIONS = {
    1: "Active Crop",
    2: "Fallow / Bare Land",
    3: "Built-up / Roads",
    4: "Clean Water",
    5: "Turbid / Algal Water",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
log = logging.getLogger(__name__)


def create_label_template(root: Path) -> Path:
    """Create an empty GeoJSON polygon layer with enforced schema in EPSG:32643."""
    out_path = root / LABELS_REL
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Create empty GeoDataFrame with explicit column types
    df = pd.DataFrame({
        "class_id": pd.Series(dtype="int64"),
        "class_name": pd.Series(dtype="str"),
        "notes": pd.Series(dtype="str"),
    })
    gdf = gpd.GeoDataFrame(df, geometry=gpd.GeoSeries([], crs=f"EPSG:{TARGET_EPSG}"), crs=f"EPSG:{TARGET_EPSG}")

    gdf.to_file(out_path, driver="GeoJSON")
    log.info("✅  Created ground-truth label template at: %s", out_path)
    return out_path


def print_qgis_guide() -> None:
    """Print step-by-step instructions for digitizing polygons in QGIS."""
    print("\n" + "=" * 70)
    print("  QGIS DIGITIZATION GUIDE (KOTHRI KALAN – CROP & WATER QUALITY)")
    print("=" * 70)
    print("1. Open QGIS and load:")
    print("     • data/01_raw/S2_KothriKalan_Rabi_2026_10m.tif")
    print("     • data/04_labels/labels.geojson")
    print("\n2. Configure False-Color Composite on the Sentinel-2 raster:")
    print("     Right-click raster -> Properties -> Symbology -> Multiband Color:")
    print("       • Red band   = Band 7 (B08 - NIR)")
    print("       • Green band = Band 3 (B04 - Red)")
    print("       • Blue band  = Band 2 (B03 - Green)")
    print("     Visual key: Bright Red = Healthy Crops | Dark Blue/Black = Water")
    print("\n3. Digitize Polygons (Toggle Editing pencil icon on labels.geojson):")
    for cid, cname in CLASS_DEFINITIONS.items():
        print(f"     • class_id = {cid}  -->  {cname}")
    print("\n4. Aim for 25-40 polygons per class across the study area, then Save.")
    print("=" * 70 + "\n")


def main() -> None:
    log.info("=" * 60)
    log.info("Phase 1 – Label Template Setup  |  Root: %s", PROJECT_ROOT.resolve())
    log.info("=" * 60)
    create_label_template(PROJECT_ROOT.resolve())
    print_qgis_guide()


if __name__ == "__main__":
    main()