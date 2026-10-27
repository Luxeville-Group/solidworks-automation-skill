"""Complex mechanical engineering DAG orchestrator regression tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from apps.desktop.cad_workbench.engineering_orchestrator import (
    CapabilityLevel,
    EngineeringPlan,
    PhaseStatus,
    build_engineering_plan,
    engineering_plan_from_dict,
    infer_affected_phases,
    requires_engineering_orchestration,
    replan_for_local_change,
)


BRIEF = "Pah, silindirik havşa, dört parçalı montaj, döner motor, GB/T çizimleri ve STEP/PDF teslimi içeren redüktör mekanizması"


def test_complex_reducer_is_split_into_complete_engineering_dag() -> None:
    """The combined gearbox request splits into eight independently acceptable stages."""
    plan = build_engineering_plan(BRIEF)

    assert [phase.id for phase in plan.phases] == [
        "requirements",
        "part-modeling",
        "holes-fillet-chamfer",
        "assembly-mates",
        "motion-study",
        "drawing-bom",
        "export-delivery",
        "final-review",
    ]
    assert plan.phase("part-modeling").depends_on == ("requirements",)
    assert plan.phase("assembly-mates").depends_on == ("holes-fillet-chamfer",)
    assert plan.phase("motion-study").depends_on == ("assembly-mates",)
    assert plan.phase("drawing-bom").depends_on == ("motion-study",)
    assert plan.phase("final-review").depends_on == ("export-delivery",)
    plan.validate()


def test_complex_classifier_does_not_force_simple_part_into_full_dag() -> None:
    """Simple extruded parts must not gain assembly, Motion, or drawing stages automatically."""
    assert requires_engineering_orchestration(BRIEF) is True
    assert requires_engineering_orchestration("50x30x10 mm dikdörtgen blok oluştur") is False
    assert requires_engineering_orchestration("Dört parçalı bir montaj tasarla ve STEP çıktısı oluştur") is True


def test_dynamic_dag_omits_unrequested_motion_and_drawing() -> None:
    """Assembly plus STEP must not expand automatically into Motion or drawing work."""
    plan = build_engineering_plan("Dört parçalı bir montaj tasarla ve STEP çıktısı oluştur")
    phase_ids = [phase.id for phase in plan.phases]

    assert phase_ids == ["requirements", "part-modeling", "assembly-mates", "export-delivery", "final-review"]
    assert plan.phase("assembly-mates").depends_on == ("part-modeling",)
    assert plan.phase("export-delivery").depends_on == ("assembly-mates",)
    with pytest.raises(KeyError):
        plan.phase("motion-study")


def test_routes_select_existing_skills_and_mcp_tools() -> None:
    """Chamfers, counterbores, assemblies, and Motion route to actual existing capabilities."""
    plan = build_engineering_plan(BRIEF)

    feature_phase = plan.phase("holes-fillet-chamfer")
    assert "solidworks-fillet-chamfer-cnc" in feature_phase.skills
    assert "solidworks_create_hole_feature" in feature_phase.mcp_tools
    assert "solidworks_inspect_hole_features" in feature_phase.mcp_tools

    assembly_phase = plan.phase("assembly-mates")
    assert "solidworks_add_component" in assembly_phase.mcp_tools
    assert "solidworks_add_concentric_mate" in assembly_phase.mcp_tools

    motion_phase = plan.phase("motion-study")
    assert "solidworks_add_rotary_motor" in motion_phase.mcp_tools
    assert "solidworks_validate_motion_study" in motion_phase.mcp_tools
    assert "solidworks_export_active" in plan.phase("export-delivery").mcp_tools


def test_every_phase_has_artifacts_acceptance_risks_and_retry_policy() -> None:
    """Each stage independently delivers evidence, acceptance, and partial retry."""
    plan = build_engineering_plan(BRIEF)

    for phase in plan.phases:
        assert phase.artifacts
        assert phase.acceptance
        assert phase.risks
        assert phase.retry_policy.max_attempts >= 1
        assert phase.retry_policy.fallback


def test_plan_never_claims_unexecuted_or_pilot_work_is_complete() -> None:
    """Successful planning must not imply completed CAD, BOM, or drawings."""
    plan = build_engineering_plan(BRIEF)
    drawing = plan.phase("drawing-bom")

    assert all(phase.status != PhaseStatus.COMPLETED for phase in plan.phases)
    assert drawing.routes[0].level == CapabilityLevel.PILOT
    assert drawing.routes[0].execution_mode == "assisted_human_gate"
    assert drawing.human_gate is True
    assert set(drawing.mcp_tools) >= {
        "solidworks_generate_drawing",
        "solidworks_review_drawing",
        "solidworks_inspect_drawing",
    }
    assert any("Gözetimsiz" in risk for risk in drawing.risks)


def test_capability_report_can_block_unimplemented_motion() -> None:
    """A local not-implemented report must prevent automatic Motion execution."""
    plan = build_engineering_plan(
        BRIEF,
        capability_report={
            "capabilities": {
                "motion_study": {
                    "implementation_status": "not_implemented",
                    "ready_for_unattended_use": False,
                }
            }
        },
    )

    motion = plan.phase("motion-study")
    assert motion.status == PhaseStatus.BLOCKED
    assert motion.routes[0].execution_mode == "blocked"
    assert motion.routes[0].level == CapabilityLevel.NOT_IMPLEMENTED

    invalid = replace(motion, status=PhaseStatus.COMPLETED)
    invalid_plan = replace(plan, phases=tuple(invalid if item.id == motion.id else item for item in plan.phases))
    with pytest.raises(ValueError, match="Uygulanmamış yetenek"):
        invalid_plan.validate()


def test_probe_capability_alias_downgrades_pilot_drawing_route() -> None:
    """The orchestrator recognizes the real capability probe's drawings key."""
    plan = build_engineering_plan(
        BRIEF,
        capability_report={
            "capabilities": {
                "drawings": {
                    "implementation_status": "not_implemented",
                    "ready_for_unattended_use": False,
                }
            }
        },
    )

    drawing = plan.phase("drawing-bom")
    assert drawing.status == PhaseStatus.BLOCKED
    assert drawing.routes[0].level == CapabilityLevel.NOT_IMPLEMENTED


