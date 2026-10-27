"""@brief Compile complex mechanical requirements into an auditable SolidWorks engineering DAG."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple


class CapabilityLevel(str, Enum):
    """@brief Describe implementation and real-regression maturity of skills."""

    VERIFIED = "verified"
    PILOT = "pilot"
    REFERENCE_ONLY = "reference_only"
    NOT_IMPLEMENTED = "not_implemented"


class PhaseStatus(str, Enum):
    """@brief Describe the execution state of one engineering stage."""

    PLANNED = "planned"
    BLOCKED = "blocked"
    COMPLETED = "completed"


@dataclass(frozen=True)
class RetryPolicy:
    """@brief Describe partial retry and fallback policies after stage failure."""

    max_attempts: int
    strategy: str
    retryable_failures: Tuple[str, ...]
    fallback: str


@dataclass(frozen=True)
class CapabilityRoute:
    """@brief Describe the capability, skill, and MCP tools."""

    capability_id: str
    level: CapabilityLevel
    skills: Tuple[str, ...]
    mcp_tools: Tuple[str, ...]
    execution_mode: str
    reason: str


@dataclass(frozen=True)
class EngineeringPhase:
    """@brief Describe an engineering DAG stage that can be executed, accepted, and retried independently."""

    id: str
    name: str
    depends_on: Tuple[str, ...]
    routes: Tuple[CapabilityRoute, ...]
    artifacts: Tuple[str, ...]
    acceptance: Tuple[str, ...]
    risks: Tuple[str, ...]
    retry_policy: RetryPolicy
    status: PhaseStatus = PhaseStatus.PLANNED
    serial_required: bool = True
    execution_lane: str = "solidworks-com"
    human_gate: bool = False

    @property
    def skills(self) -> Tuple[str, ...]:
        """@brief Return deduplicated stage skill names."""
        return _unique(item for route in self.routes for item in route.skills)

    @property
    def mcp_tools(self) -> Tuple[str, ...]:
        """@brief Return deduplicated MCP tools for the stage."""
        return _unique(item for route in self.routes for item in route.mcp_tools)


@dataclass(frozen=True)
class EngineeringPlan:
    """@brief Describe the complete stage plan for a complex mechanical project."""

    objective: str
    project_type: str
    phases: Tuple[EngineeringPhase, ...]
    assumptions: Tuple[str, ...]
    warnings: Tuple[str, ...]
    revision: int = 1
    change_request: Optional[str] = None
    critical_cad_serial: bool = True
    schema_version: str = "1.0"

    def phase(self, phase_id: str) -> EngineeringPhase:
        """@brief Return a stage by ID or raise an explicit error when it does not exist."""
        for item in self.phases:
            if item.id == phase_id:
                return item
        raise KeyError("Bilinmeyen mühendislik aşaması: {}".format(phase_id))

    def validate(self) -> None:
        """@brief Validate unique IDs, dependency references, acyclicity, and CAD serialization policy."""
        phase_ids = [phase.id for phase in self.phases]
        if len(phase_ids) != len(set(phase_ids)):
            raise ValueError("Engineering plan contains duplicate stages ID")

        known = set(phase_ids)
        for phase in self.phases:
            missing = set(phase.depends_on) - known
            if missing:
                raise ValueError("Aşama {} References an unknown dependency: {}".format(phase.id, sorted(missing)))
            if phase.id in phase.depends_on:
                raise ValueError("Aşama {} Cannot depend on itself".format(phase.id))
            if phase.status == PhaseStatus.COMPLETED and any(
                route.level == CapabilityLevel.NOT_IMPLEMENTED for route in phase.routes
            ):
                raise ValueError("Uygulanmamış yetenek gerektiren aşama tamamlandı olarak işaretlenemez: {}".format(phase.id))
            if self.critical_cad_serial and phase.serial_required and phase.execution_lane != "solidworks-com":
                raise ValueError("Kritik CAD Stage must enter  solidworks-com Seri kanal: {}".format(phase.id))

        visiting: Set[str] = set()
        visited: Set[str] = set()

        def visit(phase_id: str) -> None:
            if phase_id in visiting:
                raise ValueError("Engineering plan contains a dependency cycle: {}".format(phase_id))
            if phase_id in visited:
                return
            visiting.add(phase_id)
            for dependency in self.phase(phase_id).depends_on:
                visit(dependency)
            visiting.remove(phase_id)
            visited.add(phase_id)

        for phase_id in phase_ids:
            visit(phase_id)

    def to_dict(self) -> Dict[str, Any]:
        """@brief Return a dictionary suitable for persisting in the job protocol and audit log."""
        payload = asdict(self)
        return _enum_values(payload)


def engineering_plan_from_dict(payload: Mapping[str, Any]) -> EngineeringPlan:
    """@brief Restore a persisted queue JSON engineering plan for conversational partial replanning."""
    phases: List[EngineeringPhase] = []
    for raw_phase in payload.get("phases", []):
        if not isinstance(raw_phase, Mapping):
            continue
        routes = tuple(
            CapabilityRoute(
                capability_id=str(route.get("capability_id") or ""),
                level=CapabilityLevel(str(route.get("level") or CapabilityLevel.NOT_IMPLEMENTED.value)),
                skills=tuple(str(item) for item in route.get("skills", [])),
                mcp_tools=tuple(str(item) for item in route.get("mcp_tools", [])),
                execution_mode=str(route.get("execution_mode") or "blocked"),
                reason=str(route.get("reason") or ""),
            )
            for route in raw_phase.get("routes", [])
            if isinstance(route, Mapping)
        )
        raw_retry = raw_phase.get("retry_policy") if isinstance(raw_phase.get("retry_policy"), Mapping) else {}
        phases.append(
            EngineeringPhase(
                id=str(raw_phase.get("id") or ""),
                name=str(raw_phase.get("name") or ""),
                depends_on=tuple(str(item) for item in raw_phase.get("depends_on", [])),
                routes=routes,
                artifacts=tuple(str(item) for item in raw_phase.get("artifacts", [])),
                acceptance=tuple(str(item) for item in raw_phase.get("acceptance", [])),
                risks=tuple(str(item) for item in raw_phase.get("risks", [])),
                retry_policy=RetryPolicy(
                    max_attempts=int(raw_retry.get("max_attempts") or 1),
                    strategy=str(raw_retry.get("strategy") or "Kısmi yeniden deneme"),
                    retryable_failures=tuple(str(item) for item in raw_retry.get("retryable_failures", [])),
                    fallback=str(raw_retry.get("fallback") or "İnsan incelemesine yönlendir"),
                ),
                status=PhaseStatus(str(raw_phase.get("status") or PhaseStatus.PLANNED.value)),
                serial_required=bool(raw_phase.get("serial_required", True)),
                execution_lane=str(raw_phase.get("execution_lane") or "solidworks-com"),
                human_gate=bool(raw_phase.get("human_gate", False)),
            )
        )
    plan = EngineeringPlan(
        objective=str(payload.get("objective") or ""),
        project_type=str(payload.get("project_type") or "complex_mechanical_system"),
        phases=tuple(phases),
        assumptions=tuple(str(item) for item in payload.get("assumptions", [])),
        warnings=tuple(str(item) for item in payload.get("warnings", [])),
        revision=int(payload.get("revision") or 1),
        change_request=str(payload.get("change_request")) if payload.get("change_request") else None,
        critical_cad_serial=bool(payload.get("critical_cad_serial", True)),
        schema_version=str(payload.get("schema_version") or "1.0"),
    )
    plan.validate()
    return plan


@dataclass(frozen=True)
class _CapabilityDefinition:
    """@brief Save the orchestrator's conservative built-in capability registry."""

    level: CapabilityLevel
    skills: Tuple[str, ...]
    mcp_tools: Tuple[str, ...]
    reason: str


