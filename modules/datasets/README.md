# simple-module-datasets

Geospatial + tabular dataset upload module for [simple_module](https://github.com/antosubash/simple_module_python) apps. Users upload CSV/GeoJSON/Shapefile; the module parses, slugs a canonical name, and stores geometry using `shapely`.

## Install

```bash
pip install simple-module-datasets
```

Also needs `simple-module-file-storage` + `simple-module-background-tasks` (declared as deps).

## What it provides

- `POST /api/datasets` — multipart upload; the file is staged via `simple-module-file-storage`, then a Celery job parses it in the background.
- `Dataset` SQLModel record with `name`, `slug` (via `python-slugify`), `geometry_type`, `row_count`, `bbox`.
- Shapely-backed parsers for GeoJSON, CSV with lat/lon columns, and zipped Shapefiles.
- Admin UI for browsing + deleting datasets.

## Usage

Upload from a form:

```bash
curl -X POST -F "file=@cities.geojson" http://localhost:8000/api/datasets
```

Query parsed datasets:

```python
from datasets.service import DatasetService   # type: ignore[import-not-found]

async def list_by_bbox(svc: DatasetService = Depends(DatasetService), ...):
    return await svc.intersects(bbox=(-74.1, 40.6, -73.8, 40.9))
```

## Depends on

- `simple-module-core`, `simple-module-db`, `simple-module-hosting`
- `simple-module-file-storage`, `simple-module-background-tasks`
- `shapely>=2.0`, `python-slugify>=8.0`, `celery>=5.4`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
