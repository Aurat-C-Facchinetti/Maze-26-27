from gpiozero import Button
import time

BUTTON_PIN = 21
_button = None

def setup_button():
    global _button
    _button = Button(BUTTON_PIN, pull_up=True, bounce_time=0.05)

def wait_for_press():
    _button.wait_for_press()
    _button.wait_for_release()
