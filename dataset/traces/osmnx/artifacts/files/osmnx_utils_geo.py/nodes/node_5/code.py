from __future__ import annotations

import warnings
from math import ceil
from typing import Any, Iterator, Literal, overload

import numpy as np

try:
    import geopandas as gpd  # type: ignore
except Exception:  # pragma: no cover
    gpd = None  # type: ignore

try:
    import networkx as nx  # type: ignore
except Exception:  # pragma: no cover
    nx = None  # type: ignore

try:
    from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon  # type: ignore
    from shapely.ops import split  # type: ignore
except Exception as e:  # pragma: no cover
    raise ImportError("Shapely is required to use this module.") from e

try:
    from shapely.geometry.base import BaseGeometry  # type: ignore
except Exception:  # pragma: no cover
    BaseGeometry = object  # type: ignore

Geometry = BaseGeometry

try:
    from . import convert, projection, settings, utils  # type: ignore
except Exception:  # pragma: no cover
    convert = None  # type: ignore
    projection = None  # type: ignore
    settings = None  # type: ignore
    utils = None  # type: ignore


def buffer_geometry(geom: Geometry, dist: float) -> Geometry:
    geom_proj, crs_proj = projection.project_geometry(geom)
    geom_buff_proj = geom_proj.buffer(dist)
    geom_buff, _ = projection.project_geometry(geom_buff_proj, crs=crs_proj, to_latlong=True)
    return geom_buff


def sample_points(G: "nx.MultiGraph", n: int) -> "gpd.GeoSeries":
    if nx.is_directed(G):
        warnings.warn(
            "G should be undirected to avoid oversampling bidirectional edges.",
            UserWarning,
            stacklevel=2,
        )

    gdf_edges = convert.graph_to_gdfs(G, nodes=False)[["geometry", "length"]]
    lengths = gdf_edges["length"].to_numpy()
    weights = lengths / lengths.sum()

    rng_edges = np.random.default_rng()
    chosen_idx = rng_edges.choice(gdf_edges.index.to_numpy(), size=n, replace=True, p=weights)

    lines = gdf_edges.loc[chosen_idx, "geometry"]
    rng_pos = np.random.default_rng()
    positions = rng_pos.random(n)

    points = lines.interpolate(positions, normalized=True)
    return points


def interpolate_points(geom: LineString | MultiLineString, dist: float) -> Iterator[tuple[float, float]]:
    if not isinstance(geom, (LineString, MultiLineString)):
        raise TypeError("`geom` must be a LineString.")
    num_vert = max(round(geom.length / dist), 1)
    for n in range(num_vert + 1):
        f = n / num_vert
        pt = geom.interpolate(f, normalized=True)
        yield (pt.x, pt.y)


def _quadrat_cut_geometry(geom: Polygon | MultiPolygon, quadrat_width: float) -> MultiPolygon:
    min_num = 3
    left, bottom, right, top = geom.bounds

    x_num = int(ceil((right - left) / quadrat_width) + 1)
    y_num = int(ceil((top - bottom) / quadrat_width) + 1)

    x_points = np.linspace(left, right, num=max(x_num, min_num))
    y_points = np.linspace(bottom, top, num=max(y_num, min_num))

    vertical_lines = [LineString([(x, y_points[0]), (x, y_points[-1])]) for x in x_points]
    horizont_lines = [LineString([(x_points[0], y), (x_points[-1], y)]) for y in y_points]
    lines = vertical_lines + horizont_lines

    geoms: list[Any] = [geom]
    for line in lines:
        new_geoms: list[Any] = []
        for g in geoms:
            if g.intersects(line):
                new_geoms.extend(list(split(g, line).geoms))
            else:
                new_geoms.append(g)
        geoms = new_geoms

    return MultiPolygon(geoms)


def _consolidate_subdivide_geometry(geom: Polygon | MultiPolygon) -> MultiPolygon:
    if not isinstance(geom, (Polygon, MultiPolygon)):
        raise TypeError("Geometry must be a shapely Polygon or MultiPolygon.")

    mqas = settings.max_query_area_size

    hull_applied = False
    if isinstance(geom, MultiPolygon):
        geom = geom.convex_hull
        hull_applied = True
    elif isinstance(geom, Polygon) and geom.area > mqas:
        geom = geom.convex_hull
        hull_applied = True

    if hull_applied:
        ratio = int(geom.area / mqas)
        if ratio > 10:
            warnings.warn(
                f"Geometry's area is {ratio} times the configured maximum query area size; "
                "it will be divided into multiple sub-queries and may take a long time.",
                UserWarning,
                stacklevel=2,
            )

    if geom.area > mqas:
        cut = _quadrat_cut_geometry(geom, quadrat_width=float(np.sqrt(mqas)))

        parts: list[Polygon] = []

        def add_poly(p: Polygon) -> None:
            if not p.is_empty:
                parts.append(p)

        if isinstance(cut, Polygon):
            add_poly(cut)
        elif isinstance(cut, MultiPolygon):
            for p in cut.geoms:
                if isinstance(p, Polygon):
                    add_poly(p)
        else:
            geoms_attr = getattr(cut, "geoms", None)
            if geoms_attr is not None:
                for g in geoms_attr:
                    if isinstance(g, Polygon):
                        add_poly(g)
                    elif isinstance(g, MultiPolygon):
                        for p in g.geoms:
                            if isinstance(p, Polygon):
                                add_poly(p)

        if not parts:
            raise ValueError("Subdivision did not produce any polygonal output.")

        return MultiPolygon(parts)

    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    if isinstance(geom, MultiPolygon):
        return geom

    raise ValueError("Consolidation did not produce a polygonal geometry.")


