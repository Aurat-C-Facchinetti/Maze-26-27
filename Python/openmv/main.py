import sensor, image, time, math, os, ujson

# ================= CONFIG GENERALE =================
N_STABILE = 4

# ================= CONFIG BERSAGLIO =================
PESI = {"blu": 2, "verde": 1, "giallo": 0, "rosso": -1, "nero": -2}
RIF_LAB = (
    ("rosso", (53, 80, 67)),
    ("verde", (15, -23, 21)),
    ("blu", (32, 79, -108)),
    ("giallo", (97, -22, 94)),
    ("nero", (10, 0, 0)),
    ("bianco", (90, 0, 0)),
)
SOGLIE_BLOB = [
    (15, 70, 25, 100, 5, 90), (60, 100, -25, 25, 35, 100),
    (15, 65, -90, -15, 5, 70), (0, 55, -10, 90, -110, -20),
    (0, 22, -25, 25, -25, 25),
]
R_MIN = 28
N_ANGOLI = 24
PASSI_INTERNI = 5
FASCE_ANELLI = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0)]
MIN_COLORI_TARGET = 3        # colori diversi per accettare un bersaglio

TRIG_T = [(math.cos(2 * math.pi * k / N_ANGOLI), math.sin(2 * math.pi * k / N_ANGOLI))
          for k in range(N_ANGOLI)]

# ================= CONFIG LETTERE =================
N_RINGS = 10
N_ANG = 36
ARMONICHE = (1, 2, 3, 4)
K = 5
SOGLIA_GRIGIO = 90
SOGLIA_NERO = [(0, 35, -25, 25, -25, 25)]

try:
    os.listdir("/sd")
    FILE_DATI = "/sd/knn_lettere.json"
except OSError:
    FILE_DATI = "/flash/knn_lettere.json"

TRIG_L = [(math.cos(2 * math.pi * a / N_ANG), math.sin(2 * math.pi * a / N_ANG))
          for a in range(N_ANG)]
COSM = {m: [math.cos(2 * math.pi * m * a / N_ANG) for a in range(N_ANG)] for m in ARMONICHE}
SINM = {m: [math.sin(2 * math.pi * m * a / N_ANG) for a in range(N_ANG)] for m in ARMONICHE}

DATI, MED, IQR, SOGLIA = [], [], [], 0.0


# ================= BERSAGLIO =================
def classifica(lab):
    L, a, b = lab
    migliore, dmin = None, 1e12
    for nome, (l0, a0, b0) in RIF_LAB:
        d = (0.5 * (L - l0)) ** 2 + (a - a0) ** 2 + (b - b0) ** 2
        if d < dmin:
            migliore, dmin = nome, d
    return migliore

def leggi_anelli(img, cx, cy, R):
    w, h = img.width(), img.height()
    anelli = []
    for r_min, r_max in FASCE_ANELLI:
        voti = {}
        for p in range(PASSI_INTERNI):
            r = R * (r_min + (r_max - r_min) * (p + 0.5) / PASSI_INTERNI)
            for c, s in TRIG_T:
                x = max(0, min(w - 1, int(cx + r * c)))
                y = max(0, min(h - 1, int(cy + r * s)))
                nome = classifica(image.rgb_to_lab(img.get_pixel(x, y)))
                if nome != "bianco":
                    voti[nome] = voti.get(nome, 0) + 1
        colore, mx = "bianco", 0
        for nome, v in voti.items():
            if v > mx:
                colore, mx = nome, v
        anelli.append(colore)                   # "bianco" se la fascia e' vuota
    return anelli


def trova_target(img):
    blobs = img.find_blobs(SOGLIE_BLOB, pixels_threshold=150, area_threshold=150,
                           merge=True, margin=5)
    migliore, mx = None, 0
    for b in blobs:
        x, y, r = b.enclosing_circle()
        if r >= R_MIN and b.roundness() > 0.4 and b.pixels() > mx:
            mx = b.pixels()
            migliore = (x, y, r)
    return migliore


def leggi_target(img):
    """Restituisce (anelli, punteggio) se c'e' un bersaglio VALIDO, altrimenti None."""
    t = trova_target(img)
    if not t:
        return None
    cx, cy, R = t
    anelli = leggi_anelli(img, cx, cy, R)
    colori = set(c for c in anelli if c != "bianco")
    if len(colori) < MIN_COLORI_TARGET:         # es. una lettera nera: scartata
        return None
    img.draw_circle(int(cx), int(cy), int(R), color=(255, 255, 255))
    return anelli, sum(PESI.get(c, 0) for c in anelli)


