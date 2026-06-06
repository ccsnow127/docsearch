# osmnx Baseline Documentation

## Module: utils_geo

**Purpose**: Provides geospatial helper functions used across OSMnx for buffering geometries in meter units, sampling/interpolating points along network geometries, subdividing large polygons for efficient spatial operations, and creating/transforming bounding boxes.

**Key functions and roles**
- **buffer_geometry**: Buffers an unprojected Shapely geometry (EPSG:4326) by a distance in meters by projecting to a meter-based CRS via **projection.project_geometry**, buffering, then projecting back to lat/long.
- **sample_points**: Generates a uniform random sample of points constrained to a projected, typically undirected **networkx.MultiGraph** by converting edges to a GeoDataFrame via **convert.graph_to_gdfs**, weighting edges by their `length`, and interpolating random positions along each selected edge geometry.
- **interpolate_points**: Yields evenly spaced `(x, y)` coordinates along a **shapely.LineString** or **MultiLineString** using normalized interpolation based on the geometry’s length and the requested spacing.
- **_consolidate_subdivide_geometry**: Prepares large projected **Polygon/MultiPolygon** query geometries by optionally replacing them with their convex hull, warning when far above **settings.max_query_area_size**, and subdividing them into smaller polygons using **_quadrat_cut_geometry**.
- **_quadrat_cut_geometry**: Splits a **Polygon/MultiPolygon** into a **MultiPolygon** by recursively cutting it with a grid of vertical/horizontal **LineString** “quadrat” lines (using **shapely.ops.split**) sized by `quadrat_width`.
- **_intersect_index_quadrats**: Accelerates intersection tests between a **geopandas.GeoSeries** and a (Multi)Polygon by using the GeoSeries spatial index (`sindex`) and intersecting against quadrat-cut polygon chunks, returning the set of matching GeoSeries index labels.
- **bbox_from_point**: Computes a `(left, bottom, right, top)` bounding box around a `(lat, lon)` point for a meter distance using spherical approximations, optionally projecting the bbox to UTM (and optionally returning the CRS) by converting it with **bbox_to_poly** then calling **projection.project_geometry**.
- **bbox_to_poly**: Converts bbox coordinates into a Shapely **Polygon**, primarily to support projection and downstream spatial operations.

---

## Function: buffer_geometry

```python
def buffer_geometry(geom: Geometry, dist: float) -> Geometry
```

**buffer_geometry**: Buffer an unprojected (lat/lon) Shapely geometry by a distance in meters by projecting to a meter-based CRS, buffering, then reprojecting back.
**Signature**: def buffer_geometry(geom: Geometry, dist: float) -> Geometry
**Parameters**:
- geom (Geometry): Input Shapely geometry whose coordinates are expected to be unprojected latitude-longitude degrees (EPSG:4326).
- dist (float): Buffer distance in meters to apply around the geometry.
**Behavior**:
- Project the input geometry to a projected CRS (meter units) by calling projection.project_geometry(geom) and capture both the projected geometry and its CRS.
- Compute a buffer around the projected geometry using Shapely's buffer operation with the given dist (in meters).
- Reproject the buffered projected geometry back to unprojected lat/lon by calling projection.project_geometry with:
- geom set to the buffered projected geometry
- crs set to the projected CRS obtained earlier
- to_latlong=True
- Discard the returned CRS from the second projection call and keep only the reprojected buffered geometry.
- Return the buffered geometry in unprojected coordinates.
**Returns**:
- Geometry: The buffered geometry in unprojected lat/lon coordinates.
**Notes**:
- Correctness depends on geom being in unprojected lat/lon degrees; dist is always interpreted as meters via the intermediate projection step.

---

## Function: sample_points

```python
def sample_points(G: nx.MultiGraph, n: int) -> gpd.GeoSeries
```

**sample_points**: Randomly sample uniformly distributed points along a graph’s edge geometries, weighted by edge length.
**Signature**: def sample_points(G: nx.MultiGraph, n: int) -> gpd.GeoSeries
**Parameters**:
- G (nx.MultiGraph): Graph to sample from; intended to be undirected (to avoid oversampling bidirectional edges) and projected (so edge lengths and interpolation are in consistent linear units).
- n (int): Number of points to sample.
**Behavior**:
- If G is directed (nx.is_directed(G) is True), emit a UserWarning stating that G should be undirected to avoid oversampling bidirectional edges.
- Convert the graph’s edges to a GeoDataFrame via convert.graph_to_gdfs(G, nodes=False), then keep only the "geometry" and "length" columns.
- Compute sampling weights per edge as each edge length divided by the sum of all edge lengths.
- Use NumPy’s default random generator (np.random.default_rng()) to choose n edge index labels from the GeoDataFrame’s index with probability p=weights.
- Select the corresponding edge geometries (a GeoSeries of LineString-like geometries) for the chosen indices.
- Generate n independent uniform random numbers in [0, 1) using a (new) np.random.default_rng().random(n).
- Interpolate one point on each selected line at the corresponding normalized position using GeoSeries.interpolate(..., normalized=True).
- Return the resulting GeoSeries of points; its index corresponds to the sampled edges’ multi-index (u, v, key) inherited from the edge GeoDataFrame.
**Returns**:
- gpd.GeoSeries: Sampled point geometries, indexed by the edge identifiers (u, v, key) from which each point was sampled.
**Notes**:
- Uses two separate default_rng() instances: one for choosing edges and another for positions along edges.
- Uniformity is with respect to total edge length: longer edges are more likely to be selected, and positions along each selected edge are uniform along its length (normalized interpolation).

---

## Function: interpolate_points

```python
def interpolate_points(geom: LineString | MultiLineString, dist: float) -> Iterator[tuple[float, float]]
```

**interpolate_points**: Yield approximately evenly spaced (x, y) coordinates along a LineString or MultiLineString using normalized interpolation.
**Signature**: def interpolate_points(geom: LineString | MultiLineString, dist: float) -> Iterator[tuple[float, float]]
**Parameters**:
- geom (LineString | MultiLineString): Input linear geometry along which to interpolate points.
- dist (float): Desired spacing between points, in the same units as geom’s coordinates/length; smaller values produce more points.
**Behavior**:
- Verify geom is an instance of LineString or MultiLineString.
- Compute num_vert as max(round(geom.length / dist), 1):
- geom.length/dist is rounded to the nearest integer to determine the number of segments.
- At least 1 segment is enforced to ensure endpoints are produced.
- For each integer n from 0 through num_vert inclusive (i.e., num_vert + 1 points):
- Compute a normalized fraction f = n / num_vert.
- Interpolate a point on geom at normalized position f using geom.interpolate(f, normalized=True).
- Yield a tuple (point.x, point.y).
- If geom is not a LineString or MultiLineString, raise TypeError with message "`geom` must be a LineString.".
**Returns**:
- Iterator[tuple[float, float]]: An iterator yielding (x, y) coordinate tuples for each interpolated point, including both endpoints.
**Notes**:
- Spacing is approximate because the number of segments is derived from rounding; actual spacing is geom.length/num_vert.
- For MultiLineString, interpolation is performed over the geometry as a whole using Shapely’s normalized interpolation semantics.

---

## Function: _consolidate_subdivide_geometry

```python
def _consolidate_subdivide_geometry(geom: Polygon | MultiPolygon) -> MultiPolygon
```

**_consolidate_subdivide_geometry**: Normalize a shapely polygonal geometry into a single shapely `MultiPolygon` suitable for downstream “max area per query” constraints by (optionally) consolidating it via convex hull and (optionally) subdividing it into smaller polygon parts when its area exceeds a configured threshold, while guaranteeing polygon-only output (or a clear error) after subdivision.

**Signature**:
- def _consolidate_subdivide_geometry(geom: Polygon | MultiPolygon) -> MultiPolygon

**Parameters**:
- geom (Polygon | MultiPolygon): Input shapely polygonal geometry. It is assumed to be in a projected coordinate reference system with linear units (e.g., meters) so that `.area` is meaningful and consistent with `settings.max_query_area_size`. The geometry must support shapely operations used by this function (`.area`, `.convex_hull`, and (if present) `.geoms`) and be acceptable input to `_quadrat_cut_geometry`.

