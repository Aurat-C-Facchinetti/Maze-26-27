# =====================================================================
#  RICONOSCIMENTO LETTERE (addestramento + riconoscimento)
#  RoboCup Junior Rescue Maze - OpenMV H7 Plus
# =====================================================================
#  COSA FA QUESTO PROGRAMMA, IN BREVE
#  Insegna alla camera a riconoscere alcune lettere nere (es. phi, psi, omega)
#  e poi le riconosce quando le vede. Ha DUE MODALITA', scelte con MODALITA:
#
#    "train" (addestramento): mostri ogni lettera alla camera in tante pose
#                             diverse; il programma ne memorizza le
#                             "caratteristiche" (un elenco di numeri)
#                             e le salva in un file.
#    "run"   (riconoscimento): carica quel file e, per ogni lettera che vede,
#                             dice quale e' confrontandola con quelle memorizzate.
#
#  Si addestra UNA VOLTA, poi si passa a "run".
#
#  GLOSSARIO RAPIDO
#  - Frame   : una singola foto scattata dalla camera
#  - Blob    : una macchia di pixel dello stesso colore, attaccati tra loro
#  - Feature : un numero che descrive una caratteristica della lettera
#              (es. "quanto nero c'e' a meta' raggio"). L'insieme delle
#              feature di una lettera e' il suo "vettore".
#  - KNN     : "K vicini piu' prossimi". Per riconoscere una lettera nuova la
#              confronta con tutti gli esempi memorizzati e guarda a quali
#              somiglia di piu'. I K piu' simili "votano" per decidere chi e'.
# =====================================================================

# Moduli (librerie) che il programma usa:
#   sensor : controlla la camera
#   time   : pause e orologio
#   math   : seno, coseno, radice quadrata...
#   os     : per controllare se c'e' la scheda SD
#   ujson  : per leggere/scrivere il file JSON dove salviamo le lettere imparate
import sensor, time, math, os, ujson

# ---------------- CONFIGURAZIONE ----------------
MODALITA = "run"            # "train" per addestrare, "run" per riconoscere
LETTERE = ["H", "S", "U"]   # lettere da insegnare (usate solo in "train"); oppure ["phi", "psi", "omega"]

N_RINGS = 10                # numero di anelli concentrici con cui "misuriamo" la lettera
N_ANG = 36                  # quanti punti controlliamo su ogni anello (uno ogni 10 gradi)
ARMONICHE = (1, 2, 3, 4)    # quali "frequenze" analizziamo (vedi estrai_feature)
K = 5                       # numero di vicini che votano nella KNN
MOLT_SOGLIA = 2.5           # quanto larga e' la soglia "sconosciuta" (piu' alto = piu' permissivo)
SOGLIA_GRIGIO = 90          # pixel < 90 (su 255) = nero della lettera
SOGLIA_NERO = [(0, 35, -25, 25, -25, 25)]   # intervallo LAB per trovare la lettera nera con find_blobs

GIRI = 6                    # in training: quante pose diverse per ogni lettera
CAMPIONI_PER_GIRO = 12      # in training: quante foto per ogni posa
N_STABILE = 4               # in run: frame consecutivi uguali per confermare

# Dove salviamo/leggiamo i dati: sulla scheda SD se c'e', altrimenti nella memoria interna.
try:
    os.listdir("/sd")
    FILE_DATI = "/sd/knn_lettere.json"
except OSError:
    FILE_DATI = "/flash/knn_lettere.json"

# ---------------- TABELLE PRECALCOLATE ----------------
# Seno e coseno dei 36 angoli attorno al centro, calcolati una volta sola
# (ricalcolarli a ogni frame farebbe perdere tempo).
TRIG = [(math.cos(2 * math.pi * a / N_ANG),
         math.sin(2 * math.pi * a / N_ANG)) for a in range(N_ANG)]
# Seno e coseno anche per ogni armonica (servono per il calcolo piu' sotto).
COSM = {m: [math.cos(2 * math.pi * m * a / N_ANG) for a in range(N_ANG)] for m in ARMONICHE}
SINM = {m: [math.sin(2 * math.pi * m * a / N_ANG) for a in range(N_ANG)] for m in ARMONICHE}

