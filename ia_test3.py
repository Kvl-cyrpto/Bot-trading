import numpy as np
import pandas as pd
from datetime import datetime, timezone
from sklearn.ensemble import HistGradientBoostingRegressor
import ia_test as ia
from ia_test2 import espaces, pct

# Configuration FIGEE (on ne change rien) : achat, 2 % des signaux les plus forts, 72 h
H = 72
SEUIL = 0.02
JOURS = 2200   # environ 6 ans d'historique
PAIRES = ["BTC-EUR", "ETH-EUR", "SOL-EUR", "XRP-EUR", "LTC-EUR", "ADA-EUR", "DOGE-EUR",
          "LINK-EUR", "DOT-EUR", "AVAX-EUR", "ATOM-EUR", "XLM-EUR", "BCH-EUR", "UNI-EUR"]
CHOIX = datetime(2024, 10, 29, tzinfo=timezone.utc)   # avant cette date : jamais testee


def blocs(data):
    t0, fin = data["t"].min(), data["t"].max()
    start = t0 + ia.TRAIN_MIN_JOURS * 86400
    out = []
    while start < fin:
        stop = start + ia.BLOC_JOURS * 86400
        train = data[data["t"] <= start - H * 3600]
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
    return out


def stats(g):
    n = len(g)
    if n == 0:
        return None
    return {"n": n, "brut": g["fwd"].mean(), "med": g["fwd"].median(),
            "gagn": (g["fwd"] - 0.01 > 0).mean(), "pire": g["fwd"].min()}


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
    bl = blocs(data)
    if len(bl) < 6:
        print("Pas assez de blocs")
        return

    # le seuil de chaque mois vient uniquement des 3 mois precedents (rien du futur)
    sel, tous = [], pd.concat(bl[3:], ignore_index=True)
    for i in range(3, len(bl)):
        cut = pd.concat(bl[i - 3:i])["pred"].quantile(1 - SEUIL)
        sel.append(bl[i][bl[i]["pred"] >= cut])
    S = espaces(pd.concat(sel), H)

    cut_ts = int(CHOIX.timestamp())
    def etiquette(t):
        a = datetime.fromtimestamp(int(t), timezone.utc).year
        return f"{a} ({'nouveau' if t < cut_ts else 'deja vu'})"
    S = S.assign(per=S["t"].map(etiquette))
    tous = tous.assign(per=tous["t"].map(etiquette))

    d0 = datetime.fromtimestamp(int(tous["t"].min()), timezone.utc).strftime("%d/%m/%Y")
    d1 = datetime.fromtimestamp(int(tous["t"].max()), timezone.utc).strftime("%d/%m/%Y")
    L = ["# Test sur donnees jamais vues : Achat, top 2 %, 72 h\n"]
    L.append(f"Periode : {d0} au {d1}. Cryptos : {', '.join(utilisees)}.")
    L.append("Configuration figee, rien n'a ete regle sur ces donnees. Un trade a la fois par crypto.\n")
    L.append("| Periode | Trades | Brut | Net 1 % | Net 0,5 % | Gagnants | Marche moyen |")
    L.append("|---|---|---|---|---|---|---|")
    ordre = sorted(S["per"].unique(), key=lambda x: (x.split()[0], x))
    annees_ok = 0
    annees_tot = 0
    for per in ordre:
        g = S[S["per"] == per]
        s = stats(g)
        mm = tous[tous["per"] == per]["fwd"].mean()
        L.append(f"| {per} | {s['n']} | {pct(s['brut'])} | {pct(s['brut'] - 0.01)} | {pct(s['brut'] - 0.005)} | {s['gagn'] * 100:.0f} % | {pct(mm)} |")
        if "nouveau" in per and s["n"] >= 10:
            annees_tot += 1
            annees_ok += int(s["brut"] - 0.01 > 0)

    nouveau = S[S["t"] < cut_ts]
    vu = S[S["t"] >= cut_ts]
    L.append("\n## Totaux\n")
    L.append("| Groupe | Trades | Brut | Net 1 % | Median brut | Pire trade |")
    L.append("|---|---|---|---|---|---|")
    for nom, g in [("Nouveau (avant 29/10/2024)", nouveau), ("Deja vu (apres)", vu)]:
        s = stats(g)
        if s:
            L.append(f"| {nom} | {s['n']} | {pct(s['brut'])} | {pct(s['brut'] - 0.01)} | {pct(s['med'])} | {pct(s['pire'])} |")

    sn = stats(nouveau)
    L.append("\n## Verdict (regle fixee a l'avance)\n")
    L.append("Il faut, sur la partie nouvelle : au moins 60 trades, un net positif apres 1 % de frais, et un net positif sur au moins les deux tiers des annees ayant 10 trades ou plus.\n")
    if not sn or sn["n"] < 60:
        L.append("Resultat : trop peu de trades sur la partie nouvelle pour conclure.")
    elif sn["brut"] - 0.01 > 0 and annees_tot > 0 and annees_ok >= (2 * annees_tot + 2) // 3:
        L.append(f"Resultat : la configuration tient sur des donnees jamais vues ({annees_ok}/{annees_tot} annees positives). C'est un candidat serieux pour la simulation en direct.")
    else:
        L.append(f"Resultat : la configuration ne tient pas sur des donnees jamais vues ({annees_ok}/{annees_tot} annees positives). Ce n'etait pas un vrai avantage.")
    L.append("\nLimites : la liste des cryptos est celle qui existe aujourd'hui, donc il manque celles qui ont disparu ou fini a zero. Cela avantage les signaux d'achat. Les resultats sont a prendre avec cette reserve.")
    texte = "\n".join(L) + "\n"
    with open("ia3_resultats.md", "w", encoding="utf-8") as f:
        f.write(texte)
    print(texte)


if __name__ == "__main__":
    main()
