"""ComplianceReportPack model: table name, status constant + indexes stable."""

from app.models.compliance import REPORT_PACK_STATUSES, ComplianceReportPack


def test_report_pack_table_name_is_stable():
    assert ComplianceReportPack.__tablename__ == "compliance_report_packs"


def test_report_pack_status_constant():
    assert REPORT_PACK_STATUSES == (
        "draft",
        "ready_for_review",
        "failed",
        "approved",
        "exported",
    )


def test_report_pack_has_expected_columns():
    cols = set(ComplianceReportPack.__table__.columns.keys())
    expected = {
        "id",
        "permit_id",
        "period_start",
        "period_end",
        "status",
        "events_snapshot_json",
        "archive_id",
        "pdf_blob",
        "xlsx_blob",
        "json_blob",
        "error_message",
        "prepared_by",
        "approved_by",
        "approved_at",
        "created_at",
        "updated_at",
    }
    assert expected <= cols


def test_report_pack_indexes_present():
    index_names = {ix.name for ix in ComplianceReportPack.__table__.indexes}
    assert "ix_compliance_report_packs_permit_period" in index_names
    assert "ix_compliance_report_packs_status" in index_names


def test_report_pack_status_column_default():
    assert ComplianceReportPack.__table__.columns["status"].default.arg == "draft"
