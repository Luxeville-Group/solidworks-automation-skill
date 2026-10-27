import { describe, expect, it } from "vitest";
import { updateDownloadProgress } from "./updateProgress";

describe("updateDownloadProgress", () => {
  it("Calculate download percentage from total package size", () => {
    let progress = updateDownloadProgress({ downloadedBytes: 0 }, { event: "Started", data: { contentLength: 1000 } });
    progress = updateDownloadProgress(progress, { event: "Progress", data: { chunkLength: 260 } });
    expect(progress).toEqual({ downloadedBytes: 260, totalBytes: 1000, percent: 26 });
  });

  it("Clamp progress beyond the total size to  100%", () => {
    const progress = updateDownloadProgress(
      { downloadedBytes: 900, totalBytes: 1000, percent: 90 },
      { event: "Progress", data: { chunkLength: 500 } },
    );
    expect(progress.percent).toBe(100);
  });

  it("Accumulate bytes without inventing a percentage when total size is unknown", () => {
    const progress = updateDownloadProgress({ downloadedBytes: 0 }, { event: "Progress", data: { chunkLength: 128 } });
    expect(progress).toEqual({ downloadedBytes: 128, percent: undefined });
  });
});
