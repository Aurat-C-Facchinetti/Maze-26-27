import os
import time
import math
import cv2
import numpy as np
import serial
import struct

# Percorso della cartella FRAME sul Desktop (funziona sia su Windows che su Mac/Linux)
CARTELLA_FRAME = os.path.expanduser("~/Desktop/FRAME")

# Crea la cartella se non esiste già
if not os.path.exists(CARTELLA_FRAME):
    os.makedirs(CARTELLA_FRAME)

# Configurazione colori e anelli (rimane tutto uguale)
PESI = {"blu": 2, "verde": 1, "giallo": 0, "rosso": -1, "nero": -2}
R_MIN = 25
N_ANGOLI = 24
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


def classifica_hsv(hsv):
    h, s, v = hsv
    if v < 80:
        return "nero"
    if s < 35 and v > 180:
        return "bianco"
    if (0 <= h <= 10) or (165 <= h <= 179):
        return "rosso"
    elif 11 <= h <= 32:
        return "giallo"
    elif 33 <= h <= 85:
        return "verde"
    elif 86 <= h <= 135:
        return "blu"
    else:
        return "nero"


def leggi_anelli_geometrici(get_hsv_func, cx, cy, R):
    anelli = []
    for r_min_p, r_max_p in FASCE_ANELLI:
        voti_fascia = {}
        passi_interni = 5
        for p in range(passi_interni):
            r = R * (r_min_p + (r_max_p - r_min_p) * (p + 0.5) / passi_interni)
            for c, s in TRIG:
                x = int(cx + r * c)
                y = int(cy + r * s)
                hsv_val = get_hsv_func(x, y)
                nome = classifica_hsv(hsv_val)
                if nome and nome != "bianco":
                    voti_fascia[nome] = voti_fascia.get(nome, 0) + 1
        colore_vinto = "nero"
        max_voti = 0
        for nome, voti in voti_fascia.items():
            if voti > max_voti:
                max_voti = voti
                colore_vinto = nome
        anelli.append(colore_vinto)
    return anelli


def punteggio(anelli):
    return sum(PESI.get(c, 0) for c in anelli)


def verifica_anelli_consecutivi(anelli):
    consecutivi = []
    for i in range(len(anelli) - 1):
        if anelli[i] == anelli[i + 1]:
            if anelli[i] not in consecutivi:
                consecutivi.append(anelli[i])
    return consecutivi


def trova_target_opencv(img_bgr, img_hsv):
    lower_colore = np.array([0, 30, 30])
    upper_colore = np.array([179, 255, 255])
    mask = cv2.inRange(img_hsv, lower_colore, upper_colore)
    kernel = np.ones((7, 7), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    migliore_cerchio = None
    max_area = 0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 200:
            continue
        (x, y), radius = cv2.minEnclosingCircle(cnt)
        if radius < R_MIN:
            continue
        perimeter = cv2.arcLength(cnt, True)
        if perimeter == 0:
            continue
        circularity = 4 * math.pi * (area / (perimeter * perimeter))
        if circularity > 0.3 and area > max_area:
            max_area = area
            migliore_cerchio = (x, y, radius)
    return migliore_cerchio


def main():
    # Apertura della seriale per ricevere i frame dalla OpenMV
    porta_seriale = 'COM3'  # Cambiala con la tua porta (es. '/dev/ttyACM0' su Linux)
    try:
        ser = serial.Serial(porta_seriale, 115200, timeout=1)
        print(f"Connesso alla OpenMV. I frame verranno salvati in: {CARTELLA_FRAME}")
    except Exception as e:
        print(f"Errore porta seriale: {e}")
        return

    print("In ascolto... Premi 'q' per uscire.")

    counter = 0
    while True:
        try:
            # 1. Ricezione del frame dal robot via USB
            marker = ser.read(7)
            if marker != b'<FRAME>':
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                continue

            size_bytes = ser.read(4)
            if len(size_bytes) < 4:
                continue
            (jpeg_size,) = struct.unpack("<L", size_bytes)
            jpeg_data = ser.read(jpeg_size)
            if len(jpeg_data) < jpeg_size:
                continue

            # Decodifica l'immagine ricevuta
            np_arr = np.frombuffer(jpeg_data, np.uint8)
            img_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

            if img_bgr is None:
                continue

            # 2. SALVATAGGIO NELLA CARTELLA FRAME SUL DESKTOP (come volevi tu)
            nome_file = os.path.join(CARTELLA_FRAME, f"frame_target.jpg")
            cv2.imwrite(nome_file, img_bgr)

            # 3. ELABORAZIONE DEL BERSAGLIO PRENDENDO L'IMMAGINE DALLA CARTELLA (o direttamente)
            # Leggiamo l'immagine appena salvata nella cartella per simulare il passaggio completo
            img_letta = cv2.imread(nome_file)
            img_hsv = cv2.cvtColor(img_letta, cv2.COLOR_BGR2HSV)
            h, w = img_letta.shape[:2]

            def get_hsv(x, y):
                x = max(0, min(w - 1, x))
                y = max(0, min(h - 1, y))
                return img_hsv[y, x]

            t = trova_target_opencv(img_letta, img_hsv)

            if t is not None:
                cx, cy, R = t
                cv2.circle(img_letta, (int(cx), int(cy)), int(R), (0, 255, 0), 2)
                cv2.circle(img_letta, (int(cx), int(cy)), 3, (0, 0, 255), -1)
                anelli = leggi_anelli_geometrici(get_hsv, cx, cy, R)
                p_tot = punteggio(anelli)
                ripetuti = verifica_anelli_consecutivi(anelli)

                cv2.putText(img_letta, f"Punteggio: {p_tot}", (30, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                cv2.putText(img_letta, f"Anelli: {', '.join(anelli)}", (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                            (255, 255, 255), 2)
                if ripetuti:
                    cv2.putText(img_letta, f"ATTENZIONE: Consecutivi {', '.join(ripetuti)}", (30, 120),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
            else:
                cv2.putText(img_letta, "In attesa di bersaglio...", (30, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                            (0, 0, 255), 2)

            cv2.imshow("Analisi Bersaglio da Cartella FRAME", img_letta)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        except Exception as ex:
            print(f"Errore nel ciclo: {ex}")
            break

    ser.close()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
