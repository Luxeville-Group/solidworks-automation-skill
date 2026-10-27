import {
  Archive,
  ArrowCounterClockwise,
  CaretDown,
  Check,
  Copy,
  FilePlus,
  FolderOpen,
  MagnifyingGlass,
  PencilSimple,
  SpinnerGap,
  Trash,
} from "@phosphor-icons/react";
import { AnimatePresence, motion } from "motion/react";
import { useMemo, useState } from "react";
import { filterProjects } from "../domain/projects";
import type { ProjectRecord } from "../types";

type ProjectSwitcherProps = {
  activeProjectId: string;
  projectName: string;
  projectNameDraft: string;
  projects: ProjectRecord[];
  projectTaskCounts: Record<string, number>;
  editing: boolean;
  menuOpen: boolean;
  reducedMotion: boolean;
  deleteCandidateProjectId: string | null;
  deletingProjectId: string | null;
  onDraftChange: (value: string) => void;
  onCommitName: () => void;
  onCancelEdit: () => void;
  onStartEdit: () => void;
  onToggleMenu: () => void;
  onSelect: (project: ProjectRecord) => void;
  onCreate: () => void;
  onDuplicate: (project: ProjectRecord) => void;
  onToggleArchive: (project: ProjectRecord) => void;
  onDelete: (project: ProjectRecord) => void;
};

/** @brief ChatGPT  project selection, search and project metadata management entry point. */
export function ProjectSwitcher({
  activeProjectId,
  projectName,
  projectNameDraft,
  projects,
  projectTaskCounts,
  editing,
  menuOpen,
  reducedMotion,
  deleteCandidateProjectId,
  deletingProjectId,
  onDraftChange,
  onCommitName,
  onCancelEdit,
  onStartEdit,
  onToggleMenu,
  onSelect,
  onCreate,
  onDuplicate,
  onToggleArchive,
  onDelete,
}: ProjectSwitcherProps) {
  const [query, setQuery] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const visibleProjects = useMemo(
    () => filterProjects(projects, query, showArchived),
    [projects, query, showArchived],
  );
  const archivedCount = projects.filter((project) => project.archivedAt).length;
  const activeCount = projects.length - archivedCount;

  return (
    <div className="project-switcher">
      <div className="project-name-row">
        {editing ? (
          <input
            autoFocus
            value={projectNameDraft}
            maxLength={48}
            aria-label="Proje adı"
            onChange={(event) => onDraftChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") onCommitName();
              if (event.key === "Escape") onCancelEdit();
            }}
          />
        ) : (
          <button
            className="project-switcher-trigger"
            type="button"
            aria-label={`Proje değiştir; mevcut:  ${projectName}`}
            aria-expanded={menuOpen}
            onClick={onToggleMenu}
          >
            <FolderOpen size={15} weight="duotone" />
            <strong title={projectName}>{projectName}</strong>
            <CaretDown size={14} weight="bold" />
          </button>
        )}
        <button
          className="project-name-action"
          type="button"
          aria-label={editing ? "Proje adını onayla" : "Proje adını değiştir"}
          title={editing ? "Proje adını onayla" : "Proje adını değiştir"}
          onClick={editing ? onCommitName : onStartEdit}
        >
          {editing ? <Check size={15} weight="bold" /> : <PencilSimple size={15} weight="duotone" />}
        </button>
      </div>
      <AnimatePresence>
        {menuOpen && !editing ? (
          <motion.div
            className="project-switcher-menu"
            role="menu"
            initial={reducedMotion ? false : { opacity: 0, y: -5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reducedMotion ? undefined : { opacity: 0, y: -5 }}
            transition={{ duration: 0.16 }}
          >
            <div className="project-switcher-tabs" role="tablist" aria-label="Proje kapsamı">
              <button type="button" role="tab" aria-selected={!showArchived} onClick={() => setShowArchived(false)}>
                Proje {activeCount}
              </button>
              <button type="button" role="tab" aria-selected={showArchived} onClick={() => setShowArchived(true)}>
                Arşivle {archivedCount}
              </button>
            </div>
            <label className="project-search">
              <MagnifyingGlass size={14} />
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Proje veya klasör ara" />
            </label>
            <div className="project-switcher-list">
              {visibleProjects.map((project) => {
                const taskCount = projectTaskCounts[project.id] ?? 0;
                return (
                  <div className={project.id === activeProjectId ? "project-switcher-option active" : "project-switcher-option"} key={project.id}>
                    <button className="project-switcher-select" type="button" role="menuitem" onClick={() => onSelect(project)}>
                      <FolderOpen size={15} weight="duotone" />
                      <span>
                        <strong>{project.name}</strong>
                        <small>{taskCount ? `${taskCount}  görev` : "Boş proje"}</small>
                      </span>
                      {project.id === activeProjectId ? <Check size={14} weight="bold" /> : null}
                    </button>
                    <div className="project-option-actions">
                      {!project.archivedAt ? (
                        <button type="button" aria-label={`Projeyi kopyala ${project.name}`} title="Proje yapısını kopyala" onClick={() => onDuplicate(project)}>
                          <Copy size={14} />
                        </button>
                      ) : null}
                      <button
                        type="button"
                        disabled={project.id === activeProjectId}
                        aria-label={`${project.archivedAt ? "Kurtar" : "Arşivle"}Proje ${project.name}`}
                        title={project.id === activeProjectId ? "Etkin proje arşivlenemez" : project.archivedAt ? "Projeyi geri yükle" : "Projeyi arşivle"}
                        onClick={() => onToggleArchive(project)}
                      >
                        {project.archivedAt ? <ArrowCounterClockwise size={14} /> : <Archive size={14} />}
                      </button>
                      <button
                        className={deleteCandidateProjectId === project.id ? "project-delete-button confirm" : "project-delete-button"}
                        type="button"
                        disabled={(!project.archivedAt && activeCount <= 1) || deletingProjectId !== null}
                        aria-label={deleteCandidateProjectId === project.id ? `Proje silmeyi onayla ${project.name}` : `Projeyi sil ${project.name}`}
                        title={!project.archivedAt && activeCount <= 1 ? "En az bir arşivlenmemiş proje tutun" : deleteCandidateProjectId === project.id ? "Proje silmeyi onaylamak için tekrar seçin" : "Projeyi sil"}
                        onClick={() => onDelete(project)}
                      >
                        {deletingProjectId === project.id ? <SpinnerGap className="spin" size={14} /> : deleteCandidateProjectId === project.id ? <Check size={14} weight="bold" /> : <Trash size={14} weight="duotone" />}
                      </button>
                    </div>
                  </div>
                );
              })}
              {!visibleProjects.length ? <div className="project-search-empty">Eşleşme bulunamadı: {showArchived ? "Arşivle" : "Proje"}</div> : null}
            </div>
            <button className="create-project-button" type="button" role="menuitem" onClick={onCreate}>
              <FilePlus size={15} weight="bold" />
              Yeni proje
            </button>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
