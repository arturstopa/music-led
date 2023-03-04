import pigpio
from flask import Flask, request

server = Flask(__name__)

rpi = pigpio.pi()
pwm_pin = 12
rpi.set_PWM_range(pwm_pin, 100)


@server.route("/led_brightness")
def led_brightness():
    brightness = request.form.get("brightness", None)
    if brightness is not None:
        try:
            rpi.set_PWM_dutycycle(pwm_pin, int(brightness))
        except:
            print("Error during setting LED brightness, skipping the request")


if __name__ == "__main__":
    server.run("0.0.0.0")