# Memoria del programma:
RAW = []                    # esempi imparati, con i numeri "grezzi": [(etichetta, vettore)]
DATI = []                   # gli stessi esempi ma "messi in scala" (pronti per i confronti)
MED, IQR, SOGLIA = [], [], 0.0   # numeri per la messa in scala + distanza massima per dire "sconosciuta"


# ---------------- ESTRAZIONE FEATURE ----------------
def estrai_feature(img, b):
    """Trasforma una lettera (un blob) in una LISTA DI NUMERI che la descrive.
    Due lettere uguali hanno numeri simili, anche se ruotate o a distanza diversa.
    E' il cuore del riconoscimento.

    Idea: disegniamo mentalmente tanti cerchi concentrici sopra la lettera e
    guardiamo quanto nero incontriamo lungo ognuno. Il risultato non dipende
    da come e' ruotata la lettera."""
    cx, cy, R = b.enclosing_circle()    # centro e raggio del cerchio che contiene la lettera
    R = max(R, 5)                       # raggio minimo di sicurezza
    W, H = img.width(), img.height()

    # ritaglio quadrato attorno al cerchio, in scala di grigi
    rx = max(0, int(cx - R))
    ry = max(0, int(cy - R))
    rw = min(W - rx, int(2 * R) + 1)
    rh = min(H - ry, int(2 * R) + 1)
    g = img.copy(roi=(rx, ry, rw, rh))
    g.to_grayscale()
    lcx, lcy = cx - rx, cy - ry         # centro della lettera nel ritaglio

    f_dark, f_runs, f_harm = [], [], [] # tre gruppi di feature
    for k in range(N_RINGS):            # per ogni anello concentrico...
        r = R * (k + 0.5) / N_RINGS     # ...a questo raggio
        seg = []                        # lista di 0/1 lungo l'anello: 1 = nero, 0 = bianco
        for c, s in TRIG:               # giriamo attorno al centro
            x = int(lcx + r * c)
            y = int(lcy + r * s)
            # Pixel dentro il ritaglio e piu' scuro della soglia -> 1 (nero), altrimenti 0
            if 0 <= x < rw and 0 <= y < rh and g.get_pixel(x, y) < SOGLIA_GRIGIO:
                seg.append(1)
            else:
                seg.append(0)

        # 1) frazione di nero su questo anello (0 = tutto bianco, 1 = tutto nero)
        f_dark.append(sum(seg) / N_ANG)

        # 2) numero di tratti neri SEPARATI che l'anello attraversa
        #    (contiamo i passaggi da bianco a nero; seg[i - 1] per i = 0 e' l'ultimo
        #    elemento, cosi' l'anello e' "chiuso"). Distingue per esempio phi da omega.
        runs = 0
        for i in range(N_ANG):
            if seg[i] == 1 and seg[i - 1] == 0:
                runs += 1
        f_runs.append(min(runs, 6) / 6.0)   # limitato a 6 e portato tra 0 e 1

        # 3) "armoniche" (matematica di Fourier, versione semplice): misurano come
        #    il nero e' distribuito lungo l'anello. Il loro valore NON cambia
        #    se ruoti la lettera: e' il trucco che rende il metodo invariante alla rotazione.
        for m in ARMONICHE:
            re = 0.0
            im = 0.0
            cm, sm = COSM[m], SINM[m]
            for i in range(N_ANG):
                if seg[i]:
                    re += cm[i]
                    im += sm[i]
            f_harm.append(math.sqrt(re * re + im * im) / N_ANG)

    # 4) feature globali del blob:
    fill = b.pixels() / (math.pi * R * R)   # quanto e' "pieno" il cerchio che lo contiene
    elong = b.elongation()                  # quanto e' allungato
    rond = b.roundness()                    # quanto e' rotondo
    # quanto la forma e' compatta, senza rientranze (se solidity non esiste, usa density)
    solid = b.solidity() if hasattr(b, "solidity") else b.density()

    # Mettiamo tutto in una unica lista di numeri: il "vettore" della lettera.
    return f_dark + f_runs + f_harm + [fill, elong, rond, solid]


