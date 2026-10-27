"""
SOLIDWORKS Motion Study automation.

Wrap type-library loading, study creation, constant-speed rotary motor creation, and calculation. SOLIDWORKS API lengths use meters; rotational speeds use RPM.
"""
import glob
import os
from pathlib import Path

try:
    from .sw_preflight import import_com_dependencies
    from .sw_connect import safe_get_com_member
    from .sw_assembly import find_largest_cylinder_face
    from .cad_installation import discover_installations
except ImportError:
    from sw_preflight import import_com_dependencies
    from sw_connect import safe_get_com_member
    from sw_assembly import find_largest_cylinder_face
    from cad_installation import discover_installations

pythoncom, win32com_client, VARIANT = import_com_dependencies()


SW_FM_AEM_ROTATIONAL_MOTOR = 78
SW_MOTION_STUDY_BASIC_MOTION = 1


def _motion_typelib_candidates():
    """@brief Enumerate Motion Study type libraries from discovered installations and compatibility directories."""
    discovered = []
    for installation in discover_installations("solidworks"):
        executable = installation.get("executable")
        if executable:
            discovered.append(str(Path(executable).parent / "swmotionstudy.tlb"))
    patterns = [
        *discovered,
        r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\swmotionstudy.tlb",
        r"C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS*\swmotionstudy.tlb",
        r"C:\Program Files\Dassault Systemes\SOLIDWORKS*\swmotionstudy.tlb",
        r"E:\Solidworks\SOLIDWORKS\swmotionstudy.tlb",
    ]
    seen = set()
    for pattern in patterns:
        for path in glob.glob(os.path.expandvars(pattern)):
            norm = os.path.normcase(os.path.abspath(path))
            if norm in seen:
                continue
            seen.add(norm)
            yield path


def ensure_motion_type_library(raise_on_error=False):
    """
    @brief Generate the pywin32 wrapper for the SOLIDWORKS Motion Study type library.
    @param raise_on_error Raise when unavailable or loading fails.
    @return Loaded type-library path, or None on failure when raise_on_error=False.

    IMotionStudyManager is in swmotionstudy.tlb, not the main sldworks library. Without it, dynamic pywin32 members such as CreateMotionStudy and GetMotionStudyCount may appear as properties rather than methods.
    """
    errors = []
    for path in _motion_typelib_candidates():
        try:
            tlb = pythoncom.LoadTypeLib(path)
            guid, lcid, _syskind, major, minor, _flags = tlb.GetLibAttr()
            win32com_client.gencache.EnsureModule(guid, lcid, major, minor)
            return path
        except Exception as exc:
            errors.append(f"{path}: {exc}")

    if raise_on_error:
        detail = "\n".join(errors) if errors else "swmotionstudy.tlb bulunamadı"
        raise RuntimeError("SOLIDWORKS Motion Study type library yüklenemedi:\n" + detail)
    return None


def motion_member(obj, attr_name, *args):
    """
    @brief Support property/method duality in Motion Study COM members.
    @param obj COM object.
    @param attr_name Member name.
    @param args Arguments for callable members.
    @return Member value or method result.

    In upstream SOLIDWORKS 2024 + pywin32 checks, CreateMotionStudy, Activate, Calculate, and Play may be properties; SetDuration, CreateDefinition, and CreateFeature are usually methods. This wrapper hides those differences.
    """
    member = getattr(obj, attr_name)
    if args:
        if callable(member):
            return member(*args)
        if len(args) == 0:
            return member
        raise TypeError(f"Motion Study üyesi çağrılabilir değil: {attr_name}")
    try:
        return member() if callable(member) else member
    except Exception as exc:
        message = str(exc)
        if "-2147352573" in message or "\u627e\u4e0d\u5230\u6210\u5458" in message or "Member not found" in message:
            return member
        raise


def get_motion_study_manager(asm_model, load_type_library=True):
    """
    @brief Get the assembly MotionStudyManager.
    @param asm_model Assembly IModelDoc2/IAssemblyDoc.
    @param load_type_library Load swmotionstudy.tlb first.
    @return MotionStudyManager COM object.
    """
    if load_type_library:
        ensure_motion_type_library(raise_on_error=False)
    manager = safe_get_com_member(asm_model.Extension, "GetMotionStudyManager")
    if manager is None:
        raise RuntimeError("MotionStudyManager alınamadı; etkin belgenin montaj olduğunu ve SOLIDWORKS Motion kullanılabildiğini doğrulayın")
    return manager


