import time
import serial
from Coordinate import Coordinate


class Robot:
    def __init__(self):
        self.coordinata = Coordinate()
        self.seriale = None
        self.gradi = 0

    def inizializzaSeriale(self):
        self.seriale = serial.Serial('/dev/ttyUSB0',115200, timeout=1)

    def checkCommand(self, parCommand):
        comandoRicevuto = ""
        while comandoRicevuto != parCommand:
            comandoRicevuto = self.seriale.readline().decode('utf-8').rstrip()
            time.sleep(0.01)


    def checkConfermaMovimento(self):
        comandoRicevuto = ""
        while comandoRicevuto != "1" and comandoRicevuto != "-1":
            comandoRicevuto = self.seriale.readline().decode('utf-8').rstrip()
            time.sleep(0.01)

        if comandoRicevuto == "1":
            return True
        elif comandoRicevuto == "-1":
            return False

    def normalizzaAngolo(self):
        self.gradi = ((self.gradi % 360) + 360) % 360

    def rotateRight(self):
        self.seriale.write(b'd090,')
        self.checkCommand("True")
        self.checkConfermaMovimento()
        self.gradi += 90
        self.normalizzaAngolo()

    def rotateLeft(self):
        self.seriale.write(b'a090,')
        self.checkCommand("True")
        self.checkConfermaMovimento()
        self.gradi -= 90
        self.normalizzaAngolo()

    def Avanti(self):
        self.seriale.write(b'w032,')
        self.checkCommand("True")
        self.checkConfermaMovimento()
        dx, dy = self.headingToDelta()

        if dx == 1:
            self.coordinata.incrementoX()
        elif dx == -1:
            self.coordinata.decrementoX()

        if dy == 1:
            self.coordinata.incrementoY()
        elif dy == -1:
            self.coordinata.decrementoY()

    def headingToDelta(self):
        if self.gradi == 0:
            return (0,-1)
        elif self.gradi == 90:
            return (1,0)
        elif self.gradi == 180:
            return (0,1)
        elif self.gradi == 270:
            return (-1,0)

    def trova_muro(self, par_tof, par_dir):
        self.seriale.write(par_tof.encode())
        if self.checkCommand():
            is_wall = -1
            while is_wall == -1:
                is_wall = int(self.seriale.readline().decode('utf-8').rstrip())
                print("is_wall", is_wall)
            return is_wall


    def checkInclinazione(self):
        self.seriale.write(b'i,')
        if self.checkCommand():
            inclination = 999
            while inclination == 999:
                inclination = float(self.seriale.readline().decode('utf-8').rstrip())
            return inclination

