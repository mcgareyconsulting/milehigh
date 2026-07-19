/**
 * @milehigh-header
 * schema_version: 1
 * purpose: HTTP client for the next-week installation schedule endpoint.
 * exports:
 *   getNextWeekSchedule(days=7) — returns {window, summary, crews[]} envelope.
 * imports_from: [axios, ../utils/api]
 * imported_by: [pages/InstallSchedule.jsx]
 * invariants:
 *   - Read-only GET; axios.defaults.withCredentials sends the session cookie (login-gated route).
 */
import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

axios.defaults.withCredentials = true;

export const getNextWeekSchedule = async (days = 7) => {
    const { data } = await axios.get(`${API_BASE_URL}/brain/install-schedule/next-week`, {
        params: { days },
    });
    return data;
};