def _intersect_index_quadrats(geoms: "gpd.GeoSeries", polygon: Polygon | MultiPolygon) -> set[Any]:
    rtree = geoms.sindex
    utils.log(f"Built r-tree spatial index for {len(geoms):,} geometries", level="INFO")

    quadrat_width = max(0.1, float(np.sqrt(polygon.area)) / 10)
    multipoly = _quadrat_cut_geometry(polygon, quadrat_width)
    utils.log(f"Accelerating r-tree with {len(multipoly.geoms)} quadrats", level="INFO")

    geoms_in_poly: set[Any] = set()
    for poly in multipoly.geoms:
        poly_buff = poly.buffer(0)
        if poly_buff.is_valid and poly_buff.area > 0:
            possible_matches_iloc = list(rtree.intersection(poly_buff.bounds))
            possible_matches = geoms.iloc[possible_matches_iloc]
            precise = possible_matches[possible_matches.intersects(poly_buff)]
            geoms_in_poly.update(set(precise.index))

    utils.log(f"Identified {len(geoms_in_poly):,} geometries inside polygon", level="INFO")
    return geoms_in_poly


@overload
def bbox_from_point(point: tuple[float, float], dist: float) -> tuple[float, float, float, float]: ...


@overload
def bbox_from_point(
    point: tuple[float, float], dist: float, *, return_crs: Literal[True]
) -> tuple[float, float, float, float]: ...


@overload
def bbox_from_point(
    point: tuple[float, float], dist: float, *, return_crs: Literal[False]
) -> tuple[float, float, float, float]: ...


@overload
def bbox_from_point(
    point: tuple[float, float], dist: float, *, project_utm: Literal[True]
) -> tuple[float, float, float, float]: ...


@overload
def bbox_from_point(
    point: tuple[float, float], dist: float, *, project_utm: Literal[True], return_crs: Literal[True]
) -> tuple[tuple[float, float, float, float], Any]: ...


@overload
def bbox_from_point(
    point: tuple[float, float], dist: float, *, project_utm: Literal[True], return_crs: Literal[False]
) -> tuple[float, float, float, float]: ...


@overload
def bbox_from_point(
    point: tuple[float, float], dist: float, *, project_utm: Literal[False]
) -> tuple[float, float, float, float]: ...


@overload
def bbox_from_point(
    point: tuple[float, float], dist: float, *, project_utm: Literal[False], return_crs: Literal[True]
) -> tuple[float, float, float, float]: ...


@overload
def bbox_from_point(
    point: tuple[float, float], dist: float, *, project_utm: Literal[False], return_crs: Literal[False]
) -> tuple[float, float, float, float]: ...


@overload
def bbox_from_point(
    point: tuple[float, float], dist: float, *, project_utm: bool = False, return_crs: bool = False
) -> tuple[float, float, float, float] | tuple[tuple[float, float, float, float], Any]: ...


def bbox_from_point(
    point: tuple[float, float], dist: float, *, project_utm: bool = False, return_crs: bool = False
) -> tuple[float, float, float, float] | tuple[tuple[float, float, float, float], Any]:
    EARTH_RADIUS_M = 6_371_009

    lat, lon = point
    delta_lat = np.rad2deg(dist / EARTH_RADIUS_M)
    delta_lon = np.rad2deg(dist / EARTH_RADIUS_M) / np.cos(np.deg2rad(lat))

    top = lat + delta_lat
    bottom = lat - delta_lat
    right = lon + delta_lon
    left = lon - delta_lon

    bbox: tuple[float, float, float, float] = (left, bottom, right, top)

    crs_proj: Any = None
    if project_utm:
        bbox_poly = bbox_to_poly(bbox=bbox)
        bbox_proj, crs_proj = projection.project_geometry(bbox_poly)
        bbox = bbox_proj.bounds  # type: ignore[assignment]

    utils.log(f"Created bbox {dist} meters from {point}: {bbox}", level="INFO")

    if project_utm and return_crs:
        return bbox, crs_proj
    return bbox


def bbox_to_poly(bbox: tuple[float, float, float, float]) -> Polygon:
    left, bottom, right, top = bbox
    return Polygon([(left, bottom), (right, bottom), (right, top), (left, top)])
