import type { ManualReviewDraft } from "../types";

type ManualReviewPanelProps = {
  draft: ManualReviewDraft;
  options: Array<readonly [string, string]>;
  onChange: (draft: Partial<ManualReviewDraft>) => void;
  onSubmit: (approved: boolean) => void;
};

/** @brief Require evidence of manual checks in native CAD for dimensions, features, and outputs. */
export function ManualReviewPanel({ draft, options, onChange, onSubmit }: ManualReviewPanelProps) {
  const ready = draft.note.trim().length >= 8 && options.every(([key]) => draft.checks.includes(key));
  return (
    <div className="manual-review-form">
      <strong>İnsan incelemesi kaydı</strong>
      <div className="manual-review-checks">
        {options.map(([key, label]) => (
          <label className="manual-review-check" key={key}>
            <input
              type="checkbox"
              checked={draft.checks.includes(key)}
              onChange={(event) => onChange({
                checks: event.target.checked ? [...new Set([...draft.checks, key])] : draft.checks.filter((item) => item !== key),
              })}
            />
            <span>{label}</span>
          </label>
        ))}
      </div>
      <textarea value={draft.note} onChange={(event) => onChange({ note: event.target.value })} placeholder="Gerçek kontrol sonuçlarını, sorunları veya kabul gerekçesini yazın" />
      <div className="review-action-row">
        <button className="approval-button" type="button" disabled={!ready} title={ready ? "İnsan incelemesini geçir" : "Tüm kontrolleri tamamlayın ve en az 8 karakterlik inceleme açıklaması yazın"} onClick={() => onSubmit(true)}>
          İnceleme geçti
        </button>
        <button className="review-reject-button" type="button" onClick={() => onSubmit(false)}>Reddet</button>
      </div>
    </div>
  );
}
