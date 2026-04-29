"""Tests for generate_geofence_polygon — verify it produces true circles in meters."""
import math

from app.brain.map.utils.geofence import generate_geofence_polygon


def _polygon_extents_meters(polygon, center_lat):
    coords = polygon["coordinates"][0]
    lats = [c[1] for c in coords]
    lngs = [c[0] for c in coords]
    ns_meters = (max(lats) - min(lats)) * 111320.0 / 2
    ew_meters = (max(lngs) - min(lngs)) * 111320.0 * math.cos(math.radians(center_lat)) / 2
    return ns_meters, ew_meters


def test_polygon_is_a_circle_in_meters_at_denver():
    radius = 1000.0
    poly = generate_geofence_polygon(lat=39.74, lon=-104.99, radius_meters=radius)
    ns, ew = _polygon_extents_meters(poly, center_lat=39.74)
    assert abs(ns - radius) / radius < 0.01
    assert abs(ew - radius) / radius < 0.01
    assert abs(ew / ns - 1.0) < 0.01


def test_polygon_is_a_circle_at_high_latitude():
    radius = 500.0
    poly = generate_geofence_polygon(lat=60.0, lon=10.0, radius_meters=radius)
    ns, ew = _polygon_extents_meters(poly, center_lat=60.0)
    assert abs(ew / ns - 1.0) < 0.01


def test_polygon_ring_is_closed():
    poly = generate_geofence_polygon(lat=39.74, lon=-104.99, radius_meters=1000)
    coords = poly["coordinates"][0]
    assert coords[0] == coords[-1]
