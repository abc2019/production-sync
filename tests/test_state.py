from app.state import StateStore


def test_new_state_has_no_synced(state_db_path):
    state = StateStore(state_db_path)
    assert state.get_synced_keys() == set()
    state.close()


def test_mark_synced_excludes_from_future(state_db_path):
    state = StateStore(state_db_path)
    state.mark_synced("op-1", product_id="p1", ombor_event_id="e1", completed_units=3)
    assert state.get_synced_keys() == {"op-1"}
    state.close()


def test_mark_failed_does_not_exclude_from_future(state_db_path):
    state = StateStore(state_db_path)
    state.mark_failed("op-2", reason="Ombor unreachable")
    assert state.get_synced_keys() == set()  # qayta urinish uchun
    state.close()


def test_mark_needs_review_does_not_exclude_from_future(state_db_path):
    state = StateStore(state_db_path)
    state.mark_needs_review("op-3", reason="noaniq moslik")
    assert state.get_synced_keys() == set()
    state.close()


def test_list_needs_review(state_db_path):
    state = StateStore(state_db_path)
    state.mark_needs_review("op-3", reason="noaniq moslik")
    state.mark_synced("op-1", product_id="p1", ombor_event_id="e1", completed_units=3)
    reviews = state.list_needs_review()
    assert len(reviews) == 1
    assert reviews[0].sync_key == "op-3"
    assert reviews[0].reason == "noaniq moslik"
    state.close()


def test_upsert_updates_status(state_db_path):
    state = StateStore(state_db_path)
    state.mark_failed("op-5", reason="temp error")
    assert state.list_needs_review() == []
    state.mark_synced("op-5", product_id="p1", ombor_event_id="e1", completed_units=2)
    assert state.get_synced_keys() == {"op-5"}
    state.close()


def test_state_persists_across_reopen(state_db_path):
    state1 = StateStore(state_db_path)
    state1.mark_synced("op-1", product_id="p1", ombor_event_id="e1", completed_units=1)
    state1.close()

    state2 = StateStore(state_db_path)
    assert state2.get_synced_keys() == {"op-1"}
    state2.close()
