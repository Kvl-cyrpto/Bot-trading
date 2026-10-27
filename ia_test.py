import json, time, urllib.request, urllib.error
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

PAIRES = ["BTC-EUR", "ETH-EUR", "SOL-EUR", "XRP-EUR", "LTC-EUR", "ADA-EUR", "DOGE-EUR", "LINK-EUR"]
GRAN = 3600             # bougies d'1 heure
JOURS = 1100            # environ 3 ans d'historique
H = 24                  # on predit le mouvement des 24 prochaines heures
TRAIN_MIN_JOURS = 365   # au moins 1 an d'entrainement avant le premier test
BLOC_JOURS = 30         # on re-entraine l'IA tous les 30 jours
X_COLS = ["r1", "r4", "r12", "r24", "r72", "vol24", "vol72", "rsi",
          "sma24", "sma72", "sma168", "range24", "volrel"]


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def appel(url):
    derniere = None
    for essai in range(6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "bot-trading"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            derniere = e
            time.sleep(1 + essai)
        except Exception as e:
            derniere = e
            time.sleep(1 + essai)
    raise RuntimeError(f"telechargement impossible : {derniere}")


def telecharger(paire, jours):
    fin = int(time.time()) // GRAN * GRAN
    limite = fin - jours * 86400
    vus = {}
    cur = fin
    vides = 0
    while cur > limite:
        d = cur - 300 * GRAN
        url = (f"https://api.exchange.coinbase.com/products/{paire}/candles"
               f"?granularity={GRAN}&start={iso(d)}&end={iso(cur - GRAN)}")
        data = appel(url)
        if not data:
            vides += 1
            if vides >= 3:
                break
        else:
            vides = 0
            for b in data:
                vus[int(b[0])] = b
        cur = d
        time.sleep(0.2)
    return [{"t": t, "l": float(vus[t][1]), "h": float(vus[t][2]), "o": float(vus[t][3]),
             "c": float(vus[t][4]), "v": float(vus[t][5])} for t in sorted(vus)]


def rsi(c, n=14):
    d = c.diff()
    g = d.clip(lower=0).rolling(n).mean()
    p = (-d.clip(upper=0)).rolling(n).mean()
    return (100 - 100 / (1 + g / p.replace(0, np.nan))).fillna(50.0)


def caracteristiques(bougies, paire):
    df = pd.DataFrame(bougies).set_index("t")
    grille = np.arange(df.index.min(), df.index.max() + 1, GRAN)
    df = df.reindex(grille)
    for col in ("c", "o", "h", "l"):
        df[col] = df[col].ffill()
    df["v"] = df["v"].fillna(0.0)
    c = df["c"]
    r = c.pct_change()
    f = pd.DataFrame(index=df.index)
    for k in (1, 4, 12, 24, 72):
        f[f"r{k}"] = c / c.shift(k) - 1
    f["vol24"] = r.rolling(24).std()
    f["vol72"] = r.rolling(72).std()
    f["rsi"] = rsi(c)
    for k in (24, 72, 168):
        f[f"sma{k}"] = c / c.rolling(k).mean() - 1
    f["range24"] = (df["h"].rolling(24).max() - df["l"].rolling(24).min()) / c
    f["volrel"] = df["v"].rolling(24).sum() / df["v"].rolling(168).sum().replace(0, np.nan) * 7
    f["fwd"] = c.shift(-H) / c - 1
    f["paire"] = paire
    f["t"] = f.index
    return f.replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)


def pct(x):
    return f"{x * 100:+.2f} %"


