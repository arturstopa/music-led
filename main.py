import argparse
import queue
import sys
import time

from matplotlib.animation import FuncAnimation
import matplotlib.pyplot as plt
import numpy as np
import sounddevice as sd
import pigpio


def int_or_str(text):
    try:
        return int(text)
    except ValueError:
        return text


parser = argparse.ArgumentParser(add_help=False)
parser.add_argument(
    "-l",
    "--list-devices",
    action="store_true",
    help="show list of audio devices and exit",
)
args, remaining = parser.parse_known_args()
if args.list_devices:
    print(sd.query_devices())
    parser.exit(0)
parser = argparse.ArgumentParser(
    description=__doc__,
    formatter_class=argparse.RawDescriptionHelpFormatter,
    parents=[parser],
)
parser.add_argument(
    "channels",
    type=int,
    default=[1],
    nargs="*",
    metavar="CHANNEL",
    help="input channels to plot (default: the first)",
)
parser.add_argument(
    "-d", "--device", type=int_or_str, help="input device (numeric ID or substring)"
)
parser.add_argument(
    "-w",
    "--window",
    type=float,
    default=200,
    metavar="DURATION",
    help="visible time slot (default: %(default)s ms)",
)
parser.add_argument(
    "-i",
    "--interval",
    type=float,
    default=30,
    help="minimum time between plot updates (default: %(default)s ms)",
)
parser.add_argument("-b", "--blocksize", type=int, help="block size (in samples)")
parser.add_argument(
    "-r", "--samplerate", type=float, help="sampling rate of audio device"
)
parser.add_argument(
    "-n",
    "--downsample",
    type=int,
    default=10,
    metavar="N",
    help="display every Nth sample (default: %(default)s)",
)
parser.add_argument(
    "-g", "--graph", action="store_true", help="plot audio on a live graph"
)
args = parser.parse_args(remaining)
if any(c < 1 for c in args.channels):
    parser.error("argument CHANNEL: must be >= 1")
mapping = [c - 1 for c in args.channels]  # Channel numbers start with 1
q = queue.Queue()

rpi = pigpio.pi()
pwm_pin = 12
rpi.set_PWM_range(pwm_pin, 100)
previous_brightness_q = queue.Queue()
previous_brightness_q.put(int(0.5) * 100)


def update_led_brightness(data):
    sound_amplitude = max(max(data), abs(min(data)))
    MIN_BRIGHTNESS = 0.5
    MAX_BRIGHTNESS = 1
    previous_brightness = previous_brightness_q.get()
    led_brightness = int(min(sound_amplitude + MIN_BRIGHTNESS, MAX_BRIGHTNESS) * 100)
    previous_brightness_q.put(led_brightness)
    if abs(previous_brightness - led_brightness) > 2:
        for brightness in np.linspace(previous_brightness, led_brightness, 20):
            rpi.set_PWM_dutycycle(pwm_pin, int(brightness))
            print(int(brightness))


def audio_callback(indata, frames, time, status):
    """This is called (from a separate thread) for each audio block."""
    if status:
        print(status, file=sys.stderr)
    # Fancy indexing with mapping creates a (necessary!) copy:
    data = indata[:: args.downsample, mapping]
    q.put(data)
    update_led_brightness(data)


def update_plot(frame):
    """This is called by matplotlib for each plot update.

    Typically, audio callbacks happen more frequently than plot updates,
    therefore the queue tends to contain multiple blocks of audio data.

    """
    global plotdata
    while True:
        try:
            data = q.get_nowait()
        except queue.Empty:
            break
        shift = len(data)
        plotdata = np.roll(plotdata, -shift, axis=0)
        plotdata[-shift:, :] = data
    for column, line in enumerate(lines):
        line.set_ydata(plotdata[:, column])
    return lines


try:
    if args.samplerate is None:
        device_info = sd.query_devices(args.device, "input")
        args.samplerate = device_info["default_samplerate"]

    stream = sd.InputStream(
        device=args.device,
        channels=max(args.channels),
        samplerate=args.samplerate,
        callback=audio_callback,
    )

    if args.graph:
        length = int(args.window * args.samplerate / (1000 * args.downsample))
        plotdata = np.zeros((length, len(args.channels)))

        fig, ax = plt.subplots()
        lines = ax.plot(plotdata)
        if len(args.channels) > 1:
            ax.legend(
                [f"channel {c}" for c in args.channels],
                loc="lower left",
                ncol=len(args.channels),
            )
        ax.axis((0, len(plotdata), -1, 1))
        ax.set_yticks([0])
        ax.yaxis.grid(True)
        ax.tick_params(
            bottom=False,
            top=False,
            labelbottom=False,
            right=False,
            left=False,
            labelleft=False,
        )
        fig.tight_layout(pad=0)
        ani = FuncAnimation(fig, update_plot, interval=args.interval, blit=True)
        with stream:
            plt.show()

    with stream:
        input()
except Exception as e:
    parser.exit(type(e).__name__ + ": " + str(e))
finally:
    rpi.stop()
