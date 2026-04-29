import { API_BASE_URL } from '../utils/api';

export const buildMicrosoftLinkUrl = (next) =>
    `${API_BASE_URL}/api/auth/microsoft/initiate?next=${encodeURIComponent(next)}`;

export const MICROSOFT_ERROR_MESSAGES = {
    state_mismatch: 'Connection expired. Please try again.',
    state_expired: 'Connection expired. Please try again.',
    access_denied: 'Connection was cancelled.',
    not_configured: 'Microsoft connection is not configured on the server.',
    token_exchange_failed: "Couldn't complete the Microsoft connection.",
    profile_fetch_failed: "Couldn't read your Microsoft profile.",
    profile_invalid: "Microsoft returned an invalid profile.",
    missing_code: "The Microsoft connection didn't complete.",
    scope_missing: 'Outlook access was not granted — please retry and allow Mail.Read.',
    login_required: 'Please sign in first.',
    session_lost: 'Your session expired during the Microsoft round-trip. Please log in and try again.',
    already_linked_other_user: 'That Microsoft account is already linked to a different MHMW user.',
};

export const messageForMicrosoftError = (code) =>
    MICROSOFT_ERROR_MESSAGES[code] || (code ? "Couldn't connect Microsoft." : null);
