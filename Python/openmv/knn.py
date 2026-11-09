import sensor, time, math, os, ujson

# ---------------- CONFIGURAZIONE ----------------
MODALITA = "run"            # "train" per addestrare, "run" per riconoscere
LETTERE = ["H", "S", "U"]   # oppure ["phi", "psi", "omega"]

N_RINGS = 10                # anelli concentrici
N_ANG = 36                  # campioni per anello
ARMONICHE = (1, 2, 3, 4)
K = 5
MOLT_SOGLIA = 2.5           # come nel codice del prof
SOGLIA_GRIGIO = 90          # pixel < 90 (su 255) = nero della lettera
SOGLIA_NERO = [(0, 35, -25, 25, -25, 25)]   # per find_blobs (LAB)

GIRI = 6                    # in training: quante pose diverse
CAMPIONI_PER_GIRO = 12
N_STABILE = 4               # frame consecutivi uguali per confermare

try:
    os.listdir("/sd")
    FILE_DATI = "/sd/knn_lettere.json"
except OSError:
    FILE_DATI = "/flash/knn_lettere.json"

# ---------------- TABELLE PRECALCOLATE ----------------
TRIG = [(math.cos(2 * math.pi * a / N_ANG),
         math.sin(2 * math.pi * a / N_ANG)) for a in range(N_ANG)]
COSM = {m: [math.cos(2 * math.pi * m * a / N_ANG) for a in range(N_ANG)] for m in ARMONICHE}
SINM = {m: [math.sin(2 * math.pi * m * a / N_ANG) for a in range(N_ANG)] for m in ARMONICHE}

RAW = []                    # [(etichetta, vettore grezzo)]
DATI = []                   # [(etichetta, vettore scalato)]
MED, IQR, SOGLIA = [], [], 0.0


# ---------------- ESTRAZIONE FEATURE ----------------
def estrai_feature(img, b):
    cx, cy, R = b.enclosing_circle()
    R = max(R, 5)
    W, H = img.width(), img.height()

    # ritaglio quadrato attorno al cerchio, in scala di grigi
    rx = max(0, int(cx - R))
    ry = max(0, int(cy - R))
    rw = min(W - rx, int(2 * R) + 1)
    rh = min(H - ry, int(2 * R) + 1)
    g = img.copy(roi=(rx, ry, rw, rh))
    g.to_grayscale()
    lcx, lcy = cx - rx, cy - ry

    f_dark, f_runs, f_harm = [], [], []
    for k in range(N_RINGS):
        r = R * (k + 0.5) / N_RINGS
        seg = []
        for c, s in TRIG:
            x = int(lcx + r * c)
            y = int(lcy + r * s)
            if 0 <= x < rw and 0 <= y < rh and g.get_pixel(x, y) < SOGLIA_GRIGIO:
                seg.append(1)
            else:
                seg.append(0)

        # 1) frazione di nero
        f_dark.append(sum(seg) / N_ANG)

        # 2) numero di tratti neri (transizioni 0->1 sul cerchio chiuso)
        runs = 0
        for i in range(N_ANG):
            if seg[i] == 1 and seg[i - 1] == 0:
                runs += 1
        f_runs.append(min(runs, 6) / 6.0)

        # 3) modulo delle armoniche (invariante alla rotazione)
        for m in ARMONICHE:
            re = 0.0
            im = 0.0
            cm, sm = COSM[m], SINM[m]
            for i in range(N_ANG):
                if seg[i]:
                    re += cm[i]
                    im += sm[i]
            f_harm.append(math.sqrt(re * re + im * im) / N_ANG)

    # 4) feature globali
    fill = b.pixels() / (math.pi * R * R)
    elong = b.elongation()
    rond = b.roundness()
    solid = b.solidity() if hasattr(b, "solidity") else b.density()

    return f_dark + f_runs + f_harm + [fill, elong, rond, solid]


