import { describe, expect, it } from "vitest";
import type { AutomationJob } from "../types";
import { assessDelivery } from "./delivery";

function completedJob(requirement: string, path: string, kind?: string): AutomationJob {
  return {
    schemaVersion: "2.0",
    id: "delivery-test",
    runId: "delivery-run",
    kind: "delivery_package",
    title: "Delivery test",
    detail: "",
    status: "passed",
    progress: 100,
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    requestedBy: "test",
    createdByAppVersion: "0.3.4",
    requiredArtifacts: [requirement],
    artifacts: [{ kind, path, exists: true, producedThisRun: true }],
  };
}

describe("localized delivery requirements", () => {
  it.each([
    ["drawing", "part.slddrw"],
    ["Çizim", "part.slddrw"],
    ["çizim", "part.slddrw"],
    ["ÇİZİM", "part.slddrw"],
    ["ÇIZIM", "part.slddrw"],
    ["Malzeme", "bom.csv"],
    ["Ayrıntı tablosu", "bom.csv"],
    ["AYRINTI TABLOSU", "bom.csv"],
    ["ÖNİZLEME", "part.png"],
    ["İncele", "review.json"],
  ])("accepts %s when its matching artifact exists", (requirement, path) => {
    expect(assessDelivery(completedJob(requirement, path)).disposition).toBe("ready");
  });

  it("still requires the requested artifact type", () => {
    expect(assessDelivery(completedJob("ÇİZİM", "part.step")).disposition).toBe("incomplete");
  });

  it.each([
    ["bom", "Malzeme"],
    ["bom", "MALZEME"],
    ["preview", "Önizleme"],
    ["preview", "ÖNİZLEME"],
    ["preview", "ÖNIZLEME"],
    ["report", "İncele"],
    ["report", "İNCELE"],
    ["report", "ıncele"],
    ["report", "Rapor"],
  ])("accepts %s with the Turkish artifact kind %s", (requirement, kind) => {
    expect(assessDelivery(completedJob(requirement, "output.dat", kind)).disposition).toBe("ready");
  });

  it.each(["drawing", "ÇİZİM", "bom"])("keeps %s incomplete with an unrelated unknown artifact", (requirement) => {
    expect(assessDelivery(completedJob(requirement, "notes.txt", "attachment")).disposition).toBe("incomplete");
  });
});
