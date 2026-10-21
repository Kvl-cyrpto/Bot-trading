import json, os, urllib.request

PAIR = "BTC-EUR"
STATE = "state.json"

def prix():
    url = f"https://api.coinbase.com/v2/prices/{PAIR}/spot"
    with urllib.request.urlopen(url, timeout=20) as r:
        return float(json.load(r)["data"]["amount"])

def charger():
    if os.path.exists(STATE):
        with open(STATE) as f:
            return json.load(f)
    return {"eur": 1000.0, "btc": 0.0, "prix": [], "trades": []}

def main():
    s = charger()
    p = prix()
    s["prix"] = (s["prix"] + [p])[-60:]
    h = s["prix"]
    if len(h) >= 20:
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
    s["valeur_totale"] = round(s["eur"] + s["btc"] * p, 2)
    s["trades"] = s["trades"][-50:]
    with open(STATE, "w") as f:
        json.dump(s, f, indent=1)
    print(s["valeur_totale"])

main()
