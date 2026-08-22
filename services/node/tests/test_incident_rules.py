import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.models.incident import IncidentStatus
from app.services.incident_registry import ALLOWED_TRANSITIONS


def test_incident_state_machine_allows_expected_forward_transitions() -> None:
    assert IncidentStatus.INVESTIGATING in ALLOWED_TRANSITIONS[IncidentStatus.OPEN]
    assert IncidentStatus.RESOLVED in ALLOWED_TRANSITIONS[IncidentStatus.INVESTIGATING]
    assert IncidentStatus.CLOSED in ALLOWED_TRANSITIONS[IncidentStatus.RESOLVED]
    assert IncidentStatus.CLOSED in ALLOWED_TRANSITIONS[IncidentStatus.OPEN]


def test_incident_state_machine_rejects_reopening_closed_incidents() -> None:
    assert IncidentStatus.OPEN not in ALLOWED_TRANSITIONS[IncidentStatus.CLOSED]
    assert IncidentStatus.INVESTIGATING not in ALLOWED_TRANSITIONS[IncidentStatus.CLOSED]
