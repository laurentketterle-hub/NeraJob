import pytest, json, os, tempfile
from nerajob.tracker import Tracker, Application, AppStatus

@pytest.fixture
def tracker():
    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
        path = f.name
    t = Tracker(path)
    yield t
    if os.path.exists(path):
        os.unlink(path)

def test_add_application(tracker):
    app = tracker.add("Acme Corp", "Software Engineer")
    assert app.company == "Acme Corp"
    assert app.status == AppStatus.APPLIED
    assert len(tracker.apps) == 1

def test_status_transitions(tracker):
    app = tracker.add("Acme", "Dev")
    assert app.transition(AppStatus.PHONE_SCREEN)
    assert app.status == AppStatus.PHONE_SCREEN
    assert app.transition(AppStatus.INTERVIEW)
    assert app.status == AppStatus.INTERVIEW
    assert app.transition(AppStatus.OFFER)
    assert app.status == AppStatus.OFFER
    assert app.transition(AppStatus.ACCEPTED)
    assert app.status == AppStatus.ACCEPTED

def test_invalid_transition(tracker):
    app = tracker.add("Acme", "Dev")
    assert not app.transition(AppStatus.OFFER)
    assert app.status == AppStatus.APPLIED

def test_tracker_update(tracker):
    app = tracker.add("Acme", "Dev")
    assert tracker.update(app.id, AppStatus.PHONE_SCREEN, "HR call")
    assert tracker.apps[app.id].status == AppStatus.PHONE_SCREEN

def test_list_by_status(tracker):
    tracker.add("A", "Dev")
    app2 = tracker.add("B", "PM")
    tracker.update(app2.id, AppStatus.OFFER)
    applied = tracker.list(AppStatus.APPLIED)
    offers = tracker.list(AppStatus.OFFER)
    assert len(applied) == 1
    assert len(offers) == 1

def test_stats(tracker):
    tracker.add("A", "Dev")
    app2 = tracker.add("B", "PM")
    tracker.update(app2.id, AppStatus.OFFER)
    stats = tracker.stats()
    assert stats["total"] == 2
    assert stats["active"] == 2
    assert stats["by_status"]["applied"] == 1
    assert stats["by_status"]["offer"] == 1

def test_cli_help():
    from nerajob.tracker import cli
    import sys
    old = sys.argv
    sys.argv = ["tracker"]
    try:
        cli()
    except SystemExit:
        pass
    sys.argv = old

def test_persistence(tracker):
    app = tracker.add("PersistCo", "Role")
    t2 = Tracker(tracker.path)
    assert len(t2.apps) == 1
    assert t2.apps[app.id].company == "PersistCo"
