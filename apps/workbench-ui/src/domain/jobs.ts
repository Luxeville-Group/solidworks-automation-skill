import type { AutomationJob, AutomationJobStatus } from "../types";

/** @brief Return the complete job status label. */
export function jobStatusLabel(status: AutomationJobStatus) {
  if (status === "running") return "Çalışıyor";
  if (status === "passed") return "Tamamlandı";
  if (status === "review_required") return "İnceleme bekliyor";
  if (status === "failed") return "Başarısız";
  if (status === "cancelled") return "İptal edildi";
  if (status === "approval_required") return "Onay bekliyor";
  if (status === "blocked") return "Engellendi";
  return "Sırada";
}

/** @brief The sidebar shows jobs with generated outputs as complete while preserving their pending review state. */
export function sidebarJobStatusLabel(job: AutomationJob) {
  if (job.status === "review_required" && job.progress >= 100) return "Tamamlandı";
  return jobStatusLabel(job.status);
}

/** @brief Condense a long request into a stable job title. */
export function conciseTaskTitle(value: string | undefined, fallback: string) {
  const normalized = value?.replace(/\s+/g, " ").trim();
  if (!normalized) return fallback;
  return normalized.length > 24 ? `${normalized.slice(0, 24)}...` : normalized;
}

/** @brief Hide internal executor titles and prioritize the user's task objective. */
export function jobDisplayTitle(job: AutomationJob) {
  const title = job.title.trim();
  const internalExecutionTitle = /^(Codex|Claude Code|Gemini CLI|OpenCode|Agent|AI Konuşma)\s*Yürüt$/i.test(title);
  if (!internalExecutionTitle) return title;
  return conciseTaskTitle(job.objective, job.target ? `${job.target}Görev` : "AI CAD Görev");
}
