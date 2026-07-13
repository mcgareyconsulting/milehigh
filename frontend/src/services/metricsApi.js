/**
 * @milehigh-header
 * schema_version: 1
 * purpose: HTTP client for the admin system-usage metrics endpoints (AI spend, content, activity, health).
 * exports:
 *   getSummary, getAi, getContent, getActivity, getSystem, getDigest — each takes a period ('day'|'week'|'month').
 * imports_from: [axios, ../utils/api]
 * imported_by: [pages/Metrics.jsx]
 * invariants:
 *   - axios.defaults.withCredentials is set globally so session cookies are sent (admin-gated routes).
 *   - All endpoints are prefixed with /brain/metrics and share a {period,start,end,generated_at,...} envelope.
 */
import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

axios.defaults.withCredentials = true;

const BASE = `${API_BASE_URL}/brain/metrics`;

async function _get(path, period) {
    const { data } = await axios.get(`${BASE}/${path}`, { params: { period } });
    return data;
}

export const getSummary = (period = 'week') => _get('summary', period);
export const getAi = (period = 'week') => _get('ai', period);
export const getContent = (period = 'week') => _get('content', period);
export const getActivity = (period = 'week') => _get('activity', period);
export const getSystem = (period = 'week') => _get('system', period);
export const getDigest = (period = 'week') => _get('digest', period);
