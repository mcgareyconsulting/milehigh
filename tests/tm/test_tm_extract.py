"""Unit tests for app/brain/tm/extract.py normalization.

Pure unit layer — no Flask, no DB, no network. _call_anthropic is patched to
return canned dicts so we only exercise the normalization logic in extract().
"""
from unittest.mock import patch

import pytest

from app.brain.tm import extract


def _extract(raw):
    with patch("app.brain.tm.extract._call_anthropic", return_value=raw):
        return extract.extract(b"fake-bytes", "application/pdf")


def test_full_happy_path_mapping():
    raw = {
        "job_number": 580,
        "date_of_work": "2026-06-18",
        "customer": "Alta Metro",
        "work_description": "Installed misc railings",
        "labor": [
            {"name": "Joe Smith", "company": "MHMW", "classification": "Welder",
             "hours_reg": 8, "hours_ot": "2", "hours_dt": None, "notes": "OT approved"},
        ],
        "materials": [
            {"description": "1.5C 18Ga decking", "quantity": "45", "unit": "sheets",
             "length": "10ft", "notes": None},
        ],
        "equipment": [
            {"description": "Man lift", "quantity": 1, "hours": 4.5,
             "operator": "Joe Smith", "notes": None},
        ],
        "signature_present": True,
        "signature_name": "John Doe",
        "confidence": {"job_number": 1.0, "date_of_work": 0.9, "customer": 0.8,
                       "work_description": 0.7, "labor": 0.6, "materials": 0.5,
                       "equipment": 0.4, "signature": 1.0},
    }
    result = _extract(raw)

    assert result["job"] == 580
    assert result["date_of_work"] == "2026-06-18"
    assert result["customer"] == "Alta Metro"
    assert result["work_description"] == "Installed misc railings"

    assert result["labor"] == [{
        "name": "Joe Smith", "company": "MHMW", "classification": "Welder",
        "hours_reg": 8.0, "hours_ot": 2.0, "hours_dt": None, "notes": "OT approved",
    }]
    assert result["materials"] == [{
        "description": "1.5C 18Ga decking", "quantity": 45.0, "unit": "sheets",
        "length": "10ft", "notes": None,
    }]
    assert result["equipment"] == [{
        "description": "Man lift", "quantity": 1.0, "hours": 4.5,
        "operator": "Joe Smith", "notes": None,
    }]
    assert result["signature_present"] is True
    assert result["signature_name"] == "John Doe"
    assert result["confidence"] == raw["confidence"]
    assert result["raw"] == raw


def test_job_number_string_coerced_to_int():
    raw = {"job_number": "580"}
    result = _extract(raw)
    assert result["job"] == 580


def test_job_number_non_numeric_string_becomes_none():
    raw = {"job_number": "not-a-number"}
    result = _extract(raw)
    assert result["job"] is None


def test_job_number_none_stays_none():
    raw = {"job_number": None}
    result = _extract(raw)
    assert result["job"] is None


def test_bad_date_string_becomes_none():
    raw = {"date_of_work": "06/18/2026"}
    result = _extract(raw)
    assert result["date_of_work"] is None


def test_valid_date_passes_through():
    raw = {"date_of_work": "2026-06-18"}
    result = _extract(raw)
    assert result["date_of_work"] == "2026-06-18"


def test_labor_entries_drop_non_dict_entries():
    raw = {"labor": [{"name": "Joe"}, "not-a-dict", 42, None]}
    result = _extract(raw)
    assert len(result["labor"]) == 1
    assert result["labor"][0]["name"] == "Joe"


def test_labor_entries_drop_all_empty_entries():
    raw = {"labor": [
        {"name": None, "company": None, "classification": None,
         "hours_reg": None, "hours_ot": None, "hours_dt": None, "notes": ""},
        {"name": "Real Guy"},
    ]}
    result = _extract(raw)
    assert len(result["labor"]) == 1
    assert result["labor"][0]["name"] == "Real Guy"


def test_materials_numeric_coercion_of_quantity():
    raw = {"materials": [{"description": "Beam", "quantity": "12.5"}]}
    result = _extract(raw)
    assert result["materials"][0]["quantity"] == 12.5


def test_materials_bad_numeric_quantity_becomes_none():
    raw = {"materials": [{"description": "Beam", "quantity": "twelve"}]}
    result = _extract(raw)
    assert result["materials"][0]["quantity"] is None


def test_equipment_numeric_coercion_of_hours():
    raw = {"equipment": [{"description": "Crane", "hours": "6"}]}
    result = _extract(raw)
    assert result["equipment"][0]["hours"] == 6.0


def test_entries_not_a_list_returns_empty():
    raw = {"labor": "not-a-list", "materials": None, "equipment": 5}
    result = _extract(raw)
    assert result["labor"] == []
    assert result["materials"] == []
    assert result["equipment"] == []


def test_confidence_dict_passthrough():
    raw = {"confidence": {"job_number": 0.5, "customer": 0.2}}
    result = _extract(raw)
    assert result["confidence"] == {"job_number": 0.5, "customer": 0.2}


def test_confidence_missing_defaults_to_empty_dict():
    raw = {}
    result = _extract(raw)
    assert result["confidence"] == {}


def test_confidence_non_dict_defaults_to_empty_dict():
    raw = {"confidence": "not-a-dict"}
    result = _extract(raw)
    assert result["confidence"] == {}


def test_signature_fields():
    raw = {"signature_present": False, "signature_name": None}
    result = _extract(raw)
    assert result["signature_present"] is False
    assert result["signature_name"] is None


def test_signature_name_blank_string_becomes_none():
    raw = {"signature_name": ""}
    result = _extract(raw)
    assert result["signature_name"] is None


def test_non_dict_response_raises_value_error():
    with pytest.raises(ValueError):
        _extract(["not", "a", "dict"])


def test_customer_and_description_blank_string_become_none():
    raw = {"customer": "", "work_description": ""}
    result = _extract(raw)
    assert result["customer"] is None
    assert result["work_description"] is None