**Behavior**:
- Scope and dependency constraints (import-time safety; closes the knowledge gap):
- Implement **only** this single function: `_consolidate_subdivide_geometry`.
- Do not add or define any other top-level functions, classes, helpers, constants, or executable module-level logic as part of implementing this function.
- Do not redefine, stub, wrap, monkeypatch, or otherwise provide an implementation of `_quadrat_cut_geometry`; it is assumed to already exist in the module/runtime and tests will provide it. This function must only call it when required.
- Do not introduce new third-party dependencies. In particular, do not import or use unrelated libraries (e.g., `geopandas`, `networkx`, `pyproj`, graph utilities, projection utilities).
- Allowed imports/usages for implementing this function are limited to:
- `numpy` as `np` (only needed for `np.sqrt` or an equivalent square root computation).
- `warnings.warn` (only to emit the specified `UserWarning`).
- Shapely geometry types needed for `isinstance` checks and construction (`Polygon`, `MultiPolygon`), and shapely’s standard attributes/operations (`.area`, `.convex_hull`, `.geoms`, `.is_empty`).
- No I/O, network access, filesystem access, environment probing, logging configuration, or other side effects are permitted.
- No import-time side effects: nothing should execute at module import besides the minimal imports already present in the surrounding module and the function definition itself.

- Type validation (strict):
- If `geom` is not an instance of shapely `Polygon` or `MultiPolygon`, raise `TypeError` with message exactly: `"Geometry must be a shapely Polygon or MultiPolygon."`
- No implicit conversion from other geometry types (e.g., `GeometryCollection`, `LinearRing`) is performed.

- Configuration read:
- Read `mqas = settings.max_query_area_size`.
- `mqas` is interpreted as a maximum allowed area in the same units as `geom.area`.

- Configuration validity expectations (explicitly not pinned by this contract unless tests are added):
- `mqas` is expected to be positive and finite.
- If `mqas` is non-positive, NaN, or infinite, behavior is undefined by this contract. Implementations may raise (including due to `np.sqrt`), warn, or return unexpected results; callers/tests must not depend on a specific outcome under misconfiguration unless they add explicit tests and tighten this contract.

- Working geometry initialization:
- Set `g = geom`.

- Consolidation (convex hull) rules:
- If `geom` is a `MultiPolygon`, set `g = geom.convex_hull` unconditionally (i.e., always consolidate multiparts into a single hull geometry before considering subdivision).
- Else if `geom` is a `Polygon` and `geom.area > mqas`, set `g = geom.convex_hull`.
- Else (a `Polygon` with `geom.area <= mqas`), keep `g` unchanged.

- Consolidation semantics and invariants:
- Convex hull follows shapely semantics:
- Holes may be removed.
- Disjoint components (when input is `MultiPolygon`) may be enclosed and merged into a single convex polygon.
- The hull may change area and shape; callers must not assume preservation of boundaries, holes, or components.
- No additional validity repair is performed (e.g., no `buffer(0)` / `make_valid`) unless shapely performs it as part of `.convex_hull`.

- Warning side effect for very large consolidated geometries:
- This warning logic runs only if consolidation actually replaced the geometry with its convex hull (i.e., one of the two consolidation assignments above executed).
- Compute `ratio = int(g.area / mqas)` using Python’s `int` conversion (truncation toward zero).
- If `ratio > 10`, emit exactly one `UserWarning` during the call.
- Warning content requirements (structure, not exact string):
- The warning message must convey all of the following:
- The geometry area is `ratio` times the maximum query area size (the computed `ratio` must appear in the message in some form).
- The geometry will be divided into multiple sub-queries (or equivalent wording).
- The operation may take a long time (or equivalent wording).
- Message stability:
- The exact string (punctuation/whitespace) is not constrained; tests must not require an exact match.
- Warning emission must not affect the returned geometry and must not be repeated within a single call.

- Subdivision trigger (strict threshold):
- After consolidation and warning logic, if `g.area > mqas`, subdivision is required; otherwise subdivision is skipped.
- All area comparisons in this function use strict greater-than (`> mqas`):
- If `area == mqas`, do not convex-hull (for `Polygon`) and do not subdivide.

- Subdivision call:
- When subdivision is required, call `_quadrat_cut_geometry(g, quadrat_width=np.sqrt(mqas))`.
- `np.sqrt(mqas)` is a heuristic tile width whose square approximates the maximum allowed area; this does not guarantee every resulting piece has `area <= mqas`.
- This function does not post-check or enforce that each piece’s area is `<= mqas`; downstream code must not assume per-piece compliance unless separately enforced.

- Subdivision output normalization (polygon-only, flattening, filtering):
- `_quadrat_cut_geometry` is treated as potentially returning any shapely geometry type, including `Polygon`, `MultiPolygon`, `GeometryCollection`, other collections, mixed-type collections (points/lines/polygons), nested multipolygons, and empty geometries.
- The subdivision result must be normalized into polygon-only members before constructing the returned `MultiPolygon`. This prevents latent failures if the helper returns mixed geometries.
- Normalization procedure (conceptual algorithm; implementations may be recursive or iterative):
- Maintain an ordered list `parts = []`.
- Define “polygonal member” as a non-empty shapely `Polygon` instance.
- Traverse the subdivision result as follows:
- If the current geometry is a `Polygon`:
- If it is non-empty, append it to `parts`.
- If the current geometry is a `MultiPolygon`:
- Iterate over its `.geoms` and apply this same traversal to each member.
- If the current geometry is any other geometry with a `.geoms` attribute (e.g., `GeometryCollection` or other collections):
- Iterate over `.geoms` and apply this same traversal to each member.
- If the current geometry is any other type (or lacks `.geoms` and is not a `Polygon`/`MultiPolygon`):
- Ignore it (do not error solely due to its presence).
- Empty geometries:
- Empty `Polygon` or empty collection members must be ignored and must not cause an error by themselves.
- Ordering:
- Preserve traversal order: polygons are appended in the order encountered during `.geoms` iteration; no spatial sorting is performed and tests must not assume a particular spatial order.

- Subdivision post-condition and error:
- After normalization, if `parts` is empty, raise `ValueError` indicating that subdivision produced no polygonal output.
- The exact error message is not strictly constrained, but it must clearly communicate that no polygon parts were produced/retained after subdivision.
- If `parts` is non-empty, set `g = MultiPolygon(parts)`.
- Construction must use only `Polygon` members; no other geometry types may be passed into `MultiPolygon(...)`.

- Final output normalization (applies whether subdivision occurred or not):
- If subdivision occurred, return the normalized `MultiPolygon(parts)` as `g`.
- If subdivision did not occur:
- If `g` is a `Polygon`, return `MultiPolygon([g])`.
- If `g` is a `MultiPolygon`, return `g` unchanged.
- No other geometry types are permitted to reach this stage; if they do, it indicates unexpected shapely behavior or a violation of the above rules.

**Returns**:
- MultiPolygon: A shapely `MultiPolygon` representing the consolidated geometry (possibly convex-hulled) and, if needed, subdivided into polygon-only parts suitable for downstream processing.
- Output invariants on all successful paths:
- The return value is always a shapely `MultiPolygon`.
- The returned `MultiPolygon` contains only non-empty `Polygon` members (no `LineString`, `Point`, `GeometryCollection`, nested `MultiPolygon` members, or empty geometries).
- If the input is a `Polygon` and no subdivision occurs, the output contains exactly one polygon: the original polygon or its convex hull if hull was applied.
- If the input is a `MultiPolygon`, the output corresponds to its convex hull (and possibly a subdivided version of that hull if it exceeds `mqas`), rather than preserving the original component polygons.
- Error behavior:
- Raises `TypeError` for non-polygonal input types with the exact message specified above.
- Raises `ValueError` if subdivision is triggered but yields no polygonal parts after normalization.

---

## Function: _quadrat_cut_geometry

```python
def _quadrat_cut_geometry(geom: Polygon | MultiPolygon, quadrat_width: float) -> MultiPolygon
```

