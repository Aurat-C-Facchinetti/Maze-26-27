# =====================================================================
#  LETTURA DEL BERSAGLIO - RoboCup Junior Rescue Maze (OpenMV H7 Plus)
# =====================================================================
#  COSA FA QUESTO PROGRAMMA, IN BREVE
#  La camera cerca un BERSAGLIO a cerchi concentrici colorati (5 anelli).
#  Quando lo trova, legge il colore di ogni anello dal centro verso l'esterno
#  e calcola un PUNTEGGIO sommando i "pesi" dei colori (es. blu = +2, nero = -2).
#  Segnala anche se due anelli vicini hanno lo stesso colore (puo' essere un errore).
#
#  GLOSSARIO RAPIDO
#  - Frame   : una singola foto scattata dalla camera (ne arrivano ~15 al secondo)
#  - Pixel   : un puntino dell'immagine
#  - Blob    : una macchia di pixel dello stesso colore, attaccati tra loro
#  - LAB     : un modo di descrivere i colori con 3 numeri
#                L = luminosita' (0 nero ... 100 bianco)
#                a = da verde (negativo) a rosso (positivo)
#                b = da blu (negativo) a giallo (positivo)
#              Si usa al posto di RGB perche' resiste meglio ai cambi di luce.
# =====================================================================

# Moduli (librerie) che il programma usa:
#   sensor : controlla la camera
#   image  : funzioni per lavorare su immagini e colori
#   time   : orologio (per misurare gli FPS, cioe' i frame al secondo)
#   math   : seno, coseno, pi greco...
import sensor, image, time, math

# ---------------- CONFIGURAZIONE ----------------
# Punti che vale ogni colore. Il punteggio finale e' la somma dei 5 anelli.
PESI = {"blu": 2, "verde": 1, "giallo": 0, "rosso": -1, "nero": -2}

# Colori "ideali" in LAB (L, a, b). Ogni pixel viene confrontato con questi
# e prende il nome di quello piu' simile.
# Il verde e' tarato sui valori misurati con la TUA camera.
RIF_LAB = (
    ("rosso", (53, 80, 67)),
    ("verde", (15, -23, 21)),
    ("blu", (32, 79, -108)),
    ("giallo", (97, -22, 94)),
    ("nero", (10, 0, 0)),
    ("bianco", (90, 0, 0)),      # il bianco e' lo sfondo
)

# Intervalli LAB usati per TROVARE il bersaglio nell'immagine (uno per colore).
# Formato: (L_min, L_max, a_min, a_max, b_min, b_max) - stesso formato di find_blobs.
# Un pixel "dentro" uno di questi intervalli viene considerato parte del bersaglio.
SOGLIE_BLOB = [
    (15, 70, 25, 100, 5, 90),     # rosso
    (60, 100, -25, 25, 35, 100),  # giallo
    (15, 65, -90, -15, 5, 70),    # verde
    (0, 55, -10, 90, -110, -20),  # blu
    (0, 22, -25, 25, -25, 25),    # nero
]

R_MIN = 28          # raggio minimo (in pixel): cerchi piu' piccoli sono considerati rumore
N_ANGOLI = 24       # in quante direzioni "guardiamo" attorno al centro (una ogni 15 gradi)
PASSI_INTERNI = 5   # quanti raggi diversi controlliamo dentro ogni anello

# Il bersaglio ha 5 anelli, ognuno spesso il 20% del raggio totale
# (se il raggio e' 5 cm, ogni anello e' spesso 1 cm).
# (0.00, 0.20) = dal centro al 20% del raggio, (0.20, 0.40) = dal 20% al 40%, ecc.
FASCE_ANELLI = [
    (0.00, 0.20),
    (0.20, 0.40),
    (0.40, 0.60),
    (0.60, 0.80),
    (0.80, 1.00),
]

# Tabella precalcolata di coseno e seno per le 24 direzioni.
# Calcolarla una volta sola all'inizio fa risparmiare tempo ad ogni frame.
# Con (coseno, seno) di un angolo si ottiene un punto su un cerchio.
TRIG = [
    (math.cos(2 * math.pi * k / N_ANGOLI), math.sin(2 * math.pi * k / N_ANGOLI))
    for k in range(N_ANGOLI)
]

# ---------------- LOGICA ----------------
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


