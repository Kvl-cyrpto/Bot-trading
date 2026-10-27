import json, time, urllib.request
from datetime import datetime, timezone
import moteur, bot_melange, bot_ict

PAIR = "BTC-EUR"
GRAN = 900            # bougies de 15 minutes
JOURS = 730           # 2 ans d'historique
DEBUT = 79
FRAIS_LISTE = [0.005, 0.0025, 0.001, 0.0]
SEGMENTS = 4


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def appel(url):
    derniere = None
    for essai in range(6):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "bot-trading"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            derniere = e
            time.sleep(1 + essai)
    raise RuntimeError(f"telechargement impossible : {derniere}")


def telecharger(jours):
    fin = int(time.time()) // GRAN * GRAN
    limite = fin - jours * 86400
    vus = {}
    cur = fin
    vides = 0
    n = 0
    while cur > limite:
        d = cur - 300 * GRAN
        url = (f"https://api.exchange.coinbase.com/products/{PAIR}/candles"
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
        n += 1
        if n % 50 == 0:
            print("telechargement...", len(vus), "bougies")
        time.sleep(0.2)
    return [{"t": t, "l": float(vus[t][1]), "h": float(vus[t][2]),
             "o": float(vus[t][3]), "c": float(vus[t][4])} for t in sorted(vus)]


# reproduction de l'ancien bot (achat seulement, stop 3 %, objectif 5 %)
def ancien(h, pos):
    cl = [b["c"] for b in h]
    p = cl[-1]
    haussier = sum(cl[-5:]) / 5 > sum(cl[-20:]) / 20
    sortie = pos == "long" and not haussier
    entree = ("long", p * 0.97, p * 1.05) if haussier else None
    return sortie, entree


STRATEGIES = [("Ancien (achat seul)", ancien),
              ("Melange", bot_melange.decide),
              ("ICT", bot_ict.decide)]


def simuler(bs, decide, frais):
    moteur.FRAIS = frais
    s = moteur.charger("__aucun__.json")
    vals = []
    for i in range(DEBUT, len(bs)):
        b = bs[i]
        h = bs[max(0, i - 120): i + 1]
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
                moteur.fermer(s, sortie[0], sortie[1])
                s["bloque"] = sens
            elif s["bars"] >= moteur.MAX_BARRES:
                moteur.fermer(s, b["c"], "TEMPS")
        sortie_sig, entree = decide(h, s["pos"])
        if s["pos"] and sortie_sig:
            moteur.fermer(s, b["c"], "SIGNAL")
        if s["bloque"] and (entree is None or entree[0] != s["bloque"]):
            s["bloque"] = None
        if not s["pos"] and entree and entree[0] != s["bloque"]:
            moteur.ouvrir(s, entree[0], b["c"], entree[1], entree[2])
        v = moteur.valeur(s, b["c"])
        s["pic"] = max(s["pic"], v)
        s["baisse_max_pct"] = min(s["baisse_max_pct"], (v / s["pic"] - 1) * 100)
        vals.append(v)
        s["trades"] = s["trades"][-5:]
    return s, vals


def pct(x):
    return f"{x:+.1f} %"


def main():
    bs = telecharger(JOURS)
    if len(bs) < 2000:
        print("Pas assez de donnees telechargees :", len(bs))
        return
    n = len(bs)
    d0 = datetime.fromtimestamp(bs[0]["t"], timezone.utc).strftime("%d/%m/%Y")
    d1 = datetime.fromtimestamp(bs[-1]["t"], timezone.utc).strftime("%d/%m/%Y")
    bornes = [DEBUT + (n - DEBUT) * k // SEGMENTS for k in range(SEGMENTS + 1)]

    def segs(vals):
        out = []
        for k in range(SEGMENTS):
            a = 1000.0 if k == 0 else vals[bornes[k] - 1 - DEBUT]
            z = vals[bornes[k + 1] - 1 - DEBUT]
            out.append((z / a - 1) * 100)
        return out

    garder = []
    for k in range(SEGMENTS):
        a = bs[bornes[k] - 1]["c"]
        z = bs[bornes[k + 1] - 1]["c"]
        garder.append((z / a - 1) * 100)
    total_garder = (bs[-1]["c"] / bs[DEBUT - 1]["c"] - 1) * 100

    res = {}
    for nom, f in STRATEGIES:
        for fr in FRAIS_LISTE:
            res[(nom, fr)] = simuler(bs, f, fr)
            print(nom, fr, round(res[(nom, fr)][1][-1], 2))

    L = []
    L.append("# Backtest\n")
    L.append(f"Periode : {d0} au {d1} ({n} bougies de 15 min), {PAIR}, 1000 EUR au depart.\n")
    L.append(f"Garder du Bitcoin sur toute la periode : {pct(total_garder)}\n")
    L.append("## Avec les frais realistes (0,5 % par ordre)\n")
    L.append("| Bot | Resultat | Trades | Gagnants | Pire baisse |")
    L.append("|---|---|---|---|---|")
    for nom, _ in STRATEGIES:
        s, vals = res[(nom, 0.005)]
        g = (100 * s["nb_gagnants"] / s["nb_trades"]) if s["nb_trades"] else 0
        L.append(f"| {nom} | {pct((vals[-1]/1000-1)*100)} | {s['nb_trades']} | {g:.0f} % | {s['baisse_max_pct']:.0f} % |")
    L.append("\n## Effet des frais (resultat final)\n")
    L.append("| Bot | 0,5 % | 0,25 % | 0,1 % | 0 % |")
    L.append("|---|---|---|---|---|")
    for nom, _ in STRATEGIES:
        cells = [pct((res[(nom, fr)][1][-1] / 1000 - 1) * 100) for fr in FRAIS_LISTE]
        L.append(f"| {nom} | " + " | ".join(cells) + " |")
    L.append("\n## Resultat par periode (frais 0,5 %)\n")
    L.append("| Bot | P1 | P2 | P3 | P4 |")
    L.append("|---|---|---|---|---|")
    for nom, _ in STRATEGIES:
        L.append(f"| {nom} | " + " | ".join(pct(x) for x in segs(res[(nom, 0.005)][1])) + " |")
    L.append("| Garder du Bitcoin | " + " | ".join(pct(x) for x in garder) + " |")
    L.append("\nP1 = premier quart de la periode, P4 = dernier quart.")
    texte = "\n".join(L) + "\n"
    with open("backtest_resultats.md", "w", encoding="utf-8") as f:
        f.write(texte)
    print(texte)


if __name__ == "__main__":
    main()
