import json, os, urllib.request

PAIR = "BTC-EUR"
STATE = "state.json"
GRANULARITE = 900  # bougies de 15 minutes

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

def main():
    s = charger()
    s.pop("prix", None)
    h = prix_historiques()
    if len(h) < 20:
        print("Pas assez de données")
        return
    p = h[-1]
    court = sum(h[-5:]) / 5
    long = sum(h[-20:]) / 20
    if court > long and s["eur"] > 0:
        s["btc"] = s["eur"] * 0.995 / p
        s["eur"] = 0.0
        s["trades"].append(f"ACHAT à {p:.0f}")
    elif court < long and s["btc"] > 0:
        s["eur"] = s["btc"] * p * 0.995
        s["btc"] = 0.0
        s["trades"].append(f"VENTE à {p:.0f}")
    s["dernier_prix"] = round(p, 2)
    s["valeur_totale"] = round(s["eur"] + s["btc"] * p, 2)
    s["trades"] = s["trades"][-50:]
    with open(STATE, "w") as f:
        json.dump(s, f, indent=1)
    print(s["valeur_totale"])

main()
