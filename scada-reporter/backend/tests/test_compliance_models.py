from app.models.compliance import ComplianceEvent, ComplianceLimit, CompliancePermit


def test_compliance_table_names_are_stable():
    assert CompliancePermit.__tablename__ == "compliance_permits"
    assert ComplianceLimit.__tablename__ == "compliance_limits"
    assert ComplianceEvent.__tablename__ == "compliance_events"


def test_event_key_is_unique_constraint():
    names = {c.name for c in ComplianceEvent.__table__.constraints}
    assert "uq_compliance_events_event_key" in names
