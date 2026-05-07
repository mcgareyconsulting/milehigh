import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

axios.defaults.withCredentials = true;

const BASE = `${API_BASE_URL}/admin/fc-collection`;

export async function fetchFcCollectionRuns() {
    const { data } = await axios.get(`${BASE}/runs`);
    return data.runs;
}

export async function fetchFcCollectionRunDetail(runId) {
    const { data } = await axios.get(`${BASE}/runs/${runId}`);
    return data;
}

export async function triggerFcCollectionRun() {
    const { data } = await axios.post(`${BASE}/run-now`);
    return data;
}
