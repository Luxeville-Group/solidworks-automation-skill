import { Check, SpinnerGap, Trash } from "@phosphor-icons/react";
import { useState } from "react";
import { jobDisplayTitle, sidebarJobStatusLabel } from "../domain/jobs";
import type { AutomationJob } from "../types";

type TaskSequenceProps = {
  jobs: AutomationJob[];
  activeJobId?: string;
  deleteCandidateJobId: string | null;
  deletingJobId: string | null;
  terminalCount: number;
  onSelect: (job: AutomationJob) => void;
  onDelete: (job: AutomationJob) => void;
  onClearTerminal: () => Promise<void>;
};

/** @brief Recent jobs in a project, with individual deletion and bulk cleanup of terminal records. */
export function TaskSequence({
  jobs,
  activeJobId,
  deleteCandidateJobId,
  deletingJobId,
  terminalCount,
  onSelect,
  onDelete,
  onClearTerminal,
}: TaskSequenceProps) {
  const [clearArmed, setClearArmed] = useState(false);
  const [clearing, setClearing] = useState(false);

  async function clearTerminalRecords() {
    if (!clearArmed) {
      setClearArmed(true);
      return;
    }
    setClearing(true);
    try {
      await onClearTerminal();
      setClearArmed(false);
    } finally {
      setClearing(false);
    }
  }

  return (
    <nav className="project-sequence" aria-label="Proje görev sırası">
      <div className="project-sequence-head">
        <span className="sidebar-label">Son görevler</span>
        {terminalCount ? (
          <button
            className={clearArmed ? "clear-terminal-button confirm" : "clear-terminal-button"}
            type="button"
            disabled={clearing || deletingJobId !== null}
            title={clearArmed ? `Temizlemek için tekrar seçin ${terminalCount}  terminal kayıt` : "Tamamlanmış görev kayıtlarını temizle"}
            aria-label={clearArmed ? `Temizlemeyi onayla ${terminalCount}  terminal görev kaydı` : "Sonlanmış görev kayıtlarını topluca temizle"}
            onBlur={() => setClearArmed(false)}
            onClick={() => void clearTerminalRecords()}
          >
            {clearing ? <SpinnerGap className="spin" size={13} /> : clearArmed ? <Check size={13} weight="bold" /> : <Trash size={13} />}
          </button>
        ) : null}
      </div>
      {jobs.length ? jobs.map((job) => (
        <div className={activeJobId === job.id ? "project-sequence-item active" : "project-sequence-item"} key={job.id}>
          <button className="project-sequence-select" type="button" onClick={() => onSelect(job)}>
            <i className={job.status === "review_required" && job.progress >= 100 ? "passed" : job.status} />
            <span>
              <strong>{jobDisplayTitle(job)}</strong>
              <small>{sidebarJobStatusLabel(job)} · {job.progress}%</small>
            </span>
          </button>
          <button
            className={deleteCandidateJobId === job.id ? "project-sequence-delete confirm" : "project-sequence-delete"}
            type="button"
            disabled={deletingJobId !== null}
            aria-label={deleteCandidateJobId === job.id ? `Silmeyi onayla ${jobDisplayTitle(job)}` : `Sil ${jobDisplayTitle(job)}`}
            title={deleteCandidateJobId === job.id ? "Silmeyi onaylamak için tekrar seçin" : "Görev kaydını sil"}
            onClick={() => onDelete(job)}
          >
            {deletingJobId === job.id ? <SpinnerGap className="spin" size={15} /> : deleteCandidateJobId === job.id ? <Check size={15} weight="bold" /> : <Trash size={15} weight="duotone" />}
          </button>
        </div>
      )) : (
        <div className="sidebar-empty">Gerçekten çalıştırılan görevler burada görünür. Şablon seçmek yeni kayıt oluşturmaz.</div>
      )}
    </nav>
  );
}
