import json, os, time
import joblib
import pandas as pd
import ia_test as ia

ETAT = "state_ia.json"
MODELE = "modele_ia.joblib"
CAPITAL = 1000.0
PART = 0.10          # 10 % du capital par trade
MAX_POS = 5          # 5 positions ouvertes au maximum
FRAIS = 0.005        # 0,5 % par ordre
DUREE = 72           # on garde chaque position 72 h
STOP_CATA = 0.25     # filet de securite : sortie si -25 % (non teste dans le backtest)


def charger():
    if os.path.exists(ETAT):
        with open(ETAT, encoding="utf-8") as f:
            return json.load(f)
    return {"cash": CAPITAL, "positions": {}, "trades": [], "nb_trades": 0,
            "nb_gagnants": 0, "last_t": None, "pic": CAPITAL, "baisse_max_pct": 0.0,
            "btc_depart": None}


def bougies_recentes(paire, cur):
    url = (f"https://api.exchange.coinbase.com/products/{paire}/candles?granularity={ia.GRAN}"
           f"&start={ia.iso(cur - 299 * ia.GRAN)}&end={ia.iso(cur)}")
    data = ia.appel(url)
    if not data:
        return []
    data.sort(key=lambda b: b[0])
    return [{"t": int(b[0]), "l": float(b[1]), "h": float(b[2]), "o": float(b[3]),
             "c": float(b[4]), "v": float(b[5])} for b in data]


def derniere_ligne(fermees, paire):
    # on ajoute des bougies factices apres la derniere pour reutiliser exactement
    # le meme calcul que pendant l'entrainement (elles ne changent rien au present)
    d = fermees[-1]
    pad = [{"t": d["t"] + (k + 1) * ia.GRAN, "l": d["c"], "h": d["c"], "o": d["c"],
            "c": d["c"], "v": 0.0} for k in range(ia.H)]
    f = ia.caracteristiques(fermees + pad, paire)
    return f[f["t"] == d["t"]]


def valeur(s):
    return s["cash"] + sum(p["qty"] * p["dernier_prix"] for p in s["positions"].values())


def fermer(s, paire, prix, raison):
    p = s["positions"].pop(paire)
    produit = p["qty"] * prix * (1 - FRAIS)
    s["cash"] += produit
    res = (produit / p["mise"] - 1) * 100
    s["nb_trades"] += 1
    if res > 0:
        s["nb_gagnants"] += 1
    s["trades"].append(f"{paire} ferme ({raison}) a {prix:.4g} : {res:+.1f}%")


def main():
    try:
        m = joblib.load(MODELE)
    except Exception as e:
        print("Modele indisponible :", e)
        return
    modele, cutoff, cols = m["modele"], m["cutoff"], m["colonnes"]
    ia.H = m["horizon"]
    s = charger()
    maintenant = int(time.time())
    cur = maintenant // ia.GRAN * ia.GRAN
    nouvelle_heure = s["last_t"] is None or (cur - ia.GRAN) > s["last_t"]

    prix, signaux = {}, []
    for p in m["paires"]:
        try:
            bs = bougies_recentes(p, cur)
        except Exception as e:
            print(p, "erreur :", e)
            continue
        if len(bs) < 220:
            continue
        prix[p] = bs[-1]["c"]
        fermees = [b for b in bs if b["t"] < cur]
        if nouvelle_heure and fermees and fermees[-1]["t"] == cur - ia.GRAN:
            ligne = derniere_ligne(fermees, p)
            if len(ligne):
                pred = float(modele.predict(ligne[cols])[0])
                if pred >= cutoff:
                    signaux.append((pred, p))
    if not prix:
        print("Aucun prix recupere")
        return
    for p, pos in s["positions"].items():
        if p in prix:
            pos["dernier_prix"] = prix[p]
    if s["btc_depart"] is None and "BTC-EUR" in prix:
        s["btc_depart"] = prix["BTC-EUR"]

    # sorties : fin des 72 h, ou filet de securite
    for p in list(s["positions"]):
        pos = s["positions"][p]
        if maintenant - pos["t_open"] >= DUREE * 3600:
            fermer(s, p, pos["dernier_prix"], "72h")
        elif pos["dernier_prix"] <= pos["entry"] * (1 - STOP_CATA):
            fermer(s, p, pos["dernier_prix"], "STOP")

    # entrees : les signaux les plus forts d'abord
    for pred, p in sorted(signaux, reverse=True):
        if p in s["positions"] or len(s["positions"]) >= MAX_POS:
            continue
        mise = PART * valeur(s)
        if mise > s["cash"]:
            continue
        s["cash"] -= mise
        s["positions"][p] = {"qty": mise * (1 - FRAIS) / prix[p], "entry": prix[p],
                             "t_open": maintenant, "mise": mise, "dernier_prix": prix[p]}
        s["trades"].append(f"{p} ouvert a {prix[p]:.4g}")

    if nouvelle_heure:
        s["last_t"] = cur - ia.GRAN
    v = valeur(s)
    s["pic"] = max(s["pic"], v)
    s["baisse_max_pct"] = min(s["baisse_max_pct"], round((v / s["pic"] - 1) * 100, 2))
    s["valeur_totale"] = round(v, 2)
    s["positions_ouvertes"] = sorted(s["positions"])
    s["seuil_signal"] = round(cutoff, 5)
    s["modele_date"] = m["date"]
    if s["btc_depart"] and "BTC-EUR" in prix:
        s["bitcoin_depuis_depart_pct"] = round((prix["BTC-EUR"] / s["btc_depart"] - 1) * 100, 2)
    s["trades"] = s["trades"][-40:]
    with open(ETAT, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=1, ensure_ascii=False)
    print(s["valeur_totale"], s["positions_ouvertes"], "signaux:", len(signaux))


if __name__ == "__main__":
    main()
