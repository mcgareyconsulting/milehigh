/**
 * @milehigh-header
 * schema_version: 1
 * purpose: Provides a React context for browser geolocation state so the DWL and map pages can filter by user proximity.
 * exports:
 *   LocationProvider: Context provider managing geolocation toggle, requesting, and coords
 *   useLocationContext: Hook to consume the location context
 * imports_from: [react]
 * imported_by: [pages/DraftingWorkLoad.jsx, components/AppShell.jsx]
 * invariants:
 *   - locationFilter is null when disabled; consumers must null-check before using coords
 *   - Uses high-accuracy geolocation with a 10-second timeout
 * updated_by_agent: 2026-04-14T00:00:00Z (commit e133a47)
 */
import { createContext, useCallback, useContext, useState } from 'react';

const LocationContext = createContext(null);

export function LocationProvider({ children }) {
    const [locationEnabled, setLocationEnabled] = useState(false);
    const [userCoords, setUserCoords] = useState(null);
    const [locationRequesting, setLocationRequesting] = useState(false);

    const locationFilter = locationEnabled && userCoords ? userCoords : null;

    const handleLocationToggle = useCallback(() => {
        if (locationEnabled) {
            setLocationEnabled(false);
            setUserCoords(null);
            return;
        }
        setLocationRequesting(true);
        if (!navigator.geolocation) {
            setLocationRequesting(false);
            return;
        }
        navigator.geolocation.getCurrentPosition(
            (position) => {
                setUserCoords({ lat: position.coords.latitude, lng: position.coords.longitude });
                setLocationEnabled(true);
                setLocationRequesting(false);
            },
            () => {
                setLocationRequesting(false);
                setLocationEnabled(false);
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
        );
    }, [locationEnabled]);

    return (
        <LocationContext.Provider value={{ locationEnabled, locationRequesting, locationFilter, handleLocationToggle }}>
            {children}
        </LocationContext.Provider>
    );
}

export function useLocationContext() {
    return useContext(LocationContext);
}
