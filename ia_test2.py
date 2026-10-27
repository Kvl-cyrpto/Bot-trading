import numpy as np
import pandas as pd
from datetime import datetime, timezone
from sklearn.ensemble import HistGradientBoostingRegressor
import ia_test as ia

HORIZONS = [24, 48, 72]      # on teste des mouvements sur 24 h, 48 h et 72 h
SEUILS = [0.05, 0.02]        # on ne garde que les 5 % ou 2 % de signaux les plus forts
RESERVE_JOURS = 180          # les 6 derniers mois sont gardes en reserve
FRAIS = 0.01                 # 1 % aller-retour (0,5 % a l'achat + 0,5 % a la vente)


def predire(data, h):
    t0, fin = data["t"].min(), data["t"].max()
    start = t0 + ia.TRAIN_MIN_JOURS * 86400
    out = []
    while start < fin:
        stop = start + ia.BLOC_JOURS * 86400
        train = data[data["t"] <= start - h * 3600]   # uniquement ce qui est deja connu
        test = data[(data["t"] >= start) & (data["t"] < stop)]
        if len(train) > 5000 and len(test):
            m = HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=150,
                                              l2_regularization=1.0, min_samples_leaf=200,
                                              random_state=0)
            m.fit(train[ia.X_COLS], train["fwd"].clip(-0.3, 0.3))
            test = test.copy()
            test["pred"] = m.predict(test[ia.X_COLS])
            out.append(test)
        start = stop
    return pd.concat(out, ignore_index=True)


def espaces(g, h):
    # un seul trade a la fois par crypto : on enleve les signaux qui se chevauchent
    g = g.sort_values(["paire", "t"])
    garder, dernier = [], {}
    for idx, p, t in zip(g.index, g["paire"], g["t"]):
        if p not in dernier or t - dernier[p] >= h * 3600:
            garder.append(idx)
            dernier[p] = t
    return g.loc[garder]


def pct(x):
    return f"{x * 100:+.2f} %"


def main():
    brut = {}
    for p in ia.PAIRES:
        b = ia.telecharger(p, ia.JOURS)
        print(p, len(b), "bougies")
        if len(b) > 3000:
            brut[p] = b
    if not brut:
        print("Pas de donnees")
        return

    predictions = {}
    for h in HORIZONS:
        ia.H = h
        data = pd.concat([ia.caracteristiques(b, p) for p, b in brut.items()], ignore_index=True)
        predictions[h] = predire(data, h)
        print("horizon", h, "h termine")

    tmax = max(P["t"].max() for P in predictions.values())
    coupure = tmax - RESERVE_JOURS * 86400
    fin_dev = coupure - 72 * 3600          # marge pour ne pas melanger dev et reserve
    tmin = min(P["t"].min() for P in predictions.values())
    bornes = np.linspace(tmin, fin_dev, 5)

    configs = []
    for h in HORIZONS:
        P = predictions[h]
        dev = P[P["t"] < fin_dev]
        res = P[P["t"] >= coupure]
        for seuil in SEUILS:
            for sens in (1, -1):
                if sens == 1:
                    cut = dev["pred"].quantile(1 - seuil)
                    sel_dev = dev[dev["pred"] >= cut]
                    sel_res = res[res["pred"] >= cut]
                else:
                    cut = dev["pred"].quantile(seuil)
                    sel_dev = dev[dev["pred"] <= cut]
                    sel_res = res[res["pred"] <= cut]
                g = espaces(sel_dev, h)
                gain = sens * g["fwd"]
                positives = 0
                for k in range(4):
                    m = (g["t"] >= bornes[k]) & (g["t"] < bornes[k + 1])
                    if m.sum() and (gain[m].mean() - FRAIS) > 0:
                        positives += 1
                nom = f"{'Achat' if sens == 1 else 'Vente'} top {int(seuil * 100)} % / {h} h"
                configs.append({"nom": nom, "n": len(g), "brut": gain.mean() if len(g) else 0.0,
                                "pos": positives, "res": sel_res, "h": h, "sens": sens})

    L = ["# IA version 2 : achat ET vente, 3 horizons, 6 mois en reserve\n"]
    d0 = datetime.fromtimestamp(int(tmin), timezone.utc).strftime("%d/%m/%Y")
    d1 = datetime.fromtimestamp(int(fin_dev), timezone.utc).strftime("%d/%m/%Y")
    d2 = datetime.fromtimestamp(int(tmax), timezone.utc).strftime("%d/%m/%Y")
    dc = datetime.fromtimestamp(int(coupure), timezone.utc).strftime("%d/%m/%Y")
    L.append(f"Phase d'essais : {d0} au {d1}. Reserve (regardee une seule fois) : {dc} au {d2}.")
    L.append("Un trade a la fois par crypto (les signaux qui se chevauchent sont retires).\n")
    L.append("## Phase d'essais : les 12 configurations\n")
    L.append("| Config | Trades | Brut | Net 1 % | Net 0,5 % | Periodes + |")
    L.append("|---|---|---|---|---|---|")
    for c in configs:
        L.append(f"| {c['nom']} | {c['n']} | {pct(c['brut'])} | {pct(c['brut'] - FRAIS)} | {pct(c['brut'] - FRAIS / 2)} | {c['pos']}/4 |")

    bons = [c for c in configs if c["n"] >= 30 and c["brut"] - FRAIS > 0 and c["pos"] >= 3]
    L.append("\n## Verdict\n")
    if not bons:
        L.append("Aucune configuration ne gagne apres frais de 1 % de facon stable (au moins 3 periodes sur 4). La reserve n'a donc pas ete ouverte : il n'y a rien a confirmer.")
    else:
        meilleur = max(bons, key=lambda c: c["brut"])
        g = espaces(meilleur["res"], meilleur["h"])
        gain = meilleur["sens"] * g["fwd"]
        L.append(f"Meilleure configuration de la phase d'essais : {meilleur['nom']}.")
        L.append("Sur 12 essais, une peut sortir par chance : c'est la reserve qui tranche.\n")
        if len(g) == 0:
            L.append("Aucun signal dans la reserve.")
        else:
            L.append("| Reserve (6 derniers mois) | Trades | Brut | Net 1 % | Net 0,5 % |")
            L.append("|---|---|---|---|---|")
            L.append(f"| {meilleur['nom']} | {len(g)} | {pct(gain.mean())} | {pct(gain.mean() - FRAIS)} | {pct(gain.mean() - FRAIS / 2)} |")
            if gain.mean() - FRAIS > 0 and len(g) >= 15:
                L.append("\nLa configuration tient aussi sur la reserve. C'est un vrai candidat pour une simulation en direct.")
            else:
                L.append("\nLa configuration ne tient pas sur la reserve (ou trop peu de trades pour conclure). Ce n'est pas un avantage fiable.")
    texte = "\n".join(L) + "\n"
    with open("ia2_resultats.md", "w", encoding="utf-8") as f:
        f.write(texte)
    print(texte)


if __name__ == "__main__":
    main()
