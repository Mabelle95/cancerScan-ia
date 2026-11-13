import { describe, expect, it } from "vitest";
import { parseCoord } from "./Admin";

describe("saisie des coordonnées GPS", () => {
  it("accepte les degrés décimaux, avec point ou virgule, et les valeurs négatives", () => {
    expect(parseCoord("6.1319", 90)).toBe(6.1319);
    expect(parseCoord("6,1319", 90)).toBe(6.1319);
    expect(parseCoord("-0.5", 180)).toBe(-0.5);
    expect(parseCoord("  ", 90)).toBeNull();
  });
  it("refuse une saisie incomplète, du texte ou une valeur hors bornes", () => {
    for (const bad of ["6.", "-", "abc", "91"]) expect(parseCoord(bad, 90)).toBeUndefined();
  });
});
