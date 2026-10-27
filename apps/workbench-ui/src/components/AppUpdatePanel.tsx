import { ArrowClockwise, CheckCircle, DownloadSimple, WarningCircle } from "@phosphor-icons/react";
import { getVersion } from "@tauri-apps/api/app";
import { invoke } from "@tauri-apps/api/core";
import { check, type DownloadEvent, type Update } from "@tauri-apps/plugin-updater";
import { useCallback, useEffect, useRef, useState } from "react";
import { updateDownloadProgress, type UpdateProgress } from "../domain/updateProgress";
import { isTauriRuntime } from "../persistence";

const RELEASES_URL = "https://github.com/Luxeville-Group/solidworks-automation-skill/releases/latest";

// Enable only after configuring fork-owned signed release keys and endpoints.
const FORK_UPDATES_CONFIGURED = false;

type UpdateStatus = "idle" | "checking" | "current" | "available" | "downloading" | "installing" | "error";

/**
 * @brief Check signed releases when a trusted fork update channel is configured.
 */
export function AppUpdatePanel({ expanded }: { expanded: boolean }) {
  const [currentVersion, setCurrentVersion] = useState("Okunuyor");
  const [availableVersion, setAvailableVersion] = useState<string>();
  const [releaseNotes, setReleaseNotes] = useState<string>();
  const [status, setStatus] = useState<UpdateStatus>("idle");
  const [message, setMessage] = useState("Başlangıçta otomatik denetlenir; istediğiniz zaman elle yeniden denetleyebilirsiniz.");
  const [dismissed, setDismissed] = useState(false);
  const [progress, setProgress] = useState<UpdateProgress>({ downloadedBytes: 0 });
  const updateRef = useRef<Update | null>(null);
  const checkingRef = useRef(false);
  const mountedRef = useRef(false);

  const closeCurrentUpdate = useCallback(async () => {
    const current = updateRef.current;
    updateRef.current = null;
    if (current) await current.close().catch(() => undefined);
  }, []);

  const checkForUpdates = useCallback(async (silent = false) => {
    if (!isTauriRuntime() || !FORK_UPDATES_CONFIGURED || checkingRef.current) return;
    checkingRef.current = true;
    setDismissed(false);
    setStatus("checking");
    setMessage("GitHub Releases üzerinden yeni sürüm denetleniyor...");
    setAvailableVersion(undefined);
    setReleaseNotes(undefined);
    setProgress({ downloadedBytes: 0 });
    try {
      await closeCurrentUpdate();
      const nextUpdate = await check({ timeout: 30_000 });
      if (!mountedRef.current) {
        await nextUpdate?.close().catch(() => undefined);
        return;
      }
      if (!nextUpdate) {
        setAvailableVersion(undefined);
        setStatus("current");
        setMessage("En güncel sürümü kullanıyorsunuz.");
        return;
      }
      updateRef.current = nextUpdate;
      setAvailableVersion(nextUpdate.version);
      setReleaseNotes(nextUpdate.body?.trim());
      setStatus("available");
      setMessage(`CAD Studio ${nextUpdate.version} bulundu. Yüklemeden önce çalışmanızı kaydedebilirsiniz.`);
    } catch (error) {
      if (!mountedRef.current) return;
      const detail = error instanceof Error ? error.message : String(error);
      setStatus(silent ? "idle" : "error");
      setMessage(silent ? `Son otomatik kontrol tamamlanmadı: ${detail}. Buradan elle yeniden deneyebilirsiniz.` : `Güncelleme denetimi başarısız: ${detail}`);
    } finally {
      checkingRef.current = false;
    }
  }, [closeCurrentUpdate]);

  const installUpdate = useCallback(async () => {
    const update = updateRef.current;
    if (!update) {
      await checkForUpdates();
      return;
    }
    setStatus("downloading");
    setProgress({ downloadedBytes: 0 });
    setMessage("İmzalı güncelleme paketi indiriliyor ve doğrulanıyor...");
    try {
      let currentProgress: UpdateProgress = { downloadedBytes: 0 };
      await update.downloadAndInstall((event: DownloadEvent) => {
        currentProgress = updateDownloadProgress(currentProgress, event);
        setProgress(currentProgress);
        if (event.event === "Finished") {
          setStatus("installing");
          setMessage("Güncelleme paketi doğrulandı. Yükleyici devralacak ve mevcut pencere kapanacak.");
        }
      }, { timeout: 120_000 });
    } catch (error) {
      setStatus("error");
      setMessage(`Güncelleme yüklenemedi: ${error instanceof Error ? error.message : String(error)}`);
    }
  }, [checkForUpdates]);

  useEffect(() => {
    mountedRef.current = true;
    let timer: number | undefined;
    if (!isTauriRuntime()) {
      setCurrentVersion("Tarayıcı önizlemesi");
      setMessage("Otomatik güncelleme yalnızca CAD Studio Windows masaüstü sürümünde kullanılabilir.");
    } else {
      void getVersion().then(setCurrentVersion).catch(() => setCurrentVersion("Bilinmiyor"));
      if (FORK_UPDATES_CONFIGURED) {
        timer = window.setTimeout(() => void checkForUpdates(true), 1_500);
      } else {
        setMessage("Bu fork için imzalı güncelleme kanalı henüz yapılandırılmadı. Türkçe/İngilizce sürümleri fork yayın sayfasından takip edin.");
      }
    }
    return () => {
      mountedRef.current = false;
      if (timer !== undefined) window.clearTimeout(timer);
      void closeCurrentUpdate();
    };
  }, [checkForUpdates, closeCurrentUpdate]);

  const busy = status === "checking" || status === "downloading" || status === "installing";
  const Icon = status === "error" ? WarningCircle : status === "current" ? CheckCircle : status === "available" ? DownloadSimple : ArrowClockwise;
  if (!expanded && (dismissed || (status !== "available" && status !== "error"))) return null;

  return (
    <article className={`setting-card update-setting ${status} ${expanded ? "expanded" : "floating"}`} aria-live="polite">
      <div className="update-heading">
        <Icon size={22} weight="duotone" />
        <div>
          <span>Uygulama güncellemesi</span>
          <strong>{availableVersion ? `${currentVersion} → ${availableVersion}` : `CAD Studio ${currentVersion}`}</strong>
        </div>
      </div>
      <p>{message}</p>
      {status === "downloading" || status === "installing" ? (
        <div className="update-progress" aria-label={progress.percent === undefined ? "Güncelleme indiriliyor" : `Güncelleme indirme ilerlemesi ${progress.percent}%`}>
          <i style={{ width: `${progress.percent ?? 12}%` }} />
          <small>{progress.percent === undefined ? "Güncelleme paketi alınıyor" : `${progress.percent}%`}</small>
        </div>
      ) : null}
      {releaseNotes && status === "available" ? <details><summary>Sürüm notlarını görüntüle</summary><p>{releaseNotes}</p></details> : null}
      <div className="update-actions">
        {status === "available" ? <button type="button" disabled={busy} onClick={() => void installUpdate()}>İndir ve yükle</button> : null}
        <button type="button" disabled={busy || !isTauriRuntime() || !FORK_UPDATES_CONFIGURED} onClick={() => void checkForUpdates()}>
          {status === "checking" ? "Kontrol ediliyor" : "Güncellemeleri denetle"}
        </button>
        {status === "error" || !FORK_UPDATES_CONFIGURED ? <button type="button" onClick={() => void invoke("open_external_download", { url: RELEASES_URL }).catch((error) => setMessage(`İndirme sayfası açılamadı: ${error instanceof Error ? error.message : String(error)}`))}>İndirme sayfasını aç</button> : null}
        {!expanded ? <button type="button" onClick={() => setDismissed(true)}>Daha sonra</button> : null}
      </div>
    </article>
  );
}