MAIN_SKILL = "solidworks-automation"
VIBECAD_SKILL = "solidworks-vibecad"
FILLET_SKILL = "solidworks-fillet-chamfer-cnc"


CAPABILITIES: Mapping[str, _CapabilityDefinition] = {
    "requirements_planning": _CapabilityDefinition(
        CapabilityLevel.VERIFIED,
        (VIBECAD_SKILL, MAIN_SKILL),
        (),
        "VibeCAD Doğal dili parametrik tasarım planına dönüştürür. Yürütmeden önce kritik ölçüleri, yükleri ve üretim kısıtlarını doğrulayın.",
    ),
    "part_and_features": _CapabilityDefinition(
        CapabilityLevel.VERIFIED,
        (MAIN_SKILL, VIBECAD_SKILL),
        ("solidworks_health_check", "solidworks_new_document", "solidworks_create_basic_part", "solidworks_save_document"),
        "Parametrik parça ve temel özellikler için gerçek  COM  wrapper; karmaşık konturlar skill betikleriyle yürütülüp incelenmelidir.",
    ),
    "holes_and_finishing": _CapabilityDefinition(
        CapabilityLevel.VERIFIED,
        (MAIN_SKILL, FILLET_SKILL),
        ("solidworks_create_hole_feature", "solidworks_inspect_hole_features", "solidworks_save_document"),
        "Kör delik, silindirik havşa, konik havşa, yarım daire uçlu kanal ve delik konumu kontrolleri doğrulanmıştır; fillet/chamfer için uzmanlaşmış skill kullanılır.",
    ),
    "assembly_and_mates": _CapabilityDefinition(
        CapabilityLevel.VERIFIED,
        (MAIN_SKILL,),
        (
            "solidworks_new_document",
            "solidworks_add_component",
            "solidworks_set_component_fixed",
            "solidworks_add_coincident_mate",
            "solidworks_add_distance_mate",
            "solidworks_add_concentric_mate",
            "solidworks_save_document",
        ),
        "Bileşen ekleme; coincident, distance ve concentric  Mate  doğrulandı; hareket serbestliği ve  Mate  feature tree.",
    ),
    "motion_study": _CapabilityDefinition(
        CapabilityLevel.VERIFIED,
        (MAIN_SKILL,),
        ("solidworks_add_rotary_motor", "solidworks_inspect_motion_studies", "solidworks_validate_motion_study"),
        "Şu anda yalnızca döner motor oluşturma, hesaplama ve sonuç denetimi doğrulanmış kapsam içindedir.",
    ),
    "drawings_and_bom": _CapabilityDefinition(
        CapabilityLevel.PILOT,
        (MAIN_SKILL, "solidworks-engineering-drawing"),
        ("solidworks_generate_drawing", "solidworks_review_drawing", "solidworks_inspect_drawing"),
        "Çizim durumu:  Pilot, GB/T Birinci açı çerçevesi, BOM, Ölçü zincirleri ve sac açınımı kanıtları insan tarafından incelenmelidir; gözetimsiz tamamlandı sonucu vermeyin.",
    ),
    "export_delivery": _CapabilityDefinition(
        CapabilityLevel.VERIFIED,
        (MAIN_SKILL,),
        ("solidworks_export_active",),
        "STEP, PDF  dar kapsamlı arayüzle dışa aktarılır; her hedef dosyanın varlığı, biçimi ve özeti (hash) yine de doğrulanmalıdır.",
    ),
    "geometry_and_delivery_review": _CapabilityDefinition(
        CapabilityLevel.VERIFIED,
        (MAIN_SKILL,),
        (
            "solidworks_review_active",
            "solidworks_inspect_hole_features",
            "solidworks_inspect_motion_studies",
            "solidworks_validate_motion_study",
        ),
        "Çoklu görünüşler, delik/kanal ve  Motion Kanıt otomatik toplanabilir; GB/T Çizimler için son insan incelemesi korunur.",
    ),
}