**_quadrat_cut_geometry**: Split a Polygon or MultiPolygon into a MultiPolygon of smaller pieces by recursively cutting it with a grid of evenly spaced vertical and horizontal lines.
**Signature**: def _quadrat_cut_geometry(geom: Polygon | MultiPolygon, quadrat_width: float) -> MultiPolygon
**Parameters**:
- geom (Polygon | MultiPolygon): Polygonal geometry to be split.
- quadrat_width (float): Target width (in geom’s coordinate units) used to determine spacing of the cutting grid.
**Behavior**:
- Set min_num = 3 to enforce at least 3 grid lines in each direction (which yields at least a 2x2 grid of quadrat cells).
- Extract bounds from geom.bounds as (left, bottom, right, top).
- Compute the number of grid coordinates needed in each direction:
- x_num = int(ceil((right - left) / quadrat_width) + 1)
- y_num = int(ceil((top - bottom) / quadrat_width) + 1)
- Create evenly spaced coordinate arrays:
- x_points = linspace(left, right, num=max(x_num, min_num))
- y_points = linspace(bottom, top, num=max(y_num, min_num))
- Build cutting lines:
- vertical_lines: for each x in x_points, create LineString([(x, y_points[0]), (x, y_points[-1])]).
- horizont_lines: for each y in y_points, create LineString([(x_points[0], y), (x_points[-1], y)]).
- Concatenate all lines into a single list in the order vertical then horizontal.
- Initialize geoms = [geom].
- For each line in lines, update geoms by splitting each current geometry g:
- If g.intersects(line) is True, replace g with the sequence split(g, line).geoms.
- Otherwise keep g unchanged.
- After processing all current geometries for that line, flatten the resulting list-of-lists into a single list and continue to the next line.
- After all lines have been processed, return MultiPolygon(geoms) constructed from the final list of polygonal pieces.
**Returns**:
- MultiPolygon: A MultiPolygon containing all resulting pieces after all recursive splits.
**Notes**:
- The function applies splits sequentially for each grid line; pieces can be split multiple times as subsequent lines are processed.
- The returned MultiPolygon is constructed directly from the final list of geometries produced by shapely.ops.split.

---

## Function: _intersect_index_quadrats

```python
def _intersect_index_quadrats(geoms: gpd.GeoSeries, polygon: Polygon | MultiPolygon) -> set[Any]
```

**_intersect_index_quadrats**: Find which geometries in a GeoSeries intersect a given (Multi)Polygon using an r-tree index accelerated by subdividing the polygon into quadrats.
**Signature**: def _intersect_index_quadrats(geoms: gpd.GeoSeries, polygon: Polygon | MultiPolygon) -> set[Any]
**Parameters**:
- geoms (gpd.GeoSeries): Candidate geometries to test for intersection; must support .sindex, .iloc, and .intersects.
- polygon (Polygon | MultiPolygon): The polygonal region to intersect against; must be in the same CRS as geoms.
**Behavior**:
- Build an r-tree spatial index from geoms by accessing geoms.sindex.
- Log an INFO message via utils.log: "Built r-tree spatial index for {len(geoms):,} geometries".
- Choose a quadrat width to subdivide the polygon:
- Compute quadrat_width = max(0.1, sqrt(polygon.area) / 10).
- Subdivide polygon into a MultiPolygon of quadrats by calling _quadrat_cut_geometry(polygon, quadrat_width).
- Log an INFO message via utils.log: "Accelerating r-tree with {len(multipoly.geoms)} quadrats".
- Initialize an empty set geoms_in_poly.
- For each sub-polygon poly in multipoly.geoms:
- Compute poly_buff = poly.buffer(0) (a zero-width buffer used to clean/fix geometry).
- If poly_buff.is_valid is True and poly_buff.area > 0:
- Query the r-tree for candidates whose bounding boxes intersect poly_buff.bounds via rtree.intersection(poly_buff.bounds); this yields positional indices (iloc-style).
- Convert these to a list and select candidate geometries: possible_matches = geoms.iloc[list(possible_matches_iloc)].
- Compute precise matches by filtering candidates with possible_matches.intersects(poly_buff).
- Add the index labels of these precise matches to geoms_in_poly via set update.
- After processing all quadrats, log an INFO message via utils.log: "Identified {len(geoms_in_poly):,} geometries inside polygon".
- Return geoms_in_poly.
**Returns**:
- set[Any]: A set of index labels from geoms corresponding to geometries that intersected the polygon.
**Notes**:
- The method performs a two-stage filter: r-tree bounding-box intersection followed by exact geometric intersection.
- Subdividing the polygon reduces the candidate set per query and can improve performance on large polygons.

---

## Function: bbox_from_point

```python
def bbox_from_point(point: tuple[float, float], dist: float) -> tuple[float, float, float, float]
```

**bbox_from_point**: Compute a bounding box around a (lat, lon) point at a given meter distance in each cardinal direction, optionally projecting the bbox to UTM and optionally returning the projected CRS.
**Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: bool=False, return_crs: bool=False) -> tuple[float, float, float, float] | tuple[tuple[float, float, float, float], Any]
**Overload 1 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
**Behavior**:
- Compute an unprojected bbox in degrees around the point using the algorithm described below under the general behavior.
- Log the created bbox at INFO level.
- Return the bbox as (left, bottom, right, top).
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 2 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, return_crs: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- return_crs (Literal[True]): Accepted but has no effect unless project_utm is also True (not provided in this overload).
**Behavior**:
- Same as Overload 1: compute unprojected bbox, log it, and return only the bbox.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 3 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- return_crs (Literal[False]): Explicitly indicates CRS should not be returned.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 4 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): If True, project the bbox polygon to a UTM CRS and return projected bounds.
**Behavior**:
- Compute the initial unprojected bbox in degrees.
- Convert bbox to a Polygon via bbox_to_poly.
- Project that polygon via projection.project_geometry(bbox_poly), capturing (bbox_proj, crs_proj).
- Replace bbox with bbox_proj.bounds (left, bottom, right, top) in projected coordinates.
- Log the created bbox at INFO level (logging the final bbox tuple).
- Return the projected bbox tuple.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in projected (UTM) coordinates.
**Overload 5 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True], return_crs: Literal[True]) -> tuple[tuple[float, float, float, float], Any]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): Project the bbox polygon to UTM and return projected bounds.
- return_crs (Literal[True]): Also return the projected CRS object alongside the bbox.
**Behavior**:
- Perform the same steps as Overload 4 to compute projected bbox bounds and obtain crs_proj.
- Log the created bbox at INFO level.
- Return a 2-tuple: (bbox, crs_proj).
**Returns**:
- tuple[tuple[float, float, float, float], Any]: ( (left, bottom, right, top) in projected coordinates, projected CRS ).
**Overload 6 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True], return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): Project the bbox polygon to UTM.
- return_crs (Literal[False]): Do not return CRS.
**Behavior**:
- Same as Overload 4.
**Returns**:
- tuple[float, float, float, float]: Projected bbox bounds.
**Overload 7 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project; return unprojected bbox.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 8 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False], return_crs: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project.
- return_crs (Literal[True]): Accepted but ignored because CRS is only returned when project_utm is True.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 9 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False], return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project.
- return_crs (Literal[False]): Do not return CRS.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 10 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: bool=False, return_crs: bool=False) -> tuple[float, float, float, float] | tuple[tuple[float, float, float, float], Any]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (bool): If True, project the bbox polygon to UTM and return projected bounds.
- return_crs (bool): If True and project_utm is True, also return the projected CRS.
**Behavior**:
- Set constant EARTH_RADIUS_M = 6_371_009.
- Unpack point into lat, lon.
- Compute angular deltas corresponding to dist meters:
- delta_lat = rad2deg(dist / EARTH_RADIUS_M).
- delta_lon = rad2deg(dist / EARTH_RADIUS_M) / cos(deg2rad(lat)).
- Compute bbox edges in degrees:
- top = lat + delta_lat
- bottom = lat - delta_lat
- right = lon + delta_lon
- left = lon - delta_lon
- Form bbox = (left, bottom, right, top).
- If project_utm is True:
- Convert bbox to a Polygon using bbox_to_poly(bbox=bbox).
- Project the polygon using projection.project_geometry(bbox_poly), receiving (bbox_proj, crs_proj).
- Replace bbox with bbox_proj.bounds (a 4-tuple in projected coordinates).
- Log an INFO message via utils.log: "Created bbox {dist} meters from {point}: {bbox}".
- If project_utm is True and return_crs is True, return (bbox, crs_proj).
- Otherwise return bbox.
**Returns**:
- tuple[float, float, float, float]: If not returning CRS, returns (left, bottom, right, top) either in unprojected degrees (project_utm False) or projected coordinates (project_utm True).
- tuple[tuple[float, float, float, float], Any]: If project_utm True and return_crs True, returns (bbox, crs_proj).
**Notes**:
- The bbox tuple ordering is always (left, bottom, right, top).
- return_crs has an effect only when project_utm is True; otherwise only the bbox is returned.

