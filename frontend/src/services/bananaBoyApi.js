import axios from 'axios';
import { API_BASE_URL } from '../utils/api';

axios.defaults.withCredentials = true;

const BASE = `${API_BASE_URL}/banana-boy`;

export async function fetchMessages() {
    const { data } = await axios.get(`${BASE}/messages`);
    return data.messages;
}

export async function sendMessage(message) {
    const { data } = await axios.post(`${BASE}/chat`, { message });
    return data.message;
}

export async function clearMessages() {
    await axios.delete(`${BASE}/messages`);
}
