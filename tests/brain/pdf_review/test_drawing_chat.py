"""Carmen drawing chat — the fast path beside the heavy review (roadmap N18).

Covers POST /brain/releases/<id>/drawing/versions/<vid>/carmen-chat and the request
shaping in `pdf_review/chat.py`. The Anthropic hop is always mocked; what these assert
is the shape we send and the shape we return:
  - the PDF block leads the first user message and carries `cache_control` (the whole
    economic premise of the feature — a follow-up must re-read, not re-upload)
  - prior turns replay AFTER that cached prefix, so it stays byte-stable
  - a completed review of the same version rides in the context header
  - the spend lands in the ai_usage ledger
  - auth, validation, and the missing-file / no-key paths
"""
from unittest.mock import patch

import pytest
import requests

from app.brain.pdf_review import chat
from app.models import db, AiUsage, CarmenDrawingReview, DrawingVersionComment, ReleaseDrawingVersion
from tests.conftest import make_release


PDF = b"%PDF-1.4 fake drawing bytes"


def _anthropic_body(text="Sheet F1 shows a 7\" rise.", **usage):
    return {
        "model": "claude-sonnet-5",
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": 120, "output_tokens": 40,
                  "cache_read_input_tokens": 0, "cache_creation_input_tokens": 9000, **usage},
    }


def _seed(app, *, findings=None, status="complete", comments=(), job=590, rel="674"):
    with app.app_context():
        release = make_release(job, rel, pm="DR")
        db.session.flush()
        version = ReleaseDrawingVersion(
            release_id=release.id, version_number=2, storage_key=f"{release.id}/v2.pdf",
            original_filename="FC-set.pdf", mime_type="application/pdf",
            file_size_bytes=len(PDF), uploaded_by_user_id=1, note="approver markups",
        )
        db.session.add(version)
        db.session.flush()
        if findings is not None:
            db.session.add(CarmenDrawingReview(
                drawing_version_id=version.id, release_id=release.id,
                status=status, findings=findings, model="claude-opus-4-8",
            ))
        for body in comments:
            db.session.add(DrawingVersionComment(
                drawing_version_id=version.id, release_id=release.id,
                body=body, author_id=1, author_name="Lexi",
            ))
        db.session.commit()
        return release.id, version.id


def _url(release_id, version_id):
    return f"/brain/releases/{release_id}/drawing/versions/{version_id}/carmen-chat"


@pytest.fixture
def stub_pdf():
    with patch("app.brain.pdf_review.routes.read_pdf", return_value=PDF) as m:
        yield m


# --- the cached-prefix contract -------------------------------------------------------

def test_pdf_block_leads_and_is_cached(app, admin_client, stub_pdf):
    release_id, version_id = _seed(app)
    with patch("app.brain.pdf_review.chat._post",
               return_value=(_anthropic_body(), "req_1")) as post:
        resp = admin_client.post(_url(release_id, version_id), json={"message": "what's the rise?"})
    assert resp.status_code == 200

    messages = post.call_args[0][0]
    blocks = messages[0]["content"]
    assert blocks[0]["type"] == "document"
    assert blocks[0]["source"]["media_type"] == "application/pdf"
    # cache_control marks the END of the reusable prefix: document + context header.
    assert blocks[1]["cache_control"] == {"type": "ephemeral"}
    assert "Job/release: 590-674" in blocks[1]["text"]
    assert blocks[-1]["text"] == "what's the rise?"


def test_history_replays_after_the_cached_prefix(app, admin_client, stub_pdf):
    """The PDF must stay on the FIRST message across a whole thread, or every follow-up
    re-uploads it and prompt caching buys nothing."""
    release_id, version_id = _seed(app)
    history = [
        {"role": "user", "content": "summarize this set"},
        {"role": "assistant", "content": "Two stair flights on F1-F2."},
    ]
    with patch("app.brain.pdf_review.chat._post",
               return_value=(_anthropic_body(), "req_2")) as post:
        resp = admin_client.post(_url(release_id, version_id),
                                 json={"message": "and the guards?", "history": history})
    assert resp.status_code == 200

    messages = post.call_args[0][0]
    assert len(messages) == 3
    assert messages[0]["role"] == "user"
    assert messages[0]["content"][0]["type"] == "document"
    assert messages[0]["content"][-1]["text"] == "summarize this set"   # first question rides along
    assert messages[1] == {"role": "assistant", "content": "Two stair flights on F1-F2."}
    assert messages[2] == {"role": "user", "content": "and the guards?"}


def test_history_never_starts_on_an_assistant_turn(app, admin_client, stub_pdf):
    release_id, version_id = _seed(app)
    with patch("app.brain.pdf_review.chat._post",
               return_value=(_anthropic_body(), "req_3")) as post:
        admin_client.post(_url(release_id, version_id), json={
            "message": "ok?",
            "history": [{"role": "assistant", "content": "orphaned answer"}],
        })
    messages = post.call_args[0][0]
    assert len(messages) == 1
    assert messages[0]["content"][-1]["text"] == "ok?"


