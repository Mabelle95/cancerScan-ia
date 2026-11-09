"""Modèles respectant des contraintes de monotonie cliniques.

Certains facteurs ne peuvent, par définition médicale, que faire AUGMENTER le risque estimé (antécédent familial,
masse palpable, rétraction du mamelon…). Sur un petit jeu de données, un modèle libre peut apprendre l'inverse
par hasard ou par biais de sélection (ex. BrEaST : antécédent familial à −0,29). Ces contraintes l'en empêchent.

Les contraintes sont déclarées dans le formulaire (`"monotone": "increasing"`) et s'appliquent aux colonnes
numériques/booléennes, qui sont toujours les premières colonnes produites par `features.preprocessor`.
"""

import numpy as np
from scipy.optimize import minimize
from sklearn.base import BaseEstimator, ClassifierMixin, clone
from sklearn.ensemble import RandomForestClassifier
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier


def full_constraints(leading: tuple[int, ...], n_columns: int) -> list[int]:
    """Contraintes des premières colonnes (variables numériques), 0 pour les suivantes (indicatrices, one-hot)."""
    return list(leading) + [0] * (n_columns - len(leading))


class ConstrainedLogisticRegression(ClassifierMixin, BaseEstimator):
    """Régression logistique régularisée (L2) dont certains coefficients sont contraints en signe.

    +1 : coefficient ≥ 0 (le facteur ne peut qu'augmenter le risque) ; −1 : ≤ 0 ; 0 : libre.
    Interface compatible avec `LogisticRegression` (coef_, intercept_, predict_proba).
    """

    def __init__(self, C: float = 1.0, class_weight=None, leading_constraints: tuple[int, ...] = (), max_iter: int = 2000):
        self.C = C
        self.class_weight = class_weight
        self.leading_constraints = leading_constraints
        self.max_iter = max_iter

    def fit(self, X, y, sample_weight=None):
        X = np.asarray(X, dtype=float)
        y = np.asarray(y)
        self.classes_ = np.unique(y)
        if len(self.classes_) != 2:
            raise ValueError("Classification binaire uniquement")
        t = (y == self.classes_[1]).astype(float)
        w = np.ones(len(t)) if sample_weight is None else np.asarray(sample_weight, dtype=float)
        if self.class_weight is not None:
            w = w * compute_sample_weight(self.class_weight, y)
        n, d = X.shape
        cst = full_constraints(tuple(self.leading_constraints), d)
        bounds = [(0, None) if c > 0 else (None, 0) if c < 0 else (None, None) for c in cst] + [(None, None)]
        lam = 1.0 / (self.C * w.sum())

        def loss(params):
            coef, b = params[:-1], params[-1]
            z = X @ coef + b
            # log(1 + e^z) stable numériquement
            nll = np.sum(w * (np.logaddexp(0, z) - t * z)) / w.sum()
            p = 1 / (1 + np.exp(-z))
            grad_coef = X.T @ (w * (p - t)) / w.sum() + lam * coef
            grad_b = np.sum(w * (p - t)) / w.sum()
            return nll + 0.5 * lam * coef @ coef, np.append(grad_coef, grad_b)

        res = minimize(loss, np.zeros(d + 1), jac=True, method="L-BFGS-B", bounds=bounds,
                       options={"maxiter": self.max_iter})
        self.coef_ = res.x[:-1].reshape(1, -1)
        self.intercept_ = np.array([res.x[-1]])
        self.n_iter_ = np.array([res.nit])
        return self

    def decision_function(self, X):
        return np.asarray(X, dtype=float) @ self.coef_[0] + self.intercept_[0]

    def predict_proba(self, X):
        p = 1 / (1 + np.exp(-self.decision_function(X)))
        return np.column_stack([1 - p, p])

    def predict(self, X):
        return self.classes_[(self.predict_proba(X)[:, 1] >= 0.5).astype(int)]


class MonotoneTreeClassifier(ClassifierMixin, BaseEstimator):
    """Enveloppe Random Forest / XGBoost : applique les contraintes une fois le nombre de colonnes connu."""

    def __init__(self, base=None, leading_constraints: tuple[int, ...] = ()):
        self.base = base
        self.leading_constraints = leading_constraints

    def fit(self, X, y, sample_weight=None):
        cst = full_constraints(tuple(self.leading_constraints), np.asarray(X).shape[1])
        est = clone(self.base)
        if isinstance(est, XGBClassifier):
            est.set_params(monotone_constraints=tuple(cst))
        elif isinstance(est, RandomForestClassifier):
            est.set_params(monotonic_cst=cst)
        else:
            raise TypeError(f"Contraintes de monotonie non prises en charge pour {type(est).__name__}")
        est.fit(X, y, sample_weight=sample_weight)
        self.estimator_ = est
        self.classes_ = est.classes_
        return self

    def predict_proba(self, X):
        return self.estimator_.predict_proba(X)

    def predict(self, X):
        return self.estimator_.predict(X)