# ================= LETTERE =================
def estrai_feature(img, b):
    cx, cy, R = b.enclosing_circle()
    R = max(R, 5)
    W, H = img.width(), img.height()
    rx, ry = max(0, int(cx - R)), max(0, int(cy - R))
    rw, rh = min(W - rx, int(2 * R) + 1), min(H - ry, int(2 * R) + 1)
    g = img.copy(roi=(rx, ry, rw, rh))
    g.to_grayscale()
    lcx, lcy = cx - rx, cy - ry

    f_dark, f_runs, f_harm = [], [], []
    for k in range(N_RINGS):
        r = R * (k + 0.5) / N_RINGS
        seg = []
        for c, s in TRIG_L:
            x, y = int(lcx + r * c), int(lcy + r * s)
            seg.append(1 if (0 <= x < rw and 0 <= y < rh and g.get_pixel(x, y) < SOGLIA_GRIGIO) else 0)
        f_dark.append(sum(seg) / N_ANG)
        runs = sum(1 for i in range(N_ANG) if seg[i] == 1 and seg[i - 1] == 0)
        f_runs.append(min(runs, 6) / 6.0)
        for m in ARMONICHE:
            re = im = 0.0
            cm, sm = COSM[m], SINM[m]
            for i in range(N_ANG):
                if seg[i]:
                    re += cm[i]
                    im += sm[i]
            f_harm.append(math.sqrt(re * re + im * im) / N_ANG)

    fill = b.pixels() / (math.pi * R * R)
    solid = b.solidity() if hasattr(b, "solidity") else b.density()
    return f_dark + f_runs + f_harm + [fill, b.elongation(), b.roundness(), solid]


def scala(v):
    return [(v[j] - MED[j]) / IQR[j] for j in range(len(v))]


def manhattan(a, b):
    return sum(abs(x - y) for x, y in zip(a, b))


def predici(vs):
    dist = sorted(((manhattan(vs, v), et) for et, v in DATI), key=lambda t: t[0])
    voti = {}
    for d, et in dist[:K]:
        voti[et] = voti.get(et, 0) + 1.0 / (d + 1e-6)
    return max(voti, key=voti.get), dist[0][0]


def carica():
    global MED, IQR, SOGLIA, DATI
    with open(FILE_DATI, "r") as f:
        d = ujson.load(f)
    MED, IQR, SOGLIA = d["med"], d["iqr"], d["soglia"]
    DATI = [(et, scala(v)) for et, v in d["raw"]]
    print("Lettere caricate:", len(DATI), "| soglia:", SOGLIA)


def trova_lettera(img):
    W, H = img.width(), img.height()
    blobs = img.find_blobs(SOGLIA_NERO, pixels_threshold=300, area_threshold=300,
                           merge=True, margin=3)
    migliore, mx = None, 0
    for b in blobs:
        if b.x() < 3 or b.y() < 3 or b.x() + b.w() > W - 3 or b.y() + b.h() > H - 3:
            continue
        if b.pixels() > mx:
            mx = b.pixels()
            migliore = b
    return migliore


def leggi_lettera(img):
    b = trova_lettera(img)
    if not b:
        return None
    et, d = predici(scala(estrai_feature(img, b)))
    if d <= SOGLIA:
        img.draw_rectangle(b.rect(), color=(0, 255, 0))
        return et
    img.draw_rectangle(b.rect(), color=(255, 0, 0))   # sconosciuta
    return None


# ================= MAIN =================
sensor.reset()
sensor.set_pixformat(sensor.RGB565)
sensor.set_framesize(sensor.QVGA)
sensor.skip_frames(time=2000)
sensor.set_auto_gain(False)
sensor.set_auto_whitebal(False)

carica()
storico = []
clock = time.clock()

while True:
    clock.tick()
    img = sensor.snapshot()

    risultato = None            # stringa che identifica la vittima, es. "T:-3" o "L:phi"
    dettaglio = ""

    t = leggi_target(img)
    if t:
        anelli, punti = t
        risultato = "T:" + str(punti)
        dettaglio = str(anelli)
    else:
        let = leggi_lettera(img)
        if let:
            risultato = "L:" + let

    storico.append(risultato)
    if len(storico) > N_STABILE:
        storico.pop(0)

    if (len(storico) == N_STABILE and storico[0] is not None
            and all(s == storico[0] for s in storico)):
        print(">>> VITTIMA:", storico[0], dettaglio)
        # qui puoi inviare via UART: uart.write(storico[0] + "\n")
