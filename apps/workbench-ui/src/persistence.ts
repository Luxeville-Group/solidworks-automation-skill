import { invoke } from "@tauri-apps/api/core";

export type PersistedStateRead = {
  value: unknown | null;
  degraded: boolean;
};

export type PersistedStateWrite = {
  degraded: boolean;
};

/**
 * @brief Determine whether this page runs in  Tauri  desktop container.
 */
export function isTauriRuntime() {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

/**
 * @brief Safely parse legacy  localStorage  data; corrupted data does not prevent application startup.
 */
export function parsePersistedJson(raw: string | null): unknown | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return null;
  }
}

/**
 * @brief Önce okuyun:  SQLite; If unavailable, retain and read  localStorage  fallback copy.
 */
export async function readPersistedState(namespace: string, legacyKey: string): Promise<PersistedStateRead> {
  const legacyRaw = localStorage.getItem(legacyKey);
  const legacyValue = parsePersistedJson(legacyRaw);
  if (!isTauriRuntime()) {
    return { value: legacyValue, degraded: false };
  }

  // localStorage exists only during legacy migration or after a failed SQLite write, so it may be newer than the database copy.
  // Restore the fallback copy before returning stale database values; otherwise the latest edit can silently disappear after restart.
  if (legacyRaw !== null && legacyValue !== null) {
    try {
      await invoke("write_app_store", { namespace, payload: legacyValue });
      localStorage.setItem(`${legacyKey}.migration-backup`, legacyRaw);
      localStorage.removeItem(legacyKey);
      return { value: legacyValue, degraded: false };
    } catch {
      return { value: legacyValue, degraded: true };
    }
  }

  try {
    const stored = await invoke<unknown | null>("read_app_store", { namespace });
    return { value: stored, degraded: false };
  } catch {
    // Enter an explicit degraded state when SQLite is temporarily locked and no fallback copy is available.
    return { value: null, degraded: true };
  }
}

/**
 * @brief Yaz SQLite; On write failure, also save to  localStorage, Ensure recovery remains possible after restart.
 */
export async function writePersistedState(namespace: string, legacyKey: string, payload: unknown): Promise<PersistedStateWrite> {
  const serialized = JSON.stringify(payload);
  if (!isTauriRuntime()) {
    localStorage.setItem(legacyKey, serialized);
    return { degraded: false };
  }

  try {
    await invoke("write_app_store", { namespace, payload });
    localStorage.removeItem(legacyKey);
    return { degraded: false };
  } catch {
    localStorage.setItem(legacyKey, serialized);
    return { degraded: true };
  }
}