def create_motion_study(asm_model, name=None, duration=4.0, study_type=None):
    """
    @brief Create and activate a Motion Study.
    @param asm_model Assembly IModelDoc2/IAssemblyDoc.
    @param name Optional study name.
    @param duration Animation duration in seconds.
    @param study_type Optional type; None preserves the SOLIDWORKS default.
    @return Motion Study COM object.
    """
    manager = get_motion_study_manager(asm_model)
    study = motion_member(manager, "CreateMotionStudy")
    if study is None:
        raise RuntimeError("Motion Study oluşturulamadı")
    if name:
        try:
            study.Name = name
        except Exception:
            pass
    if study_type is not None:
        try:
            study.StudyType = int(study_type)
        except Exception:
            pass
    if not bool(motion_member(study, "Activate")):
        raise RuntimeError("Motion Study etkinleştirilemedi")
    if duration is not None:
        try:
            motion_member(study, "SetDuration", float(duration))
        except Exception:
            pass
    return study


def _set_first_supported(obj, names, value):
    """Set the first available property from candidate names."""
    last_error = None
    for name in names:
        try:
            setattr(obj, name, value)
            return name
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise ValueError("Aday özellik adları boş olamaz")


def _set_load_references(motor_data, references):
    """
    @brief Set motor load references with tuple/list/VARIANT COM compatibility.
    @param motor_data ISimulationMotorFeatureData.
    @param references Assembly-context entities.
    @return True on success.
    """
    variants = [
        tuple(references),
        list(references),
        VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_VARIANT, list(references)),
        VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, list(references)),
    ]
    for refs in variants:
        try:
            motor_data.LoadReferences = refs
            return True
        except Exception:
            continue
    return False


def add_constant_speed_rotary_motor(
    motion_study,
    direction_reference,
    load_reference,
    rpm=60.0,
    relative_component=None,
    name=None,
    reverse=False,
):
    """
    @brief Add a constant-speed rotary motor to a Motion Study.
    @param motion_study Motion Study COM object.
    @param direction_reference Rotation direction, usually an assembly-context axis or cylinder.
    @param load_reference Driven component reference, usually an impeller/rotor cylinder.
    @param rpm Speed in RPM.
    @param relative_component Optional stationary relative component.
    @param name Optional motor feature name.
    @param reverse Reverse rotation when True.
    @return Created motor Feature.
    """
    motor_data = motion_member(motion_study, "CreateDefinition", SW_FM_AEM_ROTATIONAL_MOTOR)
    if motor_data is None:
        raise RuntimeError("Rotary motor FeatureData oluşturulamadı")

    motor_data.DirectionReference = direction_reference
    motion_member(motor_data, "ConstantSpeedMotor", float(rpm))
    motor_data.ReverseDirection = bool(reverse)
    if relative_component is not None:
        motor_data.RelativeComponent = relative_component

    try:
        motor_data.Location = load_reference
    except Exception:
        pass

    if not _set_load_references(motor_data, [load_reference]):
        raise RuntimeError("Rotary motor LoadReferences ayarlanamadı")
    motor_feature = motion_member(motion_study, "CreateFeature", motor_data)
    if motor_feature is None:
        raise RuntimeError("Rotary motor özelliği oluşturulamadı")
    if name:
        try:
            motor_feature.Name = name
        except Exception:
            pass
    return motor_feature


