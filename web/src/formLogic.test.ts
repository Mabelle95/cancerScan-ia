import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { FormDef } from "./api";
import { checkForm, displayValue, fieldIndex, isVisible } from "./formLogic";

// Le vrai formulaire partagé : le test échoue si le formulaire évolue de façon incompatible.
const sein: FormDef = JSON.parse(readFileSync(resolve(__dirname, "../../shared/forms/sein.json"), "utf-8"));
const f = fieldIndex(sein);

const complet = {
  atcd_familial_sein_ovaire: false,
  atcd_personnel_sein: false,
  masse_presente: false,
  modif_peau: false,
  retraction_mamelon: "inconnu",
  examen_realise: true,
  probabilite_enqueteur: "faible",
};

describe("formulaire sein", () => {
  it("affiche les champs conditionnels selon les réponses", () => {
    expect(isVisible(f.masse_taille_cm, { masse_presente: true })).toBe(true);
    expect(isVisible(f.masse_taille_cm, { masse_presente: false })).toBe(false);
    expect(isVisible(f.age_premiere_grossesse, { nb_grossesses_terme: 0 })).toBe(false);
    expect(isVisible(f.age_premiere_grossesse, { nb_grossesses_terme: 2 })).toBe(true);
  });

  it("signale les champs obligatoires manquants ; « inconnu » compte comme une réponse", () => {
    expect(checkForm(sein, {}).missing).toContain("masse_presente");
    expect(checkForm(sein, complet).missing).toEqual([]);
  });

  it("refuse les valeurs hors bornes", () => {
    const r = checkForm(sein, { ...complet, age_premieres_regles: 3 });
    expect(r.errors.age_premieres_regles).toMatch(/Minimum/);
  });

  it("relève les signes d'alerte (booléens et options)", () => {
    const r = checkForm(sein, { ...complet, retraction_mamelon: true, ecoulement: "sanglant" });
    expect(r.alerts.map((a) => a.field).sort()).toEqual(["ecoulement", "retraction_mamelon"]);
  });

  it("n'envoie pas les champs masqués", () => {
    const r = checkForm(sein, { ...complet, nb_grossesses_terme: 0, age_premiere_grossesse: 25 });
    expect(r.cleaned).not.toHaveProperty("age_premiere_grossesse");
  });

  it("distingue inconnu, non et absent à l'affichage", () => {
    expect(displayValue(f.modif_peau, false)).toBe("Non");
    expect(displayValue(f.modif_peau, "inconnu")).toBe("Inconnu");
    expect(displayValue(f.modif_peau, null)).toBe("—");
    expect(displayValue(f.ecoulement, "non_precise")).toBe("Oui, type non précisé");
  });
});
