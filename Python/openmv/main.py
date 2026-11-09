# =====================================================================
#  RICONOSCIMENTO VITTIME - RoboCup Junior Rescue Maze (OpenMV H7 Plus)
# =====================================================================
#  COSA FA QUESTO PROGRAMMA, IN BREVE
#  La camera guarda davanti a se' e, per ogni immagine (frame), cerca
#  due tipi di "vittima":
#    1) un BERSAGLIO a cerchi concentrici colorati  -> calcola un punteggio
#    2) una LETTERA greca nera (phi, psi, omega)     -> la riconosce con una KNN
#  Quando per alcuni frame di fila vede la stessa cosa, la "conferma".
#
#  GLOSSARIO RAPIDO
#  - Frame      : una singola foto scattata dalla camera (ne arrivano ~15 al secondo)
#  - Pixel      : un puntino dell'immagine
#  - Blob       : una macchia di pixel dello stesso colore, attaccati tra loro
#  - LAB        : un modo di descrivere i colori con 3 numeri
#                   L = luminosita' (0 nero ... 100 bianco)
#                   a = da verde (negativo) a rosso (positivo)
#                   b = da blu (negativo) a giallo (positivo)
#                 Si usa al posto di RGB perche' resiste meglio ai cambi di luce.
#  - KNN        : "K vicini piu' prossimi". Per riconoscere una cosa nuova la
#                 confronta con tanti esempi gia' visti e guarda a chi somiglia di piu'.
# =====================================================================

# Moduli (librerie) che il programma usa:
import sensor, image, time, math, os, ujson
#   sensor : controlla la camera
#   image  : funzioni per lavorare sulle immagini e sui colori
#   time   : orologio (per misurare gli FPS)
#   math   : seno, coseno, radice quadrata...
#   os     : per controllare se c'e' la scheda SD
#   ujson  : per leggere/scrivere file JSON (dove salviamo le lettere imparate)

# ================= CONFIG GENERALE =================
# Quanti frame consecutivi devono dare lo stesso risultato per fidarci.
# Serve a evitare "falsi allarmi" di un solo frame.
N_STABILE = 4

# ================= CONFIG BERSAGLIO =================
# Punti che vale ogni colore. La somma dei 5 anelli e' il punteggio finale.
PESI = {"blu": 2, "verde": 1, "giallo": 0, "rosso": -1, "nero": -2}

# Colori "ideali" in LAB (L, a, b). Ogni pixel viene confrontato con questi
# e prende il nome di quello piu' simile.
# ATTENZIONE: il verde e' stato tarato sui valori misurati con la TUA camera.
RIF_LAB = (
    ("rosso", (53, 80, 67)),
    ("verde", (15, -23, 21)),
    ("blu", (32, 79, -108)),
    ("giallo", (97, -22, 94)),
    ("nero", (10, 0, 0)),
    ("bianco", (90, 0, 0)),      # il bianco e' lo sfondo
)

# Intervalli LAB usati per TROVARE il bersaglio nell'immagine (uno per colore).
# Formato: (L_min, L_max, a_min, a_max, b_min, b_max).
# Un pixel "dentro" uno di questi intervalli viene considerato parte del bersaglio.
SOGLIE_BLOB = [
    (15, 70, 25, 100, 5, 90),        # rosso
    (60, 100, -25, 25, 35, 100),     # giallo
    (15, 65, -90, -15, 5, 70),       # verde
    (0, 55, -10, 90, -110, -20),     # blu
    (0, 22, -25, 25, -25, 25),       # nero
]

R_MIN = 28              # raggio minimo (in pixel): cerchi piu' piccoli sono rumore
N_ANGOLI = 24           # in quante direzioni "guardiamo" attorno al centro (una ogni 15 gradi)
PASSI_INTERNI = 5       # quanti raggi diversi controlliamo dentro ogni anello

# Il bersaglio ha 5 anelli, ognuno spesso il 20% del raggio totale.
# (0.0, 0.2) = dal centro al 20% del raggio, (0.2, 0.4) = dal 20% al 40%, ecc.
FASCE_ANELLI = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0)]

