import { useEffect, useState } from "react";
import { api, type FormDef, type Pathology } from "../api";

// Les formulaires changent rarement : un seul chargement par session.
let cache: Promise<FormDef[]> | null = null;

export function useForms() {
  const [forms, setForms] = useState<FormDef[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    cache ??= api.forms();
    cache.then(setForms).catch((e: Error) => {
      cache = null;
      setError(e.message);
    });
  }, []);
  const byPathology = (p: Pathology) => forms?.find((f) => f.pathology === p);
  return { forms, error, byPathology };
}

/** Le sein est la pathologie prioritaire de la première version. */
export const PATHOLOGY_ORDER: Pathology[] = ["sein", "col", "ovaire", "endometre"];
