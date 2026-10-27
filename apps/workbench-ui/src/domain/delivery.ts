import { artifactGroup, collectJobArtifacts, fileNameFromPath } from "./artifacts";
import type { ArtifactRecord, AutomationJob, BackendDiagnostic, JobRunSnapshot } from "../types";

export type DeliveryDisposition = "idle" | "active" | "ready" | "review_required" | "blocked" | "failed" | "incomplete";
export type DeliveryAssessment = {
  disposition: DeliveryDisposition;
  title: string;
  summary: string;
  issues: string[];
  readyArtifacts: number;
  currentArtifacts: number;
};

const stageLabels: Record<string, string> = {
  requirements: "Gereksinim doğrulama",
  "part-modeling": "Parça modelleme",
  "holes-fillet-chamfer": "Delik/kanal ve fillet",
  "assembly-mates": "Montaj ilişkileri (mates)",
  "motion-study": "Hareket çalışması (Motion Study)",
  "drawing-bom": "Mühendislik çizimi ve BOM",
  "dfm-review": "DFM Üretim incelemesi",
  "export-delivery": "Dışa aktar ve teslim et",
  "final-review": "Son inceleme",
  intake: "Gereksinim alımı",
  planning: "Görev planlama",
  checking: "Ortam kontrolü",
  launching: "CAD Başlat",
  executing: "CAD Yürüt",
  reviewing: "Sonuç incelemesi",
  delivery: "Teslim düzenleme",
  blocked: "Yetenek veya ortam kontrolü",
};

export function retryStageLabel(stage?: string) {
  if (!stage) return "Başarısız aşama";
  return stageLabels[stage] ?? stage;
}

export function retryStageForJob(job?: AutomationJob) {
  if (!job) return "requirements";
  if (job.retryPolicy?.retryFromStage) return job.retryPolicy.retryFromStage;
  const failedPhase = job.result?.engineeringPlan?.phases?.find((phase) =>
    ["blocked", "failed", "review_required"].includes(phase.status ?? ""),
  );
  if (failedPhase?.id) return failedPhase.id;
  for (const [key, evidence] of [["drawing-bom", job.drawingEvidence], ["drawing-bom", job.bomEvidence], ["dfm-review", job.dfmEvidence] ] as const) {
    if (evidence && ["blocked", "failed", "fail", "warning"].includes(String(evidence.status))) return key;
  }
  if (["failed", "review_required"].includes(job.status)) return "final-review";
  return "requirements";
}

function requiresArtifacts(job: AutomationJob) {
  const descriptor = `${job.expectedOutput ?? ""} ${job.target ?? ""} ${(job.requiredArtifacts ?? []).join(" ")}`;
  return job.kind === "delivery_package" || Boolean(job.requiredArtifacts?.length) || /CAD(?:_FILES)?|DRAWING(?:_PACKAGE)?|PACKAGE|SLDPRT|SLDASM|STEP|STL|DWG|DXF|PDF|PNG|BOM|Model|Çizim|Teslim/i.test(descriptor);
}

function artifactMatchesRequirement(artifact: ArtifactRecord, requirement: string) {
  const normalize = (text: string) => text.toUpperCase().replaceAll("İ", "I").toLowerCase();
  const token = normalize(requirement.trim());
  if (!token) return true;
  const descriptor = normalize(`${artifact.kind ?? ""} ${artifact.path ?? ""}`);
  if (descriptor.includes(token)) return true;
  const aliases: Record<string, string[]> = {
    model: ["model", "Model", "sldprt", "sldasm", "step", "stp", "stl"],
    drawing: ["drawing", "Çizim", "Mühendislik çizimi", "slddrw", "dwg", "dxf"],
    bom: ["bom", "Malzeme", "Ayrıntı tablosu"],
    preview: ["preview", "Önizleme", "png", "bmp", "jpg", "jpeg", "webp"],
    report: ["review", "report", "ledger", "İncele", "Rapor"],
  };
  return (aliases[artifactGroup(artifact)] ?? []).some((alias) => token.includes(normalize(alias)));
}