# Un bersaglio vero ha almeno questo numero di colori diversi.
# Serve a non scambiare per bersaglio una lettera (che e' tutta nera).
MIN_COLORI_TARGET = 3

# Tabella precalcolata di coseno e seno per le 24 direzioni.
# Calcolarla una volta sola all'inizio fa risparmiare tempo ad ogni frame.
TRIG_T = [(math.cos(2 * math.pi * k / N_ANGOLI), math.sin(2 * math.pi * k / N_ANGOLI))
          for k in range(N_ANGOLI)]

# ================= CONFIG LETTERE =================
N_RINGS = 10            # quanti anelli concentrici usiamo per "misurare" la lettera
N_ANG = 36              # quanti punti campioniamo su ogni anello
ARMONICHE = (1, 2, 3, 4)  # quali "frequenze" analizziamo (vedi estrai_feature)
K = 5                   # numero di vicini che votano nella KNN
SOGLIA_GRIGIO = 90      # un pixel con luminosita' sotto 90 (su 255) e' considerato nero
SOGLIA_NERO = [(0, 35, -25, 25, -25, 25)]   # intervallo LAB per trovare la lettera nera

# Dove sta il file con le lettere imparate in addestramento:
# se c'e' la scheda SD usiamo quella, altrimenti la memoria interna.
try:
    os.listdir("/sd")
    FILE_DATI = "/sd/knn_lettere.json"
except OSError:
    FILE_DATI = "/flash/knn_lettere.json"

# Tabelle precalcolate di seno e coseno per i punti sugli anelli delle lettere.
TRIG_L = [(math.cos(2 * math.pi * a / N_ANG), math.sin(2 * math.pi * a / N_ANG))
          for a in range(N_ANG)]
# Seno e coseno anche per ogni armonica (servono per il calcolo piu' sotto).
COSM = {m: [math.cos(2 * math.pi * m * a / N_ANG) for a in range(N_ANG)] for m in ARMONICHE}
SINM = {m: [math.sin(2 * math.pi * m * a / N_ANG) for a in range(N_ANG)] for m in ARMONICHE}

# Variabili che verranno riempite da carica() leggendo il file:
#   DATI   = esempi di lettere gia' imparate (con la loro etichetta)
#   MED/IQR= numeri per "mettere in scala" le misure (vedi scala())
#   SOGLIA = distanza massima oltre la quale diciamo "lettera sconosciuta"
DATI, MED, IQR, SOGLIA = [], [], [], 0.0


# =====================================================================
#  PARTE 1: BERSAGLIO
# =====================================================================

def classifica(lab):
    """Dato un pixel (in LAB) dice di che colore e': rosso, verde, blu...
    Confronta il pixel con ogni colore di RIF_LAB e sceglie il PIU' VICINO."""
    L, a, b = lab
    migliore, dmin = None, 1e12     # dmin parte da un numero enorme
    for nome, (l0, a0, b0) in RIF_LAB:
        # Distanza tra il pixel e il colore di riferimento.
        # La luminosita' (L) conta la meta': cosi' ombre e riflessi disturbano meno.
        d = (0.5 * (L - l0)) ** 2 + (a - a0) ** 2 + (b - b0) ** 2
        if d < dmin:                # se e' il piu' vicino finora, lo ricordiamo
            migliore, dmin = nome, d
    return migliore