def add_constant_speed_rotary_motor_by_cylinders(
    motion_study,
    shaft_component,
    rotor_component,
    shaft_radius=None,
    rotor_radius=None,
    rpm=60.0,
    name=None,
    reverse=False,
):
    """
    @brief Find shaft and rotor cylinders and add a constant-speed rotary motor.
    @param motion_study Motion Study COM object.
    @param shaft_component Stationary shaft/support component.
    @param rotor_component Driven rotating component.
    @param shaft_radius Shaft cylinder radius range (min, max), meters; None means unrestricted.
    @param rotor_radius Rotor cylinder radius range (min, max), meters; None means unrestricted.
    @param rpm Speed in RPM.
    @param name Optional motor feature name.
    @param reverse Reverse rotation when True.
    @return Created motor Feature.
    """
    shaft_radius = shaft_radius or (0.0, None)
    rotor_radius = rotor_radius or (0.0, None)
    direction_reference = find_largest_cylinder_face(
        shaft_component,
        min_radius=shaft_radius[0],
        max_radius=shaft_radius[1],
    )
    load_reference = find_largest_cylinder_face(
        rotor_component,
        min_radius=rotor_radius[0],
        max_radius=rotor_radius[1],
    )
    return add_constant_speed_rotary_motor(
        motion_study,
        direction_reference,
        load_reference,
        rpm=rpm,
        relative_component=shaft_component,
        name=name,
        reverse=reverse,
    )


def calculate_and_play(motion_study, play=True):
    """
    @brief Calculate the Motion Study and optionally play animation.
    @param motion_study Motion Study COM object.
    @param play Call Play after successful calculation when True.
    @return Boolean Calculate result.
    """
    calculated = bool(motion_member(motion_study, "Calculate"))
    if play and calculated:
        try:
            motion_member(motion_study, "Play")
        except Exception:
            pass
    return calculated


def _collect_motion_features(motion_study):
    """@brief Read Motion feature names/types to identify actual features such as rotary motors."""
    try:
        raw_features = motion_member(motion_study, "GetMotionFeatures") or []
    except Exception:
        raw_features = []
    if not isinstance(raw_features, (list, tuple)):
        raw_features = [raw_features]
    features = []
    for feature in raw_features:
        try:
            type_name = None
            for member_name in ("GetTypeName2", "GetTypeName"):
                try:
                    type_name = motion_member(feature, member_name)
                    if type_name:
                        break
                except Exception:
                    continue
            features.append({
                "name": str(motion_member(feature, "Name") or ""),
                "type_id": int(motion_member(feature, "GetType") or 0),
                "type_name": str(type_name or ""),
            })
        except Exception as exc:
            features.append({"name": "", "type_id": 0, "type_name": "", "error": str(exc)})
    return features


def collect_motion_study_summary(asm_model):
    """
    @brief Collect machine-readable summaries of all assembly Motion Studies.
    @param asm_model Assembly IModelDoc2/IAssemblyDoc.
    @return Names, types, durations, motor/force counts, and result state.

    Read only members exposed by the official type library. Do not modify studies or equate study existence with correct motion results. Recalculate whenever results_out_of_date is True.
    """
    manager = get_motion_study_manager(asm_model)
    count = int(motion_member(manager, "GetMotionStudyCount") or 0)
    names = motion_member(manager, "GetMotionStudyNames") or []
    if isinstance(names, str):
        names = [names]
    names = [str(name) for name in list(names)[:count]]
    studies = []
    for name in names:
        study = motion_member(manager, "GetMotionStudy", name)
        if study is None:
            studies.append({"name": name, "available": False})
            continue
        study_type = int(motion_member(study, "StudyType") or 0)
        results = None
        results_error = None
        try:
            results = motion_member(study, "GetResults", study_type)
        except Exception as exc:
            results_error = str(exc)
        motion_features = _collect_motion_features(study)
        reported_motor_count = int(motion_member(study, "GetNumOfExternalMotors") or 0)
        motor_feature_count = sum("motor" in item.get("type_name", "").lower() for item in motion_features)
        item = {
            "name": str(motion_member(study, "Name") or name),
            "available": True,
            "study_type": study_type,
            "duration_seconds": float(motion_member(study, "GetDuration") or 0.0),
            "motor_count": max(reported_motor_count, motor_feature_count),
            "reported_motor_count": reported_motor_count,
            "motor_feature_count": motor_feature_count,
            "external_force_count": int(motion_member(study, "GetNumOfExternalForces") or 0),
            "feature_count": int(motion_member(study, "GetMotionFeaturesCount") or 0),
            "active": bool(motion_member(study, "IsActive")),
            "playing": bool(motion_member(study, "IsPlaying")),
            "results_available": results is not None,
            "motion_features": motion_features,
        }
        if results is not None:
            item["results_out_of_date"] = bool(motion_member(results, "IsOutOfDate"))
        if results_error:
            item["results_error"] = results_error
        studies.append(item)
    return {
        "motion_type_library": ensure_motion_type_library(raise_on_error=False),
        "study_count": count,
        "studies": studies,
    }