---

## Function: bbox_from_point

```python
def bbox_from_point(point: tuple[float, float], dist: float, *, return_crs: Literal[True]) -> tuple[float, float, float, float]
```

**bbox_from_point**: Compute a bounding box around a (lat, lon) point at a given meter distance in each cardinal direction, optionally projecting the bbox to UTM and optionally returning the projected CRS.
**Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: bool=False, return_crs: bool=False) -> tuple[float, float, float, float] | tuple[tuple[float, float, float, float], Any]
**Overload 1 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
**Behavior**:
- Compute an unprojected bbox in degrees around the point using the algorithm described below under the general behavior.
- Log the created bbox at INFO level.
- Return the bbox as (left, bottom, right, top).
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 2 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, return_crs: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- return_crs (Literal[True]): Accepted but has no effect unless project_utm is also True (not provided in this overload).
**Behavior**:
- Same as Overload 1: compute unprojected bbox, log it, and return only the bbox.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 3 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- return_crs (Literal[False]): Explicitly indicates CRS should not be returned.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 4 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): If True, project the bbox polygon to a UTM CRS and return projected bounds.
**Behavior**:
- Compute the initial unprojected bbox in degrees.
- Convert bbox to a Polygon via bbox_to_poly.
- Project that polygon via projection.project_geometry(bbox_poly), capturing (bbox_proj, crs_proj).
- Replace bbox with bbox_proj.bounds (left, bottom, right, top) in projected coordinates.
- Log the created bbox at INFO level (logging the final bbox tuple).
- Return the projected bbox tuple.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in projected (UTM) coordinates.
**Overload 5 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True], return_crs: Literal[True]) -> tuple[tuple[float, float, float, float], Any]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): Project the bbox polygon to UTM and return projected bounds.
- return_crs (Literal[True]): Also return the projected CRS object alongside the bbox.
**Behavior**:
- Perform the same steps as Overload 4 to compute projected bbox bounds and obtain crs_proj.
- Log the created bbox at INFO level.
- Return a 2-tuple: (bbox, crs_proj).
**Returns**:
- tuple[tuple[float, float, float, float], Any]: ( (left, bottom, right, top) in projected coordinates, projected CRS ).
**Overload 6 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True], return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): Project the bbox polygon to UTM.
- return_crs (Literal[False]): Do not return CRS.
**Behavior**:
- Same as Overload 4.
**Returns**:
- tuple[float, float, float, float]: Projected bbox bounds.
**Overload 7 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project; return unprojected bbox.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 8 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False], return_crs: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project.
- return_crs (Literal[True]): Accepted but ignored because CRS is only returned when project_utm is True.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 9 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False], return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project.
- return_crs (Literal[False]): Do not return CRS.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 10 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: bool=False, return_crs: bool=False) -> tuple[float, float, float, float] | tuple[tuple[float, float, float, float], Any]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (bool): If True, project the bbox polygon to UTM and return projected bounds.
- return_crs (bool): If True and project_utm is True, also return the projected CRS.
**Behavior**:
- Set constant EARTH_RADIUS_M = 6_371_009.
- Unpack point into lat, lon.
- Compute angular deltas corresponding to dist meters:
- delta_lat = rad2deg(dist / EARTH_RADIUS_M).
- delta_lon = rad2deg(dist / EARTH_RADIUS_M) / cos(deg2rad(lat)).
- Compute bbox edges in degrees:
- top = lat + delta_lat
- bottom = lat - delta_lat
- right = lon + delta_lon
- left = lon - delta_lon
- Form bbox = (left, bottom, right, top).
- If project_utm is True:
- Convert bbox to a Polygon using bbox_to_poly(bbox=bbox).
- Project the polygon using projection.project_geometry(bbox_poly), receiving (bbox_proj, crs_proj).
- Replace bbox with bbox_proj.bounds (a 4-tuple in projected coordinates).
- Log an INFO message via utils.log: "Created bbox {dist} meters from {point}: {bbox}".
- If project_utm is True and return_crs is True, return (bbox, crs_proj).
- Otherwise return bbox.
**Returns**:
- tuple[float, float, float, float]: If not returning CRS, returns (left, bottom, right, top) either in unprojected degrees (project_utm False) or projected coordinates (project_utm True).
- tuple[tuple[float, float, float, float], Any]: If project_utm True and return_crs True, returns (bbox, crs_proj).
**Notes**:
- The bbox tuple ordering is always (left, bottom, right, top).
- return_crs has an effect only when project_utm is True; otherwise only the bbox is returned.

---

## Function: bbox_from_point

```python
def bbox_from_point(point: tuple[float, float], dist: float, *, return_crs: Literal[False]) -> tuple[float, float, float, float]
```

**bbox_from_point**: Compute a bounding box around a (lat, lon) point at a given meter distance in each cardinal direction, optionally projecting the bbox to UTM and optionally returning the projected CRS.
**Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: bool=False, return_crs: bool=False) -> tuple[float, float, float, float] | tuple[tuple[float, float, float, float], Any]
**Overload 1 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
**Behavior**:
- Compute an unprojected bbox in degrees around the point using the algorithm described below under the general behavior.
- Log the created bbox at INFO level.
- Return the bbox as (left, bottom, right, top).
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 2 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, return_crs: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- return_crs (Literal[True]): Accepted but has no effect unless project_utm is also True (not provided in this overload).
**Behavior**:
- Same as Overload 1: compute unprojected bbox, log it, and return only the bbox.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 3 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- return_crs (Literal[False]): Explicitly indicates CRS should not be returned.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 4 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): If True, project the bbox polygon to a UTM CRS and return projected bounds.
**Behavior**:
- Compute the initial unprojected bbox in degrees.
- Convert bbox to a Polygon via bbox_to_poly.
- Project that polygon via projection.project_geometry(bbox_poly), capturing (bbox_proj, crs_proj).
- Replace bbox with bbox_proj.bounds (left, bottom, right, top) in projected coordinates.
- Log the created bbox at INFO level (logging the final bbox tuple).
- Return the projected bbox tuple.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in projected (UTM) coordinates.
**Overload 5 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True], return_crs: Literal[True]) -> tuple[tuple[float, float, float, float], Any]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): Project the bbox polygon to UTM and return projected bounds.
- return_crs (Literal[True]): Also return the projected CRS object alongside the bbox.
**Behavior**:
- Perform the same steps as Overload 4 to compute projected bbox bounds and obtain crs_proj.
- Log the created bbox at INFO level.
- Return a 2-tuple: (bbox, crs_proj).
**Returns**:
- tuple[tuple[float, float, float, float], Any]: ( (left, bottom, right, top) in projected coordinates, projected CRS ).
**Overload 6 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True], return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): Project the bbox polygon to UTM.
- return_crs (Literal[False]): Do not return CRS.
**Behavior**:
- Same as Overload 4.
**Returns**:
- tuple[float, float, float, float]: Projected bbox bounds.
**Overload 7 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project; return unprojected bbox.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 8 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False], return_crs: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project.
- return_crs (Literal[True]): Accepted but ignored because CRS is only returned when project_utm is True.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 9 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False], return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project.
- return_crs (Literal[False]): Do not return CRS.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 10 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: bool=False, return_crs: bool=False) -> tuple[float, float, float, float] | tuple[tuple[float, float, float, float], Any]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (bool): If True, project the bbox polygon to UTM and return projected bounds.
- return_crs (bool): If True and project_utm is True, also return the projected CRS.
**Behavior**:
- Set constant EARTH_RADIUS_M = 6_371_009.
- Unpack point into lat, lon.
- Compute angular deltas corresponding to dist meters:
- delta_lat = rad2deg(dist / EARTH_RADIUS_M).
- delta_lon = rad2deg(dist / EARTH_RADIUS_M) / cos(deg2rad(lat)).
- Compute bbox edges in degrees:
- top = lat + delta_lat
- bottom = lat - delta_lat
- right = lon + delta_lon
- left = lon - delta_lon
- Form bbox = (left, bottom, right, top).
- If project_utm is True:
- Convert bbox to a Polygon using bbox_to_poly(bbox=bbox).
- Project the polygon using projection.project_geometry(bbox_poly), receiving (bbox_proj, crs_proj).
- Replace bbox with bbox_proj.bounds (a 4-tuple in projected coordinates).
- Log an INFO message via utils.log: "Created bbox {dist} meters from {point}: {bbox}".
- If project_utm is True and return_crs is True, return (bbox, crs_proj).
- Otherwise return bbox.
**Returns**:
- tuple[float, float, float, float]: If not returning CRS, returns (left, bottom, right, top) either in unprojected degrees (project_utm False) or projected coordinates (project_utm True).
- tuple[tuple[float, float, float, float], Any]: If project_utm True and return_crs True, returns (bbox, crs_proj).
**Notes**:
- The bbox tuple ordering is always (left, bottom, right, top).
- return_crs has an effect only when project_utm is True; otherwise only the bbox is returned.