def leggi_anelli(img, cx, cy, R):
    """Legge il colore di ognuno dei 5 anelli del bersaglio.
    cx, cy = centro del bersaglio, R = raggio totale (in pixel).
    Restituisce una lista, ad esempio ['nero','rosso','giallo','verde','blu']
    (dal centro verso l'esterno)."""
    w, h = img.width(), img.height()
    anelli = []
    for r_min, r_max in FASCE_ANELLI:        # ripetiamo per ognuno dei 5 anelli
        voti = {}                            # conteggio: quante volte vediamo ogni colore
        for p in range(PASSI_INTERNI):
            # Raggio (distanza dal centro) a cui guardiamo, dentro questo anello.
            r = R * (r_min + (r_max - r_min) * (p + 0.5) / PASSI_INTERNI)
            for c, s in TRIG_T:              # giriamo attorno al centro, direzione per direzione
                # Coordinate del pixel da controllare. max/min lo tengono dentro l'immagine.
                x = max(0, min(w - 1, int(cx + r * c)))
                y = max(0, min(h - 1, int(cy + r * s)))
                # Prendiamo il colore del pixel, lo convertiamo in LAB e lo classifichiamo.
                nome = classifica(image.rgb_to_lab(img.get_pixel(x, y)))
                if nome != "bianco":         # lo sfondo bianco non ci interessa
                    voti[nome] = voti.get(nome, 0) + 1
        # Il colore con piu' "voti" vince: cosi' pochi pixel sbagliati non rovinano la lettura.
        colore, mx = "bianco", 0             # se nessun colore trovato, l'anello e' "bianco" (vuoto)
        for nome, v in voti.items():
            if v > mx:
                colore, mx = nome, v
        anelli.append(colore)
    return anelli


def trova_target(img):
    """Cerca nell'immagine una zona colorata e rotonda: candidata a essere il bersaglio.
    Restituisce (x, y, raggio) oppure None se non trova niente."""
    # find_blobs trova le "macchie" dei colori indicati in SOGLIE_BLOB.
    # merge=True unisce macchie vicine: cosi' gli anelli concentrici diventano UN solo blob.
    blobs = img.find_blobs(SOGLIE_BLOB, pixels_threshold=150, area_threshold=150,
                           merge=True, margin=5)
    migliore, mx = None, 0
    for b in blobs:
        x, y, r = b.enclosing_circle()       # il cerchio piu' piccolo che contiene il blob
        # Teniamo il blob se e' abbastanza grande, abbastanza rotondo,
        # e (tra tutti) quello con piu' pixel.
        if r >= R_MIN and b.roundness() > 0.4 and b.pixels() > mx:
            mx = b.pixels()
            migliore = (x, y, r)
    return migliore


def leggi_target(img):
    """Prova a leggere un bersaglio. Restituisce (anelli, punteggio) se ne trova
    uno VALIDO, altrimenti None."""
    t = trova_target(img)
    if not t:
        return None                          # niente di rotondo: nessun bersaglio
    cx, cy, R = t
    anelli = leggi_anelli(img, cx, cy, R)
    # Controllo di validita': un vero bersaglio ha almeno 3 colori diversi.
    # Una lettera nera ne avrebbe solo 1, quindi viene scartata.
    colori = set(c for c in anelli if c != "bianco")
    if len(colori) < MIN_COLORI_TARGET:
        return None
    img.draw_circle(int(cx), int(cy), int(R), color=(255, 255, 255))  # cerchio bianco di debug
    # Punteggio = somma dei pesi dei 5 anelli (.get(c, 0): colore sconosciuto vale 0).
    return anelli, sum(PESI.get(c, 0) for c in anelli)


# =====================================================================
#  PARTE 2: LETTERE (con KNN)
# =====================================================================

