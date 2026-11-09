# CancerScan

Système d'aide au dépistage et à l'orientation précoce des cancers du sein et gynécologiques (Togo).

> **Outil d'aide à la décision clinique : il ne pose pas de diagnostic.** Les formulaires, seuils et
> recommandations sont provisoires (`"validated": false`) et doivent être validés par des professionnels de santé.

## Architecture

| Dossier | Rôle | État |
|---|---|---|
| `shared/forms/` | Formulaires de dépistage (source unique : API, Web, mobile, ML) | v0.1.0, à valider |
| `api/` | API REST FastAPI + PostgreSQL : authentification, rôles, dossiers, dépistages, orientations, suivi, statistiques, journal, synchronisation hors ligne | fonctionnel, testé |
| `ml/` | Pipeline d'entraînement (CRISP-DM) et moteur d'inférence | fonctionnel, testé |
| `web/` | Plateforme Web React + TypeScript : saisie guidée, résultat IA expliqué, validation médicale, suivi, statistiques, administration | fonctionnel |
| `mobile/` | Application Flutter Android pour les agents : saisie hors ligne chiffrée, synchronisation idempotente | fonctionnel, testé |

Flux : agent → API (validation, signes d'alerte) → moteur IA (score calibré, niveau, explications SHAP) →
orientation proposée → décision du professionnel → suivi de la référence.

## Démarrage (Docker)

```bash
cp .env.example .env   # renseigner JWT_SECRET, DATA_ENCRYPTION_KEY, LOOKUP_HMAC_KEY, ENGINE_API_KEY
docker compose up --build
```

- API : http://localhost:8000/docs · moteur IA : http://localhost:8001/health
- Comptes de démonstration (environnement `development`) : `admin@`, `agent@`, `medecin@`, `specialiste@`,
  `responsable@cancerscan.tg`, mot de passe `ADMIN_PASSWORD`.

## Développement local

```bash
cd api && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt && .venv/Scripts/pytest
cd ml  && python -m venv .venv && .venv/Scripts/pip install -r requirements.txt && .venv/Scripts/pytest
```

### Plateforme Web

```bash
cd web && npm install
npm run dev      # http://127.0.0.1:5173 — les appels /api sont relayés vers l'API sur le port 8000
npm test         # logique des formulaires, testée sur les vrais fichiers shared/forms
npm run build
```

### Application mobile (agents de santé)

```bash
cd mobile
flutter pub get
flutter test                       # logique des formulaires + synchronisation hors ligne (faux serveur)
flutter run                        # émulateur : l'API locale est jointe via http://10.0.2.2:8000
flutter build apk --release --dart-define=API_URL=https://api.exemple.tg/api/v1
```

Mode hors ligne : patientes et dépistages sont enregistrés d'abord sur l'appareil (SQLite, contenu chiffré en
AES-256-GCM, clé dans le Keystore Android, sauvegarde Android désactivée), puis envoyés à `POST /sync` dès que la
connexion revient. Chaque saisie porte un identifiant unique : un renvoi ne crée pas de doublon. Les signes d'alerte
sont détectés sur l'appareil ; l'application affiche « Analyse IA non encore calculée » tant que le serveur n'a pas
produit le résultat. La première connexion doit se faire en ligne (téléchargement des formulaires). La déconnexion
est refusée tant que des saisies ne sont pas synchronisées, et un autre compte ne peut pas se connecter tant que la
file d'attente du précédent n'est pas vide.

## Modèles IA

```bash
cd ml
# 1. Données — ici SYNTHÉTIQUES, uniquement pour tester le pipeline
python -m cancerscan_ml.synthetic --pathology sein --n 3000 --out data/sein_synthetique.csv
# 2. Entraînement : LR / Random Forest / XGBoost, séparation par patiente, calibration, seuils, rapport
python -m cancerscan_ml.train --pathology sein --data data/sein_synthetique.csv --external-site Kara
# 3. Versions et validation clinique (refusée pour un modèle synthétique ou sans validation externe)
python -m cancerscan_ml.promote list
```

### Données réelles — sein : BrEaST-Lesions_USG

```bash
# Télécharger depuis TCIA (CC BY 4.0) dans ml/data/breast/ puis :
python -m cancerscan_ml.datasets.breast_lesions_usg --xlsx data/breast/BrEaST-clinical.xlsx --out data/breast/sein_breast_lesions_usg.csv
python -m cancerscan_ml.train --pathology sein --data data/breast/sein_breast_lesions_usg.csv \
    --data-source "BrEaST-Lesions_USG (TCIA, CC BY 4.0)" --no-missing-indicators
```

256 patientes polonaises (98 cancers confirmés par biopsie ou suivi) ayant toutes une lésion à l'échographie :
ce n'est **pas** une population de dépistage togolaise. Les 46 cas sans signes cliniques renseignés sont exclus, et
`--no-missing-indicators` empêche le modèle d'apprendre qu'une donnée manquante modifie le risque (artefact du jeu).
Modèle utilisable pour le prototype et la démonstration uniquement.

> Citation obligatoire : Pawłowska A., Ćwierz-Pieńkowska A., Domalik A., et al. *Curated benchmark dataset for
> ultrasound based breast lesion analysis.* Scientific Data 11, 148 (2024). doi:10.1038/s41597-024-02984-z —
> données : The Cancer Imaging Archive, collection BrEaST-Lesions_USG, licence CC BY 4.0.

Chaque version est enregistrée dans `ml/models/<pathologie>/<version>/` avec `metadata.json` (seuils, métriques,
provenance des données, statut de validation) et `rapport.md`. Le moteur refuse les modèles non validés sauf si
`ENGINE_ALLOW_UNVALIDATED=true` (développement uniquement) ; l'analyse est alors différée et la patiente reste
orientable par le professionnel.

### Contraintes de monotonie cliniques

Les facteurs déclarés `"monotone": "increasing"` dans le formulaire (antécédents familial et personnel, masse, taille
de la masse, modification de la peau, rétraction du mamelon, ganglions, traitement hormonal, âge) ne peuvent
qu'**augmenter** le risque estimé : régression logistique à coefficients bornés, contraintes natives de Random Forest
et XGBoost. Sans elles, le modèle BrEaST faisait baisser le risque jusqu'à 22 points en cas d'antécédent familial
(biais d'un petit échantillon) ; avec elles, la performance est identique ou meilleure. La liste des facteurs
contraints est à valider par les professionnels de santé. `--no-monotone` ne sert qu'à comparer.

### Règles de sécurité clinique implémentées

- Un **signe d'alerte** saisi impose au minimum une orientation « moyen », même si le modèle estime un risque faible.
- Une décision prise par un professionnel n'est jamais écrasée par une nouvelle analyse.
- Le modèle ne reçoit que les variables `ml` du formulaire et l'âge — jamais le nom ni le téléphone.
- Le moteur refuse un modèle dont les variables ne correspondent plus au formulaire (ajouter des champs non utilisés par le modèle reste compatible).
- Une réponse non renseignée n'est jamais présentée comme un facteur explicatif.
- « Inconnu » / absent est distinct d'une réponse négative, à la saisie comme dans le modèle.

### Sécurité des données

Nom et téléphone chiffrés en AES-256-GCM ; recherche de doublons par HMAC ; accès aux dossiers restreint à
l'établissement (et aux patientes référées pour le spécialiste) ; l'administrateur n'accède pas aux dossiers
médicaux ; statistiques masquées sous 5 effectifs ; journal des connexions, consultations, modifications,
exécutions IA et changements de droits.

## Supervision : logs, erreurs, traçabilité

| Besoin | Où | Contenu |
|---|---|---|
| Journal d'activité (qui a fait quoi) | Table `audit_logs` · Web : *Journal d'activité* | Connexions et échecs, consultations, créations, modifications, analyses IA, décisions, changements de droits |
| Logs techniques | `logs/api.log`, `logs/engine.log` (JSON, rotation 10 × 10 Mo) | Une ligne par requête : méthode, chemin, statut, durée, utilisateur, référence |
| Erreurs | Table `system_errors` · Web : *État du système* | Erreurs de l'API, du moteur IA, du site et de l'application mobile, avec la trace technique |
| État des composants | `GET /api/v1/system/status` · Web : *État du système* | Base, moteur IA et modèles, temps de réponse, erreurs 24 h, analyses en attente |

- **Référence de requête** : chaque requête reçoit un identifiant (en-tête `X-Request-ID`), transmis au moteur IA. En cas
  d'erreur, l'utilisateur voit « référence a3f9… » ; l'administrateur la recherche dans *État du système* et dans les logs.
- **Confidentialité** : les logs ne contiennent jamais de corps de requête ni de paramètres de recherche (testé). Les
  journaux d'accès d'uvicorn et de httpx, qui écrivent l'URL complète, sont désactivés ou limités aux avertissements.
- **Mobile** : les erreurs sont mises en file sur le téléphone et envoyées à la synchronisation suivante.
- Une panne du moteur IA (erreur 5xx) diffère l'analyse sans perdre la saisie, et elle est enregistrée comme erreur.

