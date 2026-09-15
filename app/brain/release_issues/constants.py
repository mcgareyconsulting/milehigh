"""Allowed values for release issues. Stored as slugs; labels are for display.

Order matters: the frontend renders the lists in this order. Served to the UI via
GET /brain/release-issues/options so the two sides never drift.
"""

# Simple fixed list for v1 (Daniel, 2026-09-15). A label only — no routing yet.
DEPARTMENTS = [
    ('drafting', 'Drafting'),
    ('paint', 'Paint'),
    ('fab', 'Fab'),
    ('ship_install', 'Ship/Install'),
]

CATEGORIES = [
    ('quality_rework', 'Quality/Rework'),
    ('fabrication', 'Fabrication'),
    ('paint', 'Paint'),
    ('shipping_delivery', 'Shipping/Delivery'),
    ('missing_product', 'Missing Product/Hardware'),
    ('installation_field', 'Installation/Field'),
    ('drawing_engineering', 'Drawing/Engineering'),
    ('material_vendor', 'Material/Vendor'),
    ('customer_gc', 'Customer/GC'),
    ('subcontractor', 'Subcontractor'),
    ('damage', 'Damage'),
    ('other', 'Other'),
]

PRIORITIES = [
    ('low', 'Low'),
    ('normal', 'Normal'),
    ('high', 'High'),
    ('critical', 'Critical'),
]

STATUSES = [
    ('open', 'Open'),
    ('under_review', 'Under Review'),
    ('in_progress', 'In Progress'),
    ('waiting_on_others', 'Waiting on Others'),
    ('resolved', 'Resolved'),
    ('closed', 'Closed'),
]

# Statuses that count toward the open-issue count and open estimated cost.
CLOSED_STATUSES = frozenset({'resolved', 'closed'})

DEPARTMENT_KEYS = frozenset(k for k, _ in DEPARTMENTS)
CATEGORY_KEYS = frozenset(k for k, _ in CATEGORIES)
PRIORITY_KEYS = frozenset(k for k, _ in PRIORITIES)
STATUS_KEYS = frozenset(k for k, _ in STATUSES)

# field -> {slug: label}, for the human-readable release event payloads.
FIELD_VALUE_LABELS = {
    'department': dict(DEPARTMENTS),
    'category': dict(CATEGORIES),
    'priority': dict(PRIORITIES),
    'status': dict(STATUSES),
}


def value_label(field, value):
    if value is None:
        return None
    return FIELD_VALUE_LABELS.get(field, {}).get(value, value)


TITLE_MAX = 200
ATTACHMENT_MAX_BYTES = 50 * 1024 * 1024


def as_options():
    def _pairs(items):
        return [{'value': k, 'label': v} for k, v in items]

    return {
        'departments': _pairs(DEPARTMENTS),
        'categories': _pairs(CATEGORIES),
        'priorities': _pairs(PRIORITIES),
        'statuses': _pairs(STATUSES),
        'closed_statuses': sorted(CLOSED_STATUSES),
    }