def test_history_is_capped(app, admin_client, stub_pdf):
    release_id, version_id = _seed(app)
    long_history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"t{i}"}
                    for i in range(60)]
    with patch("app.brain.pdf_review.chat._post",
               return_value=(_anthropic_body(), "req_4")) as post:
        admin_client.post(_url(release_id, version_id),
                          json={"message": "latest", "history": long_history})
    messages = post.call_args[0][0]
    assert len(messages) <= chat.MAX_HISTORY_TURNS + 1


def test_runs_sonnet_not_opus(app, admin_client, stub_pdf):
    release_id, version_id = _seed(app)
    with patch("app.brain.pdf_review.chat._post",
               return_value=(_anthropic_body(), "req_5")) as post:
        admin_client.post(_url(release_id, version_id), json={"message": "hi"})
    assert post.call_args[0][2] == "claude-sonnet-5"


# --- context header -------------------------------------------------------------------

def test_completed_review_rides_in_the_context(app, admin_client, stub_pdf):
    release_id, version_id = _seed(app, findings=[
        {"rule_id": "stair-terminal-rise-over-max", "verdict": "violation",
         "location": "F1", "issue": "terminal rise 8\""},
    ])
    with patch("app.brain.pdf_review.chat._post",
               return_value=(_anthropic_body(), "req_6")) as post:
        admin_client.post(_url(release_id, version_id), json={"message": "why f1?"})
    header = post.call_args[0][0][0]["content"][1]["text"]
    assert "1 findings" in header
    assert "stair-terminal-rise-over-max" in header
    assert "terminal rise 8\"" in header
    assert "Open version: v2" in header
    assert "approver markups" in header


def test_no_review_says_so(app, admin_client, stub_pdf):
    release_id, version_id = _seed(app)
    with patch("app.brain.pdf_review.chat._post",
               return_value=(_anthropic_body(), "req_7")) as post:
        admin_client.post(_url(release_id, version_id), json={"message": "hi"})
    header = post.call_args[0][0][0]["content"][1]["text"]
    assert "no code-compliance review has been run on this version yet" in header


def test_comments_ride_in_the_context(app, admin_client, stub_pdf):
    release_id, version_id = _seed(app, comments=["check the landing guard"])
    with patch("app.brain.pdf_review.chat._post",
               return_value=(_anthropic_body(), "req_8")) as post:
        admin_client.post(_url(release_id, version_id), json={"message": "hi"})
    header = post.call_args[0][0][0]["content"][1]["text"]
    assert "Lexi: check the landing guard" in header


# --- response, ledger, failure paths ---------------------------------------------------

def test_answer_and_metrics_come_back(app, admin_client, stub_pdf):
    release_id, version_id = _seed(app)
    with patch("app.brain.pdf_review.chat._post",
               return_value=(_anthropic_body("Sheet F1: 7\" rise."), "req_9")):
        resp = admin_client.post(_url(release_id, version_id), json={"message": "rise?"})
    data = resp.get_json()
    assert data["configured"] is True
    assert data["answer"] == "Sheet F1: 7\" rise."
    m = data["metrics"]
    assert m["model"] == "claude-sonnet-5"
    assert m["cache_write_tokens"] == 9000
    assert m["cost_usd"] > 0
    assert m["request_id"] == "req_9"
    assert m["duration_ms"] >= 0


def test_turn_lands_in_the_usage_ledger(app, admin_client, stub_pdf):
    release_id, version_id = _seed(app)
    with patch("app.brain.pdf_review.chat._post",
               return_value=(_anthropic_body(), "req_10")):
        admin_client.post(_url(release_id, version_id), json={"message": "rise?"})
    with app.app_context():
        rows = AiUsage.query.filter_by(feature="carmen_drawing_chat").all()
        assert len(rows) == 1
        assert rows[0].entity_type == "drawing_version"
        assert str(rows[0].entity_id) == str(version_id)   # ledger stores it as text
        assert rows[0].anthropic_request_id == "req_10"


def test_nothing_is_persisted_as_a_conversation(app, admin_client, stub_pdf):
    """v1 is session-only: the client carries the thread, the server keeps no turn rows."""
    release_id, version_id = _seed(app)
    with patch("app.brain.pdf_review.chat._post",
               return_value=(_anthropic_body(), "req_11")):
        admin_client.post(_url(release_id, version_id), json={"message": "rise?"})
    with app.app_context():
        from app.models import CarmenChatMessage
        assert CarmenChatMessage.query.count() == 0


