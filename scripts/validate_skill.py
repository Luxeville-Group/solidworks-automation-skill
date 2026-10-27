"""
Validate basic SOLIDWORKS Automation Skill integrity.

Static checks only; no SOLIDWORKS connection or pywin32 installation required. Catch syntax errors, missing key files, and SKILL.md metadata issues before commits or in CI.
"""
import ast
import json
import pathlib
import sys


def _configure_stdio_utf8():
    """Prefer UTF-8 diagnostics on Windows systems with legacy code pages."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


_configure_stdio_utf8()

ROOT = pathlib.Path(__file__).resolve().parents[1]
REQUIRED_FILES = [
    "SKILL.md",
    "README.md",
    "capabilities.yaml",
    "golden-workflows.yaml",
    "agents/openai.yaml",
    "scripts/sw_preflight.py",
    "scripts/sw_macro_guard.py",
    "scripts/sw_connect.py",
    "scripts/__init__.py",
    "scripts/sw_appearance.py",
    "scripts/sw_part.py",
    "scripts/sw_assembly.py",
    "scripts/sw_drawing.py",
    "scripts/sw_export.py",
    "scripts/sw_review.py",
    "scripts/sw_hole_features.py",
    "scripts/sw_motion.py",
    "scripts/sw_capability_probe.py",
    "scripts/sw_session.py",
    "scripts/capabilities.py",
    "scripts/cad_doctor.py",
    "scripts/cad_installation.py",
    "scripts/cad_diagnostics.py",
    "scripts/cad_studio.py",
    "scripts/headless_cad_writer.py",
    "scripts/headless_occt_service.py",
    "scripts/dxf_preview_scene.py",
    "scripts/dfm_profiles.py",
    "scripts/routing_review.py",
    "scripts/fea_analysis.py",
    "scripts/advanced_geometry.py",
    "requirements-occt.txt",
    "requirements-pdf.txt",
    "scripts/sw_entity_reference.py",
    "scripts/validate_mcp.py",
    "mcp-server/server.py",
    "mcp-server/README.md",
    "mcp-server/requirements.txt",
    "mcp-server/register_all_ai_mcp.js",
    "mcp-server/register_all_ai_mcp.ps1",
    "examples/08_mini_fan_motion_assembly.py",
    "references/part-modeling.md",
    "references/assembly.md",
    "references/mcp-server.md",
    "references/design-spec.md",
    "references/edge-selection.md",
    "scripts/design_spec.py",
    "scripts/build_from_spec.py",
    "scripts/sw_measure.py",
    "scripts/sw_edge_select.py",
    "references/drawing.md",
    "references/export.md",
    "references/review.md",
    "references/complex-hole-features.md",
    "references/motion-study.md",
    "references/agent-provider-architecture.md",
    "references/complex-mechanical-routing.md",
    "references/enterprise-agent-rag.md",
    "references/api-lookup.md",
    "references/troubleshooting.md",
]


def check_required_files():
    """Check required files exist."""
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).exists()]
    if missing:
        raise AssertionError("Eksik gerekli dosyalar: " + ", ".join(missing))


def check_skill_frontmatter():
    """Check basic SKILL.md frontmatter."""
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise AssertionError("SKILL.md YAML frontmatter ile başlamalı")
    if "name: solidworks-automation" not in text:
        raise AssertionError("SKILL.md doğru name alanını içermiyor")
    if "description:" not in text:
        raise AssertionError("SKILL.md description alanı eksik")


def check_python_syntax():
    """Check Python syntax in primary scripts, desktop backend, MCP, tests, and every subskill."""
    roots = ["scripts", "examples", "tests", "apps/desktop", "mcp-server", "subskills"]
    targets = sorted(
        path
        for relative in roots
        for path in (ROOT / relative).rglob("*.py")
        if not {"__pycache__", "node_modules", "target", "ai_team"}.intersection(path.parts)
    )
    for path in targets:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return len(targets)


def check_json_files():
    """Check task/output contracts and design-plan schemas are valid JSON."""
    targets = [
        ROOT / "apps/desktop/cad_workbench/schemas/automation_job.schema.json",
        ROOT / "apps/desktop/cad_workbench/schemas/codex_final_response.schema.json",
        ROOT / "apps/desktop/cad_workbench/schemas/neutral_cad_document.schema.json",
        ROOT / "apps/desktop/cad_workbench/schemas/preview_manifest.schema.json",
        ROOT / "apps/desktop/cad_workbench/schemas/evidence_graph.schema.json",
        ROOT / "apps/desktop/cad_workbench/schemas/fea_analysis.schema.json",
        ROOT / "apps/desktop/cad_workbench/schemas/advanced_geometry.schema.json",
        ROOT / "subskills/solidworks-vibecad/schemas/design_plan.schema.json",
        ROOT / "subskills/solidworks-engineering-drawing/schemas/drawing_spec.schema.json",
    ]
    for path in targets:
        json.loads(path.read_text(encoding="utf-8"))
    json.loads((ROOT / "capabilities.yaml").read_text(encoding="utf-8"))
    workflows = json.loads((ROOT / "golden-workflows.yaml").read_text(encoding="utf-8"))
    if len(workflows.get("workflows", [])) != 10:
        raise AssertionError("Golden workflow temel kümesi 10 öğe olarak kalmalı")
    return len(targets)


def main():
    """Run all static checks."""
    check_required_files()
    check_skill_frontmatter()
    python_count = check_python_syntax()
    json_count = check_json_files()
    print(f"Doğrulama başarılı: skill dosyaları eksiksiz; {python_count} Python dosyası ve {json_count} JSON Schema geçerli.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Doğrulama başarısız: {exc}", file=sys.stderr)
        sys.exit(1)
