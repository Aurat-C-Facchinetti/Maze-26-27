# -*- coding: utf-8 -*-
"""Script webcam basato su HSV per massima stabilita' dei colori.

IDEA GENERALE DEL PROGRAMMA
---------------------------
1. Prende i fotogrammi (frame) dalla webcam, uno dopo l'altro.
2. In ogni frame cerca un bersaglio circolare colorato (cerchi concentrici).
3. Se lo trova, "legge" il colore di ciascuno dei 5 anelli.
4. Calcola un punteggio sommando un peso per ogni colore.
5. Disegna tutto sopra l'immagine e la mostra a schermo.
"""

import math          # funzioni matematiche (seno, coseno, pi greco)
import cv2           # OpenCV: la libreria per elaborare immagini e video
import numpy as np   # NumPy: libreria per lavorare con array di numeri.
                     # In OpenCV un'immagine E' un array NumPy.

# ---------------- CONFIGURAZIONE ----------------

# Quanti punti vale ciascun colore. Il punteggio finale e' la somma
# dei pesi dei 5 anelli (es. blu=+2, nero=-2).
PESI = {"blu": 2, "verde": 1, "giallo": 0, "rosso": -1, "nero": -2}

# Raggio minimo (in pixel) perche' un cerchio venga considerato un bersaglio.
# Serve a scartare macchioline piccole che non sono il bersaglio.
R_MIN = 25

# In ogni anello campioniamo il colore lungo 24 direzioni (una ogni 15 gradi),
# come se guardassimo le lancette di un orologio con 24 posizioni.
N_ANGOLI = 24

# Ogni anello e' definito come una "fascia" tra due frazioni del raggio.
# 0.0 = centro del bersaglio, 1.0 = bordo esterno.
# Esempio: (0.20, 0.40) = dal 20% al 40% della distanza centro->bordo.
FASCE_ANELLI = [
    (0.00, 0.20),  # 1° anello (Centro)
    (0.20, 0.40),  # 2° anello
    (0.40, 0.60),  # 3° anello
    (0.60, 0.80),  # 4° anello
    (0.80, 1.00),  # 5° anello (Esterno)
]

# Pre-calcoliamo una volta sola coseno e seno dei 24 angoli.
# Servono per trasformare "distanza + angolo" in coordinate (x, y):
#   x = centro_x + distanza * coseno(angolo)
#   y = centro_y + distanza * seno(angolo)
# Calcolarli qui evita di rifarlo migliaia di volte per ogni frame.
TRIG = [
    (
        math.cos(2 * math.pi * k / N_ANGOLI),  # 2*pi = giro completo (in radianti)
        math.sin(2 * math.pi * k / N_ANGOLI),
    )
    for k in range(N_ANGOLI)
]


def classifica_hsv(hsv):
    """Dato UN pixel in formato HSV, restituisce il nome del colore.

    Cos'e' HSV? E' un modo alternativo a RGB/BGR di descrivere un colore:
      H (Hue, tinta)        = "che colore e'" (rosso, verde, blu...).
                              In OpenCV va da 0 a 179.
      S (Saturation)        = quanto e' "puro" il colore (0 = grigio/bianco,
                              255 = colore vivido). Range 0-255.
      V (Value, luminosita')= quanto e' chiaro (0 = nero, 255 = massima luce).
    Il vantaggio: la tinta (H) cambia poco se cambia la luce della stanza,
    quindi il riconoscimento e' piu' stabile rispetto a usare BGR.
    """
    h, s, v = hsv  # "spacchettiamo" i tre valori del pixel

    # Se la luminosita' e' molto bassa, qualunque sia la tinta e' nero
    if v < 80:
        return "nero"

    # Poca saturazione + molta luce = bianco (lo sfondo del foglio)
    if s < 35 and v > 180:
        return "bianco"

    # Ora decidiamo il colore in base alla tinta (H, da 0 a 179).
    # Rosso: sta a CAVALLO dell'inizio e della fine della scala,
    # quindi servono due intervalli.
    if (0 <= h <= 10) or (165 <= h <= 179):
        return "rosso"
    # Giallo
    elif 11 <= h <= 32:
        return "giallo"
    # Verde
    elif 33 <= h <= 85:
        return "verde"
    # Blu
    elif 86 <= h <= 135:
        return "blu"
    else:
        # Siamo nelle tinte rimaste (136-164, viola/magenta) che non ci
        # interessano: le trattiamo come "nero".
        # (Nota: i due return qui sotto restituiscono la stessa cosa.)
        if v < 70:
            return "nero"
        return "nero"