# ---------------- SCALER (equivalente RobustScaler) ----------------
def calcola_scaler(vettori):
    """Calcola, per ogni feature, due numeri di riferimento:
    la MEDIANA (valore "centrale") e l'IQR (quanto i valori sono sparpagliati).
    Servono a mettere tutte le feature sulla stessa scala: senza, quelle con
    numeri grandi "comanderebbero" su quelle con numeri piccoli."""
    med, iqr = [], []
    n = len(vettori)
    for j in range(len(vettori[0])):                # per ogni feature...
        col = sorted(v[j] for v in vettori)         # ...tutti i suoi valori, in ordine
        med.append(col[n // 2])                     # mediana = valore a meta' della lista
        q1 = col[int(0.25 * (n - 1))]               # primo quartile (25%)
        q3 = col[int(0.75 * (n - 1))]               # terzo quartile (75%)
        iqr.append(max(q3 - q1, 0.05))   # soglia minima per evitare divisioni esplosive
    return med, iqr


def scala(v):
    """Mette in scala un vettore: (valore - mediana) / IQR, feature per feature."""
    return [(v[j] - MED[j]) / IQR[j] for j in range(len(v))]


def manhattan(a, b):
    """Distanza tra due vettori: somma delle differenze, numero per numero.
    Piu' e' piccola, piu' le due lettere si somigliano."""
    return sum(abs(x - y) for x, y in zip(a, b))


# ---------------- KNN ----------------
def predici(vs):
    """KNN: dato il vettore di una lettera nuova (vs), dice chi e'.
    Restituisce (etichetta, distanza dall'esempio piu' simile)."""
    # 1) distanza da TUTTI gli esempi imparati
    dist = [(manhattan(vs, v), et) for et, v in DATI]
    dist.sort(key=lambda t: t[0])       # ordinati dal piu' vicino al piu' lontano
    # 2) i K piu' vicini "votano"; chi e' piu' vicino pesa di piu'
    voti = {}
    for d, et in dist[:K]:
        voti[et] = voti.get(et, 0) + 1.0 / (d + 1e-6)   # pesata per distanza (+1e-6 evita divisione per zero)
    # 3) vince l'etichetta con piu' voti
    vinta = max(voti, key=voti.get)
    return vinta, dist[0][0]


# ---------------- ADDESTRAMENTO / SALVATAGGIO ----------------
def finalizza():
    """Ultimo passo dell'addestramento: prepara i dati, calcola la soglia
    "sconosciuta" e salva tutto su file."""
    global MED, IQR, SOGLIA, DATI       # "global": modifichiamo le variabili definite in alto
    MED, IQR = calcola_scaler([v for _, v in RAW])
    DATI = [(et, scala(v)) for et, v in RAW]

    # Per ogni esempio cerchiamo l'esempio PIU' VICINO tra tutti gli altri.
    # Cosi' vediamo "quanto sono distanti, di solito, esempi simili tra loro".
    nn = []
    for i in range(len(DATI)):
        dmin = 1e12                     # numero enorme di partenza
        for j in range(len(DATI)):
            if i != j:                  # non confrontiamo un esempio con se' stesso
                d = manhattan(DATI[i][1], DATI[j][1])
                if d < dmin:
                    dmin = d
        nn.append(dmin)
    nn.sort()
    # Prendiamo il valore sotto cui cade il 95% delle distanze e lo moltiplichiamo
    # per MOLT_SOGLIA: oltre questa distanza una lettera e' "sconosciuta".
    p95 = nn[int(0.95 * (len(nn) - 1))]
    SOGLIA = p95 * MOLT_SOGLIA

    # Salviamo tutto nel file, cosi' in modalita' "run" non serve riaddestrare.
    with open(FILE_DATI, "w") as f:
        ujson.dump({"raw": RAW, "med": MED, "iqr": IQR, "soglia": SOGLIA}, f)
    print("Salvato:", len(RAW), "campioni | soglia:", SOGLIA)


def carica():
    """Legge dal file i dati salvati in addestramento.
    Restituisce True se va a buon fine, False se il file non esiste."""
    global RAW, MED, IQR, SOGLIA, DATI
    try:
        with open(FILE_DATI, "r") as f:
            d = ujson.load(f)
        RAW = d["raw"]
        MED, IQR, SOGLIA = d["med"], d["iqr"], d["soglia"]
        DATI = [(et, scala(v)) for et, v in RAW]    # mettiamo in scala ogni esempio
        print("Caricati", len(DATI), "campioni | soglia:", SOGLIA)
        return True
    except OSError:
        print("Nessun dataset: usa MODALITA = 'train'")
        return False


def trova_lettera(img):
    """Cerca nell'immagine il blob nero piu' grande: e' la candidata lettera."""
    W, H = img.width(), img.height()
    blobs = img.find_blobs(SOGLIA_NERO, pixels_threshold=300,
                           area_threshold=300, merge=True, margin=3)
    migliore, max_p = None, 0
    for b in blobs:
        # scarta blob che toccano il bordo (lettera tagliata)
        if b.x() < 3 or b.y() < 3 or b.x() + b.w() > W - 3 or b.y() + b.h() > H - 3:
            continue
        if b.pixels() > max_p:          # teniamo il piu' grande
            max_p = b.pixels()
            migliore = b
    return migliore


def addestra(etichetta):
    """Insegna UNA lettera. Fa GIRI "giri": a ogni giro tu cambi posa
    (rotazione, distanza, inclinazione) e il programma scatta CAMPIONI_PER_GIRO foto.
    Piu' pose diverse mostri, piu' il riconoscimento sara' robusto."""
    for giro in range(GIRI):
        print("Lettera", etichetta, "- giro", giro + 1, "/", GIRI,
              "- cambia rotazione/distanza. Parto tra 4 s...")
        time.sleep(4)                   # 4 secondi per cambiare posa
        presi = 0
        while presi < CAMPIONI_PER_GIRO:
            img = sensor.snapshot()
            b = trova_lettera(img)
            if b:                       # se vede una lettera, memorizza le sue feature
                RAW.append((etichetta, estrai_feature(img, b)))
                presi += 1
                img.draw_rectangle(b.rect(), color=(0, 255, 0))
            time.sleep_ms(150)          # piccola pausa tra una foto e l'altra


# ---------------- MAIN ----------------
# --- Preparazione della camera (si fa una volta sola) ---
sensor.reset()                          # riavvia il sensore
sensor.set_pixformat(sensor.RGB565)     # immagini a colori
sensor.set_framesize(sensor.QVGA)       # risoluzione 320x240 pixel
sensor.skip_frames(time=2000)           # aspetta 2 secondi che la camera si assesti sulla luce
# Blocchiamo esposizione e bilanciamento del bianco, cosi' i colori non cambiano da un frame all'altro.
sensor.set_auto_gain(False)
sensor.set_auto_whitebal(False)

if MODALITA == "train":
    # ===== MODALITA' ADDESTRAMENTO =====
    RAW = []                            # si riparte da zero: i vecchi esempi vengono sovrascritti
    for l in LETTERE:                   # insegniamo le lettere una alla volta
        addestra(l)
    finalizza()                         # calcola la soglia e salva il file
    print("Addestramento completato: metti MODALITA = 'run'")
else:
    # ===== MODALITA' RICONOSCIMENTO =====
    if not carica():                    # se non c'e' il file di addestramento...
        raise SystemExit                # ...il programma si ferma

    storico = []                        # ricordo degli ultimi risultati (per la conferma)
    clock = time.clock()                # orologio per misurare gli FPS
    while True:                         # ciclo infinito: ripete tutto per ogni frame
        clock.tick()
        img = sensor.snapshot()         # scatta una foto
        b = trova_lettera(img)
        risultato = None                # cosa abbiamo riconosciuto (None = niente)

        if b:
            v = scala(estrai_feature(img, b))   # numeri della lettera vista, messi in scala
            et, d = predici(v)                  # KNN: chi e'? e quanto e' vicina agli esempi?
            if d <= SOGLIA:
                # Abbastanza simile a una lettera nota: rettangolo VERDE.
                risultato = et
                img.draw_rectangle(b.rect(), color=(0, 255, 0))
            else:
                # Troppo diversa da tutte quelle imparate: rettangolo ROSSO, "sconosciuta".
                img.draw_rectangle(b.rect(), color=(255, 0, 0))   # sconosciuto
            print("Letter:", et, "| dist:", round(d, 1), "| soglia:", round(SOGLIA, 1))

        # Aggiungiamo il risultato allo storico e teniamo solo gli ultimi N_STABILE.
        storico.append(risultato)
        if len(storico) > N_STABILE:
            storico.pop(0)              # butta via il piu' vecchio
        # CONFERMA: storico pieno, non "niente", e tutti uguali -> siamo sicuri della lettera.
        if len(storico) == N_STABILE and storico[0] is not None \
                and all(s == storico[0] for s in storico):
            print(">>> CONFERMATA:", storico[0])

        print("FPS:", round(clock.fps(), 1))   # quanti frame al secondo sta elaborando
