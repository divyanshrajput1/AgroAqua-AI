from __future__ import annotations

import datetime
import logging
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio

PROJECT_ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent

RASTER_REL = "data/01_raw/S2_KothriKalan_Rabi_2026_10m.tif"
LABELS_REL = "data/04_labels/labels.geojson"
METADATA_REL = "data/01_raw/metadata.txt"

EXPECTED_BANDS = 9
EXPECTED_EPSG = 32643
EXPECTED_RES = 10.0  # metres
BAND_NAMES = ["B02", "B03", "B04", "B05", "B06", "B07", "B08", "B11", "B12"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
log = logging.getLogger(__name__)


class ValidationResult:
    """Collects pass/fail checks."""

    def __init__(self):
        self.checks: list[dict] = []

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        status = "PASS" if passed else "FAIL"
        self.checks.append({"name": name, "status": status, "detail": detail})
        level = logging.INFO if passed else logging.ERROR
        log.log(level, "  [%s]  %s  %s", status, name, detail)

    @property
    def all_passed(self) -> bool:
        return all(c["status"] == "PASS" for c in self.checks)


def verify_raster(root: Path, vr: ValidationResult) -> dict:
    """Validate the stacked GeoTIFF and return metadata dict."""
    raster_path = root / RASTER_REL
    meta: dict = {}

    if not raster_path.exists():
        vr.add("Raster file exists", False, str(raster_path))
        return meta
    vr.add("Raster file exists", True, str(raster_path))

    with rasterio.open(raster_path) as src:
        vr.add("Band count",
               src.count == EXPECTED_BANDS,
               f"got {src.count}, expected {EXPECTED_BANDS}")

        epsg = src.crs.to_epsg() if src.crs else None
        vr.add("CRS (EPSG)",
               epsg == EXPECTED_EPSG,
               f"got EPSG:{epsg}, expected EPSG:{EXPECTED_EPSG}")

        res_x, res_y = abs(src.res[0]), abs(src.res[1])
        res_ok = (abs(res_x - EXPECTED_RES) < 0.5) and (abs(res_y - EXPECTED_RES) < 0.5)
        vr.add("Pixel resolution",
               res_ok,
               f"got {res_x:.2f} m x {res_y:.2f} m, expected {EXPECTED_RES} m")

        vr.add("Data type",
               src.dtypes[0] == "float32",
               f"got {src.dtypes[0]}, expected float32")

        total_pixels = src.width * src.height
        nan_percents = []
        value_ranges = []
        for i in range(1, src.count + 1):
            data = src.read(i)
            nan_count = int(np.isnan(data).sum())
            nan_pct = 100.0 * nan_count / total_pixels
            nan_percents.append(nan_pct)

            valid = data[~np.isnan(data)]
            if valid.size > 0:
                vmin, vmax = float(valid.min()), float(valid.max())
            else:
                vmin, vmax = np.nan, np.nan
            value_ranges.append((vmin, vmax))

            band_label = BAND_NAMES[i - 1] if i <= len(BAND_NAMES) else f"Band{i}"
            vr.add(f"NaN% {band_label}",
                   nan_pct < 50,
                   f"{nan_pct:.2f}%  range [{vmin:.4f}, {vmax:.4f}]")

        overall_nan = float(np.mean(nan_percents))
        vr.add("Overall NaN < 50%",
               overall_nan < 50,
               f"mean NaN across bands: {overall_nan:.2f}%")

        meta = {
            "file": str(raster_path),
            "file_size_mb": f"{raster_path.stat().st_size / (1024**2):.2f}",
            "driver": src.driver,
            "width_px": src.width,
            "height_px": src.height,
            "bands": src.count,
            "band_names": BAND_NAMES,
            "dtype": src.dtypes[0],
            "crs": str(src.crs),
            "epsg": epsg,
            "resolution_m": f"{res_x:.2f} x {res_y:.2f}",
            "bounds": {
                "left": round(src.bounds.left, 2),
                "bottom": round(src.bounds.bottom, 2),
                "right": round(src.bounds.right, 2),
                "top": round(src.bounds.top, 2),
            },
            "nodata": str(src.nodata),
            "compress": src.profile.get("compress", "none"),
            "nan_percent_per_band": {
                BAND_NAMES[i]: f"{nan_percents[i]:.2f}%"
                for i in range(min(len(BAND_NAMES), len(nan_percents)))
            },
            "value_range_per_band": {
                BAND_NAMES[i]: f"[{value_ranges[i][0]:.4f}, {value_ranges[i][1]:.4f}]"
                for i in range(min(len(BAND_NAMES), len(value_ranges)))
            },
            "overall_mean_nan_pct": f"{overall_nan:.2f}%",
        }

    return meta


def verify_labels(root: Path, vr: ValidationResult) -> dict:
    """Check that the label GeoJSON exists, has the expected schema, and report polygon counts."""
    label_path = root / LABELS_REL
    label_summary = {}

    if not label_path.exists():
        vr.add("Label file exists", False, f"{label_path} (Run 03_create_label_template.py first)")
        return label_summary
    vr.add("Label file exists", True, str(label_path))

    gdf = gpd.read_file(label_path)
    epsg = gdf.crs.to_epsg() if gdf.crs else None
    vr.add("Label CRS",
           epsg == EXPECTED_EPSG,
           f"got EPSG:{epsg}")
    vr.add("Label schema has class_id",
           "class_id" in gdf.columns,
           str(list(gdf.columns)))
    vr.add("Label schema has class_name",
           "class_name" in gdf.columns,
           str(list(gdf.columns)))

    n_poly = len(gdf)
    label_summary["total_polygons"] = n_poly
    if n_poly == 0:
        log.warning("  [WARN]  labels.geojson currently has 0 polygons — digitize classes 1-5 in QGIS before Phase 3.")
    else:
        counts = gdf["class_id"].value_counts().to_dict()
        label_summary["polygons_per_class"] = counts
        log.info("  [INFO]  Polygons per class_id: %s", counts)

    return label_summary


def write_metadata(root: Path, meta: dict, label_summary: dict, vr: ValidationResult) -> Path:
    """Write a human-readable metadata report."""
    out_path = root / METADATA_REL
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "=" * 70,
        "  PHASE 1  -  DATA VERIFICATION & METADATA REPORT",
        f"  Generated: {datetime.datetime.now(datetime.timezone.utc).isoformat()}",
        "=" * 70,
        "",
        "-- RASTER METADATA ---------------------------------------------------",
    ]
    for k, v in meta.items():
        if isinstance(v, dict):
            lines.append(f"  {k}:")
            for kk, vv in v.items():
                lines.append(f"    {kk}: {vv}")
        else:
            lines.append(f"  {k}: {v}")

    lines.append("")
    lines.append("-- LABEL DATASET SUMMARY ---------------------------------------------")
    for k, v in label_summary.items():
        lines.append(f"  {k}: {v}")

    lines.append("")
    lines.append("-- VALIDATION CHECKS -------------------------------------------------")
    for c in vr.checks:
        lines.append(f"  [{c['status']}]  {c['name']}  {c['detail']}")

    lines.append("")
    overall = "ALL CHECKS PASSED" if vr.all_passed else "SOME CHECKS FAILED"
    lines.append(f"-- RESULT: {overall}")
    lines.append("=" * 70)
    lines.append("")
    lines.append("Handoff notes for Person 2 (Phase 2 - Preprocessing):")
    lines.append("  * Composite is a 9-band Float32 GeoTIFF scaled to [0, 1] reflectance.")
    lines.append("  * Bands: B02, B03, B04, B05, B06, B07, B08, B11, B12.")
    lines.append("  * NaN pixels indicate cloud/shadow-masked areas - fill or mask in Phase 2.")
    lines.append("  * Labels GeoJSON contains class_id (1-5) and class_name attributes.")
    lines.append("  * CRS is EPSG:32643 (UTM 43N) throughout - no reprojection needed.")
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    log.info("✅  Metadata report written to %s", out_path)
    return out_path


def main() -> None:
    root = PROJECT_ROOT.resolve()
    log.info("=" * 60)
    log.info("Phase 1 – Data Verification  |  Root: %s", root)
    log.info("=" * 60)

    vr = ValidationResult()
    log.info("-- Raster Checks --")
    meta = verify_raster(root, vr)

    log.info("-- Label Checks --")
    label_summary = verify_labels(root, vr)

    if meta:
        report = write_metadata(root, meta, label_summary, vr)
        print(f"\nMetadata report: {report}")

    print()
    if vr.all_passed:
        print("🟢  All verification checks PASSED — ready for QGIS labeling & Phase 2 handoff.")
    else:
        print("🔴  Some checks FAILED — review the report and fix before handoff.")
        sys.exit(1)


if __name__ == "__main__":
    main()