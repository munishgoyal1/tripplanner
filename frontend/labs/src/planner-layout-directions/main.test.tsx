import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { options } from "./options";
import { allLabs, LAST_ASSIGNED_LAB_NUMBER } from "../shared/labRecords";

describe("planner layout directions lab", () => {
  it("allocates permanent Lab number 30 and a catalog entry", () => {
    const lab = allLabs.find((entry) => entry.id === "planner-layout-directions");
    expect(LAST_ASSIGNED_LAB_NUMBER).toBe(30);
    expect(lab).toMatchObject({ labNumber: 30, href: "./lab-30-planner-layout-directions.html" });
  });

  it("offers two fresh directions, one evolution, and one nuance pass", () => {
    expect(options.map((option) => option.id)).toEqual(["journey", "storyboard", "refined", "polish"]);
    expect(options.map((option) => option.score)).toEqual([95, 91, 88, 80]);
    expect(options.map((option) => option.eyebrow)).toEqual(["Fresh direction 01", "Fresh direction 02", "Evolve sbx4", "Nuance pass"]);
  });

  it("keeps the Lab wired as a standalone Vite entry", () => {
    const vite = readFileSync(resolve(process.cwd(), "labs/vite.config.ts"), "utf8");
    const html = readFileSync(resolve(process.cwd(), "labs/lab-30-planner-layout-directions.html"), "utf8");
    expect(vite).toContain('plannerLayoutDirections: resolve(__dirname, "lab-30-planner-layout-directions.html")');
    expect(html).toContain("./src/planner-layout-directions/main.tsx");
  });
});
