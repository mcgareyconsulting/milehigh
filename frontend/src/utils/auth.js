// Auth utility functions
import { API_BASE_URL } from './api';

export const checkAuth = async () => {
    try {
        const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
            credentials: 'include'
        });
        if (response.ok) {
            const data = await response.json();
            return data;
        }
        return null;
    } catch (err) {
        return null;
    }
};

export const logout = async () => {
    try {
        await fetch(`${API_BASE_URL}/api/auth/logout`, {
            method: 'POST',
            credentials: 'include'
        });
    } catch (err) {
        console.error('Logout error:', err);
    }
};

