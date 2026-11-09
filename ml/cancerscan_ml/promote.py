"""Gestion des versions déployées et validation clinique d'un modèle.

    python -m cancerscan_ml.promote list
    python -m cancerscan_ml.promote activate --pathology sein --version 20261109-101500
    python -m cancerscan_ml.promote validate --pathology sein --version 20261109-101500 \\
        --approved-by "Dr X, Dr Y" --reference "PV comité scientifique n°3" --evidence "étude prospective silencieuse 2027"

La validation est un acte humain tracé : elle n'est possible que pour un modèle entraîné sur des données
réelles, après validation externe et prospective (cahier des charges §12).
"""

import argparse
from datetime import datetime, timezone

from cancerscan_ml import registry


def list_models(models_dir=None) -> list[dict]:
    models_dir = models_dir or registry.MODELS_DIR
    rows = []
    for pdir in sorted(p for p in models_dir.iterdir() if p.is_dir()) if models_dir.exists() else []:
        active = registry.active_version(pdir.name, models_dir)
        for vdir in sorted(v for v in pdir.iterdir() if (v / "metadata.json").exists()):
            m = registry.read_metadata(pdir.name, vdir.name, models_dir)
            test = m["evaluation"]["test"]
            rows.append({
                "pathology": m["pathology"], "version": m["version"], "model_id": m["model_id"], "algorithm": m["algorithm"],
                "active": m["version"] == active, "validated": m["validated"], "data_source": m["data_source"],
                "form_version": m["form_version"], "trained_at": m["trained_at"], "thresholds": m["thresholds"],
                "test_roc_auc": test["roc_auc"], "test_pr_auc": test["pr_auc"],
                "test_sensitivity": test["orientation_moyen_ou_plus"]["sensibilite"],
                "test_specificity": test["orientation_moyen_ou_plus"]["specificite"],
            })
    return rows


def validate(pathology: str, version: str, approved_by: str, reference: str, evidence: str, models_dir=None) -> dict:
    meta = registry.read_metadata(pathology, version, models_dir)
    if meta["data_source"] == "synthetique":
        raise SystemExit("Refusé : un modèle entraîné sur des données synthétiques ne peut pas être validé.")
    if "validation_externe" not in meta["evaluation"]:
        raise SystemExit("Refusé : aucune validation externe n'est enregistrée pour ce modèle (--external-site à l'entraînement).")
    meta["validated"] = True
    meta["validation"] = {"approved_by": approved_by, "reference": reference, "evidence": evidence,
                          "date": datetime.now(timezone.utc).isoformat()}
    registry.write_metadata(meta, models_dir)
    return meta


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    for name in ("activate", "validate"):
        p = sub.add_parser(name)
        p.add_argument("--pathology", required=True)
        p.add_argument("--version", required=True)
        if name == "validate":
            p.add_argument("--approved-by", required=True)
            p.add_argument("--reference", required=True)
            p.add_argument("--evidence", required=True)
    args = parser.parse_args()

    if args.cmd == "list":
        for r in list_models():
            flag = "*" if r["active"] else " "
            print(f"{flag} {r['pathology']:<10} {r['version']}  {r['algorithm']:<20} validé={r['validated']!s:<5} "
                  f"source={r['data_source']}  sens={r['test_sensitivity']} spec={r['test_specificity']}")
    elif args.cmd == "activate":
        registry.read_metadata(args.pathology, args.version)  # vérifie l'existence
        (registry.MODELS_DIR / args.pathology / "ACTIVE").write_text(args.version, encoding="utf-8")
        print(f"Version active pour {args.pathology} : {args.version} (recharger le moteur : POST /reload)")
    else:
        validate(args.pathology, args.version, args.approved_by, args.reference, args.evidence)
        print("Modèle marqué comme validé.")


if __name__ == "__main__":
    main()
