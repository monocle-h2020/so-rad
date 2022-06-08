


try:
    import RPi.GPIO as GPIO
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
except Exception as msg:
    log.warning("Could not import GPIO. Functionality may be limited to system tests.\n{0}".format(msg))
