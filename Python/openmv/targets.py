import sensor, image, time, math

# ---------------- CONFIGURAZIONE ----------------
PESI = {"blu": 2, "verde": 1, "giallo": 0, "rosso": -1, "nero": -2}

RIF_LAB = (
    ("rosso", (53, 80, 67)),
    ("verde", (15, -23, 21)),
    ("blu", (32, 79, -108)),
    ("giallo", (97, -22, 94)),
    ("nero", (10, 0, 0)),
    ("bianco", (90, 0, 0)),
)

# (L_min, L_max, A_min, A_max, B_min, B_max) - stesso formato di find_blobs
SOGLIE_BLOB = [
    (15, 70, 25, 100, 5, 90),     # rosso
    (60, 100, -25, 25, 35, 100),  # giallo
    (15, 65, -90, -15, 5, 70),    # verde
    (0, 55, -10, 90, -110, -20),  # blu
    (0, 22, -25, 25, -25, 25),    # nero
]

R_MIN = 28
N_ANGOLI = 24
PASSI_INTERNI = 5

FASCE_ANELLI = [
    (0.00, 0.20),
    (0.20, 0.40),
    (0.40, 0.60),
    (0.60, 0.80),
    (0.80, 1.00),
]

TRIG = [
    (math.cos(2 * math.pi * k / N_ANGOLI), math.sin(2 * math.pi * k / N_ANGOLI))
    for k in range(N_ANGOLI)
]

# ---------------- LOGICA ----------------
def classifica(lab):
    L, a, b = lab
    migliore, dmin = None, 1e12
    for nome, (l0, a0, b0) in RIF_LAB:
        d = (0.5 * (L - l0)) ** 2 + (a - a0) ** 2 + (b - b0) ** 2
        if d < dmin:
            migliore, dmin = nome, d
    return migliore


def leggi_anelli_geometrici(img, cx, cy, R):
    w = img.width()
    h = img.height()
    anelli = []

    for r_min_p, r_max_p in FASCE_ANELLI:
        voti = {}
        for p in range(PASSI_INTERNI):
            r = R * (r_min_p + (r_max_p - r_min_p) * (p + 0.5) / PASSI_INTERNI)
            for c, s in TRIG:
                x = max(0, min(w - 1, int(cx + r * c)))
                y = max(0, min(h - 1, int(cy + r * s)))
                lab = image.rgb_to_lab(img.get_pixel(x, y))
                nome = classifica(lab)
                if nome != "bianco":
                    voti[nome] = voti.get(nome, 0) + 1

        colore, max_voti = None, 0
        for nome, v in voti.items():
            if v > max_voti:
                colore, max_voti = nome, v
        if colore:
            anelli.append(colore)

    return anelli


def punteggio(anelli):
    return sum(PESI.get(c, 0) for c in anelli)


def verifica_anelli_consecutivi(anelli):
    ripetuti = []
    for i in range(len(anelli) - 1):
        if anelli[i] == anelli[i + 1] and anelli[i] not in ripetuti:
            ripetuti.append(anelli[i])
    return ripetuti


def trova_target(img):
    blobs = img.find_blobs(
        SOGLIE_BLOB,
        pixels_threshold=150,
        area_threshold=150,
        merge=True,   # unisce gli anelli concentrici in un unico blob
        margin=5,
    )
    migliore, max_pixels = None, 0
    for b in blobs:
        x, y, r = b.enclosing_circle()
        if r < R_MIN:
            continue
        if b.roundness() > 0.4 and b.pixels() > max_pixels:
            max_pixels = b.pixels()
            migliore = (x, y, r)
    return migliore


# ---------------- MAIN ----------------
sensor.reset()
sensor.set_pixformat(sensor.RGB565)
sensor.set_framesize(sensor.QVGA)
sensor.skip_frames(time=2000)
sensor.set_auto_gain(False)       # importante per colori stabili
sensor.set_auto_whitebal(False)
clock = time.clock()

while True:
    clock.tick()
    img = sensor.snapshot()

    t = trova_target(img)
    if t:
        cx, cy, R = t
        anelli = leggi_anelli_geometrici(img, cx, cy, R)
        img.draw_circle(int(cx), int(cy), int(R), color=(255, 255, 255))

        if len(anelli) >= 2:
            p = punteggio(anelli)
            ripetuti = verifica_anelli_consecutivi(anelli)
            print("Anelli:", anelli, "| Somma:", p, "| Ripetuti:", ripetuti)
        else:
            print("Anelli non determinabili")
    else:
        print("Nessun bersaglio")

    print("FPS:", clock.fps())
