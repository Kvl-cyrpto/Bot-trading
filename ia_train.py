import json
from datetime import datetime, timezone
import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
import ia_test as ia

H = 72                 # l'IA predit le mouvement des 72 prochaines heures
SEUIL = 0.02           # on ne garde que les 2 % de signaux les plus forts
JOURS = 2200           # environ 6 ans d'historique
PAIRES = ["BTC-EUR", "ETH-EUR", "SOL-EUR", "XRP-EUR", "LTC-EUR", "ADA-EUR", "DOGE-EUR",
          "LINK-EUR", "DOT-EUR", "AVAX-EUR", "ATOM-EUR", "XLM-EUR", "BCH-EUR", "UNI-EUR"]


def nouveau_modele():
    return HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=150,
                                         l2_regularization=1.0, min_samples_leaf=200,
                                         random_state=0)


def main():
    ia.H = H
    morceaux, utilisees = [], []
    for p in PAIRES:
        b = ia.telecharger(p, JOURS)
        print(p, len(b), "bougies")
        if len(b) > 3000:
            morceaux.append(ia.caracteristiques(b, p))
            utilisees.append(p)
    if not morceaux:
        print("Pas de donnees")
        return
    data = pd.concat(morceaux, ignore_index=True)
    tmax = int(data["t"].max())

    # le seuil vient des predictions des 3 derniers mois, faites sans voir le futur
    preds = []
    for j in range(3):
        debut = tmax - (3 - j) * 30 * 86400
        fin = debut + 30 * 86400
        train = data[data["t"] <= debut - H * 3600]
        test = data[(data["t"] > debut) & (data["t"] <= fin)]
        if len(train) > 5000 and len(test):
            m = nouveau_modele()
            m.fit(train[ia.X_COLS], train["fwd"].clip(-0.3, 0.3))
            preds.append(m.predict(test[ia.X_COLS]))
    if not preds:
        print("Pas assez de donnees pour le seuil")
        return
    cutoff = float(np.quantile(np.concatenate(preds), 1 - SEUIL))

    final = nouveau_modele()
    final.fit(data[ia.X_COLS], data["fwd"].clip(-0.3, 0.3))
    maintenant = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")
    joblib.dump({"modele": final, "cutoff": cutoff, "colonnes": ia.X_COLS, "paires": utilisees,
                 "horizon": H, "date": maintenant, "sklearn": sklearn.__version__},
                "modele_ia.joblib", compress=3)
    info = {"date": maintenant, "lignes": int(len(data)), "paires": utilisees,
            "seuil_signal": cutoff, "horizon_h": H, "sklearn": sklearn.__version__}
    with open("modele_ia_info.json", "w", encoding="utf-8") as f:
        json.dump(info, f, indent=1, ensure_ascii=False)
    print(info)


if __name__ == "__main__":
    main()
