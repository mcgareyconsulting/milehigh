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
