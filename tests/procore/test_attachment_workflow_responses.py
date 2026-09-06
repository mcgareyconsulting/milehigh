"""Reading Procore's Workflow Responses block off a submittal payload.

That block — one row per approver, carrying a response name like "Final PDF Pack" — is the
only place Procore says what a returned drawing *is*; the attachment object never does.
`app.procore.procore._final_pdf_approver_ids` has always read it for the FC viewer link;
these tests cover the shared parse the attachment puller now uses for its labels.
"""

from app.procore.attachments import is_final_pdf_response_name, workflow_responses


def _submittal(*responses):
    return {'last_distributed_submittal': {'distributed_responses': list(responses)}}


def test_final_pdf_response_name_matches_procores_wording():
    assert is_final_pdf_response_name('Final PDF Pack')
    assert is_final_pdf_response_name('  final pdf pack  ')
    # Procore renames the response after some FC set updates — stay tolerant.
    assert is_final_pdf_response_name('Final PDF Pack (Rev 2)')
    assert is_final_pdf_response_name('FINAL Approved PDF')


def test_other_responses_are_not_the_pack():
    for name in ('Approved', 'Approved as Noted', 'Revise & Resubmit', '', None):
        assert not is_final_pdf_response_name(name)


def test_workflow_responses_keys_by_approver_id():
    sub = _submittal(
        {'submittal_approver_id': 991, 'response_name': 'Final PDF Pack',
         'approver_name': 'Dalton Rauer (Mile High Metal Works, Inc.)'},
        {'submittal_approver_id': 992, 'response_name': 'Approved as Noted',
         'approver_name': 'GC Reviewer'},
    )
    rows = workflow_responses(sub)

    assert rows[991]['is_final_pdf'] is True
    assert rows[991]['approver_name'] == 'Dalton Rauer (Mile High Metal Works, Inc.)'
    assert rows[992]['is_final_pdf'] is False


def test_approver_name_read_from_a_nested_object():
    sub = _submittal({
        'submittal_approver_id': 991,
        'response_name': 'Final PDF Pack',
        'user': {'name': 'Dalton Rauer'},
    })
    assert workflow_responses(sub)[991]['approver_name'] == 'Dalton Rauer'


def test_missing_or_thin_payloads_degrade_to_empty():
    assert workflow_responses({}) == {}
    assert workflow_responses({'last_distributed_submittal': None}) == {}
    # A response with no approver id can't be matched to an attachment, so it's dropped.
    assert workflow_responses(_submittal({'response_name': 'Final PDF Pack'})) == {}


# ---------------------------------------------------------------------------
# Where the file actually lives
# ---------------------------------------------------------------------------
#
# Procore does not keep returned drawings in one place. The same Final PDF Pack can arrive
# as a submittal attachment, as a workflow_data attachment, and as a *document* on the
# approver's own response row — so the collector walks the payloads instead of reading
# payload["attachments"].

from unittest.mock import patch

from app.procore.attachments import find_submittal_drawing_refs, walk_file_objects

PACK_URL = ("https://app.procore.com/1234/project/submittal_logs/view_attachment"
            "?attachment_id=5150&item_id=900&item_type=SubmittalLogApprover&project_id=777")

PACK_FILE = {'name': 'Bearing Angles.181.pdf', 'viewer_url': PACK_URL, 'download_url': PACK_URL}


def _refs_from(submittal, workflow):
    with patch('app.procore.attachments._request_json', side_effect=[submittal, workflow]):
        return find_submittal_drawing_refs(777, 4242)


def test_walk_finds_files_under_documents_not_just_attachments():
    found = walk_file_objects({'documents': [{'name': 'a.pdf'}], 'attachments': [{'name': 'b.pdf'}]})
    assert sorted(f['name'] for f, _ in found) == ['a.pdf', 'b.pdf']


def test_walk_carries_the_response_row_down_to_a_nested_file():
    payload = {'workflow_responses': [{
        'submittal_approver_id': 991,
        'response_name': 'Final PDF Pack',
        'approver_name': 'Dalton Rauer',
        'documents': [{'name': 'Bearing Angles.181.pdf'}],
    }]}
    (file_obj, ctx), = walk_file_objects(payload)
    assert file_obj['name'] == 'Bearing Angles.181.pdf'
    assert (ctx['approver_id'], ctx['response_name']) == (991, 'Final PDF Pack')


def test_file_carried_only_as_a_workflow_document_is_still_collected():
    """The gap: a pack Procore hangs off `documents` was invisible to a bare
    payload["attachments"] read."""
    refs = _refs_from({}, {'documents': [PACK_FILE]})

    assert len(refs) == 1
    assert refs[0]['attachment_id'] == 5150


def test_response_row_labels_a_file_nested_inside_it():
    workflow = {'workflow_responses': [{
        'submittal_approver_id': 991,
        'response_name': 'Final PDF Pack',
        'approver_name': 'Dalton Rauer (Mile High Metal Works, Inc.)',
        'documents': [PACK_FILE],
    }]}
    refs = _refs_from({}, workflow)

    assert refs[0]['is_final_pdf_response'] is True
    assert refs[0]['response_name'] == 'Final PDF Pack'
    assert refs[0]['approver_name'] == 'Dalton Rauer (Mile High Metal Works, Inc.)'
    assert refs[0]['approver_id'] == 991


