"""Table-driven tests for the voice intent parser (pure, no Flask/DB)."""
import pytest

from app.brain.voice.intent import Intent, parse_intent, strip_wake_word


class TestWakeWord:
    @pytest.mark.parametrize("text,expected", [
        ("hey banana boy bump 234-433", "bump 234-433"),
        ("Banana Boy, resort colton's list", "resort colton's list"),
        ("ok banana boy move 234-433 to 5", "move 234-433 to 5"),
        ("...anyway, hey Banana Boy, bump 234-433", "bump 234-433"),
    ])
    def test_strips(self, text, expected):
        assert strip_wake_word(text) == expected

    def test_no_wake_word(self):
        assert strip_wake_word("just move 234-433 to 5") is None

    def test_no_wake_word_yields_no_intent(self):
        assert parse_intent("move 234-433 to number 5 in colton's list") is None


class TestSetOrder:
    def test_full_command(self):
        i = parse_intent("hey banana boy move 234-433 to number 5 in Colton's list")
        assert i.action == "set_order"
        assert i.raw_submittal == "234-433"
        assert i.position == 5
        assert i.raw_drafter == "colton"
        assert i.confidence == "high"

    def test_spoken_digits(self):
        i = parse_intent("banana boy move two thirty four dash four thirty three to the top")
        assert i.action == "set_order"
        assert i.raw_submittal == "234-433"
        assert i.position == 1

    def test_missing_position_is_low_confidence(self):
        i = parse_intent("banana boy move 234-433 in colton's list")
        assert i.action == "set_order"
        assert "position" in i.unknown_slots
        assert i.confidence == "low"


class TestBump:
    @pytest.mark.parametrize("text", [
        "hey banana boy bump 234-433",
        "banana boy make 234-433 urgent",
        "banana boy escalate 234 dash 433",
    ])
    def test_bump(self, text):
        i = parse_intent(text)
        assert i.action == "bump"
        assert i.raw_submittal == "234-433"


class TestStep:
    def test_up(self):
        i = parse_intent("banana boy step 234-433 up")
        assert i.action == "step"
        assert i.direction == "up"
        assert i.raw_submittal == "234-433"

    def test_down(self):
        i = parse_intent("banana boy nudge 234-433 down")
        assert i.action == "step"
        assert i.direction == "down"


class TestResort:
    def test_with_drafter(self):
        i = parse_intent("banana boy resort colton's list")
        assert i.action == "resort"
        assert i.raw_drafter == "colton"

    def test_without_drafter_is_low(self):
        i = parse_intent("banana boy resort")
        assert i.action == "resort"
        assert i.confidence == "low"


class TestStatus:
    @pytest.mark.parametrize("text,value", [
        ("banana boy mark 234-433 started", "STARTED"),
        ("banana boy put 234-433 on hold", "HOLD"),
        ("banana boy 234-433 needs vif", "NEED VIF"),
    ])
    def test_status(self, text, value):
        i = parse_intent(text)
        assert i.action == "set_status"
        assert i.value == value
        assert i.raw_submittal == "234-433"


class TestDueDate:
    def test_due_date(self):
        i = parse_intent("banana boy set due date on 234-433 to next friday")
        assert i.action == "set_due_date"
        assert i.raw_submittal == "234-433"
        assert i.value == "next friday"


class TestAddNote:
    def test_note(self):
        i = parse_intent("banana boy note on 234-433: waiting on shop drawings")
        assert i.action == "add_note"
        assert i.raw_submittal == "234-433"
        assert "waiting on shop drawings" in i.value


class TestNoMatch:
    def test_gibberish(self):
        assert parse_intent("banana boy what time is it") is None