def test_critical_cad_phases_share_single_serial_lane() -> None:
    """Critical SolidWorks COM stages must not be scheduled as concurrent writes."""
    plan = build_engineering_plan(BRIEF)
    critical = [phase for phase in plan.phases if phase.serial_required]

    assert plan.critical_cad_serial is True
    assert critical
    assert {phase.execution_lane for phase in critical} == {"solidworks-com"}
    assert plan.phase("requirements").serial_required is False


def test_local_hole_change_replans_only_affected_phase_and_descendants() -> None:
    """Changing a counterbore preserves accepted requirements and parts while invalidating hole features and all successors."""
    plan = build_engineering_plan(BRIEF)
    completed_phases = tuple(
        replace(phase, status=PhaseStatus.COMPLETED) if phase.id in {"requirements", "part-modeling"} else phase
        for phase in plan.phases
    )
    progressed = replace(plan, phases=completed_phases)

    replanned = replan_for_local_change(progressed, "Silindirik havşa çapını 12 mm yap")

    assert infer_affected_phases("Silindirik havşa çapını 12 mm yap") == ("holes-fillet-chamfer",)
    assert replanned.revision == 2
    assert replanned.phase("requirements").status == PhaseStatus.COMPLETED
    assert replanned.phase("part-modeling").status == PhaseStatus.COMPLETED
    assert replanned.phase("holes-fillet-chamfer").status == PhaseStatus.PLANNED
    assert replanned.phase("assembly-mates").status == PhaseStatus.PLANNED
    assert replanned.phase("drawing-bom").status == PhaseStatus.PLANNED
    assert replanned.phase("final-review").status == PhaseStatus.PLANNED
    assert "Silindirik havşa çapı" in (replanned.change_request or "")


def test_plan_serializes_to_provider_friendly_values() -> None:
    """Plans serialize directly into unified Agent job JSON."""
    payload = build_engineering_plan(BRIEF).to_dict()

    assert payload["schema_version"] == "1.0"
    assert payload["phases"][0]["status"] == "planned"
    assert payload["phases"][5]["routes"][0]["level"] == "pilot"
    assert payload["phases"][5]["human_gate"] is True


def test_persisted_plan_round_trip_supports_follow_up_replanning() -> None:
    """Restore the previous queued DAG and continue local edits."""
    original = build_engineering_plan(BRIEF)

    restored = engineering_plan_from_dict(original.to_dict())
    replanned = replan_for_local_change(restored, "Silindirik havşa çapını 12 mm yap")

    assert restored.to_dict() == original.to_dict()
    assert replanned.revision == original.revision + 1
    assert replanned.phase("holes-fillet-chamfer").status == PhaseStatus.PLANNED
