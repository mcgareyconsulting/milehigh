import { useEffect, useRef } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { useJobsiteMap } from '../../hooks/useJobsiteMap';

const OSM_STYLE = {
    version: 8,
    sources: {
        osm: {
            type: 'raster',
            tiles: ['https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png'],
            tileSize: 256,
            attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors © <a href="https://carto.com/attributions">CARTO</a>',
        },
    },
    layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
};

export default function JobsiteMap() {
    const mapContainer = useRef(null);
    const mapRef = useRef(null);
    const { geojson, loading, error } = useJobsiteMap();

    useEffect(() => {
        if (!mapContainer.current) return;

        // Destroy any existing instance (handles React StrictMode double-invoke)
        if (mapRef.current) {
            mapRef.current.remove();
            mapRef.current = null;
        }

        const map = new maplibregl.Map({
            container: mapContainer.current,
            style: OSM_STYLE,
            center: [-104.9903, 39.7392],
            zoom: 10,
        });

        mapRef.current = map;
        map.addControl(new maplibregl.NavigationControl(), 'top-right');

        return () => {
            map.remove();
            mapRef.current = null;
        };
    }, []);

    // Add geofence layers when data arrives
    useEffect(() => {
        if (!mapRef.current || !geojson) return;

        const setup = () => {
            if (mapRef.current.getSource('jobsites')) {
                mapRef.current.removeLayer('jobsites-fill');
                mapRef.current.removeLayer('jobsites-outline');
                mapRef.current.removeSource('jobsites');
            }

            mapRef.current.addSource('jobsites', { type: 'geojson', data: geojson });

            mapRef.current.addLayer({
                id: 'jobsites-fill',
                type: 'fill',
                source: 'jobsites',
                paint: {
                    'fill-color': ['get', 'pm_color'],
                    'fill-opacity': 0.3,
                },
            });

            mapRef.current.addLayer({
                id: 'jobsites-outline',
                type: 'line',
                source: 'jobsites',
                paint: {
                    'line-color': ['get', 'pm_color'],
                    'line-width': 2,
                },
            });

            if (geojson.features.length > 0) {
                const bounds = new maplibregl.LngLatBounds();
                geojson.features.forEach(f => {
                    f.geometry?.coordinates?.[0]?.forEach(coord => bounds.extend(coord));
                });
                if (!bounds.isEmpty()) {
                    mapRef.current.fitBounds(bounds, { padding: 60 });
                }
            }

            mapRef.current.on('click', 'jobsites-fill', (e) => {
                const p = e.features[0].properties;
                const directionsUrl =
                    `https://www.google.com/maps/dir/?api=1&destination=${p.latitude},${p.longitude}`;

                new maplibregl.Popup({ maxWidth: '240px' })
                    .setLngLat(e.lngLat)
                    .setHTML(`
                        <div style="font-family:sans-serif;padding:4px 2px">
                            <strong style="font-size:14px">${p.job_name}</strong>
                            ${p.address ? `<p style="margin:6px 0 2px;color:#555;font-size:13px">${p.address}</p>` : ''}
                            ${p.pm_name ? `<p style="margin:4px 0;font-size:13px">PM: ${p.pm_name}</p>` : ''}
                            <a href="${directionsUrl}" target="_blank" rel="noopener noreferrer"
                               style="display:inline-block;margin-top:8px;padding:5px 12px;
                                      background:#2563eb;color:#fff;border-radius:4px;
                                      text-decoration:none;font-size:13px">
                                Get Directions
                            </a>
                        </div>
                    `)
                    .addTo(mapRef.current);
            });

            mapRef.current.on('mouseenter', 'jobsites-fill', () => {
                mapRef.current.getCanvas().style.cursor = 'pointer';
            });
            mapRef.current.on('mouseleave', 'jobsites-fill', () => {
                mapRef.current.getCanvas().style.cursor = '';
            });
        };

        if (mapRef.current.isStyleLoaded()) {
            setup();
        } else {
            mapRef.current.once('load', setup);
        }
    }, [geojson]);

    return (
        <div className="relative" style={{ height: 'calc(100vh - 3.5rem)' }}>
            {loading && (
                <div className="absolute inset-0 flex items-center justify-center bg-white/80 z-10">
                    <span className="text-gray-600">Loading jobsites...</span>
                </div>
            )}
            {error && (
                <div className="absolute inset-0 flex items-center justify-center bg-white/80 z-10">
                    <span className="text-red-500">Error: {error}</span>
                </div>
            )}
            {!loading && !error && geojson?.features?.length === 0 && (
                <div className="absolute inset-0 flex items-center justify-center z-10 pointer-events-none">
                    <div className="bg-white/90 rounded-lg px-6 py-4 text-center shadow-md pointer-events-auto">
                        <p className="text-gray-700 font-medium">No jobsites found</p>
                        <p className="text-gray-500 text-sm mt-1">
                            Jobsites with geofence polygons will appear here.
                        </p>
                    </div>
                </div>
            )}
            <div ref={mapContainer} style={{ width: '100%', height: '100%' }} />
        </div>
    );
}
