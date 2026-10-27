"""Preserve English/Turkish input and legacy saved CAD aliases."""
import pytest

from scripts.sw_part import _get_sketch_name_candidates
from scripts.sw_preflight import ask_install_permission
from scripts.dfm_review import PROCESS_ALIASES


@pytest.mark.parametrize("answer", ["e", "evet", "EVET", "y", "yes", "YES"])
def test_explicit_turkish_and_english_install_confirmation(answer):
    assert ask_install_permission(input_func=lambda _: answer, output_func=lambda _: None)


@pytest.mark.parametrize("answer", ["", "h", "hayır", "no", "n", "maybe"])
def test_other_input_does_not_authorize_installation(answer):
    assert not ask_install_permission(input_func=lambda _: answer, output_func=lambda _: None)


def test_turkish_sketch_names_find_english_and_legacy_aliases():
    assert "Sketch3" in _get_sketch_name_candidates("Eskiz3")
    assert "Eskiz3" in _get_sketch_name_candidates("Sketch3")
    assert "\u8349\u56fe3" in _get_sketch_name_candidates("Sketch3")


def test_injection_process_keeps_saved_aliases():
    for alias in ("injection", "enjeksiyon", "\u6ce8\u5851"):
        assert PROCESS_ALIASES[alias] == "injection_molding"