---

## Function: bbox_from_point

```python
def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True]) -> tuple[float, float, float, float]
```

**bbox_from_point**: Compute a bounding box around a (lat, lon) point at a given meter distance in each cardinal direction, optionally projecting the bbox to UTM and optionally returning the projected CRS.
**Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: bool=False, return_crs: bool=False) -> tuple[float, float, float, float] | tuple[tuple[float, float, float, float], Any]
**Overload 1 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
**Behavior**:
- Compute an unprojected bbox in degrees around the point using the algorithm described below under the general behavior.
- Log the created bbox at INFO level.
- Return the bbox as (left, bottom, right, top).
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 2 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, return_crs: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- return_crs (Literal[True]): Accepted but has no effect unless project_utm is also True (not provided in this overload).
**Behavior**:
- Same as Overload 1: compute unprojected bbox, log it, and return only the bbox.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 3 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- return_crs (Literal[False]): Explicitly indicates CRS should not be returned.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 4 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): If True, project the bbox polygon to a UTM CRS and return projected bounds.
**Behavior**:
- Compute the initial unprojected bbox in degrees.
- Convert bbox to a Polygon via bbox_to_poly.
- Project that polygon via projection.project_geometry(bbox_poly), capturing (bbox_proj, crs_proj).
- Replace bbox with bbox_proj.bounds (left, bottom, right, top) in projected coordinates.
- Log the created bbox at INFO level (logging the final bbox tuple).
- Return the projected bbox tuple.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in projected (UTM) coordinates.
**Overload 5 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True], return_crs: Literal[True]) -> tuple[tuple[float, float, float, float], Any]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): Project the bbox polygon to UTM and return projected bounds.
- return_crs (Literal[True]): Also return the projected CRS object alongside the bbox.
**Behavior**:
- Perform the same steps as Overload 4 to compute projected bbox bounds and obtain crs_proj.
- Log the created bbox at INFO level.
- Return a 2-tuple: (bbox, crs_proj).
**Returns**:
- tuple[tuple[float, float, float, float], Any]: ( (left, bottom, right, top) in projected coordinates, projected CRS ).
**Overload 6 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True], return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): Project the bbox polygon to UTM.
- return_crs (Literal[False]): Do not return CRS.
**Behavior**:
- Same as Overload 4.
**Returns**:
- tuple[float, float, float, float]: Projected bbox bounds.
**Overload 7 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project; return unprojected bbox.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 8 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False], return_crs: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project.
- return_crs (Literal[True]): Accepted but ignored because CRS is only returned when project_utm is True.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 9 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False], return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project.
- return_crs (Literal[False]): Do not return CRS.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 10 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: bool=False, return_crs: bool=False) -> tuple[float, float, float, float] | tuple[tuple[float, float, float, float], Any]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (bool): If True, project the bbox polygon to UTM and return projected bounds.
- return_crs (bool): If True and project_utm is True, also return the projected CRS.
**Behavior**:
- Set constant EARTH_RADIUS_M = 6_371_009.
- Unpack point into lat, lon.
- Compute angular deltas corresponding to dist meters:
- delta_lat = rad2deg(dist / EARTH_RADIUS_M).
- delta_lon = rad2deg(dist / EARTH_RADIUS_M) / cos(deg2rad(lat)).
- Compute bbox edges in degrees:
- top = lat + delta_lat
- bottom = lat - delta_lat
- right = lon + delta_lon
- left = lon - delta_lon
- Form bbox = (left, bottom, right, top).
- If project_utm is True:
- Convert bbox to a Polygon using bbox_to_poly(bbox=bbox).
- Project the polygon using projection.project_geometry(bbox_poly), receiving (bbox_proj, crs_proj).
- Replace bbox with bbox_proj.bounds (a 4-tuple in projected coordinates).
- Log an INFO message via utils.log: "Created bbox {dist} meters from {point}: {bbox}".
- If project_utm is True and return_crs is True, return (bbox, crs_proj).
- Otherwise return bbox.
**Returns**:
- tuple[float, float, float, float]: If not returning CRS, returns (left, bottom, right, top) either in unprojected degrees (project_utm False) or projected coordinates (project_utm True).
- tuple[tuple[float, float, float, float], Any]: If project_utm True and return_crs True, returns (bbox, crs_proj).
**Notes**:
- The bbox tuple ordering is always (left, bottom, right, top).
- return_crs has an effect only when project_utm is True; otherwise only the bbox is returned.

---

## Function: bbox_from_point

```python
def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True], return_crs: Literal[True]) -> tuple[tuple[float, float, float, float], Any]
```

**bbox_from_point**: Compute a bounding box around a (lat, lon) point at a given meter distance in each cardinal direction, optionally projecting the bbox to UTM and optionally returning the projected CRS.
**Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: bool=False, return_crs: bool=False) -> tuple[float, float, float, float] | tuple[tuple[float, float, float, float], Any]
**Overload 1 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
**Behavior**:
- Compute an unprojected bbox in degrees around the point using the algorithm described below under the general behavior.
- Log the created bbox at INFO level.
- Return the bbox as (left, bottom, right, top).
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 2 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, return_crs: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- return_crs (Literal[True]): Accepted but has no effect unless project_utm is also True (not provided in this overload).
**Behavior**:
- Same as Overload 1: compute unprojected bbox, log it, and return only the bbox.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 3 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- return_crs (Literal[False]): Explicitly indicates CRS should not be returned.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 4 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): If True, project the bbox polygon to a UTM CRS and return projected bounds.
**Behavior**:
- Compute the initial unprojected bbox in degrees.
- Convert bbox to a Polygon via bbox_to_poly.
- Project that polygon via projection.project_geometry(bbox_poly), capturing (bbox_proj, crs_proj).
- Replace bbox with bbox_proj.bounds (left, bottom, right, top) in projected coordinates.
- Log the created bbox at INFO level (logging the final bbox tuple).
- Return the projected bbox tuple.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in projected (UTM) coordinates.
**Overload 5 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True], return_crs: Literal[True]) -> tuple[tuple[float, float, float, float], Any]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): Project the bbox polygon to UTM and return projected bounds.
- return_crs (Literal[True]): Also return the projected CRS object alongside the bbox.
**Behavior**:
- Perform the same steps as Overload 4 to compute projected bbox bounds and obtain crs_proj.
- Log the created bbox at INFO level.
- Return a 2-tuple: (bbox, crs_proj).
**Returns**:
- tuple[tuple[float, float, float, float], Any]: ( (left, bottom, right, top) in projected coordinates, projected CRS ).
**Overload 6 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True], return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): Project the bbox polygon to UTM.
- return_crs (Literal[False]): Do not return CRS.
**Behavior**:
- Same as Overload 4.
**Returns**:
- tuple[float, float, float, float]: Projected bbox bounds.
**Overload 7 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project; return unprojected bbox.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 8 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False], return_crs: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project.
- return_crs (Literal[True]): Accepted but ignored because CRS is only returned when project_utm is True.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 9 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False], return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project.
- return_crs (Literal[False]): Do not return CRS.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 10 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: bool=False, return_crs: bool=False) -> tuple[float, float, float, float] | tuple[tuple[float, float, float, float], Any]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (bool): If True, project the bbox polygon to UTM and return projected bounds.
- return_crs (bool): If True and project_utm is True, also return the projected CRS.
**Behavior**:
- Set constant EARTH_RADIUS_M = 6_371_009.
- Unpack point into lat, lon.
- Compute angular deltas corresponding to dist meters:
- delta_lat = rad2deg(dist / EARTH_RADIUS_M).
- delta_lon = rad2deg(dist / EARTH_RADIUS_M) / cos(deg2rad(lat)).
- Compute bbox edges in degrees:
- top = lat + delta_lat
- bottom = lat - delta_lat
- right = lon + delta_lon
- left = lon - delta_lon
- Form bbox = (left, bottom, right, top).
- If project_utm is True:
- Convert bbox to a Polygon using bbox_to_poly(bbox=bbox).
- Project the polygon using projection.project_geometry(bbox_poly), receiving (bbox_proj, crs_proj).
- Replace bbox with bbox_proj.bounds (a 4-tuple in projected coordinates).
- Log an INFO message via utils.log: "Created bbox {dist} meters from {point}: {bbox}".
- If project_utm is True and return_crs is True, return (bbox, crs_proj).
- Otherwise return bbox.
**Returns**:
- tuple[float, float, float, float]: If not returning CRS, returns (left, bottom, right, top) either in unprojected degrees (project_utm False) or projected coordinates (project_utm True).
- tuple[tuple[float, float, float, float], Any]: If project_utm True and return_crs True, returns (bbox, crs_proj).
**Notes**:
- The bbox tuple ordering is always (left, bottom, right, top).
- return_crs has an effect only when project_utm is True; otherwise only the bbox is returned.

