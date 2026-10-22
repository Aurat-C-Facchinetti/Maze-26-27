class Coordinata:
    def __init__(self):
        self.x = 0
        self.y = 0

    def getCoordinate(self):
        return (self.y, self.x)

    def incrementoX(self):
        self.x += 1

    def decrementoX(self):
        self.x -= 1

    def incrementoY(self):
        self.y += 1

    def decrementoY(self):
        self.y -= 1