export function assessDelivery(job?: AutomationJob): DeliveryAssessment {
  if (!job) return { disposition: "idle", title: "Görev sonucu bekleniyor", summary: "Yürütmeden sonra teslim değerlendirmesi burada görünür.", issues: [], readyArtifacts: 0, currentArtifacts: 0 };
  const artifacts = collectJobArtifacts(job);
  const readyArtifacts = artifacts.filter((item) => item.exists !== false && item.producedThisRun !== false);
  const issues: string[] = [];
  const staleOrMissing = artifacts.filter((item) => item.exists === false || item.producedThisRun === false);
  if (staleOrMissing.length) issues.push(`${staleOrMissing.length}  çıktı eksik veya bu yürütmede üretilmedi`);
  for (const requirement of job.requiredArtifacts ?? []) {
    if (!readyArtifacts.some((artifact) => artifactMatchesRequirement(artifact, requirement))) issues.push(`Gerekli çıktı eksik: ${requirement}`);
  }
  for (const evidence of [job.drawingEvidence, job.bomEvidence, job.dfmEvidence]) {
    if (!evidence) continue;
    if (evidence.error_code) issues.push(String(evidence.error_code));
    if (Array.isArray(evidence.limitations)) issues.push(...evidence.limitations.map(String));
  }
  if (job.blockedReasons?.length) issues.push(...job.blockedReasons);
  const uniqueIssues = [...new Set(issues.filter(Boolean))];
  const evidenceStatuses = [job.drawingEvidence?.status, job.bomEvidence?.status, job.dfmEvidence?.status].map(String);
  if (job.status === "blocked" || evidenceStatuses.includes("blocked")) {
    return { disposition: "blocked", title: "Teslim engellendi", summary: "Ortam, lisans veya yetenek koşulları henüz karşılanmadı.", issues: uniqueIssues, readyArtifacts: readyArtifacts.length, currentArtifacts: artifacts.length };
  }
  if (job.status === "failed" || evidenceStatuses.some((status) => ["failed", "fail"].includes(status))) {
    return { disposition: "failed", title: "Teslim kontrolden geçmedi", summary: "Yürütme veya mühendislik incelemesinde başarısız öğeler var; önceki sürümün kanıtları korundu.", issues: uniqueIssues.length ? uniqueIssues : [job.error || "Yürütme günlüğünü ve inceleme raporunu kontrol edin"], readyArtifacts: readyArtifacts.length, currentArtifacts: artifacts.length };
  }
  if (["queued", "running", "approval_required"].includes(job.status)) {
    return { disposition: "active", title: job.status === "approval_required" ? "Onay bekleniyor" : "Teslim hazırlanıyor", summary: "Bu yürütmenin makine kanıtları eksik; tamamlandı kararı verilemez.", issues: uniqueIssues, readyArtifacts: readyArtifacts.length, currentArtifacts: artifacts.length };
  }
  if (job.status === "cancelled") {
    return { disposition: "incomplete", title: "Görev iptal edildi", summary: "Bu yürütme iptal edildi; mevcut dosyalar otomatik olarak son teslim sayılamaz.", issues: uniqueIssues, readyArtifacts: readyArtifacts.length, currentArtifacts: artifacts.length };
  }
  if ((requiresArtifacts(job) && readyArtifacts.length === 0) || uniqueIssues.some((issue) => issue.startsWith("Gerekli çıktı eksik"))) {
    return { disposition: "incomplete", title: "Teslim kanıtları eksik", summary: "Görev sona erdi ancak gerekli dosyalar veya çıktı kayıtları henüz eksiksiz değil.", issues: uniqueIssues.length ? uniqueIssues : ["Bu yürütme için doğrulanabilir çıktı yok:  CAD Çıktı"], readyArtifacts: readyArtifacts.length, currentArtifacts: artifacts.length };
  }
  const manualReviewRequired = [job.drawingEvidence, job.bomEvidence, job.dfmEvidence].some((item) => item?.manual_review_required);
  if (job.status === "review_required" || manualReviewRequired || job.reviewGate?.status === "warning") {
    return { disposition: "review_required", title: "İnsan incelemesi bekleniyor", summary: "Dosyalar üretildi. Teslimden önce özgün CAD uygulamasında açıp ölçüleri, özellikleri ve sayfa düzenini kontrol edin.", issues: uniqueIssues, readyArtifacts: readyArtifacts.length, currentArtifacts: artifacts.length };
  }
  return { disposition: "ready", title: "Bu yürütme teslim edilebilir", summary: job.reviewDecision === "approved" ? "Makine kontrolleri ve insan incelemesi tamamlandı." : "Bu yürütmenin makine kanıtları eksiksiz; görev tamamlandı.", issues: uniqueIssues, readyArtifacts: readyArtifacts.length, currentArtifacts: artifacts.length };
}

export function backendDiagnosticsFor(job?: AutomationJob): BackendDiagnostic[] {
  const value = job?.backendDiagnostics ?? job?.result?.backendDiagnostics;
  if (Array.isArray(value)) return value.filter((item): item is BackendDiagnostic => Boolean(item) && typeof item === "object");
  if (value && typeof value === "object") {
    return Object.entries(value).flatMap(([backend, item]) => {
      if (!item || typeof item !== "object" || Array.isArray(item)) return [];
      return [{ ...item, backend: item.backend ?? backend }];
    });
  }
  return [];
}

export function artifactVersionComparison(job?: AutomationJob) {
  const current = collectJobArtifacts(job);
  const latest = job?.runHistory?.at(-1)?.artifacts ?? [];
  const previousByKey = new Map(latest.map((item) => [`${item.kind ?? ""}:${fileNameFromPath(item.path)}`, item]));
  const currentKeys = new Set(current.map((item) => `${item.kind ?? ""}:${fileNameFromPath(item.path)}`));
  let added = 0;
  let changed = 0;
  let unchanged = 0;
  for (const item of current) {
    const previous = previousByKey.get(`${item.kind ?? ""}:${fileNameFromPath(item.path)}`);
    if (!previous) added += 1;
    else if (item.sha256 && previous.sha256 && item.sha256 !== previous.sha256) changed += 1;
    else unchanged += 1;
  }
  const removed = [...previousByKey.keys()].filter((key) => !currentKeys.has(key)).length;
  return { added, removed, changed, unchanged, previous: latest.length, current: current.length };
}

export function createRunSnapshot(job: AutomationJob): JobRunSnapshot {
  return {
    runId: job.runId,
    status: job.status,
    stage: job.stage,
    createdAt: job.createdAt,
    updatedAt: job.updatedAt,
    lastMessage: job.lastMessage,
    error: job.error,
    result: job.result,
    artifacts: job.artifacts,
    artifactLedgerPath: job.artifactLedgerPath,
    reviewGatePath: job.reviewGatePath,
    reviewGate: job.reviewGate,
    drawingEvidence: job.drawingEvidence,
    bomEvidence: job.bomEvidence,
    dfmEvidence: job.dfmEvidence,
    reviewFindings: job.reviewFindings,
    artifactRelations: job.artifactRelations,
    blockedReasons: job.blockedReasons,
  };
}
