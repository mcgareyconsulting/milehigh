/**
 * N1 billing classifier for releases (Contracted / Change Order / MHMW Cost).
 * Stored values match app.models.RELEASE_TAGS. Required on create; nullable in DB.
 */

export const RELEASE_TAGS = [
    { value: 'contracted', label: 'Contracted' },
    { value: 'change_order', label: 'Change Order' },
    { value: 'mhmw_cost', label: 'MHMW Cost' },
];

export const RELEASE_TAG_VALUES = RELEASE_TAGS.map((t) => t.value);

export function releaseTagLabel(value) {
    if (!value) return null;
    const hit = RELEASE_TAGS.find((t) => t.value === value);
    return hit ? hit.label : value;
}
