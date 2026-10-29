import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.unit3 import Unit3State


def test_lamport_clock_merges_received_timestamp():
    state = Unit3State()
    assert state.tick("CCTV-A") == 1
    assert state.tick("CCTV-B", received_clock=8) == 9
    assert state.nodes["CCTV-B"]["lamport_clock"] == 9


def test_bully_election_chooses_highest_online_priority():
    state = Unit3State()
    result = state.elect("SECURITY-A")
    assert result["leader"] == "CCTV-A"
    assert state.nodes["SECURITY-A"]["status"] == "OFFLINE"


def test_mutex_queues_second_request_and_promotes_it_on_release():
    state = Unit3State()
    first = state.request_lock("CCTV-A", "INC-000001")
    second = state.request_lock("CCTV-B", "INC-000001")
    released = state.release_lock("CCTV-A")
    assert first["granted"] is True
    assert second["granted"] is False
    assert released["owner_node_id"] == "CCTV-B"


def test_snapshot_contains_consistent_global_state():
    state = Unit3State()
    snapshot = state.snapshot()
    assert snapshot["algorithm"] == "MARKER_BASED_GLOBAL_STATE"
    assert set(snapshot["nodes"]) == {"SECURITY-A", "CCTV-A", "CCTV-B", "MOBILE-A"}
