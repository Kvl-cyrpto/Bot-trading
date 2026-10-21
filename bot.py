import json, os, urllib.request

PAIR = "BTC-EUR"
STATE = "state.json"
GRANULARITE = 900   # bougies de 15 minutes
STOP_LOSS = 3.0     # vente si perte de 3 %
TAKE_PROFIT = 5.0   # vente si gain de 5 %

def prix_historiques():
    url = f"https://api.exchange.coinbase.com/products/{PAIR}/candles?granularity={GRANULARITE}"
    req = urllib.request.Request(url, headers={"User-Agent": "bot-trading"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.load(r)
    data.sort(key=lambda b: b[0])
    return [float(b[4]) for b in data]

def charger():
    if os.path.exists(STATE):
        with open(STATE) as f:
            return json.load(f)
    return {"eur": 1000.0, "btc": 0.0, "trades": []}

def acheter(s, p):
    s["btc"] = s["eur"] * 0.995 / p
    s["eur"] = 0.0
    s["prix_achat"] = p
    s["trades"].append(f"ACHAT a {p:.0f}")

def vendre(s, p, raison):
    s["eur"] = s["btc"] * p * 0.995
    s["btc"] = 0.0
    s["prix_achat"] = None
    s["trades"].append(f"{raison} a {p:.0f}")

def main():
    s = charger()
    s.pop("prix", None)
    h = prix_historiques()
    if len(h) < 20:
        print("Pas assez de donnees")
        return
    p = h[-1]
    court = sum(h[-5:]) / 5
    long = sum(h[-20:]) / 20

    # reprise de la position deja ouverte (ancienne version du bot)
    if s["btc"] > 0 and not s.get("prix_achat"):
        try:
            s["prix_achat"] = float(s["trades"][-1].split()[-1])
        except Exception:
            s["prix_achat"] = p

    if s["btc"] > 0:
        variation = (p / s["prix_achat"] - 1) * 100
        if variation <= -STOP_LOSS:
            vendre(s, p, "VENTE STOP LOSS")
            s["attente_signal"] = True
        elif variation >= TAKE_PROFIT:
            vendre(s, p, "VENTE TAKE PROFIT")
            s["attente_signal"] = True
        elif court < long:
            vendre(s, p, "VENTE")
            s["attente_signal"] = False
    else:
        if court < long:
            s["attente_signal"] = False
        elif court > long and not s.get("attente_signal"):
            acheter(s, p)

    s["dernier_prix"] = round(p, 2)
    s["valeur_totale"] = round(s["eur"] + s["btc"] * p, 2)
    s["trades"] = s["trades"][-50:]
    with open(STATE, "w") as f:
        json.dump(s, f, indent=1)
    print(s["valeur_totale"])

main()