# The orchestrator has finer-grained capabilities than the probe; these aliases route local type-library results to related stages.
CAPABILITY_REPORT_ALIASES: Mapping[str, str] = {
    "holes_and_finishing": "part_and_features",
    "drawings_and_bom": "drawings",
    "export_delivery": "part_and_features",
    "geometry_and_delivery_review": "part_and_features",
}

def _normalize_request(text: str) -> str:
    """Normalize Turkish casing for Turkish and English keyword routing."""
    return text.strip().replace("İ", "i").casefold().replace("ı", "i")


_ASSEMBLY_WORDS = ("assembly", "assemblies", "multi-part", "multiple parts", "mechanism", "montaj", "çok parçalı", "birden fazla parça", "tam makine", "mekanizma")
_MATE_WORDS = ("mate", "concentric", "interference", "degree of freedom", "dof", "ilişki", "eş merkez", "çakışma", "serbestlik")
_MOTION_WORDS = ("motion", "motor", "rpm", "dynamics", "hareket", "devir", "dinamik")
_DRAWING_WORDS = ("drawing", "bom", "bill of materials", "gb/t", "çizim", "teknik resim", "parça listesi", "malzeme listesi", "ayrıntı tablosu")
_EXPORT_WORDS = ("step", "stp", "stl", "pdf", "export", "delivery", "dışa aktar", "teslim")
_FEATURE_WORDS = ("hole", "slot", "fillet", "chamfer", "tolerance", "thread", "counterbore", "delik", "kanal", "yuvarlatma", "pah", "tolerans", "diş", "havşa")
_COMPLEX_PROJECT_SIGNALS: Tuple[Tuple[str, ...], ...] = (
    _ASSEMBLY_WORDS, _MATE_WORDS, _MOTION_WORDS, _DRAWING_WORDS,
    ("step", "pdf", "delivery package", "complete delivery", "teslim paketi", "tam teslim"),
    _FEATURE_WORDS,
)