def leggi_anelli_geometrici(img, cx, cy, R):
    """Legge il colore di ognuno dei 5 anelli.
    cx, cy = centro del bersaglio, R = raggio totale (in pixel).
    Restituisce una lista, ad esempio ['nero','rosso','giallo','verde','blu']
    (dal centro verso l'esterno)."""
    w = img.width()
    h = img.height()
    anelli = []

    for r_min_p, r_max_p in FASCE_ANELLI:    # ripetiamo per ognuno dei 5 anelli
        voti = {}                            # conteggio: quante volte vediamo ogni colore
        for p in range(PASSI_INTERNI):
            # Raggio (distanza dal centro) a cui guardiamo, dentro questo anello.
            r = R * (r_min_p + (r_max_p - r_min_p) * (p + 0.5) / PASSI_INTERNI)
            for c, s in TRIG:                # giriamo attorno al centro, direzione per direzione
                # Coordinate del pixel da controllare. max/min lo tengono dentro l'immagine.
                x = max(0, min(w - 1, int(cx + r * c)))
                y = max(0, min(h - 1, int(cy + r * s)))
                # Prendiamo il colore del pixel e lo convertiamo in LAB...
                lab = image.rgb_to_lab(img.get_pixel(x, y))
                # ...poi lo classifichiamo (rosso, blu, ...).
                nome = classifica(lab)
                if nome != "bianco":         # lo sfondo bianco non ci interessa
                    voti[nome] = voti.get(nome, 0) + 1

        # Il colore con piu' "voti" vince: cosi' pochi pixel sbagliati non rovinano la lettura.
        colore, max_voti = None, 0
        for nome, v in voti.items():
            if v > max_voti:
                colore, max_voti = nome, v
        # Se in questo anello non e' stato trovato alcun colore (es. e' bianco),
        # l'anello NON viene aggiunto alla lista (quindi la lista puo' avere meno di 5 elementi).
        if colore:
            anelli.append(colore)

    return anelli


def punteggio(anelli):
    """Somma i pesi dei colori degli anelli. .get(c, 0): un colore sconosciuto vale 0."""
    return sum(PESI.get(c, 0) for c in anelli)


def verifica_anelli_consecutivi(anelli):
    """Controlla se due anelli VICINI hanno lo stesso colore.
    Restituisce la lista dei colori ripetuti (vuota se non ce ne sono).
    Utile come avviso: potrebbe essere una lettura sbagliata."""
    ripetuti = []
    for i in range(len(anelli) - 1):                      # confrontiamo ogni anello col successivo
        if anelli[i] == anelli[i + 1] and anelli[i] not in ripetuti:
            ripetuti.append(anelli[i])
    return ripetuti


def trova_target(img):
    """Cerca nell'immagine una zona colorata e rotonda: candidata a essere il bersaglio.
    Restituisce (x, y, raggio) oppure None se non trova niente."""
    # find_blobs trova le "macchie" dei colori indicati in SOGLIE_BLOB.
    blobs = img.find_blobs(
        SOGLIE_BLOB,
        pixels_threshold=150,   # ignora macchie con meno di 150 pixel
        area_threshold=150,     # ignora macchie con area piccola
        merge=True,   # unisce gli anelli concentrici in un unico blob
        margin=5,     # unisce macchie che distano meno di 5 pixel
    )
    migliore, max_pixels = None, 0
    for b in blobs:
        x, y, r = b.enclosing_circle()      # il cerchio piu' piccolo che contiene il blob
        if r < R_MIN:                       # troppo piccolo: probabilmente rumore
            continue
        # Teniamo il blob se e' abbastanza rotondo e (tra tutti) quello con piu' pixel.
        if b.roundness() > 0.4 and b.pixels() > max_pixels:
            max_pixels = b.pixels()
            migliore = (x, y, r)
    return migliore


# ---------------- MAIN ----------------
# --- Preparazione della camera (si fa una volta sola) ---
sensor.reset()                          # riavvia il sensore
sensor.set_pixformat(sensor.RGB565)     # immagini a colori
sensor.set_framesize(sensor.QVGA)       # risoluzione 320x240 pixel
sensor.skip_frames(time=2000)           # aspetta 2 secondi che la camera si assesti sulla luce
sensor.set_auto_gain(False)       # importante per colori stabili
sensor.set_auto_whitebal(False)   # blocchiamo il bilanciamento del bianco: i colori non cambiano a ogni frame
clock = time.clock()                    # orologio per misurare gli FPS

# --- Ciclo infinito: ripete tutto per ogni frame ---
while True:
    clock.tick()
    img = sensor.snapshot()             # scatta una foto

    t = trova_target(img)               # cerchiamo il bersaglio
    if t:
        cx, cy, R = t                   # centro (cx, cy) e raggio R del bersaglio
        anelli = leggi_anelli_geometrici(img, cx, cy, R)
        img.draw_circle(int(cx), int(cy), int(R), color=(255, 255, 255))  # cerchio bianco di debug

        # Servono almeno 2 anelli per fidarci della lettura.
        if len(anelli) >= 2:
            p = punteggio(anelli)
            ripetuti = verifica_anelli_consecutivi(anelli)
            print("Anelli:", anelli, "| Somma:", p, "| Ripetuti:", ripetuti)
        else:
            print("Anelli non determinabili")
    else:
        print("Nessun bersaglio")

    print("FPS:", clock.fps())         # quanti frame al secondo sta elaborando
