import { ArrowSquareOut, Copy, Wrench } from "@phosphor-icons/react";
import type { RuntimeRemediation } from "../types";

type EnvironmentRemediationPanelProps = {
  remediations: RuntimeRemediation[];
  onCopyCommand: (command: string) => void | Promise<void>;
  onOpenDownload: (url: string) => void | Promise<void>;
};

/** @brief Display unified  doctor  returned environment remediation actions. */
export function EnvironmentRemediationPanel({ remediations, onCopyCommand, onOpenDownload }: EnvironmentRemediationPanelProps) {
  if (!remediations.length) return null;
  const requiredCount = remediations.filter((item) => item.required).length;

  return (
    <section className="environment-remediation" aria-labelledby="environment-remediation-title">
      <div className="environment-remediation-heading">
        <Wrench size={20} weight="duotone" />
        <div>
          <span>Ortam düzeltme</span>
          <strong id="environment-remediation-title">Algılandı {remediations.length}  ele alınabilir sorun</strong>
        </div>
        <small>{requiredCount ? `${requiredCount} öğe mevcut yürütme yolunu engelliyor` : "Bu isteğe bağlı yetenekler diğer backend işlemlerini engellemez"}</small>
      </div>
      <div className="environment-remediation-list">
        {remediations.map((item) => (
          <article className={item.required ? "environment-remediation-row required" : "environment-remediation-row"} key={item.id}>
            <div className="environment-remediation-copy">
              <span>{item.required ? "İşlem gerekiyor" : "Gerektiğinde kur"}</span>
              <strong>{item.title}</strong>
              {item.reason ? <p>{item.reason}</p> : null}
              {item.installCommand ? <code>{item.installCommand}</code> : null}
            </div>
            <div className="environment-remediation-actions">
              {item.installCommand ? (
                <button type="button" title="Kurulum komutunu kopyala" aria-label={`Kopyala ${item.title}  installation command`} onClick={() => void onCopyCommand(item.installCommand!)}>
                  <Copy size={16} />
                </button>
              ) : null}
              {item.downloadUrl ? (
                <button type="button" className="download-action" title={`Aç ${item.title} Resmî indirme sayfası`} onClick={() => void onOpenDownload(item.downloadUrl!)}>
                  <ArrowSquareOut size={16} />
                  <span>Resmî indirme</span>
                </button>
              ) : null}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
