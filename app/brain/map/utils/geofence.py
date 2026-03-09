import math
from shapely.geometry import Polygon, mapping


def generate_geofence_polygon(lat, lon, radius_meters, num_points=64):
    """
    Generate a GeoJSON polygon approximating a circle around a lat/lon point.

    Uses a degree-based approximation that is accurate enough for jobsite-scale
    radii (tens to hundreds of meters). No external projection library required.

    Args:
        lat: Latitude of center point
        lon: Longitude of center point
        radius_meters: Radius of the circle in meters
        num_points: Number of vertices in the polygon (default 64)

    Returns:
        GeoJSON geometry dict with type "Polygon"
    """
    lat_radius = radius_meters / 111320.0
    lng_radius = radius_meters / (111320.0 * math.cos(math.radians(lat)))

    coords = []
    for i in range(num_points):
        angle = 2 * math.pi * i / num_points
        coords.append((
            lon + lng_radius * math.cos(angle),
            lat + lat_radius * math.sin(angle),
        ))
    coords.append(coords[0])  # close the ring

    return mapping(Polygon(coords))
