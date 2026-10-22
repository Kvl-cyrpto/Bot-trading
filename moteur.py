import json, os, time, urllib.request

PAIR = "BTC-EUR"
GRANULARITE = 900        # bougies de 15 minutes
FRAIS = 0.005            # 0,5 % par ordre (achat ou vente)
MAX_BARRES = 96          # sortie forcee apres 24 h


def bougies():
    url = f"https://api.exchange.coinbase.com/products/{PAIR}/candles?granularity={GRANULARITE}"
    req = urllib.request.Request(url, headers={"User-Agent": "bot-trading"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    data.sort(key=lambda b: b[0])
    return [{"t": int(b[0]), "l": float(b[1]), "h": float(b[2]),
             "o": float(b[3]), "c": float(b[4])} for b in data]


def charger(fichier):
    if os.path.exists(fichier):
        with open(fichier, encoding="utf-8") as f:
            return json.load(f)
    return {"eur": 1000.0, "pos": None, "qty": 0.0, "capital": 0.0,
            "mise": 0.0, "entry": 0.0, "sl": 0.0, "tp": 0.0, "bars": 0,
            "bloque": None, "last_t": None, "pic": 1000.0,
            "baisse_max_pct": 0.0, "nb_trades": 0, "nb_gagnants": 0,
            "trades": []}


def ouvrir(s, sens, p, sl, tp):
    s["mise"] = s["eur"]
    s["capital"] = s["eur"] * (1 - FRAIS)
    s["eur"] = 0.0
    s["qty"] = s["capital"] / p
    s["pos"], s["entry"], s["sl"], s["tp"], s["bars"] = sens, p, sl, tp, 0
    s["trades"].append(f"{sens.upper()} ouvert a {p:.0f}")


def fermer(s, p, raison):
    d = 1 if s["pos"] == "long" else -1
    val = s["capital"] + s["qty"] * (p - s["entry"]) * d
    val -= FRAIS * s["qty"] * p
    res = (val / s["mise"] - 1) * 100
    s["trades"].append(f"{s['pos'].upper()} ferme ({raison}) a {p:.0f} : {res:+.1f}%")
    s["nb_trades"] += 1
    if res > 0:
        s["nb_gagnants"] += 1
    s["eur"] = val
    s["pos"], s["qty"], s["capital"] = None, 0.0, 0.0


def valeur(s, p):
    if not s["pos"]:
        return s["eur"]
    d = 1 if s["pos"] == "long" else -1
    return s["capital"] + s["qty"] * (p - s["entry"]) * d


def lancer(fichier, decide, fermees, prix_actuel):
    s = charger(fichier)
    if s["last_t"] is None:
        nouvelles = [fermees[-1]]
    else:
        nouvelles = [b for b in fermees if b["t"] > s["last_t"]]
    for b in nouvelles:
        idx = fermees.index(b)
        h = fermees[max(0, idx - 120): idx + 1]
        if s["pos"]:
            s["bars"] += 1
            sens = s["pos"]
            sortie = None
            if sens == "long":
                if b["o"] <= s["sl"]:
                    sortie = (b["o"], "STOP")
                elif b["l"] <= s["sl"]:
                    sortie = (s["sl"], "STOP")
                elif b["h"] >= s["tp"]:
                    sortie = (s["tp"], "OBJECTIF")
            else:
                if b["o"] >= s["sl"]:
                    sortie = (b["o"], "STOP")
                elif b["h"] >= s["sl"]:
                    sortie = (s["sl"], "STOP")
                elif b["l"] <= s["tp"]:
                    sortie = (s["tp"], "OBJECTIF")
            if sortie:
                fermer(s, sortie[0], sortie[1])
                s["bloque"] = sens
            elif s["bars"] >= MAX_BARRES:
                fermer(s, b["c"], "TEMPS")
        sortie_sig, entree = decide(h, s["pos"])
        if s["pos"] and sortie_sig:
            fermer(s, b["c"], "SIGNAL")
        if s["bloque"] and (entree is None or entree[0] != s["bloque"]):
            s["bloque"] = None
        if not s["pos"] and entree and entree[0] != s["bloque"]:
            ouvrir(s, entree[0], b["c"], entree[1], entree[2])
        v = valeur(s, b["c"])
        s["pic"] = max(s["pic"], v)
        s["baisse_max_pct"] = min(s["baisse_max_pct"], round((v / s["pic"] - 1) * 100, 2))
    s["last_t"] = fermees[-1]["t"]
    s["position"] = s["pos"] or "aucune"
    s["dernier_prix"] = round(prix_actuel, 2)
    s["valeur_totale"] = round(valeur(s, prix_actuel), 2)
    s["trades"] = s["trades"][-40:]
    with open(fichier, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1, ensure_ascii=False)
    print(fichier, s["valeur_totale"], s["position"])


def executer(fichier, decide):
    tout = bougies()
    fermees = [b for b in tout if b["t"] + GRANULARITE <= time.time()]
    if len(fermees) < 80:
        print("Pas assez de donnees")
        return
    lancer(fichier, decide, fermees, tout[-1]["c"])
