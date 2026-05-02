import { API_BASE_URL } from '../utils/api';

export const buildGoogleLinkUrl = (next) =>
    `${API_BASE_URL}/api/auth/google/initiate?next=${encodeURIComponent(next)}`;

export const GOOGLE_ERROR_MESSAGES = {
    state_mismatch: 'Connection expired. Please try again.',
    state_expired: 'Connection expired. Please try again.',
    access_denied: 'Connection was cancelled.',
    not_configured: 'Google connection is not configured on the server.',
    token_exchange_failed: "Couldn't complete the Google connection.",
    invalid_id_token: "Couldn't verify Google identity.",
    missing_id_token: "Couldn't verify Google identity.",
    missing_code: "The Google connection didn't complete.",
    email_unverified: 'Your Google email is not verified.',
    scope_missing: 'Gmail access was not granted — please retry and allow read access.',
    login_required: 'Please sign in first.',
    session_lost: 'Your session expired during the Google round-trip. Please log in and try again.',
    already_linked_other_user: 'That Google account is already linked to a different MHMW user.',
};

export const messageForGoogleError = (code) =>
    GOOGLE_ERROR_MESSAGES[code] || (code ? "Couldn't connect Google." : null);