def test_same_file_in_both_places_dedups_but_keeps_the_response_evidence():
    """It is one file, listed twice: a plain submittal attachment (which says nothing about
    what it is) and the workflow response row (which names it). One ref, labelled."""
    submittal = {'attachments': [PACK_FILE]}
    workflow = {'attachments': [dict(PACK_FILE, approver_id=991)],
                'last_distributed_submittal': {'distributed_responses': [
                    {'submittal_approver_id': 991, 'response_name': 'Final PDF Pack',
                     'approver_name': 'Dalton Rauer'},
                ]}}
    refs = _refs_from(submittal, workflow)

    assert len(refs) == 1
    assert refs[0]['response_name'] == 'Final PDF Pack'
    assert refs[0]['is_final_pdf_response'] is True


def test_duplicate_sighting_fills_in_missing_display_metadata():
    thin = dict(PACK_FILE)
    rich = dict(PACK_FILE, created_at='2026-08-30T18:02:00Z', byte_size=2411724,
                created_by={'name': 'Dalton Rauer'})
    refs = _refs_from({'attachments': [thin]}, {'attachments': [rich]})

    assert len(refs) == 1
    assert refs[0]['size_bytes'] == 2411724
    assert refs[0]['created_by'] == 'Dalton Rauer'


def test_non_pdf_files_are_still_ignored_wherever_they_hide():
    refs = _refs_from({}, {'documents': [{'name': 'site-photo.jpg', 'viewer_url': PACK_URL}]})
    assert refs == []


# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------


def test_probe_asks_the_approver_record_when_the_file_is_an_approver_attachment():
    """The case that prompted it: response_name came back null, so the approver record is
    the next place the name can live. Probing an approver attachment must ask for it."""
    from app.procore.attachments import probe_attachment

    with patch('app.procore.attachments._probe_get', return_value=(404, None)) as get:
        probe_attachment(2968284, 71563766, 6172561559,
                         item_id=184985005, item_type='SubmittalLogApprover')

    asked = [call.args[0] for call in get.call_args_list]
    assert any('/approvers/184985005' in url for url in asked)
    assert any(url.endswith('/submittals/71563766/approvers') for url in asked)
    assert any('/attachments/6172561559' in url for url in asked)


def test_probe_reports_status_shape_and_any_response_names_found():
    from app.procore.attachments import probe_attachment

    body = {'id': 184985005, 'response_name': 'Final PDF Pack',
            'attachments': [{'id': 6172561559}]}
    with patch('app.procore.attachments._probe_get', return_value=(200, body)):
        rows = probe_attachment(2968284, 71563766, 6172561559,
                                item_id=184985005, item_type='SubmittalLogApprover')

    row = rows[0]
    assert row['status'] == 200
    assert row['shape'] == {'type': 'object',
                            'keys': ['attachments', 'id', 'response_name']}
    assert row['mentions_attachment'] is True
    assert row['mentions_approver'] is True
    assert row['response_names'] == ['Final PDF Pack']


def test_probe_never_raises_when_procore_refuses():
    from app.procore.attachments import probe_attachment

    with patch('app.procore.attachments._probe_get', return_value=(None, {'error': 'timeout'})):
        rows = probe_attachment(2968284, 71563766, 6172561559)

    assert all(r['status'] is None for r in rows)
    # No approver ids to chase, so the approver-record URLs are skipped.
    assert not any('submittal_approvers' in r['url'] for r in rows)


# ---------------------------------------------------------------------------
# Response names that aren't where the docs say
# ---------------------------------------------------------------------------
#
# A pack is attached and *then* distributed, so the response can land somewhere other than
# `last_distributed_submittal.distributed_responses` on the revision we asked about.

def test_response_name_read_from_a_nested_response_object():
    from app.procore.attachments import response_name_of

    assert response_name_of({'response': {'name': 'Final PDF Pack'}}) == 'Final PDF Pack'
    assert response_name_of({'distributed_response': {'name': 'Final PDF Pack'}}) == 'Final PDF Pack'
    assert response_name_of({'submittal_response_name': 'Final PDF Pack'}) == 'Final PDF Pack'
    assert response_name_of({'response': {'id': 7}}) is None
    assert response_name_of({}) is None


def test_workflow_responses_finds_approver_rows_outside_last_distributed():
    """workflow_data carries the approvers with their responses nested — the shape a
    fixed `last_distributed_submittal` read returned nothing for."""
    workflow = {'approvers': [
        {'id': 184985005, 'response': {'name': 'Final PDF Pack'},
         'user': {'name': 'Dalton Rauer'}},
        {'id': 184985006, 'response': {'name': 'Approved as Noted'}},
    ]}
    rows = workflow_responses(workflow)

    assert rows[184985005]['is_final_pdf'] is True
    assert rows[184985005]['approver_name'] == 'Dalton Rauer'
    assert rows[184985006]['is_final_pdf'] is False


def test_nested_approver_response_labels_the_attachment():
    workflow = {
        'attachments': [dict(PACK_FILE, approver_id=184985005)],
        'approvers': [{'id': 184985005, 'response': {'name': 'Final PDF Pack'}}],
    }
    refs = _refs_from({}, workflow)

    assert refs[0]['is_final_pdf_response'] is True
    assert refs[0]['response_name'] == 'Final PDF Pack'


def test_probe_covers_the_confirmation_endpoint_families():
    """Revisions, the response-name config, distributions and the change log — the places a
    'Final PDF Pack' label can live once the pack was attached then distributed."""
    from app.procore.attachments import probe_attachment

    with patch('app.procore.attachments._probe_get', return_value=(404, None)) as get:
        probe_attachment(2968284, 71563766, 6172561559,
                         item_id=184985005, item_type='SubmittalLogApprover')

    asked = ' '.join(call.args[0] for call in get.call_args_list)
    assert '/submittal_responses' in asked          # id -> name config
    assert '/revisions' in asked                    # the pack may be on another revision
    assert '/distributions' in asked
    assert '/changes' in asked                      # the change log the client reads
    assert 'filters[id][]=71563766' in asked        # the index serializer