---

## Function: bbox_from_point

```python
def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True], return_crs: Literal[False]) -> tuple[float, float, float, float]
```

**bbox_from_point**: Compute a bounding box around a (lat, lon) point at a given meter distance in each cardinal direction, optionally projecting the bbox to UTM and optionally returning the projected CRS.
**Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: bool=False, return_crs: bool=False) -> tuple[float, float, float, float] | tuple[tuple[float, float, float, float], Any]
**Overload 1 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
**Behavior**:
- Compute an unprojected bbox in degrees around the point using the algorithm described below under the general behavior.
- Log the created bbox at INFO level.
- Return the bbox as (left, bottom, right, top).
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 2 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, return_crs: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- return_crs (Literal[True]): Accepted but has no effect unless project_utm is also True (not provided in this overload).
**Behavior**:
- Same as Overload 1: compute unprojected bbox, log it, and return only the bbox.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 3 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- return_crs (Literal[False]): Explicitly indicates CRS should not be returned.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 4 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): If True, project the bbox polygon to a UTM CRS and return projected bounds.
**Behavior**:
- Compute the initial unprojected bbox in degrees.
- Convert bbox to a Polygon via bbox_to_poly.
- Project that polygon via projection.project_geometry(bbox_poly), capturing (bbox_proj, crs_proj).
- Replace bbox with bbox_proj.bounds (left, bottom, right, top) in projected coordinates.
- Log the created bbox at INFO level (logging the final bbox tuple).
- Return the projected bbox tuple.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in projected (UTM) coordinates.
**Overload 5 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True], return_crs: Literal[True]) -> tuple[tuple[float, float, float, float], Any]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): Project the bbox polygon to UTM and return projected bounds.
- return_crs (Literal[True]): Also return the projected CRS object alongside the bbox.
**Behavior**:
- Perform the same steps as Overload 4 to compute projected bbox bounds and obtain crs_proj.
- Log the created bbox at INFO level.
- Return a 2-tuple: (bbox, crs_proj).
**Returns**:
- tuple[tuple[float, float, float, float], Any]: ( (left, bottom, right, top) in projected coordinates, projected CRS ).
**Overload 6 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True], return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): Project the bbox polygon to UTM.
- return_crs (Literal[False]): Do not return CRS.
**Behavior**:
- Same as Overload 4.
**Returns**:
- tuple[float, float, float, float]: Projected bbox bounds.
**Overload 7 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project; return unprojected bbox.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 8 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False], return_crs: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project.
- return_crs (Literal[True]): Accepted but ignored because CRS is only returned when project_utm is True.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 9 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False], return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project.
- return_crs (Literal[False]): Do not return CRS.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 10 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: bool=False, return_crs: bool=False) -> tuple[float, float, float, float] | tuple[tuple[float, float, float, float], Any]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (bool): If True, project the bbox polygon to UTM and return projected bounds.
- return_crs (bool): If True and project_utm is True, also return the projected CRS.
**Behavior**:
- Set constant EARTH_RADIUS_M = 6_371_009.
- Unpack point into lat, lon.
- Compute angular deltas corresponding to dist meters:
- delta_lat = rad2deg(dist / EARTH_RADIUS_M).
- delta_lon = rad2deg(dist / EARTH_RADIUS_M) / cos(deg2rad(lat)).
- Compute bbox edges in degrees:
- top = lat + delta_lat
- bottom = lat - delta_lat
- right = lon + delta_lon
- left = lon - delta_lon
- Form bbox = (left, bottom, right, top).
- If project_utm is True:
- Convert bbox to a Polygon using bbox_to_poly(bbox=bbox).
- Project the polygon using projection.project_geometry(bbox_poly), receiving (bbox_proj, crs_proj).
- Replace bbox with bbox_proj.bounds (a 4-tuple in projected coordinates).
- Log an INFO message via utils.log: "Created bbox {dist} meters from {point}: {bbox}".
- If project_utm is True and return_crs is True, return (bbox, crs_proj).
- Otherwise return bbox.
**Returns**:
- tuple[float, float, float, float]: If not returning CRS, returns (left, bottom, right, top) either in unprojected degrees (project_utm False) or projected coordinates (project_utm True).
- tuple[tuple[float, float, float, float], Any]: If project_utm True and return_crs True, returns (bbox, crs_proj).
**Notes**:
- The bbox tuple ordering is always (left, bottom, right, top).
- return_crs has an effect only when project_utm is True; otherwise only the bbox is returned.

---

## Function: bbox_from_point

```python
def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False]) -> tuple[float, float, float, float]
```

**bbox_from_point**: Compute a bounding box around a (lat, lon) point at a given meter distance in each cardinal direction, optionally projecting the bbox to UTM and optionally returning the projected CRS.
**Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: bool=False, return_crs: bool=False) -> tuple[float, float, float, float] | tuple[tuple[float, float, float, float], Any]
**Overload 1 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
**Behavior**:
- Compute an unprojected bbox in degrees around the point using the algorithm described below under the general behavior.
- Log the created bbox at INFO level.
- Return the bbox as (left, bottom, right, top).
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 2 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, return_crs: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- return_crs (Literal[True]): Accepted but has no effect unless project_utm is also True (not provided in this overload).
**Behavior**:
- Same as Overload 1: compute unprojected bbox, log it, and return only the bbox.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 3 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- return_crs (Literal[False]): Explicitly indicates CRS should not be returned.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 4 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): If True, project the bbox polygon to a UTM CRS and return projected bounds.
**Behavior**:
- Compute the initial unprojected bbox in degrees.
- Convert bbox to a Polygon via bbox_to_poly.
- Project that polygon via projection.project_geometry(bbox_poly), capturing (bbox_proj, crs_proj).
- Replace bbox with bbox_proj.bounds (left, bottom, right, top) in projected coordinates.
- Log the created bbox at INFO level (logging the final bbox tuple).
- Return the projected bbox tuple.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in projected (UTM) coordinates.
**Overload 5 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True], return_crs: Literal[True]) -> tuple[tuple[float, float, float, float], Any]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): Project the bbox polygon to UTM and return projected bounds.
- return_crs (Literal[True]): Also return the projected CRS object alongside the bbox.
**Behavior**:
- Perform the same steps as Overload 4 to compute projected bbox bounds and obtain crs_proj.
- Log the created bbox at INFO level.
- Return a 2-tuple: (bbox, crs_proj).
**Returns**:
- tuple[tuple[float, float, float, float], Any]: ( (left, bottom, right, top) in projected coordinates, projected CRS ).
**Overload 6 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True], return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): Project the bbox polygon to UTM.
- return_crs (Literal[False]): Do not return CRS.
**Behavior**:
- Same as Overload 4.
**Returns**:
- tuple[float, float, float, float]: Projected bbox bounds.
**Overload 7 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project; return unprojected bbox.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 8 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False], return_crs: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project.
- return_crs (Literal[True]): Accepted but ignored because CRS is only returned when project_utm is True.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 9 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False], return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project.
- return_crs (Literal[False]): Do not return CRS.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 10 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: bool=False, return_crs: bool=False) -> tuple[float, float, float, float] | tuple[tuple[float, float, float, float], Any]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (bool): If True, project the bbox polygon to UTM and return projected bounds.
- return_crs (bool): If True and project_utm is True, also return the projected CRS.
**Behavior**:
- Set constant EARTH_RADIUS_M = 6_371_009.
- Unpack point into lat, lon.
- Compute angular deltas corresponding to dist meters:
- delta_lat = rad2deg(dist / EARTH_RADIUS_M).
- delta_lon = rad2deg(dist / EARTH_RADIUS_M) / cos(deg2rad(lat)).
- Compute bbox edges in degrees:
- top = lat + delta_lat
- bottom = lat - delta_lat
- right = lon + delta_lon
- left = lon - delta_lon
- Form bbox = (left, bottom, right, top).
- If project_utm is True:
- Convert bbox to a Polygon using bbox_to_poly(bbox=bbox).
- Project the polygon using projection.project_geometry(bbox_poly), receiving (bbox_proj, crs_proj).
- Replace bbox with bbox_proj.bounds (a 4-tuple in projected coordinates).
- Log an INFO message via utils.log: "Created bbox {dist} meters from {point}: {bbox}".
- If project_utm is True and return_crs is True, return (bbox, crs_proj).
- Otherwise return bbox.
**Returns**:
- tuple[float, float, float, float]: If not returning CRS, returns (left, bottom, right, top) either in unprojected degrees (project_utm False) or projected coordinates (project_utm True).
- tuple[tuple[float, float, float, float], Any]: If project_utm True and return_crs True, returns (bbox, crs_proj).
**Notes**:
- The bbox tuple ordering is always (left, bottom, right, top).
- return_crs has an effect only when project_utm is True; otherwise only the bbox is returned.

