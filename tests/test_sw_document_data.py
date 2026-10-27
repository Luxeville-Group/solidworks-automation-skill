'COM-free SolidWorks parameter/property wrapper regressions.'
from __future__ import annotations

from scripts import sw_document_data as document_data


class FakeVariant:
    def __init__(self, _variant_type, value):
        self.value = value


class FakeDimension:
    def __init__(self):
        self.values = {'Varsayılan': 0.01, 'İşleme': 0.02}
        self.current = 'Varsayılan'

    @property
    def SystemValue(self):
        return self.values[self.current]

    def GetSystemValue2(self, name):
        return self.values[name]

    def SetSystemValue3(self, value, mode, names):
        if mode == 1:
            self.values[self.current] = value
        elif mode == 2:
            self.values = {name: value for name in self.values}
        elif mode == 3:
            for name in names.value:
                self.values[name] = value
        return 0


class FakePropertyManager:
    def __init__(self):
        self.values = {}

    def Add3(self, name, _kind, value, _option):
        self.values[name] = value
        return 0

    def Get6(self, name, _cached, raw, resolved, was_resolved, linked):
        if name not in self.values:
            return 1
        raw.value = self.values[name]
        resolved.value = self.values[name]
        was_resolved.value = True
        linked.value = False
        return 2


class FakeExtension:
    def __init__(self):
        self.managers = {}

    def CustomPropertyManager(self, configuration):
        return self.managers.setdefault(configuration, FakePropertyManager())


class FakeModel:
    def __init__(self):
        self.dimension = FakeDimension()
        self.Extension = FakeExtension()

    def Parameter(self, name):
        return self.dimension if name == "D1@Boss-Extrude1" else None

    def GetConfigurationNames(self):
        return ['Varsayılan', 'İşleme']

    def EditRebuild3(self):
        return True


class FakePropertyRebuildModel(FakeModel):
    'Simulate SW2024 exposing EditRebuild3 as a Boolean pseudo-property.'

    EditRebuild3 = True


class FakeConfigurationModel(FakeModel):
    'Simulate AddConfiguration3, ShowConfiguration2 and active-configuration readback.'

    def __init__(self):
        super().__init__()
        self.names = ['Varsayılan']
        self.active = type("Config", (), {"Name": 'Varsayılan'})()
        self.ConfigurationManager = type("Manager", (), {})()
        self.ConfigurationManager.ActiveConfiguration = self.active

    def GetConfigurationNames(self):
        return list(self.names)

    def AddConfiguration3(self, name, comment, alternate_name, options):
        config = type(
            "Config",
            (),
            {"Name": name, "Comment": comment, "AlternateName": alternate_name, "Options": options},
        )()
        self.names.append(name)
        return config

    def ShowConfiguration2(self, name):
        if name not in self.names:
            return False
        self.active = type("Config", (), {"Name": name})()
        self.ConfigurationManager.ActiveConfiguration = self.active
        self.dimension.current = name if name in self.dimension.values else 'Varsayılan'
        return True


def setup_module():
    document_data.VARIANT = FakeVariant
    document_data.pythoncom.VT_ARRAY = 0x2000
    document_data.pythoncom.VT_BSTR = 8
    document_data.pythoncom.VT_BYREF = 0x4000
    document_data.pythoncom.VT_BOOL = 11


def test_updates_specific_configuration_with_mm_conversion():
    model = FakeModel()
    result = document_data.update_dimension_mm(
        model,
        "D1@Boss-Extrude1",
        35.0,
        configuration_mode="specific",
        configuration_names=['İşleme'],
    )
    assert result["success"] is True
    assert result["before_mm"] == {'İşleme': 20.0}
    assert result["after_mm"] == {'İşleme': 35.0}
    assert model.dimension.values['Varsayılan'] == 0.01


def test_accepts_edit_rebuild_as_boolean_property():
    model = FakePropertyRebuildModel()
    result = document_data.update_dimension_mm(
        model,
        "D1@Boss-Extrude1",
        15.0,
    )
    assert result["success"] is True
    assert result["rebuild_success"] is True
    assert result["after_mm"] == {"current": 15.0}


