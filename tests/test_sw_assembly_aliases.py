'SolidWorks assembly localized reference-plane alias tests.'

from scripts import sw_assembly


class FakeModel:
    'Contains only the legacy localized front-plane alias.'

    def FeatureByName(self, name):
        return object() if name == '\u524d\u89c6\u57fa\u51c6\u9762' else None


class FakeComponent:
    'Provide the component name for error reporting.'

    Name2 = "base-1"


def test_component_feature_expands_english_plane_to_chinese_alias(monkeypatch) -> None:
    monkeypatch.setattr(sw_assembly, "get_component_model", lambda component, resolve=True: FakeModel())

    feature = sw_assembly.get_component_feature(FakeComponent(), "Front Plane")

    assert feature is not None
