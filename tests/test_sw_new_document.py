"SolidWorks new-document regressions. If NewDocument returns None, falling back to an unrelated preexisting ActiveDoc could silently write all subsequent features into the user's document. These tests lock that destructive failure out."
from pathlib import Path

import pytest

from scripts import sw_connect


class FakeModel:
    'Minimal document identified by title.'

    def __init__(self, title, path=""):
        self._title = title
        self._path = path

    def GetTitle(self):
        return self._title

    def GetPathName(self):
        return self._path


class FakeSolidWorks:
    'Controllable SolidWorks fake maintaining open documents.'

    def __init__(self, documents=()):
        self.documents = list(documents)
        self.new_document_return = None
        self.new_document_side_effect = None
        self.new_document_calls = []

    def GetDocuments(self):
        return list(self.documents)

    def NewDocument(self, template, *_args):
        self.new_document_calls.append(template)
        if self.new_document_side_effect is not None:
            self.new_document_side_effect(self)
        return self.new_document_return


@pytest.fixture(autouse=True)
def _stub_template(monkeypatch):
    'Bypass template lookup to test new-document identity.'
    monkeypatch.setattr(sw_connect, "find_template", lambda _sw, _doc_type: r"C:\fake\part.prtdot")


def test_new_document_uses_returned_model():
    'Normal path: NewDocument returns the newly created document.'
    created = FakeModel("Part1")
    sw = FakeSolidWorks()

    def create(document_owner):
        document_owner.documents.append(created)

    sw.new_document_side_effect = create
    sw.new_document_return = created

    assert sw_connect.new_document(sw, "part") is created


def test_new_document_never_falls_back_to_preexisting_active_document():
    'If NewDocument returns None, never return an already open user document as the new result; doing so would direct later modeling into the wrong file.'
    user_part = FakeModel("UserPart.SLDPRT", r"C:\user\important.sldprt")
    sw = FakeSolidWorks([user_part])
    sw.new_document_return = None  # No new document was created.

    with pytest.raises(RuntimeError) as excinfo:
        sw_connect.new_document(sw, "part")

    message = str(excinfo.value)
    assert 'yeni belge döndürmedi' in message
    # The error must provide an actionable next step, not just failure.
    assert 'Şablon' in message


def test_new_document_recovers_when_return_value_is_none_but_document_exists():
    'When the return is absent, recover the actual new document through title-set difference.'
    user_part = FakeModel("UserPart.SLDPRT", r"C:\user\important.sldprt")
    created = FakeModel("Part1")
    sw = FakeSolidWorks([user_part])

    def create(document_owner):
        document_owner.documents.append(created)

    sw.new_document_side_effect = create
    sw.new_document_return = None

    assert sw_connect.new_document(sw, "part") is created


def test_new_document_rejects_stale_return_value():
    'Treat a same-name preexisting return as stale and use set-difference lookup.'
    user_part = FakeModel("UserPart.SLDPRT")
    created = FakeModel("Part1")
    sw = FakeSolidWorks([user_part])

    def create(document_owner):
        document_owner.documents.append(created)

    sw.new_document_side_effect = create
    sw.new_document_return = user_part  # Stale reference.

    assert sw_connect.new_document(sw, "part") is created


def test_new_document_detects_two_documents_with_same_title():
    'Title-based set difference must not select an existing user document.'
    user_part = FakeModel("Part1")
    sw = FakeSolidWorks([user_part])
    sw.new_document_return = None

    with pytest.raises(RuntimeError):
        sw_connect.new_document(sw, "part")


def test_snapshot_open_documents_tolerates_none():
    'GetDocuments may return None when no documents exist.'

    class EmptySolidWorks:
        def GetDocuments(self):
            return None

    assert sw_connect.snapshot_open_documents(EmptySolidWorks()) == set()


def test_snapshot_open_documents_tolerates_broken_member():
    'A single unreadable title must not interrupt the entire snapshot.'

    class BrokenSolidWorks:
        def GetDocuments(self):
            return [FakeModel("Good"), object()]

    assert sw_connect.snapshot_open_documents(BrokenSolidWorks()) == {"Good"}


def test_new_document_expands_explicit_template(monkeypatch, tmp_path):
    'Expand explicit template paths to absolute paths before NewDocument.'
    template = tmp_path / "custom.prtdot"
    template.write_bytes(b"template")
    created = FakeModel("Part1")
    sw = FakeSolidWorks()

    def create(document_owner):
        document_owner.documents.append(created)

    sw.new_document_side_effect = create
    sw.new_document_return = created

    sw_connect.new_document(sw, "part", str(template))

    assert Path(sw.new_document_calls[0]) == template.resolve()