def test_rejects_missing_dimension_and_invalid_value():
    model = FakeModel()
    try:
        document_data.update_dimension_mm(model, "missing", 10)
    except LookupError as error:
        assert 'Ölçü bulunamadı' in str(error)
    else:
        raise AssertionError("missing dimension should fail")

    try:
        document_data.update_dimension_mm(model, "D1@Boss-Extrude1", 0)
    except ValueError as error:
        assert 'sıfırdan büyük' in str(error)
    else:
        raise AssertionError("non-positive dimension should fail")


def test_sets_and_reads_back_configuration_properties():
    model = FakeModel()
    result = document_data.set_custom_properties(
        model,
        {"PartNumber": "PN-001", "Material": "45#"},
        configuration_name='İşleme',
    )
    assert result["success"] is True
    assert [item["verified"] for item in result["properties"]] == [True, True]
    assert result["properties"][0]["readback"]["raw"] == "PN-001"


def test_inspects_configurations_and_active_configuration():
    model = FakeModel()
    model.ConfigurationManager = type(
        "Manager",
        (),
        {"ActiveConfiguration": type("Config", (), {"Name": 'İşleme'})()},
    )()

    result = document_data.inspect_configurations(model)

    assert result["status"] == "pilot"
    assert result["configurations"] == ['Varsayılan', 'İşleme']
    assert result["active_configuration"] == 'İşleme'


def test_creates_activates_and_reads_back_configuration():
    'New configurations must appear in the list and become active.'
    model = FakeConfigurationModel()

    result = document_data.create_configuration(
        model,
        'İşleme',
        comment='CNC çalışma durumu',
        alternate_name="MACHINED",
    )

    assert result["success"] is True
    assert result["created"] is True
    assert result["configurations_after"] == ['Varsayılan', 'İşleme']
    assert result["activation"]["readback_verified"] is True
    assert result["activation"]["after"] == 'İşleme'


def test_configuration_create_is_idempotent_or_strict_on_request():
    'Reuse existing configurations by default; strict mode rejects same-name replacement.'
    model = FakeConfigurationModel()
    model.AddConfiguration3('İşleme', "", "", 0)

    reused = document_data.create_configuration(model, 'İşleme')

    assert reused["success"] is True
    assert reused["created"] is False
    assert reused["reused"] is True
    try:
        document_data.create_configuration(model, 'İşleme', if_exists="error")
    except FileExistsError as error:
        assert 'Konfigürasyon zaten var' in str(error)
    else:
        raise AssertionError("strict duplicate configuration should fail")


def test_activate_configuration_rejects_unknown_name_before_com_call():
    'Unknown configurations fail before calling ShowConfiguration2.'
    model = FakeConfigurationModel()

    try:
        document_data.activate_configuration(model, 'missing')
    except LookupError as error:
        assert 'Konfigürasyon bulunamadı' in str(error)
    else:
        raise AssertionError("unknown configuration should fail")


def test_activate_configuration_accepts_already_active_readback_without_redundant_call():
    'SW2026 auto-activation after creation must not be misread as failure from a repeated ShowConfiguration2=False.'
    model = FakeConfigurationModel()
    model.AddConfiguration3('İnce', "", "", 0)
    model.ShowConfiguration2('İnce')
    calls = 0

    def unexpected_show(_name):
        nonlocal calls
        calls += 1
        return False

    model.ShowConfiguration2 = unexpected_show
    result = document_data.activate_configuration(model, 'İnce')

    assert result["success"] is True
    assert result["api_called"] is False
    assert result["api_return"] is None
    assert calls == 0


def test_configuration_names_are_resolved_case_insensitively() -> None:
    'English configuration-name casing must not create duplicates.'
    model = FakeConfigurationModel()
    model.AddConfiguration3("Machined", "", "", 0)

    result = document_data.create_configuration(model, "MACHINED")

    assert result["success"] is True
    assert result["created"] is False
    assert result["configuration"] == "Machined"
    assert result["requested_configuration"] == "MACHINED"
    assert model.names.count("Machined") == 1