def leggi_anelli_geometrici(get_hsv_func, cx, cy, R):
    """Per ogni anello del bersaglio determina il colore dominante.

    Parametri:
      get_hsv_func : funzione che dato (x, y) restituisce il pixel HSV
      cx, cy       : coordinate del centro del bersaglio (in pixel)
      R            : raggio del bersaglio (in pixel)

    Metodo: "voto a maggioranza". Si prelevano molti pixel campione
    dentro la fascia dell'anello, si classifica ognuno, vince il colore
    che compare piu' volte. Cosi' un pixel disturbato non rovina il risultato.
    """
    anelli = []  # qui metteremo il colore vincitore di ogni anello

    for r_min_p, r_max_p in FASCE_ANELLI:
        voti_fascia = {}      # dizionario: nome colore -> numero di voti
        passi_interni = 5     # dentro la fascia usiamo 5 distanze diverse

        for p in range(passi_interni):
            # Distanza dal centro del campione, in pixel.
            # Si prende il punto medio di ognuna delle 5 sotto-fasce
            # (da qui il "+ 0.5"), poi si moltiplica per R per passare
            # da frazione del raggio a pixel.
            r = R * (r_min_p + (r_max_p - r_min_p) * (p + 0.5) / passi_interni)

            # Per ogni distanza, guardiamo tutte le 24 direzioni
            for c, s in TRIG:
                # Coordinate del pixel da leggere (devono essere intere)
                x = int(cx + r * c)
                y = int(cy + r * s)
                hsv_val = get_hsv_func(x, y)        # leggo il pixel
                nome = classifica_hsv(hsv_val)      # lo classifico
                # Il bianco (sfondo) non vota: non fa parte degli anelli
                if nome and nome != "bianco":
                    voti_fascia[nome] = voti_fascia.get(nome, 0) + 1

        # Totale campioni per anello: 5 distanze x 24 angoli = 120 voti.
        # Cerchiamo il colore con piu' voti.
        colore_vinto = "nero"   # valore di default se nessuno ha votato
        max_voti = 0
        for nome, voti in voti_fascia.items():
            if voti > max_voti:
                max_voti = voti
                colore_vinto = nome
        anelli.append(colore_vinto)

    return anelli  # lista di 5 colori, dal centro verso l'esterno


def punteggio(anelli):
    """Somma i pesi dei colori degli anelli (colori sconosciuti valgono 0)."""
    return sum(PESI.get(c, 0) for c in anelli)


def verifica_anelli_consecutivi(anelli):
    """Cerca anelli ADIACENTI con lo stesso colore e restituisce i colori
    coinvolti (senza duplicati). Es: [blu, blu, rosso, nero, nero] -> [blu, nero]
    """
    consecutivi = []
    for i in range(len(anelli) - 1):          # confronto ogni anello col successivo
        if anelli[i] == anelli[i + 1]:
            if anelli[i] not in consecutivi:  # evito di scrivere due volte lo stesso colore
                consecutivi.append(anelli[i])
    return consecutivi