def test_truncated_answer_is_flagged(app, admin_client, stub_pdf):
    release_id, version_id = _seed(app)
    body = _anthropic_body("half an ans")
    body["stop_reason"] = "max_tokens"
    with patch("app.brain.pdf_review.chat._post", return_value=(body, "req_12")):
        resp = admin_client.post(_url(release_id, version_id), json={"message": "long one"})
    assert "Cut off" in resp.get_json()["answer"]


def test_anthropic_failure_is_502(app, admin_client, stub_pdf):
    release_id, version_id = _seed(app)
    with patch("app.brain.pdf_review.chat._post",
               side_effect=requests.RequestException("boom")):
        resp = admin_client.post(_url(release_id, version_id), json={"message": "rise?"})
    assert resp.status_code == 502
    with app.app_context():
        assert AiUsage.query.filter_by(feature="carmen_drawing_chat").count() == 0


def test_missing_key_is_not_an_error(app, admin_client, stub_pdf):
    release_id, version_id = _seed(app)
    with patch("app.brain.pdf_review.chat.cfg.ANTHROPIC_API_KEY", None):
        resp = admin_client.post(_url(release_id, version_id), json={"message": "rise?"})
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["configured"] is False
    with app.app_context():   # a stub answer is not spend
        assert AiUsage.query.filter_by(feature="carmen_drawing_chat").count() == 0


def test_missing_file_is_404(app, admin_client):
    release_id, version_id = _seed(app)
    with patch("app.brain.pdf_review.routes.read_pdf", side_effect=FileNotFoundError):
        resp = admin_client.post(_url(release_id, version_id), json={"message": "rise?"})
    assert resp.status_code == 404


def test_empty_message_is_400(app, admin_client, stub_pdf):
    release_id, version_id = _seed(app)
    resp = admin_client.post(_url(release_id, version_id), json={"message": "   "})
    assert resp.status_code == 400


def test_unknown_version_is_404(app, admin_client, stub_pdf):
    release_id, _ = _seed(app)
    resp = admin_client.post(_url(release_id, 99999), json={"message": "rise?"})
    assert resp.status_code == 404


def test_drafter_may_chat(app, drafter_client, stub_pdf):
    release_id, version_id = _seed(app)
    with patch("app.brain.pdf_review.chat._post",
               return_value=(_anthropic_body(), "req_13")):
        resp = drafter_client.post(_url(release_id, version_id), json={"message": "rise?"})
    assert resp.status_code == 200


def test_plain_user_may_not(app, non_admin_client, stub_pdf):
    release_id, version_id = _seed(app)
    resp = non_admin_client.post(_url(release_id, version_id), json={"message": "rise?"})
    assert resp.status_code == 403


def test_oversized_pdf_is_400(app, admin_client):
    release_id, version_id = _seed(app)
    huge = b"x" * (chat.MAX_PDF_BYTES + 1)
    with patch("app.brain.pdf_review.routes.read_pdf", return_value=huge):
        resp = admin_client.post(_url(release_id, version_id), json={"message": "rise?"})
    assert resp.status_code == 400


# --- markups are not findings ---------------------------------------------------------
#
# Bill's first real question was "summarize the markups" and Carmen answered that the
# review hadn't been run. Those are different objects, and the context header is where
# the model learns that, so these pin the markup half of it down.

def _pdf_with_annotations(specs):
    """A 2-page PDF carrying `specs` = [(page_index, subtype, contents)] as annotations."""
    import io as _io
    from pypdf import PdfWriter
    from pypdf.generic import (ArrayObject, DictionaryObject, FloatObject,
                               NameObject, TextStringObject)

    writer = PdfWriter()
    for _ in range(2):
        writer.add_blank_page(width=612, height=792)
    for page_index, subtype, contents in specs:
        annot = DictionaryObject({
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject(subtype),
            NameObject("/Rect"): ArrayObject([FloatObject(x) for x in (10, 20, 110, 60)]),
            NameObject("/Contents"): TextStringObject(contents),
        })
        page = writer.pages[page_index]
        if "/Annots" in page:
            page[NameObject("/Annots")].append(annot)
        else:
            page[NameObject("/Annots")] = ArrayObject([annot])
    buf = _io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_summarize_markups_reads_annotations():
    pdf = _pdf_with_annotations([
        (0, "/Ink", ""),
        (1, "/FreeText", "verify this weld"),
        (1, "/Popup", "structural, not a markup"),
    ])
    found = chat.summarize_markups(pdf)
    assert [(m["page"], m["kind"]) for m in found] == [(1, "pen/shape"), (2, "typed note")]
    assert found[1]["text"] == "verify this weld"


def test_summarize_markups_never_raises():
    assert chat.summarize_markups(b"not a pdf at all") == []


