import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

axios.defaults.withCredentials = true;

const BASE = `${API_BASE_URL}/brain/submittal-matching`;

export async function fetchMatchingProjects() {
    const { data } = await axios.get(`${BASE}/projects`);
    return data.projects;
}

export async function fetchMatchingDrrs(project) {
    const { data } = await axios.get(`${BASE}/drrs`, { params: { project } });
    return data;
}

export async function linkSubmittalRelease(submittalPk, releaseId) {
    const { data } = await axios.post(`${BASE}/${submittalPk}/link`, { release_id: releaseId });
    return data;
}

export async function unlinkSubmittalRelease(submittalPk) {
    const { data } = await axios.post(`${BASE}/${submittalPk}/unlink`);
    return data;
}

export async function markSubmittalNoMatch(submittalPk) {
    const { data } = await axios.post(`${BASE}/${submittalPk}/no-match`);
    return data;
}
