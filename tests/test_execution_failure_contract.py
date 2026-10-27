'Assert failure facts and final completion independently without native CAD.'
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "mcp-server"))
sys.path.insert(0, str(ROOT / "apps" / "desktop"))
from core.execution import execute_with_core, normalize_tool_payload


@pytest.mark.parametrize("payload", [
    {"status": "ok", "feature_created": False},
    {"status": "ok", "saved": False},
    {"status": "ok", "rebuild_ok": False},
    {"success": False}, {"status": "error"}, None, False,
])
def test_failed_tool_cannot_complete_even_if_reviewer_passes(payload):
    'A later PASS must not hide an independent failure.'
    result = execute_with_core(handler=lambda _: payload, run_id="failed",
        requires_review=True, reviewer_result={"status": "pass"})
    assert result.execution_result.success is False
    assert result.run_context.status.value == "failed"


@pytest.mark.parametrize("review", [
    {"status": "warning"}, {"status": "review_required"},
    {"status": "pass", "manual_review_required": True},
    {"status": "pass", "checks": [{"status": "fail", "required": True}]},
])
def test_review_not_approved_cannot_complete(review):
    'Pending review and critical failures are not final task success.'
    result = execute_with_core(handler=lambda _: {"status": "ok"}, run_id="review",
        requires_review=True, reviewer_result=review)
    assert result.run_context.status.value != "completed"


def test_dry_run_and_optional_unsaved_result_keep_compatibility():
    'Preview-only operations and tasks without a save request must not be falsely reported as failed.'
    payload = {"status": "ok", "dry_run": True, "feature_created": False, "saved": None}
    assert normalize_tool_payload(payload) == payload


def test_handler_manual_review_cannot_be_bypassed_by_caller():
    "A tool's manual-review declaration survives the default requires_review value."
    result = execute_with_core(handler=lambda _: {"status": "review_required", "manualReviewRequired": True},
        run_id="manual", reviewer_result={"status": "pass"})
    assert result.run_context.status.value == "blocked"


def test_registry_review_cannot_be_disabled_by_caller():
    'Default parameters cannot bypass a capability-registry review gate.'
    result = execute_with_core(handler=lambda _: {"status": "ok"}, run_id="registry",
        operation_id="solidworks_standard_automation", requires_review=False)
    assert result.run_context.status.value == "blocked"


def test_invalid_boolean_is_unverified_instead_of_truthy():
    assert normalize_tool_payload({"status": "ok", "success": "false"})["status"] == "blocked"


def test_mcp_json_and_markdown_expose_failure():
    'All formats derive failure status from the same facts.'
    import server
    raw = {"status": "ok", "feature_created": False}
    assert json.loads(server._result(raw, server.ResponseFormat.JSON))["status"] == "error"
    assert server._result(raw, server.ResponseFormat.MARKDOWN).startswith("# error")


def test_worker_records_review_failure_as_core_failure(tmp_path):
    'Missing artifacts must prevent completed states in both Queue and Core.'
    from cad_workbench.queue_worker import process_job
    path = tmp_path / "job.json"
    path.write_text(json.dumps({"id": "review-fail", "kind": "create_shell",
        "status": "queued", "expectedOutput": "STEP", "capabilities": []}), encoding="utf-8")
    result = process_job(path, handlers={"create_shell": lambda _: {"message": "ok", "outputs": []}})
    assert result["status"] == "failed"
    assert result["executionAssessment"]["status"] == "failed"


def test_worker_rejects_structured_handler_failure(tmp_path):
    'A failed handler must block delivery even without an exception.'
    from cad_workbench.queue_worker import process_job
    path = tmp_path / "job.json"
    path.write_text(json.dumps({"id": "tool-fail", "kind": "create_shell", "status": "queued"}), encoding="utf-8")
    result = process_job(path, handlers={"create_shell": lambda _: {"success": False, "message": "cut failed"}})
    assert result["status"] == "failed"
    assert result["executionAssessment"]["execution"]["success"] is False