def estrai_feature(img, b):
    """Trasforma una lettera (un blob) in una LISTA DI NUMERI che la descrive.
    Questi numeri si chiamano "feature". Due lettere uguali hanno numeri simili,
    anche se ruotate o a distanza diversa. E' il cuore del riconoscimento.

    Idea: disegniamo mentalmente tanti cerchi concentrici sopra la lettera e
    guardiamo quanto nero incontriamo lungo ognuno. Il risultato non dipende
    da come e' ruotata la lettera."""
    cx, cy, R = b.enclosing_circle()
    R = max(R, 5)                            # raggio minimo di sicurezza
    W, H = img.width(), img.height()
    # Ritagliamo un quadrato attorno alla lettera e lo mettiamo in scala di grigi.
    rx, ry = max(0, int(cx - R)), max(0, int(cy - R))
    rw, rh = min(W - rx, int(2 * R) + 1), min(H - ry, int(2 * R) + 1)
    g = img.copy(roi=(rx, ry, rw, rh))
    g.to_grayscale()
    lcx, lcy = cx - rx, cy - ry              # centro della lettera nel ritaglio

    f_dark, f_runs, f_harm = [], [], []      # tre gruppi di feature
    for k in range(N_RINGS):                 # per ogni anello concentrico...
        r = R * (k + 0.5) / N_RINGS          # ...a questo raggio
        seg = []                             # lista di 0/1: 1 = nero, 0 = bianco
        for c, s in TRIG_L:                  # giriamo attorno al centro
            x, y = int(lcx + r * c), int(lcy + r * s)
            # Pixel dentro il ritaglio e piu' scuro della soglia -> 1 (nero), altrimenti 0
            seg.append(1 if (0 <= x < rw and 0 <= y < rh and g.get_pixel(x, y) < SOGLIA_GRIGIO) else 0)

        # FEATURE 1: frazione di nero su questo anello (0 = tutto bianco, 1 = tutto nero)
        f_dark.append(sum(seg) / N_ANG)

        # FEATURE 2: quanti "tratti neri" separati attraversa l'anello
        # (contiamo i passaggi da bianco a nero). Distingue per esempio phi da omega.
        runs = sum(1 for i in range(N_ANG) if seg[i] == 1 and seg[i - 1] == 0)
        f_runs.append(min(runs, 6) / 6.0)    # limitato a 6 e portato tra 0 e 1

        # FEATURE 3: "armoniche" (matematica di Fourier, versione semplice).
        # Misurano come il nero e' distribuito lungo l'anello. Il trucco e' che
        # il loro valore NON cambia se ruoti la lettera.
        for m in ARMONICHE:
            re = im = 0.0
            cm, sm = COSM[m], SINM[m]
            for i in range(N_ANG):
                if seg[i]:
                    re += cm[i]
                    im += sm[i]
            f_harm.append(math.sqrt(re * re + im * im) / N_ANG)

    # FEATURE 4: caratteristiche generali del blob:
    #   fill  = quanto e' "pieno" il cerchio che lo contiene
    #   solid = quanto la forma e' compatta (senza rientranze)
    fill = b.pixels() / (math.pi * R * R)
    solid = b.solidity() if hasattr(b, "solidity") else b.density()
    # Mettiamo tutto in una unica lista di numeri: il "vettore" della lettera.
    return f_dark + f_runs + f_harm + [fill, b.elongation(), b.roundness(), solid]


def scala(v):
    """Mette tutte le feature sulla stessa scala. Serve perche' alcune feature hanno
    numeri grandi e altre piccoli, e senza questo passaggio le grandi
    "comanderebbero" sulle piccole. MED e IQR sono calcolati in addestramento."""
    return [(v[j] - MED[j]) / IQR[j] for j in range(len(v))]


def manhattan(a, b):
    """Distanza tra due vettori: somma delle differenze, numero per numero.
    Piu' e' piccola, piu' le due lettere si somigliano."""
    return sum(abs(x - y) for x, y in zip(a, b))


def predici(vs):
    """KNN: dato il vettore di una lettera nuova (vs), dice chi e'.
    Restituisce (etichetta, distanza dal piu' simile)."""
    # 1) distanza da TUTTI gli esempi imparati, ordinati dal piu' vicino al piu' lontano
    dist = sorted(((manhattan(vs, v), et) for et, v in DATI), key=lambda t: t[0])
    # 2) i K piu' vicini "votano"; chi e' piu' vicino pesa di piu'
    voti = {}
    for d, et in dist[:K]:
        voti[et] = voti.get(et, 0) + 1.0 / (d + 1e-6)   # +1e-6 evita divisione per zero
    # 3) vince l'etichetta con piu' voti; restituiamo anche la distanza migliore
    return max(voti, key=voti.get), dist[0][0]


