from pathlib import Path
import logging
import geopandas as gpd
import numpy as np
import rasterio
from rasterio.crs import CRS
import xarray as xr
from pystac_client import Client
import planetary_computer as pc
import odc.stac
from odc.geo.geobox import GeoBox
from shapely.geometry import mapping

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s")
log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
STUDY_AREA = ROOT / "data/01_raw/study_area.geojson"
OUT_TIF = ROOT / "data/01_raw/S2_KothriKalan_Rabi_2026_10m.tif"

TARGET_EPSG = 32643
BANDS_10M = ["B02", "B03", "B04", "B08"]
BANDS_20M = ["B05", "B06", "B07", "B11", "B12"]
BAND_ORDER = ["B02", "B03", "B04", "B05", "B06", "B07", "B08", "B11", "B12"]

gdf = gpd.read_file(STUDY_AREA)
gdf_utm = gdf.to_crs(epsg=TARGET_EPSG)
gdf_wgs = gdf.to_crs(epsg=4326)

minx, miny, maxx, maxy = gdf_utm.total_bounds
if maxx < 1000:
    gdf_utm = gdf.set_crs(epsg=4326, allow_override=True).to_crs(epsg=TARGET_EPSG)
    gdf_wgs = gdf.set_crs(epsg=4326, allow_override=True)
    minx, miny, maxx, maxy = gdf_utm.total_bounds

catalog = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
items = list(catalog.search(
    collections=["sentinel-2-l2a"],
    intersects=mapping(gdf_wgs.union_all()),
    datetime="2026-01-15/2026-03-10",
    query={"eo:cloud_cover": {"lt": 10}},
).items())

# Keep only the 5 lowest-cloud scenes (< 0.001% cloud cover) for 3x faster download
items = sorted(items, key=lambda it: it.properties.get("eo:cloud_cover", 100))[:5]
log.info("Selected top %d clearest scenes.", len(items))

gbox = GeoBox.from_bbox((minx, miny, maxx, maxy), crs=f"EPSG:{TARGET_EPSG}", resolution=10)

log.info("[1/3] Downloading SCL cloud mask...")
ds_scl = odc.stac.load(items, bands=["SCL"], geobox=gbox, groupby="solar_day", resampling="nearest")
invalid_mask = ds_scl["SCL"].isin([3, 8, 9, 10]).values  # Computed ONCE in memory

arrays = []
for idx, b in enumerate(BAND_ORDER, start=1):
    resamp = "nearest" if b in BANDS_10M else "bilinear"
    log.info("[%d/9] Downloading & compositing band %s...", idx, b)
    ds_b = odc.stac.load(items, bands=[b], geobox=gbox, groupby="solar_day", resampling=resamp)
    arr = ds_b[b].values.astype(np.float32)
    arr[invalid_mask] = np.nan
    med = np.clip(np.nanmedian(arr, axis=0) / 10000.0, 0.0, 1.0)
    arrays.append(med.astype(np.float32))

stack = np.stack(arrays, axis=0)
OUT_TIF.parent.mkdir(parents=True, exist_ok=True)

with rasterio.open(
    OUT_TIF, "w",
    driver="GTiff", dtype="float32",
    width=gbox.width, height=gbox.height, count=len(BAND_ORDER),
    crs=CRS.from_epsg(TARGET_EPSG), transform=gbox.transform,
    nodata=np.nan, compress="deflate", tiled=True
) as dst:
    for idx, b in enumerate(BAND_ORDER, start=1):
        dst.write(stack[idx - 1], idx)
        dst.set_band_description(idx, b)

log.info("SUCCESS! Saved %s (%.1f MB)", OUT_TIF, OUT_TIF.stat().st_size / 1e6)
