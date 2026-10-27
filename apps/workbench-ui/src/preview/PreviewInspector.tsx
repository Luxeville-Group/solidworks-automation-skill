import type { PreviewLayer, PreviewManifest, PreviewSelection, PreviewStats } from "./previewTypes";
import { fileName } from "./previewUtils";

type PreviewInspectorProps = {
  artifactPath?: string;
  manifest?: PreviewManifest | null;
  stats: PreviewStats;
  selection?: PreviewSelection | null;
  layers: PreviewLayer[];
  visibleLayers: Set<string>;
  onToggleLayer: (layer: string) => void;
};

/** @brief Show the model tree, layers, bounds, and selected objects. */
export function PreviewInspector({ artifactPath, manifest, stats, selection, layers, visibleLayers, onToggleLayer }: PreviewInspectorProps) {
  return (
    <aside className="cad-preview-inspector" aria-label="Önizleme inceleyicisi">
      <div className="inspector-block">
        <span>Dosya</span>
        <strong>{fileName(artifactPath)}</strong>
        {manifest?.sourceArtifact ? <small>Kaynak: {fileName(manifest.sourceArtifact)}</small> : null}
      </div>
      <div className="inspector-grid">
        <div><span>Birim</span><strong>{stats.units || manifest?.units || "mm"}</strong></div>
        <div><span>Nesne</span><strong>{stats.entityCount ?? stats.meshCount ?? 0}</strong></div>
        <div><span>Katman</span><strong>{stats.layerCount ?? layers.length}</strong></div>
        <div><span>Kapsam</span><strong>{stats.boundsLabel || "Okuma bekliyor"}</strong></div>
      </div>
      {selection ? (
        <div className="inspector-block selected">
          <span>Mevcut seçim</span>
          <strong>{selection.name}</strong>
          <small>{selection.type}{selection.layer ? ` · ${selection.layer}` : ""}</small>
        </div>
      ) : <div className="inspector-empty-mini">Kanıt referanslarını görmek için bir model nesnesi veya DXF çizgisi seçin.</div>}
      {layers.length ? (
        <div className="layer-list" aria-label="DXF Katman">
          <span>Katman</span>
          {layers.map((layer) => (
            <label key={layer.name}>
              <input type="checkbox" checked={visibleLayers.has(layer.name)} onChange={() => onToggleLayer(layer.name)} />
              <i style={{ background: layer.color || "#176c65" }} />
              <strong>{layer.name}</strong>
              <small>{layer.count ?? 0}</small>
            </label>
          ))}
        </div>
      ) : null}
    </aside>
  );
}
