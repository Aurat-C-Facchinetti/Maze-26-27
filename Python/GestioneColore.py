from imps import *
import board
import busio
import time
import adafruit_tcs34725
from gpiozero import DigitalOutputDevice

pin_interrupt = DigitalOutputDevice(27)

i2c = busio.I2C(board.SCL, board.SDA)
sensor = adafruit_tcs34725.TCS34725(i2c)

sensor.integration_time = 100
sensor.gain = 4


def check_black(run_event, stop_event):
    while not stop_event.is_set():
        if run_event.is_set():
            r, g, b, c = sensor.color_raw
            if c < 100:
                print("~~~~~~~ BLACK DETECTED ~~~~~~~")
                pin_interrupt.on()
                time.sleep(0.05)
                pin_interrupt.off()
            time.sleep(0.05)
        else:
            run_event.wait()


def check_color():
    r, g, b, c = sensor.color_raw
    detected_color = 1

    if (c < 100):
        print("BLACK detected")
        detected_color = 2
    elif (b > r and b > g):
        print("BLUE detected")
        detected_color = 3
    elif (c > 700 and c < 850):
        print("REFLECTIVE detected")
        detected_color = 5
    elif (r > g and r > b):
        print("RED detected")
    else:
        print("WHITE detected")

    print("detected color:", detected_color)

    return detected_color