# ---------------- SCALER (equivalente RobustScaler) ----------------
def calcola_scaler(vettori):
    med, iqr = [], []
    n = len(vettori)
    for j in range(len(vettori[0])):
        col = sorted(v[j] for v in vettori)
        med.append(col[n // 2])
        q1 = col[int(0.25 * (n - 1))]
        q3 = col[int(0.75 * (n - 1))]
        iqr.append(max(q3 - q1, 0.05))   # soglia minima per evitare divisioni esplosive
    return med, iqr


def scala(v):
    return [(v[j] - MED[j]) / IQR[j] for j in range(len(v))]


def manhattan(a, b):
    return sum(abs(x - y) for x, y in zip(a, b))


# ---------------- KNN ----------------
def predici(vs):
    dist = [(manhattan(vs, v), et) for et, v in DATI]
    dist.sort(key=lambda t: t[0])
    voti = {}
    for d, et in dist[:K]:
        voti[et] = voti.get(et, 0) + 1.0 / (d + 1e-6)   # pesata per distanza
    vinta = max(voti, key=voti.get)
    return vinta, dist[0][0]


# ---------------- ADDESTRAMENTO / SALVATAGGIO ----------------
def finalizza():
    global MED, IQR, SOGLIA, DATI
    MED, IQR = calcola_scaler([v for _, v in RAW])
    DATI = [(et, scala(v)) for et, v in RAW]

    # distanza al vicino piu' prossimo (leave-one-out)
    nn = []
    for i in range(len(DATI)):
        dmin = 1e12
        for j in range(len(DATI)):
            if i != j:
                d = manhattan(DATI[i][1], DATI[j][1])
                if d < dmin:
                    dmin = d
        nn.append(dmin)
    nn.sort()
    p95 = nn[int(0.95 * (len(nn) - 1))]
    SOGLIA = p95 * MOLT_SOGLIA

    with open(FILE_DATI, "w") as f:
        ujson.dump({"raw": RAW, "med": MED, "iqr": IQR, "soglia": SOGLIA}, f)
    print("Salvato:", len(RAW), "campioni | soglia:", SOGLIA)


def carica():
    global RAW, MED, IQR, SOGLIA, DATI
    try:
        with open(FILE_DATI, "r") as f:
            d = ujson.load(f)
        RAW = d["raw"]
        MED, IQR, SOGLIA = d["med"], d["iqr"], d["soglia"]
        DATI = [(et, scala(v)) for et, v in RAW]
        print("Caricati", len(DATI), "campioni | soglia:", SOGLIA)
        return True
    except OSError:
        print("Nessun dataset: usa MODALITA = 'train'")
        return False


def trova_lettera(img):
    W, H = img.width(), img.height()
    blobs = img.find_blobs(SOGLIA_NERO, pixels_threshold=300,
                           area_threshold=300, merge=True, margin=3)
    migliore, max_p = None, 0
    for b in blobs:
        # scarta blob che toccano il bordo (lettera tagliata)
        if b.x() < 3 or b.y() < 3 or b.x() + b.w() > W - 3 or b.y() + b.h() > H - 3:
            continue
        if b.pixels() > max_p:
            max_p = b.pixels()
            migliore = b
    return migliore


def addestra(etichetta):
    for giro in range(GIRI):
        print("Lettera", etichetta, "- giro", giro + 1, "/", GIRI,
              "- cambia rotazione/distanza. Parto tra 4 s...")
        time.sleep(4)
        presi = 0
        while presi < CAMPIONI_PER_GIRO:
            img = sensor.snapshot()
            b = trova_lettera(img)
            if b:
                RAW.append((etichetta, estrai_feature(img, b)))
                presi += 1
                img.draw_rectangle(b.rect(), color=(0, 255, 0))
            time.sleep_ms(150)


# ---------------- MAIN ----------------
sensor.reset()
sensor.set_pixformat(sensor.RGB565)
sensor.set_framesize(sensor.QVGA)
sensor.skip_frames(time=2000)
sensor.set_auto_gain(False)
sensor.set_auto_whitebal(False)

if MODALITA == "train":
    RAW = []
    for l in LETTERE:
        addestra(l)
    finalizza()
    print("Addestramento completato: metti MODALITA = 'run'")
else:
    if not carica():
        raise SystemExit

    storico = []
    clock = time.clock()
    while True:
        clock.tick()
        img = sensor.snapshot()
        b = trova_lettera(img)
        risultato = None

        if b:
            v = scala(estrai_feature(img, b))
            et, d = predici(v)
            if d <= SOGLIA:
                risultato = et
                img.draw_rectangle(b.rect(), color=(0, 255, 0))
            else:
                img.draw_rectangle(b.rect(), color=(255, 0, 0))   # sconosciuto
            print("Letter:", et, "| dist:", round(d, 1), "| soglia:", round(SOGLIA, 1))

        storico.append(risultato)
        if len(storico) > N_STABILE:
            storico.pop(0)
        if len(storico) == N_STABILE and storico[0] is not None \
                and all(s == storico[0] for s in storico):
            print(">>> CONFERMATA:", storico[0])

        print("FPS:", round(clock.fps(), 1))