---

## Function: bbox_from_point

```python
def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False], return_crs: Literal[True]) -> tuple[float, float, float, float]
```

**bbox_from_point**: Compute a bounding box around a (lat, lon) point at a given meter distance in each cardinal direction, optionally projecting the bbox to UTM and optionally returning the projected CRS.
**Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: bool=False, return_crs: bool=False) -> tuple[float, float, float, float] | tuple[tuple[float, float, float, float], Any]
**Overload 1 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
**Behavior**:
- Compute an unprojected bbox in degrees around the point using the algorithm described below under the general behavior.
- Log the created bbox at INFO level.
- Return the bbox as (left, bottom, right, top).
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 2 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, return_crs: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- return_crs (Literal[True]): Accepted but has no effect unless project_utm is also True (not provided in this overload).
**Behavior**:
- Same as Overload 1: compute unprojected bbox, log it, and return only the bbox.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 3 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- return_crs (Literal[False]): Explicitly indicates CRS should not be returned.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 4 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): If True, project the bbox polygon to a UTM CRS and return projected bounds.
**Behavior**:
- Compute the initial unprojected bbox in degrees.
- Convert bbox to a Polygon via bbox_to_poly.
- Project that polygon via projection.project_geometry(bbox_poly), capturing (bbox_proj, crs_proj).
- Replace bbox with bbox_proj.bounds (left, bottom, right, top) in projected coordinates.
- Log the created bbox at INFO level (logging the final bbox tuple).
- Return the projected bbox tuple.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in projected (UTM) coordinates.
**Overload 5 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True], return_crs: Literal[True]) -> tuple[tuple[float, float, float, float], Any]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): Project the bbox polygon to UTM and return projected bounds.
- return_crs (Literal[True]): Also return the projected CRS object alongside the bbox.
**Behavior**:
- Perform the same steps as Overload 4 to compute projected bbox bounds and obtain crs_proj.
- Log the created bbox at INFO level.
- Return a 2-tuple: (bbox, crs_proj).
**Returns**:
- tuple[tuple[float, float, float, float], Any]: ( (left, bottom, right, top) in projected coordinates, projected CRS ).
**Overload 6 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True], return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): Project the bbox polygon to UTM.
- return_crs (Literal[False]): Do not return CRS.
**Behavior**:
- Same as Overload 4.
**Returns**:
- tuple[float, float, float, float]: Projected bbox bounds.
**Overload 7 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project; return unprojected bbox.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 8 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False], return_crs: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project.
- return_crs (Literal[True]): Accepted but ignored because CRS is only returned when project_utm is True.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 9 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False], return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project.
- return_crs (Literal[False]): Do not return CRS.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 10 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: bool=False, return_crs: bool=False) -> tuple[float, float, float, float] | tuple[tuple[float, float, float, float], Any]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (bool): If True, project the bbox polygon to UTM and return projected bounds.
- return_crs (bool): If True and project_utm is True, also return the projected CRS.
**Behavior**:
- Set constant EARTH_RADIUS_M = 6_371_009.
- Unpack point into lat, lon.
- Compute angular deltas corresponding to dist meters:
- delta_lat = rad2deg(dist / EARTH_RADIUS_M).
- delta_lon = rad2deg(dist / EARTH_RADIUS_M) / cos(deg2rad(lat)).
- Compute bbox edges in degrees:
- top = lat + delta_lat
- bottom = lat - delta_lat
- right = lon + delta_lon
- left = lon - delta_lon
- Form bbox = (left, bottom, right, top).
- If project_utm is True:
- Convert bbox to a Polygon using bbox_to_poly(bbox=bbox).
- Project the polygon using projection.project_geometry(bbox_poly), receiving (bbox_proj, crs_proj).
- Replace bbox with bbox_proj.bounds (a 4-tuple in projected coordinates).
- Log an INFO message via utils.log: "Created bbox {dist} meters from {point}: {bbox}".
- If project_utm is True and return_crs is True, return (bbox, crs_proj).
- Otherwise return bbox.
**Returns**:
- tuple[float, float, float, float]: If not returning CRS, returns (left, bottom, right, top) either in unprojected degrees (project_utm False) or projected coordinates (project_utm True).
- tuple[tuple[float, float, float, float], Any]: If project_utm True and return_crs True, returns (bbox, crs_proj).
**Notes**:
- The bbox tuple ordering is always (left, bottom, right, top).
- return_crs has an effect only when project_utm is True; otherwise only the bbox is returned.

---

## Function: bbox_from_point

```python
def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False], return_crs: Literal[False]) -> tuple[float, float, float, float]
```