def main():
    morceaux = []
    for p in PAIRES:
        b = telecharger(p, JOURS)
        print(p, len(b), "bougies")
        if len(b) > 3000:
            morceaux.append(caracteristiques(b, p))
    if not morceaux:
        print("Pas de donnees")
        return
    data = pd.concat(morceaux, ignore_index=True)
    t0, fin = data["t"].min(), data["t"].max()
    start = t0 + TRAIN_MIN_JOURS * 86400
    preds = []
    while start < fin:
        stop = start + BLOC_JOURS * 86400
        train = data[data["t"] <= start - H * 3600]   # on n'utilise que ce qui est connu
        test = data[(data["t"] >= start) & (data["t"] < stop)]
        if len(train) > 5000 and len(test):
            m = HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=150,
                                              l2_regularization=1.0, min_samples_leaf=200,
                                              random_state=0)
            m.fit(train[X_COLS], train["fwd"].clip(-0.3, 0.3))
            test = test.copy()
            test["pred"] = m.predict(test[X_COLS])
            preds.append(test)
        start = stop
    P = pd.concat(preds, ignore_index=True)
    ic = float(np.corrcoef(P["pred"], P["fwd"])[0, 1])
    q05, q20, q80, q95 = P["pred"].quantile([0.05, 0.2, 0.8, 0.95])
    d0 = datetime.fromtimestamp(int(P["t"].min()), timezone.utc).strftime("%d/%m/%Y")
    d1 = datetime.fromtimestamp(int(P["t"].max()), timezone.utc).strftime("%d/%m/%Y")
    paires_ok = ", ".join(sorted(P["paire"].unique()))

    groupes = [("Bas 5 % (signal de vente)", P[P["pred"] <= q05], -1),
               ("Bas 20 %", P[P["pred"] <= q20], -1),
               ("Milieu 60 %", P[(P["pred"] > q20) & (P["pred"] < q80)], 0),
               ("Haut 20 %", P[P["pred"] >= q80], 1),
               ("Haut 5 % (signal d'achat)", P[P["pred"] >= q95], 1)]

    L = ["# Test de l'IA (hors echantillon)\n"]
    L.append(f"Periode testee : {d0} au {d1}. Paires : {paires_ok}.")
    L.append(f"Chaque jour, l'IA ne voit que le passe et predit le mouvement des {H} prochaines heures.\n")
    L.append(f"Correlation entre prediction et realite : {ic:+.3f} (0 = aucune, 0,05 = faible, 0,1 = bonne)\n")
    L.append(f"Mouvement moyen sur {H} h, tous moments confondus : {pct(P['fwd'].mean())}\n")
    L.append("## Que gagne-t-on en suivant les signaux ? (moyenne par signal)\n")
    L.append("| Groupe | Signaux | Gain brut | Net frais 1 % | Net frais 0,5 % |")
    L.append("|---|---|---|---|---|")
    for nom, g, sens in groupes:
        if len(g) == 0:
            continue
        if sens == 0:
            L.append(f"| {nom} | {len(g)} | {pct(g['fwd'].mean())} (mouvement) | - | - |")
        else:
            brut = sens * g["fwd"].mean()
            L.append(f"| {nom} | {len(g)} | {pct(brut)} | {pct(brut - 0.01)} | {pct(brut - 0.005)} |")

    hauts = P[P["pred"] >= q95]
    bas = P[P["pred"] <= q05]
    net = pd.concat([hauts["fwd"] - 0.01, -bas["fwd"] - 0.01])
    L.append("\n## Stabilite dans le temps (signaux d'achat 5 % + de vente 5 %, frais 1 %)\n")
    L.append("| Periode | Signaux | Net moyen par signal |")
    L.append("|---|---|---|")
    bornes = np.linspace(P["t"].min(), P["t"].max() + 1, 5)
    positives = 0
    for k in range(4):
        a, z = bornes[k], bornes[k + 1]
        h_ = hauts[(hauts["t"] >= a) & (hauts["t"] < z)]
        b_ = bas[(bas["t"] >= a) & (bas["t"] < z)]
        v = pd.concat([h_["fwd"] - 0.01, -b_["fwd"] - 0.01])
        if len(v):
            positives += int(v.mean() > 0)
            L.append(f"| P{k + 1} | {len(v)} | {pct(v.mean())} |")
        else:
            L.append(f"| P{k + 1} | 0 | - |")
    L.append("\nAttention : les signaux voisins se chevauchent (deux signaux a 1 h d'ecart couvrent presque le meme mouvement), donc le nombre de vrais trades independants est bien plus petit que la colonne Signaux.\n")
    if net.mean() > 0 and positives >= 3:
        verdict = "Il y a un signal qui survit aux frais de 1 % sur au moins 3 periodes sur 4. A confirmer avec un test plus strict avant toute idee de reel."
    else:
        verdict = "Pas d'avantage net apres frais de 1 % de facon stable. Dans cet etat, l'IA ne vaut pas la peine d'etre branchee."
    L.append(f"## Verdict automatique\n\n{verdict}\n")
    texte = "\n".join(L)
    with open("ia_resultats.md", "w", encoding="utf-8") as f:
        f.write(texte)
    print(texte)


if __name__ == "__main__":
    main()