def test_markups_are_listed_in_the_context(app, admin_client):
    release_id, version_id = _seed(app)
    pdf = _pdf_with_annotations([(0, "/Ink", ""), (1, "/FreeText", "verify this weld")])
    with patch("app.brain.pdf_review.routes.read_pdf", return_value=pdf), \
         patch("app.brain.pdf_review.chat._post",
               return_value=(_anthropic_body(), "req_20")) as post:
        admin_client.post(_url(release_id, version_id), json={"message": "summarize the markups"})
    header = post.call_args[0][0][0]["content"][1]["text"]
    assert "MARKUPS on this PDF: 2 annotation(s)" in header
    assert "p1 pen/shape" in header
    assert 'p2 typed note: "verify this weld"' in header


def test_no_markups_says_so_without_mentioning_the_review(app, admin_client):
    release_id, version_id = _seed(app)
    with patch("app.brain.pdf_review.routes.read_pdf", return_value=_pdf_with_annotations([])), \
         patch("app.brain.pdf_review.chat._post",
               return_value=(_anthropic_body(), "req_21")) as post:
        admin_client.post(_url(release_id, version_id), json={"message": "summarize the markups"})
    header = post.call_args[0][0][0]["content"][1]["text"]
    assert "MARKUPS: this PDF carries no markup annotations." in header
    # The findings line must read as a separate object, not as an answer about markups.
    assert "this says nothing about the markups above" in header


def test_new_markups_are_diffed_against_the_source_version(app, admin_client):
    """'What changed in the markups on this version?' — annotations carry forward, so the
    answer is the delta against the version this one was saved from, not the full list."""
    with app.app_context():
        release = make_release(170, "448", pm="DR")
        db.session.flush()
        v1 = ReleaseDrawingVersion(
            release_id=release.id, version_number=1, storage_key=f"{release.id}/v1.pdf",
            mime_type="application/pdf", file_size_bytes=1, uploaded_by_user_id=1)
        db.session.add(v1)
        db.session.flush()
        v2 = ReleaseDrawingVersion(
            release_id=release.id, version_number=2, storage_key=f"{release.id}/v2.pdf",
            mime_type="application/pdf", file_size_bytes=1, uploaded_by_user_id=1,
            source_version_id=v1.id)
        db.session.add(v2)
        db.session.commit()
        release_id, v1_key, v2_id = release.id, v1.storage_key, v2.id

    carried = (0, "/Ink", "")
    added = (1, "/FreeText", "new note on v2")
    pdfs = {v1_key: _pdf_with_annotations([carried])}

    def _read(key):
        return pdfs.get(key, _pdf_with_annotations([carried, added]))

    with patch("app.brain.pdf_review.routes.read_pdf", side_effect=_read), \
         patch("app.brain.pdf_review.chat._post",
               return_value=(_anthropic_body(), "req_22")) as post:
        resp = admin_client.post(_url(release_id, v2_id), json={"message": "what changed?"})
    assert resp.status_code == 200
    header = post.call_args[0][0][0]["content"][1]["text"]
    assert "2 annotation(s), 1 of them NEW on this version" in header
    assert 'p2 typed note: "new note on v2" [new on this version]' in header
    assert "p1 pen/shape" in header and "p1 pen/shape [new" not in header


def test_missing_source_pdf_does_not_break_the_turn(app, admin_client):
    """A deleted predecessor file means no diff — it must not cost you the answer."""
    with app.app_context():
        release = make_release(170, "449", pm="DR")
        db.session.flush()
        v1 = ReleaseDrawingVersion(
            release_id=release.id, version_number=1, storage_key="gone/v1.pdf",
            mime_type="application/pdf", file_size_bytes=1, uploaded_by_user_id=1)
        db.session.add(v1)
        db.session.flush()
        v2 = ReleaseDrawingVersion(
            release_id=release.id, version_number=2, storage_key="here/v2.pdf",
            mime_type="application/pdf", file_size_bytes=1, uploaded_by_user_id=1,
            source_version_id=v1.id)
        db.session.add(v2)
        db.session.commit()
        release_id, v2_id = release.id, v2.id

    def _read(key):
        if key == "gone/v1.pdf":
            raise FileNotFoundError
        return _pdf_with_annotations([(0, "/Ink", "")])

    with patch("app.brain.pdf_review.routes.read_pdf", side_effect=_read), \
         patch("app.brain.pdf_review.chat._post",
               return_value=(_anthropic_body(), "req_23")) as post:
        resp = admin_client.post(_url(release_id, v2_id), json={"message": "markups?"})
    assert resp.status_code == 200
    header = post.call_args[0][0][0]["content"][1]["text"]
    assert "1 annotation(s)" in header
    assert "NEW on this version" not in header   # no baseline, so no delta claimed


def test_system_prompt_separates_markups_from_findings():
    assert "never reply that the review has not been run" in chat.SYSTEM_PROMPT
    assert "MARKUPS are annotations drawn ON the sheets" in chat.SYSTEM_PROMPT