def validate_motion_study_summary(
    summary,
    study_name=None,
    expected_study_type=None,
    minimum_duration_seconds=0.001,
    minimum_motor_count=1,
    require_results=True,
):
    """
    @brief Validate delivery evidence for Motion Studies.
    @param summary collect_motion_study_summary() result.
    @param study_name Optional target name; None checks all available studies.
    @param expected_study_type Optional expected StudyType enum.
    @param minimum_duration_seconds Minimum duration.
    @param minimum_motor_count Minimum motor count.
    @param require_results Require calculated, current results.
    @return dict with status, checks, issues, and matched_studies.
    """
    checks = []
    issues = []

    def check(check_id, passed, failure_message, study=None, success_message=None):
        """@brief Append one acceptance check."""
        message = success_message if passed and success_message else failure_message
        item = {"id": check_id, "passed": bool(passed), "message": message}
        if study:
            item["study"] = study
        checks.append(item)
        if not passed:
            issues.append(failure_message)

    studies = [item for item in summary.get("studies", []) if item.get("available")]
    if study_name is not None:
        studies = [item for item in studies if item.get("name") == study_name]
    check(
        "study-present",
        bool(studies),
        f"Kullanılabilir Motion Study bulunamadı: {study_name or 'Herhangi bir çalışma'}",
        success_message=f"Motion Study bulundu: {study_name or 'Herhangi bir çalışma'}",
    )
    check(
        "type-library",
        bool(summary.get("motion_type_library")),
        "swmotionstudy.tlb doğrulanamadı; Motion sonuçları eksik okunabilir",
        success_message="swmotionstudy.tlb doğrulandı",
    )

    for study in studies:
        name = str(study.get("name") or "Adsız çalışma")
        duration = float(study.get("duration_seconds") or 0.0)
        motor_count = int(study.get("motor_count") or 0)
        check(
            "duration",
            duration >= float(minimum_duration_seconds),
            f"{name} süresi {duration:g} s; gereken süreden kısa: {minimum_duration_seconds:g}s",
            name,
            f"{name} süresi {duration:g} s gereksinimi karşılıyor",
        )
        check(
            "motor-count",
            motor_count >= int(minimum_motor_count),
            f"{name} motor sayısı {motor_count} gereken değerden küçük: {minimum_motor_count}",
            name,
            f"{name} bulunan {motor_count} motor özelliği",
        )
        if expected_study_type is not None:
            actual_type = int(study.get("study_type") or 0)
            check(
                "study-type",
                actual_type == int(expected_study_type),
                f"{name} StudyType={actual_type}; beklenen {expected_study_type}",
                name,
                f"{name} StudyType={actual_type} gereksinimi karşılıyor",
            )
        if require_results:
            available = bool(study.get("results_available"))
            check("results-present", available, f"{name} okunabilir hesaplama sonucu yok", name, f"{name} hesaplama sonuçları okunabilir")
            check(
                "results-fresh",
                available and study.get("results_out_of_date") is False,
                f"{name} sonuç yok veya güncelliğini yitirmiş; Calculate yeniden çalıştırılmalı",
                name,
                f"{name} sonuç mevcut ve güncel",
            )
        if study.get("results_error"):
            check("results-readable", False, f"{name} sonuçları okunamadı: {study['results_error']}", name)

    return {
        "status": "pass" if checks and all(item["passed"] for item in checks) else "fail",
        "checks": checks,
        "issues": issues,
        "matched_studies": [item.get("name") for item in studies],
        "requirements": {
            "study_name": study_name,
            "expected_study_type": expected_study_type,
            "minimum_duration_seconds": float(minimum_duration_seconds),
            "minimum_motor_count": int(minimum_motor_count),
            "require_results": bool(require_results),
        },
    }


def validate_motion_studies(asm_model, **requirements):
    """@brief Read assembly Motion summaries and apply the delivery gate."""
    summary = collect_motion_study_summary(asm_model)
    validation = validate_motion_study_summary(summary, **requirements)
    return {"summary": summary, "validation": validation}