def requires_engineering_orchestration(brief: str) -> bool:
    """@brief Determine whether a natural-language request needs a cross-stage engineering DAG. Return True for at least two independent engineering domains or an explicit complete-machine or combined-engineering request."""
    normalized = _normalize_request(brief)
    if not normalized:
        return False
    if any(_normalize_request(keyword) in normalized for keyword in ("combined engineering", "complete engineering", "complete workflow", "complete machine design", "birleşik mühendislik", "tam mühendislik", "tam iş akışı", "tam makine tasarımı")):
        return True
    matched_domains = sum(any(_normalize_request(keyword) in normalized for keyword in domain) for domain in _COMPLEX_PROJECT_SIGNALS)
    return matched_domains >= 2


def _unique(values: Iterable[str]) -> Tuple[str, ...]:
    """@brief Remove duplicate strings while preserving original order."""
    seen: Set[str] = set()
    result: List[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


def _enum_values(value: Any) -> Any:
    """@brief Recursively convert enums to JSON-compatible values."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _enum_values(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_enum_values(item) for item in value]
    return value


def _normalise_level(raw_status: str, fallback: CapabilityLevel) -> CapabilityLevel:
    """@brief Normalize capability probe status into orchestrator maturity levels."""
    status = raw_status.strip().lower()
    if status.startswith("verified"):
        return CapabilityLevel.VERIFIED
    if status == "pilot":
        return CapabilityLevel.PILOT
    if status == "reference_only":
        return CapabilityLevel.REFERENCE_ONLY
    if status == "not_implemented":
        return CapabilityLevel.NOT_IMPLEMENTED
    return fallback


def _route(capability_id: str, capability_report: Optional[Mapping[str, Any]]) -> CapabilityRoute:
    """@brief Select execution routes from the built-in registry and optional local probe report."""
    definition = CAPABILITIES[capability_id]
    level = definition.level
    if capability_report:
        report_capabilities = capability_report.get("capabilities", {})
        report_key = capability_id
        if isinstance(report_capabilities, Mapping) and report_key not in report_capabilities:
            report_key = CAPABILITY_REPORT_ALIASES.get(capability_id, capability_id)
        report_item = report_capabilities.get(report_key, {}) if isinstance(report_capabilities, Mapping) else {}
        if isinstance(report_item, Mapping):
            level = _normalise_level(str(report_item.get("implementation_status", "")), level)
            if report_item.get("ready_for_unattended_use") is False and level == CapabilityLevel.VERIFIED:
                level = CapabilityLevel.PILOT

    if level == CapabilityLevel.VERIFIED:
        mode = "mcp_and_skill" if definition.mcp_tools else "skill"
    elif level == CapabilityLevel.PILOT:
        mode = "assisted_human_gate"
    else:
        mode = "blocked"
    return CapabilityRoute(capability_id, level, definition.skills, definition.mcp_tools, mode, definition.reason)


def _phase_status(routes: Sequence[CapabilityRoute]) -> PhaseStatus:
    """@brief Unimplemented or reference-only capabilities are blocked by default; remaining stages start pending."""
    blocked_levels = {CapabilityLevel.REFERENCE_ONLY, CapabilityLevel.NOT_IMPLEMENTED}
    return PhaseStatus.BLOCKED if any(route.level in blocked_levels for route in routes) else PhaseStatus.PLANNED


def _phase(
    phase_id: str,
    name: str,
    depends_on: Sequence[str],
    capability_ids: Sequence[str],
    artifacts: Sequence[str],
    acceptance: Sequence[str],
    risks: Sequence[str],
    retry_policy: RetryPolicy,
    capability_report: Optional[Mapping[str, Any]],
    human_gate: bool = False,
    serial_required: bool = True,
) -> EngineeringPhase:
    """@brief Create engineering stages with conservative status and traceable capabilities."""
    routes = tuple(_route(item, capability_report) for item in capability_ids)
    return EngineeringPhase(
        id=phase_id,
        name=name,
        depends_on=tuple(depends_on),
        routes=routes,
        artifacts=tuple(artifacts),
        acceptance=tuple(acceptance),
        risks=tuple(risks),
        retry_policy=retry_policy,
        status=_phase_status(routes),
        serial_required=serial_required,
        execution_lane="solidworks-com" if serial_required else "planning",
        human_gate=human_gate or any(route.level != CapabilityLevel.VERIFIED for route in routes),
    )


def build_engineering_plan(
    brief: str,
    capability_report: Optional[Mapping[str, Any]] = None,
) -> EngineeringPlan:
    """@brief Split natural-language mechanical requirements into a SolidWorks DAG selected from eight stages. Optionally use a sw_capability_probe.py report. The returned plan is pending or blocked; it does not claim that CAD work is complete."""
    objective = brief.strip()
    if not objective:
        raise ValueError("Karmaşık mekanik görev açıklaması boş olamaz")

    planning_retry = RetryPolicy(2, "Eksik kısıtları tamamlayıp yeniden planlayın", ("missing_requirement", "ambiguous_constraint"), "Kritik mühendislik parametreleri için insan onayı isteyin")
    cad_retry = RetryPolicy(2, "Yalnızca mevcut aşamayı geri alıp yeniden deneyin", ("com_error", "rebuild_error", "selection_error"), "Özellik gruplarını küçültüp hata kanıtını koruyun")
    review_retry = RetryPolicy(1, "Return the first failed stage for local rework", ("acceptance_failed", "artifact_missing"), "Teslimi durdurup insan incelemesi isteyin")

    phase_catalog = (
        _phase(
            "requirements",
            "Gereksinimlerin netleştirilmesi ve mühendislik kısıtları",
            (),
            ("requirements_planning",),
            ("requirements.json", "design_plan.json", "assumptions.json"),
            ("Parça adedi, işlev, arayüzler ve hareket hedefi açık", "Kritik ölçüler, malzemeler, yükler, toleranslar ve üretim yöntemi kaynak veya açık varsayımla destekleniyor", "Teslim biçimleri ve kabul kontrolleri eksiksiz"),
            ("Doğal dilde ölçü veya yük eksikliği üretilemez bir tasarıma yol açabilir", "GB/T Standart sürümü ve şirket şablonu belirtilmemişse tahmin etmeyin"),
            planning_retry,
            capability_report,
            human_gate=True,
            serial_required=False,
        ),
        _phase(
            "part-modeling",
            "Parametrik parça modelleme",
            ("requirements",),
            ("part_and_features",),
            ("Dört adet veya gereksinimde belirtilen sayıda  SLDPRT Dosya", "part_parameters.json", "part_rebuild_report.json"),
            ("Parça adedi gereksinimle uyumlu ve dosyalar özgün uygulamada açılıyor", "Eskiz ve kritik özellikler yeniden oluşturulabiliyor (rebuild)", "Kütle özellikleri ve bounding box tasarım parametreleriyle uyumlu"),
            ("Eksik kısıtlanmış eskiz sonraki özelliklerin kaymasına yol açabilir", "Parça arayüz ölçülerinin uyuşmaması montajı engeller"),
            cad_retry,
            capability_report,
        ),
        _phase(
            "holes-fillet-chamfer",
            "Delik/kanal, fillet ve chamfer",
            ("part-modeling",),
            ("holes_and_finishing",),
            ("feature_parameters.json", "hole_geometry_evidence.json", "updated SLDPRT files"),
            ("Havşa, kör delik veya kanal özellikleri, derinliği ve konumu parametrelerle uyumlu", "Delik ekseni konumu ve çap toleransları geometri kontrolünden geçti", "Fillet ve chamfer mevcut, modelde rebuild hatası yok"),
            ("Kararsız özellik sırası fillet çözümünün başarısız olmasına yol açabilir", "B-Rep  kör veya geçişli deliği tek başına kanıtlamaz; oluşturma parametreleriyle çapraz kontrol gerekir"),
            cad_retry,
            capability_report,
        ),
        _phase(
            "assembly-mates",
            "Montaj ve  Mate",
            ("holes-fillet-chamfer",),
            ("assembly_and_mates",),
            ("assembly.SLDASM", "mate_inventory.json", "degree_of_freedom_report.json"),
            ("Bileşen adedi ve referans dosyaları eksiksiz", "concentric, coincident, distance gibi  Mate Tasarımın serbestlik derecesi hedefiyle uyumlu", "Dönen parça yanlışlıkla kilitlenmemiş ve belirgin çakışma yok"),
            ("Aşırı kısıtlı Mate Mekanizmayı kilitleyebilir", "Bileşen adı, konfigürasyon veya düzlem dili farklılıkları seçimin başarısız olmasına yol açabilir"),
            cad_retry,
            capability_report,
        ),
        _phase(
            "motion-study",
            "Motion Hareket çalışması (Motion Study)",
            ("assembly-mates",),
            ("motion_study",),
            ("motion_study.json", "motion_validation.json", "calculated Motion Study in SLDASM"),
            ("Döner motor nesnesi gerçekten mevcut", "Çalışma süresi ve motor adedi plana uygun", "Hesaplama sonucu mevcut ve  results_out_of_date=False"),
            ("Doğrulanmış kapsam temas, sürtünme, yay veya tam dinamik analizi içermez", "Motion Analysis Lisans eksikse açıkça daha sınırlı çalışma moduna geçin; sonuç uydurmayın"),
            cad_retry,
            capability_report,
        ),
        _phase(
            "drawing-bom",
            "GB/T Mühendislik çizimi ve  BOM",
            ("motion-study",),
            ("drawings_and_bom",),
            ("part_and_assembly_drawings.SLDDRW", "bom.csv", "drawing_review_checklist.json"),
            ("Sayfa boyutu, çerçeve, antet, yazı tipi ve çizgi türleri belirtilen standarda uygun:  GB/T/Şirket şablonu", "Ölçü zincirleri, delik/kanal özellikleri ve konum ölçüleri eksiksiz", "BOM Adet, parça kodu, malzeme ve montaj referansları tutarlı", "İnsan görsel incelemesinde çakışma, üst üste çizgiler veya antet taşması yok"),
            ("Bu yetenek hâlâ  Pilot, Gözetimsiz teslim edilemez", "Otomatik ölçüler ve  BOM Alanlar eksik veya düzen sıkışık olabilir"),
            RetryPolicy(2, "Görünüş veya tabloyu yerel yeniden düzenleyip inceleyin", ("layout_overlap", "dimension_missing", "bom_mismatch"), "Koru SLDDRW  ve son inceleme için mühendise yönlendirin"),
            capability_report,
            human_gate=True,
        ),
        _phase(
            "export-delivery",
            "STEP/PDF  ve teslim export işlemi",
            ("drawing-bom",),
            ("export_delivery",),
            ("assembly.step", "drawing.pdf", "artifact_ledger.json"),
            ("STEP Yeniden açılabilir ve katı /Bileşen adedi uygun", "PDF Sayfa adedi, boyutu ve içerik boş değil", "Tüm teslim dosyaları mevcut, boş değil ve kayıtlı:  SHA-256"),
            ("Başarılı export dönüş değeri dosya biçimi doğrulamasının yerini tutmaz", "Eksik referanslar veya font değişimi teslimde sapmaya yol açabilir"),
            cad_retry,
            capability_report,
        ),
        _phase(
            "final-review",
            "Birleşik inceleme ve teslim kontrolü",
            ("export-delivery",),
            ("geometry_and_delivery_review",),
            ("isometric/front/top/right previews", "review_report.json", "review_gate.json"),
            ("Birden çok görünüşün görsel incelemesi geçti", "Parça, delik/kanal, Mate, Motion, Çizimler, BOM  ve export kanıtları tek tek doğrulandı", "Any  Pilot  öğeleri insan tarafından onaylandı; başarısız öğeler tamamlandı olarak işaretlenmedi"),
            ("Yalnızca dosya varlığını denetlemek geometri ve montaj hatalarını kaçırır", "Yerel değişiklik sonraki çizimi veya  Motion Sonuç güncel değil"),
            review_retry,
            capability_report,
            human_gate=True,
        ),
    )

    normalized = _normalize_request(objective)
    requested_features = any(_normalize_request(keyword) in normalized for keyword in _FEATURE_WORDS)
    requested_assembly = any(_normalize_request(keyword) in normalized for keyword in (*_ASSEMBLY_WORDS, *_MATE_WORDS))
    requested_motion = any(_normalize_request(keyword) in normalized for keyword in _MOTION_WORDS)
    requested_drawing = any(_normalize_request(keyword) in normalized for keyword in _DRAWING_WORDS)
    requested_export = any(_normalize_request(keyword) in normalized for keyword in _EXPORT_WORDS)
    requested_ids = {"requirements", "part-modeling", "final-review"}
    if requested_features:
        requested_ids.add("holes-fillet-chamfer")
    if requested_assembly or requested_motion:
        requested_ids.add("assembly-mates")
    if requested_motion:
        requested_ids.add("motion-study")
    if requested_drawing:
        requested_ids.add("drawing-bom")
    if requested_export:
        requested_ids.add("export-delivery")

    selected_phases: List[EngineeringPhase] = []
    previous_phase_id: Optional[str] = None
    for phase in phase_catalog:
        if phase.id not in requested_ids:
            continue
        dependencies = () if previous_phase_id is None else (previous_phase_id,)
        selected_phases.append(replace(phase, depends_on=dependencies))
        previous_phase_id = phase.id
    phases = tuple(selected_phases)

    warnings = tuple(
        "{} Kullan {}, İnsan onayından geçmelidir.".format(phase.name, route.level.value)
        for phase in phases
        for route in phase.routes
        if route.level != CapabilityLevel.VERIFIED
    )
    plan = EngineeringPlan(
        objective=objective,
        project_type="complex_mechanical_system",
        phases=phases,
        assumptions=(
            "Verilmeyen ölçüleri, malzemeleri, yükleri, toleransları ve standart sürümlerini doğrulanacak bilgi olarak kaydedin; gerçekmiş gibi sunmayın.",
            "Tümü SolidWorks COM Write operations enter  solidworks-com  single-concurrency channel.",
            "Bu plan yapılacak işi tanımlar; aşamanın yönlendirilmesi model veya teslim dosyalarının tamamlandığını göstermez.",
        ),
        warnings=warnings,
    )
    plan.validate()
    return plan


_CHANGE_PHASE_KEYWORDS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("requirements", ("requirement", "material", "load", "standard", "quantity", "gereksinim", "malzeme", "yük", "standart", "adet")),
    ("part-modeling", ("part", "dimension", "sketch", "extrude", "parça", "dış ölçü", "ölçü", "eskiz", "ekstrüzyon")),
    ("holes-fillet-chamfer", _FEATURE_WORDS),
    ("assembly-mates", (*_ASSEMBLY_WORDS, *_MATE_WORDS)),
    ("motion-study", (*_MOTION_WORDS, "animation", "animasyon")),
    ("drawing-bom", (*_DRAWING_WORDS, "dimensioning", "ölçülendirme")),
    ("export-delivery", _EXPORT_WORDS),
    ("final-review", ("review", "acceptance", "preview", "incele", "kabul", "önizleme")),
)


def infer_affected_phases(change_request: str) -> Tuple[str, ...]:
    """@brief Infer the earliest affected stage from the local edit description."""
    normalized = _normalize_request(change_request)
    if not normalized:
        raise ValueError("Yerel değişiklik açıklaması boş olamaz")
    matched = [phase_id for phase_id, keywords in _CHANGE_PHASE_KEYWORDS if any(_normalize_request(keyword) in normalized for keyword in keywords)]
    return (matched[0],) if matched else ("requirements",)


def replan_for_local_change(
    plan: EngineeringPlan,
    change_request: str,
    affected_phase_ids: Optional[Sequence[str]] = None,
) -> EngineeringPlan:
    """@brief Replan a modified stage and all DAG successors. Unaffected stages with acceptance evidence retain their state. Affected stages return to planned, or remain blocked when their capability was blocked, preventing reuse of stale results."""
    plan.validate()
    roots = tuple(affected_phase_ids or infer_affected_phases(change_request))
    known = {phase.id for phase in plan.phases}
    unknown = set(roots) - known
    if unknown:
        raise ValueError("Local edit refers to an unknown stage: {}".format(sorted(unknown)))

    invalidated: Set[str] = set(roots)
    changed = True
    while changed:
        changed = False
        for phase in plan.phases:
            if phase.id not in invalidated and any(parent in invalidated for parent in phase.depends_on):
                invalidated.add(phase.id)
                changed = True

    phases: List[EngineeringPhase] = []
    for phase in plan.phases:
        if phase.id not in invalidated:
            phases.append(phase)
            continue
        next_status = _phase_status(phase.routes)
        phases.append(replace(phase, status=next_status))

    replanned = replace(
        plan,
        phases=tuple(phases),
        revision=plan.revision + 1,
        change_request=change_request.strip(),
        warnings=plan.warnings
        + ("Yerel düzenleme şu aşama ve devamını geçersiz kıldı: {}".format(", ".join(sorted(invalidated))),),
    )
    replanned.validate()
    return replanned
