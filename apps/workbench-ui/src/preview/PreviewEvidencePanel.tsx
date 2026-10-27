import type { PreviewManifest, PreviewSelection } from "./previewTypes";

type PreviewEvidencePanelProps = {
  manifest?: PreviewManifest | null;
  selection?: PreviewSelection | null;
};

/** @brief Show how previews link to delivery evidence, hashes and limitations. */
export function PreviewEvidencePanel({ manifest, selection }: PreviewEvidencePanelProps) {
  const evidence = [...new Set([...(manifest?.evidenceRefs ?? []), ...(selection?.evidenceRefs ?? [])])];
  const limitations = manifest?.limitations ?? [];
  return (
    <div className="cad-preview-evidence">
      <div><span>Önizleme özeti (hash)</span><strong>{manifest?.sha256 ? `${manifest.sha256.slice(0, 12)}…` : "Kaydedilmedi"}</strong></div>
      <div><span>Oluşturulma zamanı</span><strong>{manifest?.generatedAt || "Kaydedilmedi"}</strong></div>
      {evidence.length ? <div className="evidence-tags">{evidence.map((item) => <small key={item}>{item}</small>)}</div> : <small>Yok Evidence Graph  binding.</small>}
      {limitations.length ? <div className="preview-limitations">{limitations.map((item) => <small key={item}>{item}</small>)}</div> : null}
    </div>
  );
}
