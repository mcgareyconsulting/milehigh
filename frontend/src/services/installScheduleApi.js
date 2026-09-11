/**
 * @milehigh-header
 * schema_version: 2
 * purpose: HTTP client for the installation schedule endpoints — the same cards in two groupings.
 * exports:
 *   getNextWeekSchedule(days=7) — {window, summary, crews[]} envelope (crew columns, desktop).
 *   getDaySchedule({days, pastDays, installer}) — {window, summary, past_due[], days[]} envelope
 *     (day rows, the vertical calendar).
 * imports_from: [axios, ../utils/api]
 * imported_by: [pages/InstallSchedule.jsx]
 * invariants:
 *   - Read-only GETs; axios.defaults.withCredentials sends the session cookie (login-gated routes).
 *   - `installer` is omitted rather than sent empty when no crew filter is set — the backend treats a
 *     blank string as "no filter", but leaving it out keeps the request URL honest in the network log.
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

export const getDaySchedule = async ({ days = 14, pastDays = 14, installer = null } = {}) => {
    const params = { days, past_days: pastDays };
    if (installer) params.installer = installer;
    const { data } = await axios.get(`${API_BASE_URL}/brain/install-schedule/by-day`, { params });
    return data;
};