**bbox_from_point**: Compute a bounding box around a (lat, lon) point at a given meter distance in each cardinal direction, optionally projecting the bbox to UTM and optionally returning the projected CRS.
**Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: bool=False, return_crs: bool=False) -> tuple[float, float, float, float] | tuple[tuple[float, float, float, float], Any]
**Overload 1 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
**Behavior**:
- Compute an unprojected bbox in degrees around the point using the algorithm described below under the general behavior.
- Log the created bbox at INFO level.
- Return the bbox as (left, bottom, right, top).
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 2 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, return_crs: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- return_crs (Literal[True]): Accepted but has no effect unless project_utm is also True (not provided in this overload).
**Behavior**:
- Same as Overload 1: compute unprojected bbox, log it, and return only the bbox.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 3 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- return_crs (Literal[False]): Explicitly indicates CRS should not be returned.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 4 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): If True, project the bbox polygon to a UTM CRS and return projected bounds.
**Behavior**:
- Compute the initial unprojected bbox in degrees.
- Convert bbox to a Polygon via bbox_to_poly.
- Project that polygon via projection.project_geometry(bbox_poly), capturing (bbox_proj, crs_proj).
- Replace bbox with bbox_proj.bounds (left, bottom, right, top) in projected coordinates.
- Log the created bbox at INFO level (logging the final bbox tuple).
- Return the projected bbox tuple.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in projected (UTM) coordinates.
**Overload 5 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True], return_crs: Literal[True]) -> tuple[tuple[float, float, float, float], Any]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): Project the bbox polygon to UTM and return projected bounds.
- return_crs (Literal[True]): Also return the projected CRS object alongside the bbox.
**Behavior**:
- Perform the same steps as Overload 4 to compute projected bbox bounds and obtain crs_proj.
- Log the created bbox at INFO level.
- Return a 2-tuple: (bbox, crs_proj).
**Returns**:
- tuple[tuple[float, float, float, float], Any]: ( (left, bottom, right, top) in projected coordinates, projected CRS ).
**Overload 6 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True], return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): Project the bbox polygon to UTM.
- return_crs (Literal[False]): Do not return CRS.
**Behavior**:
- Same as Overload 4.
**Returns**:
- tuple[float, float, float, float]: Projected bbox bounds.
**Overload 7 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project; return unprojected bbox.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 8 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False], return_crs: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project.
- return_crs (Literal[True]): Accepted but ignored because CRS is only returned when project_utm is True.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 9 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False], return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project.
- return_crs (Literal[False]): Do not return CRS.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 10 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: bool=False, return_crs: bool=False) -> tuple[float, float, float, float] | tuple[tuple[float, float, float, float], Any]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (bool): If True, project the bbox polygon to UTM and return projected bounds.
- return_crs (bool): If True and project_utm is True, also return the projected CRS.
**Behavior**:
- Set constant EARTH_RADIUS_M = 6_371_009.
- Unpack point into lat, lon.
- Compute angular deltas corresponding to dist meters:
- delta_lat = rad2deg(dist / EARTH_RADIUS_M).
- delta_lon = rad2deg(dist / EARTH_RADIUS_M) / cos(deg2rad(lat)).
- Compute bbox edges in degrees:
- top = lat + delta_lat
- bottom = lat - delta_lat
- right = lon + delta_lon
- left = lon - delta_lon
- Form bbox = (left, bottom, right, top).
- If project_utm is True:
- Convert bbox to a Polygon using bbox_to_poly(bbox=bbox).
- Project the polygon using projection.project_geometry(bbox_poly), receiving (bbox_proj, crs_proj).
- Replace bbox with bbox_proj.bounds (a 4-tuple in projected coordinates).
- Log an INFO message via utils.log: "Created bbox {dist} meters from {point}: {bbox}".
- If project_utm is True and return_crs is True, return (bbox, crs_proj).
- Otherwise return bbox.
**Returns**:
- tuple[float, float, float, float]: If not returning CRS, returns (left, bottom, right, top) either in unprojected degrees (project_utm False) or projected coordinates (project_utm True).
- tuple[tuple[float, float, float, float], Any]: If project_utm True and return_crs True, returns (bbox, crs_proj).
**Notes**:
- The bbox tuple ordering is always (left, bottom, right, top).
- return_crs has an effect only when project_utm is True; otherwise only the bbox is returned.

---

## Function: bbox_from_point

```python
def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: bool=False, return_crs: bool=False) -> tuple[float, float, float, float] | tuple[tuple[float, float, float, float], Any]
```

**bbox_from_point**: Compute a bounding box around a (lat, lon) point at a given meter distance in each cardinal direction, optionally projecting the bbox to UTM and optionally returning the projected CRS.
**Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: bool=False, return_crs: bool=False) -> tuple[float, float, float, float] | tuple[tuple[float, float, float, float], Any]
**Overload 1 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
**Behavior**:
- Compute an unprojected bbox in degrees around the point using the algorithm described below under the general behavior.
- Log the created bbox at INFO level.
- Return the bbox as (left, bottom, right, top).
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 2 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, return_crs: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- return_crs (Literal[True]): Accepted but has no effect unless project_utm is also True (not provided in this overload).
**Behavior**:
- Same as Overload 1: compute unprojected bbox, log it, and return only the bbox.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 3 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- return_crs (Literal[False]): Explicitly indicates CRS should not be returned.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in unprojected lon/lat degrees.
**Overload 4 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): If True, project the bbox polygon to a UTM CRS and return projected bounds.
**Behavior**:
- Compute the initial unprojected bbox in degrees.
- Convert bbox to a Polygon via bbox_to_poly.
- Project that polygon via projection.project_geometry(bbox_poly), capturing (bbox_proj, crs_proj).
- Replace bbox with bbox_proj.bounds (left, bottom, right, top) in projected coordinates.
- Log the created bbox at INFO level (logging the final bbox tuple).
- Return the projected bbox tuple.
**Returns**:
- tuple[float, float, float, float]: (left, bottom, right, top) in projected (UTM) coordinates.
**Overload 5 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True], return_crs: Literal[True]) -> tuple[tuple[float, float, float, float], Any]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): Project the bbox polygon to UTM and return projected bounds.
- return_crs (Literal[True]): Also return the projected CRS object alongside the bbox.
**Behavior**:
- Perform the same steps as Overload 4 to compute projected bbox bounds and obtain crs_proj.
- Log the created bbox at INFO level.
- Return a 2-tuple: (bbox, crs_proj).
**Returns**:
- tuple[tuple[float, float, float, float], Any]: ( (left, bottom, right, top) in projected coordinates, projected CRS ).
**Overload 6 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[True], return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[True]): Project the bbox polygon to UTM.
- return_crs (Literal[False]): Do not return CRS.
**Behavior**:
- Same as Overload 4.
**Returns**:
- tuple[float, float, float, float]: Projected bbox bounds.
**Overload 7 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project; return unprojected bbox.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 8 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False], return_crs: Literal[True]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project.
- return_crs (Literal[True]): Accepted but ignored because CRS is only returned when project_utm is True.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 9 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: Literal[False], return_crs: Literal[False]) -> tuple[float, float, float, float]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (Literal[False]): Do not project.
- return_crs (Literal[False]): Do not return CRS.
**Behavior**:
- Same as Overload 1.
**Returns**:
- tuple[float, float, float, float]: Unprojected bbox bounds.
**Overload 10 — Signature**: def bbox_from_point(point: tuple[float, float], dist: float, *, project_utm: bool=False, return_crs: bool=False) -> tuple[float, float, float, float] | tuple[tuple[float, float, float, float], Any]
**Parameters**:
- point (tuple[float, float]): Center point as (lat, lon) in degrees.
- dist (float): Distance in meters from the center to each side of the bbox.
- project_utm (bool): If True, project the bbox polygon to UTM and return projected bounds.
- return_crs (bool): If True and project_utm is True, also return the projected CRS.
**Behavior**:
- Set constant EARTH_RADIUS_M = 6_371_009.
- Unpack point into lat, lon.
- Compute angular deltas corresponding to dist meters:
- delta_lat = rad2deg(dist / EARTH_RADIUS_M).
- delta_lon = rad2deg(dist / EARTH_RADIUS_M) / cos(deg2rad(lat)).
- Compute bbox edges in degrees:
- top = lat + delta_lat
- bottom = lat - delta_lat
- right = lon + delta_lon
- left = lon - delta_lon
- Form bbox = (left, bottom, right, top).
- If project_utm is True:
- Convert bbox to a Polygon using bbox_to_poly(bbox=bbox).
- Project the polygon using projection.project_geometry(bbox_poly), receiving (bbox_proj, crs_proj).
- Replace bbox with bbox_proj.bounds (a 4-tuple in projected coordinates).
- Log an INFO message via utils.log: "Created bbox {dist} meters from {point}: {bbox}".
- If project_utm is True and return_crs is True, return (bbox, crs_proj).
- Otherwise return bbox.
**Returns**:
- tuple[float, float, float, float]: If not returning CRS, returns (left, bottom, right, top) either in unprojected degrees (project_utm False) or projected coordinates (project_utm True).
- tuple[tuple[float, float, float, float], Any]: If project_utm True and return_crs True, returns (bbox, crs_proj).
**Notes**:
- The bbox tuple ordering is always (left, bottom, right, top).
- return_crs has an effect only when project_utm is True; otherwise only the bbox is returned.

---

## Function: bbox_to_poly

```python
def bbox_to_poly(bbox: tuple[float, float, float, float]) -> Polygon
```

**bbox_to_poly**: Convert a bounding box tuple into a Shapely Polygon representing the rectangle.
**Signature**: def bbox_to_poly(bbox: tuple[float, float, float, float]) -> Polygon
**Parameters**:
- bbox (tuple[float, float, float, float]): Bounding box as (left, bottom, right, top).
**Behavior**:
- Unpack bbox into left, bottom, right, top.
- Construct and return a shapely Polygon from the four corner coordinates in this order:
- (left, bottom)
- (right, bottom)
- (right, top)
- (left, top)
- The polygon is implicitly closed by Shapely.
**Returns**:
- Polygon: A rectangular polygon corresponding to the input bounding box.
