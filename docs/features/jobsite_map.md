# Feature Contract: Jobsite Geofence Map

## Goal

Provide a map visualization of jobsites.

Each jobsite appears as a colored geofence showing its operational area.

Color represents the assigned project manager.

Users should be able to click a jobsite and open navigation directions.

---

# Architecture

Database
→ Flask API
→ GeoJSON polygons
→ React Map Component
→ MapLibre Map

---

# Data Model

Jobsites table fields:

* id
* name
* address
* latitude
* longitude
* radius_meters
* pm_id
* geofence_geojson

Project managers table:

* id
* name
* color

The `geofence_geojson` column stores a polygon representing the jobsite radius.

---

# Polygon Generation

Polygons must be generated using the Python library:

Shapely.

Input:

* latitude
* longitude
* radius_meters

Output:

GeoJSON Polygon.

Polygon should approximate a circle.

---

# Polygon Generation Utility

Location:

```
app/brain/map/utils/geofence.py
```

Function:

```
generate_geofence_polygon(lat, lon, radius_meters)
```

Returns GeoJSON geometry.

---

# Polygon Lifecycle

Polygons should be generated:

* when a jobsite is created
* when latitude changes
* when longitude changes
* when radius_meters changes

Polygons should not be generated during API requests.

---

# Map API

Endpoint:

```
GET /brain/jobsites/map
```

Returns GeoJSON FeatureCollection.

Each feature contains:

Properties:

* job_name
* address
* pm_name
* pm_color

Geometry:

* Polygon

---

# Admin Polygon Regeneration

Provide an admin endpoint:

```
POST /admin/jobsites/regenerate-geofences
```

This endpoint:

* queries all jobsites
* regenerates geofence polygons
* updates the database

Response example:

```
{
  "jobsites_updated": 142
}
```

---

# Frontend Map Component

Location:

```
frontend/src/pages/maps/JobsiteMap.tsx
```

Responsibilities:

* fetch `/brain/jobsites/map`
* render polygons
* show popup on click
* fit map to jobsites

Architecture:

* Similar to Drafting Work Load and Job Log, data fetching should use hooks and services setup for API calls.

Use MapLibre GL JS.

---

# Popup

Clicking a jobsite polygon shows:

Job name
Address
Project manager

Include button:

Get Directions

---

# Directions Link

Use:

```
https://www.google.com/maps/dir/?api=1&destination=LAT,LNG
```

This opens:

* Google Maps
* Apple Maps

depending on device.

---

# Map Style

Use simple OpenStreetMap tiles.

Geofence style:

* fill opacity ~0.3
* outline width ~2px
* color from pm_color

---

# Constraints

Use free tools only.

Do not use Google Maps SDK.

Keep implementation simple.

Avoid unnecessary libraries.
