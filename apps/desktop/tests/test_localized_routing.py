"""Regression checks for Turkish/English engineering request routing."""
import tempfile
import unittest
from pathlib import Path

from apps.desktop.cad_workbench.engineering_orchestrator import (
    build_engineering_plan,
    infer_affected_phases,
    requires_engineering_orchestration,
)
from apps.desktop.cad_workbench.knowledge_retrieval import retrieve_local_knowledge


class LocalizedRoutingTests(unittest.TestCase):
    def test_turkish_and_english_requests_have_matching_stages(self):
        requests = (
            "Create an assembly with holes, fillets, concentric mates, a motion motor, drawings, BOM and STEP delivery",
            "DELİK, YUVARLATMA, EŞ MERKEZLİ İLİŞKİ, HAREKET MOTORU, ÇİZİM, BOM VE STEP TESLİMİ İÇEREN MONTAJ",
        )
        plans = []
        for request in requests:
            self.assertTrue(requires_engineering_orchestration(request))
            plans.append([stage.id for stage in build_engineering_plan(request).phases])
        self.assertEqual(plans[0], plans[1])
        self.assertIn("holes-fillet-chamfer", plans[0])
        self.assertIn("motion-study", plans[0])
        self.assertIn("drawing-bom", plans[0])

    def test_local_changes_route_to_the_feature_stage(self):
        for request in ("Increase the fillet radius", "YUVARLATMA YARIÇAPINI ARTIR"):
            self.assertEqual(infer_affected_phases(request), ("holes-fillet-chamfer",))

    def test_a_simple_part_does_not_require_combined_orchestration(self):
        for request in ("Create a basic block", "Basit bir blok oluştur"):
            self.assertFalse(requires_engineering_orchestration(request))

    def test_turkish_knowledge_retrieval_preserves_unicode_words(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "manufacturing.md"
            source.write_text("# Duvar kalınlığı\nÜretim için duvar kalınlığı doğrulanmalıdır.", encoding="utf-8")
            result = retrieve_local_knowledge("DUVAR KALINLIĞI", [source])
            self.assertEqual(len(result), 1)
            self.assertIn("Duvar kalınlığı", result[0].title)


if __name__ == "__main__":
    unittest.main()
