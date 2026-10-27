import { CadPreview } from "../CadPreview";
import { artifactKindLabel, artifactStatusLabel, formatBytes } from "../domain/artifacts";
import type { ArtifactRecord } from "../types";

type ArtifactBrowserProps = {
  artifacts: ArtifactRecord[];
  selected?: ArtifactRecord;
  onSelect: (path?: string) => void;
  showPreview?: boolean;
};

/** @brief Show actual delivery files and preview supported formats. */
export function ArtifactBrowser({ artifacts, selected, onSelect, showPreview = true }: ArtifactBrowserProps) {
  return (
    <div className="artifact-list delivery-artifacts">
      {artifacts.length ? artifacts.map((artifact, index) => (
        <button
          type="button"
          className={`${artifact.exists === false ? "artifact-row missing" : "artifact-row"} ${selected?.path === artifact.path ? "selected" : ""}`}
          key={`${artifact.path}-${index}`}
          onClick={() => onSelect(artifact.path)}
          title="Bu çıktıyı sağda önizle"
        >
          <div>
            <strong>{artifactKindLabel(artifact.kind, artifact.path)}</strong>
            <span>{artifact.path}</span>
          </div>
          <small>{formatBytes(artifact.sizeBytes) || artifactStatusLabel(artifact)}</small>
        </button>
      )) : (
        <div className="inspector-empty">
          <strong>Henüz teslim dosyası yok</strong>
          <p>Önce  AI Modelleme, çizim veya dönüştürme görevini tamamlayın; teslim merkezi gerçek çıktıları okuyacaktır.</p>
        </div>
      )}
      {showPreview ? <CadPreview artifact={selected} /> : null}
    </div>
  );
}
