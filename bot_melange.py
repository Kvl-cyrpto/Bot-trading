import moteur

SL, TP = 0.02, 0.04   # stop 2 %, objectif 4 %


def sma(xs, n):
    return sum(xs[-n:]) / n


def rsi(cl, n=14):
    g = pe = 0.0
    for i in range(-n, 0):
        d = cl[i] - cl[i - 1]
        if d > 0:
            g += d
        else:
            pe -= d
    if pe == 0:
        return 100.0
    return 100 - 100 / (1 + g / pe)


def decide(h, pos):
    cl = [b["c"] for b in h]
    p = cl[-1]
    haussier = sma(cl, 20) > sma(cl, 50)
    r = rsi(cl)
    sortie = (pos == "long" and not haussier) or (pos == "short" and haussier)
    entree = None
    if haussier and 50 <= r <= 65:
        entree = ("long", p * (1 - SL), p * (1 + TP))
    elif (not haussier) and 35 <= r <= 50:
        entree = ("short", p * (1 + SL), p * (1 - TP))
    return sortie, entree


if __name__ == "__main__":
    moteur.executer("state_melange.json", decide)
