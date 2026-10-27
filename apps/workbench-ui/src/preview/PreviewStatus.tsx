import { WarningCircle } from "@phosphor-icons/react";
import type { PreviewManifest, PreviewPhase } from "./previewTypes";

type PreviewStatusProps = {
  phase: PreviewPhase;
  message: string;
  manifest?: PreviewManifest | null;
};

/** @brief Show granular preview loading stages and actual /Demo provenance. */
export function PreviewStatus({ phase, message, manifest }: PreviewStatusProps) {
  const isDemo = manifest?.isDemo || manifest?.mode === "demo-showcase";
  return (
    <div className={`cad-preview-status-line ${phase === "Önizleme başarısız" ? "error" : phase === "Etkileşimli" ? "ready" : "loading"}`}>
      <span>{phase}</span>
      <small>{message}</small>
      <em className={isDemo ? "demo" : "delivery"}>{isDemo ? "Demo verisi" : "Gerçek çıktı"}</em>
      {isDemo ? <WarningCircle size={15} /> : null}
    </div>
  );
}
