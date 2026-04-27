// Mention extraction shared between frontend and backend.
//
// The MentionInput component inserts `@FirstName` tokens during typing using
// a different (trailing) regex; this MENTION_RE matches the backend's
// `re.findall(r'@(\w+)')` in app/brain/mentions.py so frontend code that
// previews or counts mentions stays consistent with what the server extracts
// when it parses saved comments and creates Notification rows.
export const MENTION_RE = /@(\w+)/g;

export function parseMentions(text) {
    if (!text) return [];
    return Array.from(text.matchAll(MENTION_RE), (m) => m[1].toLowerCase());
}