def carica():
    """Legge dal file le lettere imparate in addestramento (fatto con lo script di training)."""
    global MED, IQR, SOGLIA, DATI            # "global": modifichiamo le variabili definite in alto
    with open(FILE_DATI, "r") as f:
        d = ujson.load(f)
    MED, IQR, SOGLIA = d["med"], d["iqr"], d["soglia"]
    # Mettiamo in scala ogni esempio salvato, pronto per i confronti.
    DATI = [(et, scala(v)) for et, v in d["raw"]]
    print("Lettere caricate:", len(DATI), "| soglia:", SOGLIA)


def trova_lettera(img):
    """Cerca nell'immagine il blob nero piu' grande: e' la candidata lettera."""
    W, H = img.width(), img.height()
    blobs = img.find_blobs(SOGLIA_NERO, pixels_threshold=300, area_threshold=300,
                           merge=True, margin=3)
    migliore, mx = None, 0
    for b in blobs:
        # Scartiamo i blob che toccano il bordo: la lettera sarebbe tagliata.
        if b.x() < 3 or b.y() < 3 or b.x() + b.w() > W - 3 or b.y() + b.h() > H - 3:
            continue
        if b.pixels() > mx:                  # teniamo il piu' grande
            mx = b.pixels()
            migliore = b
    return migliore


def leggi_lettera(img):
    """Trova una lettera e la riconosce. Restituisce il nome (es. 'phi') oppure None."""
    b = trova_lettera(img)
    if not b:
        return None                          # nessun blob nero: niente lettera
    et, d = predici(scala(estrai_feature(img, b)))
    if d <= SOGLIA:
        # Abbastanza simile a una lettera nota: rettangolo VERDE e restituiamo il nome.
        img.draw_rectangle(b.rect(), color=(0, 255, 0))
        return et
    # Troppo diversa da tutte quelle imparate: rettangolo ROSSO, "sconosciuta".
    img.draw_rectangle(b.rect(), color=(255, 0, 0))
    return None


# =====================================================================
#  PROGRAMMA PRINCIPALE
# =====================================================================

# --- Preparazione della camera (si fa una volta sola) ---
sensor.reset()                          # riavvia il sensore
sensor.set_pixformat(sensor.RGB565)     # immagini a colori
sensor.set_framesize(sensor.QVGA)       # risoluzione 320x240 pixel
sensor.skip_frames(time=2000)           # aspetta 2 secondi che la camera si assesti sulla luce
# Blocchiamo esposizione e bilanciamento del bianco: senza, i colori cambierebbero
# da un frame all'altro e le soglie LAB smetterebbero di funzionare.
sensor.set_auto_gain(False)
sensor.set_auto_whitebal(False)

carica()                                # leggiamo le lettere imparate
storico = []                            # ricordo degli ultimi risultati (per la conferma)
clock = time.clock()                    # orologio per misurare gli FPS

# --- Ciclo infinito: ripete tutto per ogni frame ---
while True:
    clock.tick()
    img = sensor.snapshot()             # scatta una foto

    risultato = None                    # cosa abbiamo visto: "T:-3" (bersaglio), "L:phi" (lettera) o None
    dettaglio = ""                      # info extra da stampare (gli anelli)

    # PRIORITA': prima cerchiamo il bersaglio. Solo se non c'e', cerchiamo una lettera.
    # (Il centro nero del bersaglio potrebbe altrimenti sembrare una lettera.)
    t = leggi_target(img)
    if t:
        anelli, punti = t
        risultato = "T:" + str(punti)
        dettaglio = str(anelli)
    else:
        let = leggi_lettera(img)
        if let:
            risultato = "L:" + let

    # Aggiungiamo il risultato allo storico e teniamo solo gli ultimi N_STABILE.
    storico.append(risultato)
    if len(storico) > N_STABILE:
        storico.pop(0)                  # butta via il piu' vecchio

    # CONFERMA: se lo storico e' pieno, non e' "niente", e sono TUTTI uguali,
    # allora siamo sicuri di aver visto una vittima.
    if (len(storico) == N_STABILE and storico[0] is not None
            and all(s == storico[0] for s in storico)):
        print(">>> VITTIMA:", storico[0], dettaglio)
        # qui puoi inviare via UART: uart.write(storico[0] + "\n")
