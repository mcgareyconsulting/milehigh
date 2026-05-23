"""Unit tests for the voice normalizers (pure, no Flask/DB)."""
import pytest

from app.brain.voice.normalizers import (
    extract_position,
    extract_submittal_id,
    match_drafter,
    match_submittal_id,
    normalize_text,
    words_to_number,
)


class TestNormalizeText:
    def test_lowercases_and_strips_filler(self):
        assert normalize_text("Um, MOVE the Thing") == "move the thing"

    def test_collapses_punctuation_to_spaces(self):
        assert normalize_text("move 234-433, please!") == "move 234-433"

    def test_keeps_apostrophes_and_hyphens(self):
        assert normalize_text("colton's 234-433") == "colton's 234-433"

    def test_empty(self):
        assert normalize_text("") == ""


class TestWordsToNumber:
    @pytest.mark.parametrize("phrase,expected", [
        ("five", 5),
        ("thirty four", 34),
        ("two thirty four", 234),
        ("four thirty three", 433),
        ("twenty", 20),
        ("100", 100),
        ("nineteen", 19),
        ("first", 1),
        ("fifth", 5),
    ])
    def test_conversions(self, phrase, expected):
        assert words_to_number(phrase) == expected

    def test_non_number_returns_none(self):
        assert words_to_number("colton") is None


class TestExtractSubmittalId:
    @pytest.mark.parametrize("text,expected", [
        ("move 234-433 to number 5", "234-433"),
        ("bump 234 dash 433", "234-433"),
        ("two thirty four dash four thirty three", "234-433"),
        ("234 to 433 please", "234-433"),
        ("234 433", "234-433"),
        ("number 234-433", "234-433"),
    ])
    def test_extracts(self, text, expected):
        assert extract_submittal_id(text) == expected

    def test_no_id(self):
        assert extract_submittal_id("resort colton's list") is None


class TestExtractPosition:
    @pytest.mark.parametrize("text,expected", [
        ("to number 5", 5),
        ("position 3", 3),
        ("to the top", 1),
        ("slot 2", 2),
        ("to five", 5),
        ("third", 3),
    ])
    def test_extracts(self, text, expected):
        assert extract_position(text) == expected

    def test_no_position(self):
        assert extract_position("bump it urgent") is None


class TestMatchSubmittalId:
    KNOWN = ["234-433", "234-453", "101-202", "999-888"]

    def test_exact(self):
        rid, cands = match_submittal_id("234-433", self.KNOWN)
        assert rid == "234-433"

    def test_fuzzy_single(self):
        # "101-203" is one digit off from "101-202" and far from the rest.
        rid, cands = match_submittal_id("101-203", self.KNOWN)
        assert rid == "101-202"

    def test_ambiguous_returns_candidates(self):
        # "234-443" is equally close to 234-433 and 234-453.
        rid, cands = match_submittal_id("234-443", self.KNOWN)
        assert rid is None
        assert set(cands) >= {"234-433", "234-453"}

    def test_no_match(self):
        rid, cands = match_submittal_id("555-555", self.KNOWN)
        assert rid is None


class TestMatchDrafter:
    KNOWN = ["Colton Reed", "Maria Sanchez", "Colby Smith"]

    def test_exact_first_name(self):
        name, cands = match_drafter("colton", self.KNOWN)
        assert name == "Colton Reed"

    def test_comma_separated(self):
        name, cands = match_drafter("maria", ["Colton Reed, Maria Sanchez"])
        assert name == "Colton Reed, Maria Sanchez"

    def test_unknown(self):
        name, cands = match_drafter("zelda", self.KNOWN)
        assert name is None
