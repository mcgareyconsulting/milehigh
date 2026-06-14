"""Tests for the rental -> job resolver and address normalization."""
from app.brain.sunbelt.matching import normalize_address, RentalMatcher


def test_normalize_address_equates_sunbelt_and_project_forms():
    a = normalize_address("220 E OAK ST, FORT COLLINS")
    b = normalize_address("220 E Oak St Fort Collins, CO 80524")
    assert a == b == "220 E OAK ST FORT COLLINS"


def test_normalize_address_standardizes_suffixes():
    assert normalize_address("81 W Flatiron Crossing Drive") == \
        normalize_address("81 W FLATIRON CROSSING DR")


def test_normalize_address_empty():
    assert normalize_address(None) == ""
    assert normalize_address("") == ""


def test_resolve_exact_po_to_release(app, seed_jobs):
    matcher = RentalMatcher()
    job, name, method = matcher.resolve("480", "350 GATEWAY DR, SUPERIOR")
    assert (job, name, method) == (480, "Wood Partners - Alta Flatirons", "po_number")


def test_resolve_miskeyed_po_falls_back_to_address(app, seed_jobs):
    # Sunbelt PO 520 is a typo; the address is the truth -> our job 530.
    matcher = RentalMatcher()
    job, name, method = matcher.resolve("520", "220 E OAK ST, FORT COLLINS")
    assert job == 530
    assert name == "East Oak Townhomes"
    assert method == "address"


def test_resolve_po_to_submittal_only_job(app, seed_jobs):
    matcher = RentalMatcher()
    job, name, method = matcher.resolve("490", "655 N PEARL ST, DENVER")
    assert (job, name, method) == (490, "Capital Hill", "submittal")


def test_resolve_unmatched(app, seed_jobs):
    matcher = RentalMatcher()
    job, name, method = matcher.resolve("999", "1 NOWHERE LANE, ATLANTIS")
    assert (job, name, method) == (None, None, "unmatched")
