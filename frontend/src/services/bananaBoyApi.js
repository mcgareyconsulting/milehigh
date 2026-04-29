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

export async function sendVoiceMessage(audioBlob, filename = 'voice.webm') {
    const fd = new FormData();
    fd.append('audio', audioBlob, filename);
    const { data } = await axios.post(`${BASE}/voice/chat`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data; // { transcript, message, audio_b64, audio_mime }
}

export async function clearMessages() {
    await axios.delete(`${BASE}/messages`);
}

export async function setBananaBoyPreferences({ wants_daily_brief }) {
    const { data } = await axios.put(`${BASE}/preferences`, { wants_daily_brief });
    return data;
}