def trova_target_opencv(img_bgr, img_hsv):
    """Trova nell'immagine il bersaglio circolare.

    Restituisce (x_centro, y_centro, raggio) oppure None se non trova nulla.

    Strategia:
      1. Creo una "maschera": immagine in bianco/nero dove bianco = pixel colorato.
      2. Pulisco la maschera dal rumore.
      3. Trovo i "contorni" delle zone bianche.
      4. Tra i contorni scelgo il piu' grande che somigli a un cerchio.
    """
    h, w = img_bgr.shape[:2]  # altezza e larghezza (qui in realta' non servono)

    # --- 1. MASCHERA ---
    # Teniamo solo i pixel con saturazione >= 30 e luminosita' >= 30,
    # cioe' quelli "colorati". Il bianco/grigio dello sfondo ha bassa
    # saturazione, quindi viene escluso. Gli array sono [H, S, V].
    lower_colore = np.array([0, 30, 30])      # limite inferiore
    upper_colore = np.array([179, 255, 255])  # limite superiore
    # inRange: pixel dentro l'intervallo -> 255 (bianco), fuori -> 0 (nero)
    mask = cv2.inRange(img_hsv, lower_colore, upper_colore)

    # --- 2. PULIZIA (operazioni morfologiche) ---
    # Il "kernel" e' una piccola finestra 7x7 che scorre sulla maschera.
    kernel = np.ones((7, 7), np.uint8)
    # CLOSE: chiude i buchi neri dentro le zone bianche
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    # OPEN: elimina i puntini bianchi isolati (rumore)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    # --- 3. CONTORNI ---
    # findContours trova i bordi delle zone bianche. RETR_EXTERNAL = solo i
    # contorni piu' esterni; CHAIN_APPROX_SIMPLE = salva solo i punti utili.
    contours, _ = cv2.findContours(
        mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    migliore_cerchio = None   # per ora non ho trovato niente
    max_area = 0              # area del miglior candidato finora

    # --- 4. SCELTA DEL MIGLIOR CANDIDATO ---
    for cnt in contours:
        area = cv2.contourArea(cnt)          # area della zona in pixel
        if area < 200:                       # troppo piccola: scarto
            continue
        # Cerchio piu' piccolo che contiene tutto il contorno
        (x, y), radius = cv2.minEnclosingCircle(cnt)
        if radius < R_MIN:                   # cerchio troppo piccolo: scarto
            continue
        perimeter = cv2.arcLength(cnt, True)  # lunghezza del bordo
        if perimeter == 0:                    # evito divisione per zero
            continue
        # "Circolarita'": 1.0 = cerchio perfetto, valori bassi = forma allungata
        # o irregolare. Formula: 4 * pi * area / perimetro^2
        circularity = 4 * math.pi * (area / (perimeter * perimeter))
        # Tengo il candidato se e' abbastanza tondo ED e' il piu' grande visto
        if circularity > 0.3 and area > max_area:
            max_area = area
            migliore_cerchio = (x, y, radius)

    return migliore_cerchio


def main():
    # Apro la webcam. 0 = prima webcam del computer (1 = seconda, ecc.)
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Errore: Impossibile aprire la webcam.")
        return

    print(
        "Webcam HSV avviata. Inquadra il bersaglio. Premi 'q' per uscire."
    )

    # Ciclo infinito: un giro = un fotogramma elaborato
    while True:
        # Leggo un fotogramma. ret = True se la lettura e' riuscita,
        # img_bgr = l'immagine. OpenCV usa l'ordine colori Blu-Verde-Rosso (BGR).
        ret, img_bgr = cap.read()
        if not ret:
            break  # niente frame: esco dal ciclo

        # Converto l'immagine da BGR a HSV (tutta in una volta)
        img_hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        h, w = img_bgr.shape[:2]  # altezza e larghezza dell'immagine

        # Funzione "di comodo" che legge il pixel HSV in (x, y).
        # Prima limita x e y dentro i bordi dell'immagine, cosi' non si
        # va mai fuori e non si ottiene un errore.
        # Nota: nelle immagini NumPy si indica prima la riga (y), poi la colonna (x).
        def get_hsv(x, y):
            x = max(0, min(w - 1, x))
            y = max(0, min(h - 1, y))
            return img_hsv[y, x]

        # Cerco il bersaglio nel frame corrente
        t = trova_target_opencv(img_bgr, img_hsv)

        if t is not None:
            cx, cy, R = t
            # Cerchio verde attorno al bersaglio (spessore 2)
            # (i colori in OpenCV sono (B, G, R): (0,255,0) = verde)
            cv2.circle(img_bgr, (int(cx), int(cy)), int(R), (0, 255, 0), 2)
            # Pallino rosso pieno (-1 = riempito) nel centro
            cv2.circle(img_bgr, (int(cx), int(cy)), 3, (0, 0, 255), -1)

            # Leggo i colori dei 5 anelli e calcolo punteggio e ripetizioni
            anelli = leggi_anelli_geometrici(get_hsv, cx, cy, R)
            p_tot = punteggio(anelli)
            ripetuti = verifica_anelli_consecutivi(anelli)

            # Scrivo il punteggio sull'immagine
            # putText(immagine, testo, posizione(x,y), font, dimensione, colore, spessore)
            cv2.putText(
                img_bgr,
                f"Punteggio: {p_tot}",
                (30, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2,
            )
            # Scrivo l'elenco dei colori degli anelli
            cv2.putText(
                img_bgr,
                f"Anelli: {', '.join(anelli)}",
                (30, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2,
            )

            # Se ci sono anelli adiacenti dello stesso colore, avviso in rosso
            if ripetuti:
                cv2.putText(
                    img_bgr,
                    f"ATTENZIONE: Consecutivi {', '.join(ripetuti)}",
                    (30, 120),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 0, 255),
                    2,
                )
        else:
            # Nessun bersaglio trovato: messaggio in rosso
            cv2.putText(
                img_bgr,
                "Nessun bersaglio trovato",
                (30, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 255),
                2,
            )

        # Mostro il frame in una finestra
        cv2.imshow("Riconoscimento Bersaglio - Webcam HSV", img_bgr)
        # waitKey(1) aspetta 1 ms un tasto e permette alla finestra di aggiornarsi.
        # "& 0xFF" isola l'ultimo byte del codice tasto; ord("q") = codice di 'q'.
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    # Pulizia finale: rilascio la webcam e chiudo le finestre
    cap.release()
    cv2.destroyAllWindows()


# Questo blocco fa partire main() solo se il file viene eseguito direttamente
# (e non se viene importato da un altro script).
if __name__ == "__main__":
    main()
