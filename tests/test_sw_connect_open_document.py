'SolidWorks document-opening compatibility paths.'
from pathlib import Path

from scripts import sw_connect


class FakeModel:
    'Minimal document object.'


def test_open_document_reuses_existing_model(tmp_path):
    'Do not repeat OpenDoc6 for components already loaded by an assembly.'
    source = tmp_path / "part.sldprt"
    source.write_bytes(b"part")
    expected = FakeModel()

    class FakeSolidWorks:
        def GetOpenDocumentByName(self, path):
            assert Path(path) == source.resolve()
            return expected

        def OpenDoc6(self, *_args):
            raise AssertionError('Do not reopen an already loaded document')

    assert sw_connect.open_document(FakeSolidWorks(), source) is expected


def test_open_document_falls_back_to_dynamic_proxy(tmp_path, monkeypatch):
    'Use a dynamic proxy when makepy rejects by-ref VARIANT.'
    source = tmp_path / "part.sldprt"
    source.write_bytes(b"part")
    expected = FakeModel()

    class GeneratedSolidWorks:
        _oleobj_ = object()

        def GetOpenDocumentByName(self, _path):
            return None

        def OpenDoc6(self, *_args):
            raise TypeError("int() argument must not be VARIANT")

    class DynamicSolidWorks:
        def OpenDoc6(self, _path, _doc_type, _options, _configuration, errors, warnings):
            errors.value = 0
            warnings.value = 0
            return expected

    monkeypatch.setattr(
        sw_connect.win32com_client.dynamic,
        "DumbDispatch",
        lambda ole_object, _name: DynamicSolidWorks() if ole_object is GeneratedSolidWorks._oleobj_ else None,
    )

    assert sw_connect.open_document(GeneratedSolidWorks(), source, silent=True) is expected


def test_step_import_falls_back_to_dynamic_loadfile4(tmp_path, monkeypatch):
    'SW2026 LoadFile4 must also switch to a dynamic proxy on by-ref VARIANT failure.'
    source = tmp_path / "complex.step"
    source.write_bytes(b"ISO-10303-21")
    expected = FakeModel()
    import_data = object()

    class GeneratedSolidWorks:
        _oleobj_ = object()

        def GetOpenDocumentByName(self, _path):
            return None

        def GetImportFileData(self, _path):
            return import_data

        def LoadFile4(self, *_args):
            raise TypeError("int() argument must not be VARIANT")

    class DynamicSolidWorks:
        def LoadFile4(self, path, argument, data, errors):
            assert Path(path) == source.resolve()
            assert argument == "r"
            assert data is import_data
            errors.value = 0
            return expected

    monkeypatch.setattr(sw_connect, "ensure_default_templates", lambda _sw: True)
    monkeypatch.setattr(
        sw_connect.win32com_client.dynamic,
        "DumbDispatch",
        lambda ole_object, _name: DynamicSolidWorks()
        if ole_object is GeneratedSolidWorks._oleobj_
        else None,
    )

    assert sw_connect.open_document(GeneratedSolidWorks(), source) is expected
