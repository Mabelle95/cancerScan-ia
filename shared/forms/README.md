# Formulaires de dépistage

Source unique des formulaires CancerScan, utilisée par :
- l'**API** pour valider les saisies et extraire les variables du modèle ;
- le **Web** et le **mobile** pour afficher les formulaires (mis en cache sur le mobile pour le mode hors ligne) ;
- le **pipeline ML** pour connaître la liste des variables (`"ml": true`).

> ⚠️ `"validated": false` — contenu provisoire. Les champs, les signes d'alerte et les
> libellés doivent être validés par des professionnels de santé avant tout usage clinique.

## Format des champs

| Clé | Rôle |
|---|---|
| `type` | `boolean` (Oui / Non / Inconnu), `integer`, `number`, `choice`, `multichoice`, `text`, `date` |
| `required` | le champ doit être renseigné (« Inconnu » compte comme une réponse pour un booléen) |
| `min` / `max` / `unit` | bornes et unité des champs numériques |
| `options` | valeurs d'un `choice` / `multichoice` ; `"alert": true` marque un signe d'alerte |
| `alert_when` | pour un booléen : la valeur qui constitue un signe d'alerte |
| `show_if` | affichage conditionnel : `{"field": "...", "equals": ...}` ou `{"field": "...", "greater_than": n}` |
| `ml` | variable transmise au moteur IA (aucune donnée identifiante ne doit l'être) |
| `help` | texte d'aide affiché sous le champ |
| `after_result` | question posée **après** le résultat de l'IA (ex. appréciation de l'agent) : cachée pendant la saisie, enregistrée ensuite sans relancer l'analyse (`PATCH /screenings/{id}/agent-notes`) |
| `monotone` | `"increasing"` : facteur qui ne peut qu'**augmenter** le risque estimé ; le modèle IA y est contraint (à valider cliniquement). `age_monotone` au niveau du formulaire fait de même pour l'âge |

Une valeur `null` (ou absente) signifie **donnée manquante**, ce qui est distinct d'une
réponse négative (`false`). Pour un booléen, l'interface propose « Inconnu », enregistré
comme `"inconnu"`.
