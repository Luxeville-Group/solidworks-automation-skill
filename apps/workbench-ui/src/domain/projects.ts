import type { AgentConversation, AutomationJob, ProjectRecord } from "../types";

export const LEGACY_PROJECT_ID = "project-default";

export const DEFAULT_PROJECT: ProjectRecord = {
  id: LEGACY_PROJECT_ID,
  name: "Adsız proje",
  createdAt: "",
  updatedAt: "",
};

/** @brief Return the job's project, supporting  1.0  job. */
export function jobProjectId(job: AutomationJob) {
  return job.projectId || LEGACY_PROJECT_ID;
}

/** @brief Create a local project ID that does not collide with existing projects. */
export function newProjectId() {
  return `project-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
}

/** @brief Sanitize project names to keep sidebar layout stable. */
export function normalizeProjectName(value: string) {
  return value.replace(/\s+/g, " ").trim().slice(0, 48) || "Adsız proje";
}

/** @brief Return recent project conversations ordered by update time. */
export function latestProjectConversation(conversations: AgentConversation[], projectId: string) {
  return conversations
    .filter((conversation) => conversation.projectId === projectId)
    .reduce<AgentConversation | undefined>((latest, conversation) => (
      !latest || conversation.updatedAt.localeCompare(latest.updatedAt) > 0 ? conversation : latest
    ), undefined);
}

/** @brief Return visible projects; show archived projects only when explicitly requested. */
export function filterProjects(projects: ProjectRecord[], query: string, showArchived: boolean) {
  const normalized = query.trim().toLocaleLowerCase("tr-TR");
  return projects.filter((project) => {
    if (Boolean(project.archivedAt) !== showArchived) return false;
    if (!normalized) return true;
    return project.name.toLocaleLowerCase("tr-TR").includes(normalized)
      || project.sourcePath?.toLocaleLowerCase("tr-TR").includes(normalized);
  });
}

/** @brief Copy project metadata without copying jobs, conversations or  CAD  delivery files. */
export function duplicateProjectRecord(project: ProjectRecord, existingCount: number) {
  const now = new Date().toISOString();
  return {
    id: newProjectId(),
    name: normalizeProjectName(`${project.name} Kopya ${existingCount + 1}`),
    sourcePath: project.sourcePath,
    createdAt: now,
    updatedAt: now,
  } satisfies ProjectRecord;
}

/** @brief Determine whether the project has nonterminal jobs. */
export function hasActiveProjectJobs(jobs: AutomationJob[], projectId: string) {
  return jobs.some((job) => jobProjectId(job) === projectId && ["queued", "running", "approval_required"].includes(job.status));
}

/** @brief Select only terminal job records that can be safely removed. */
export function terminalProjectJobs(jobs: AutomationJob[], projectId: string) {
  return jobs.filter((job) => jobProjectId(job) === projectId && ["passed", "failed", "cancelled", "review_required", "blocked"].includes(job.status));
}
