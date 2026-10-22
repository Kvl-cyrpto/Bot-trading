import moteur

STOP_MIN, STOP_MAX = 0.01, 0.03   # stop entre 1 % et 3 %, objectif = 2x le risque


def decide(h, pos):
    b = h[-1]
    p = b["c"]
    ref = h[-51:-3]
    haut_liq = max(x["h"] for x in ref)
    bas_liq = min(x["l"] for x in ref)
    recent = h[-3:]
    # balayage de liquidite : meche qui depasse puis cloture de retour
    sweep_bas = any(x["l"] < bas_liq and x["c"] > bas_liq for x in recent)
    sweep_haut = any(x["h"] > haut_liq and x["c"] < haut_liq for x in recent)

    n = len(h)
    fvg_h = fvg_b = ob_h = ob_b = False
    # fair value gaps sur les 30 dernieres bougies
    for i in range(n - 30, n - 3):
        c1, c3 = h[i], h[i + 2]
        if c3["l"] > c1["h"]:  # ecart haussier
            if b["l"] <= c3["l"] and b["c"] >= c1["h"]:
                fvg_h = True
        if c3["h"] < c1["l"]:  # ecart baissier
            if b["h"] >= c3["h"] and b["c"] <= c1["l"]:
                fvg_b = True
    # order blocks : derniere bougie opposee avant un fort mouvement
    corps = [abs(x["c"] - x["o"]) for x in h[-21:-1]]
    moy = sum(corps) / len(corps)
    for i in range(n - 30, n - 3):
        k = h[i]
        if abs(k["c"] - k["o"]) < 1.5 * moy:
            continue
        for j in range(i - 1, i - 4, -1):
            o = h[j]
            if k["c"] > k["o"] and o["c"] < o["o"]:  # bloc haussier
                if b["l"] <= o["h"] and b["c"] >= o["l"]:
                    ob_h = True
                break
            if k["c"] < k["o"] and o["c"] > o["o"]:  # bloc baissier
                if b["h"] >= o["l"] and b["c"] <= o["h"]:
                    ob_b = True
                break

    entree = None
    score_h = int(sweep_bas) + int(fvg_h) + int(ob_h)
    score_b = int(sweep_haut) + int(fvg_b) + int(ob_b)
    if score_h >= 2 and b["c"] > b["o"]:
        d = (p - min(x["l"] for x in h[-6:])) / p
        d = min(max(d, STOP_MIN), STOP_MAX)
        entree = ("long", p * (1 - d), p * (1 + 2 * d))
    elif score_b >= 2 and b["c"] < b["o"]:
        d = (max(x["h"] for x in h[-6:]) - p) / p
        d = min(max(d, STOP_MIN), STOP_MAX)
        entree = ("short", p * (1 + d), p * (1 - 2 * d))
    return False, entree


if __name__ == "__main__":
    moteur.executer("state_ict.json", decide)
