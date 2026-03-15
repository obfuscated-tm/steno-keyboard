import board
import digitalio
import usb_hid
import time
import usb_cdc

def make_pin(gp_num):
    pin = digitalio.DigitalInOut(getattr(board, f"GP{gp_num}"))
    pin.direction = digitalio.Direction.INPUT
    pin.pull = digitalio.Pull.UP
    return pin

PINS = {
    "STN_S":    make_pin(0), # BTN 0
    "STN_TL":   make_pin(1), # BTN 1
    "STN_PL":   make_pin(2), # BTN 2
    "STN_HL":   make_pin(3), # BTN 3
    "STN_ST1":  make_pin(4), # BTN 4
    "STN_KL":   make_pin(5), # BTN 11
    "STN_WL":   make_pin(6), # BTN 12
    "STN_RL":   make_pin(7), # BTN 13
    "NUML":     make_pin(8), # BTN 19
    "STN_A":    make_pin(9), # BTN 20
    "STN_O":    make_pin(10), # BTN 21
    "STN_E":    make_pin(11), # BTN 22
    "STN_U":    make_pin(12), # BTN 23
    "NUMR":     make_pin(13), # BTN 24
    "STN_ZR":   make_pin(14), # BTN 18
    "STN_SR":   make_pin(15), # BTN 17
    "STN_GR":   make_pin(16), # BTN 16
    "STN_BR":   make_pin(17), # BTN 15
    "STN_RR":   make_pin(18), # BTN 14
    "STN_ST3":  make_pin(19), # BTN 5
    "STN_FR":   make_pin(20), # BTN 6
    "STN_PR":   make_pin(21), # BTN 7
    "STN_LR":   make_pin(22), # BTN 8
    "STN_TR":   make_pin(27), # BTN 9
    "STN_DR":   make_pin(28) # BTN 10
}

DEBOUNCE_MS = 10 # debounce time in milliseconds for the keys
CHORD_WINDOW_MS = 50 # time window in milliseconds to consider keys as part of the same chord
steno_device = None
for device in usb_hid.devices:
    if device.usage_page == 0xFF50:
        steno_device = device
        break
    
def is_pressed(pin):
    return not pin.value

# Return which keys are currently pressed
def read_keys():
    return {name: is_pressed(pin) for name, pin in PINS.items()}

# Debounce logic, counts a key as pressed only if it's still pressed after DEBOUNCE_MS milliseconds
def debounce_read():
    first = read_keys()
    time.sleep(DEBOUNCE_MS / 1000)
    second = read_keys()
    return {name: first[name] and second[name] for name in PINS}

# Adds newly pressed keys into the chord
def merge_chord(accumulated, new_read):
    return {name: accumulated[name] or new_read[name] for name in PINS}

def build_gemini_report(chord):
    """
    Turning a chord into a 6-byte GeminiPR report according to the spec:
    https://docs.qmk.fm/features/stenography

    Byte 0: 1 Fn  #1  #2 #3 #4 #5   #6
    Byte 1: 0 S1- S2- T- K- P- W-   H-
    Byte 2: 0 R-  A-  O- *1 *2 res1 res2
    Byte 3: 0 pwr *3  *4 -E -U -F   -R
    Byte 4: 0 -P  -B  -L -G -T -S   -D
    Byte 5: 0 #7  #8  #9 #A #B #C   -Z
    """
    
    # If either num bar keys are pressed, true
    num = chord["NUML"] or chord["NUMR"]
    
    # If either asterisk keys are pressed, true
    ast = chord["STN_ST1"] or chord["STN_ST3"]

    bits = [
        # Byte 0: 1 Fn #1 #2 #3 #4 #5 #6
        True,  False, num, num, num, num, num, num,
        # Byte 1: 0 S1- S2- T- K- P- W- H-
        False, chord["STN_S"], chord["STN_S"], chord["STN_TL"], chord["STN_KL"], chord["STN_PL"], chord["STN_WL"], chord["STN_HL"],
        # Byte 2: 0 R- A- O- *1 *2 res res
        False, chord["STN_RL"], chord["STN_A"], chord["STN_O"], ast, ast, False, False,
        # Byte 3: 0 pwr *3 *4 -E -U -F -R
        False, False, ast, ast, chord["STN_E"], chord["STN_U"], chord["STN_FR"], chord["STN_RR"],
        # Byte 4: 0 -P -B -L -G -T -S -D
        False, chord["STN_PR"], chord["STN_BR"], chord["STN_LR"], chord["STN_GR"], chord["STN_TR"], chord["STN_SR"], chord["STN_DR"],
        # Byte 5: 0 #7 #8 #9 #A #B #C -Z
        False, num, num, num, num, num, num, chord["STN_ZR"],
    ]

    # Pack every 8 bits into a byte, set MSB for first byte
    result = []
    for b in range(6):
        byte_val = 0
        for i in range(8):
            if bits[b * 8 + i]:
                byte_val |= (1 << (7 - i))
        result.append(byte_val)

    return bytes(result)

def send_chord(chord):
    usb_cdc.data.write(build_gemini_report(chord))

# MAIN LOOP
BLANK_REPORT = bytes(6)
BLANK_CHORD  = {name: False for name in PINS}

# The chord itself, initally blank, and builds up over time as keys are pressed
accumulated = dict(BLANK_CHORD)
# Timestamp of when the chord started 
chord_start_ms: int | None = None
# Tracks if whether we're mid-chord 
in_chord = False

while True:
    current = debounce_read()
    any_pressed = any(current.values()) # Turns dict into array of keys

    # If any keys are pressed, we're either starting a new chord or continuing an existing chord
    if any_pressed:
        if not in_chord:
            in_chord = True
            chord_start_ms = time.monotonic_ns() // 1_000_000 
        accumulated = merge_chord(accumulated, current)
    else:
        if in_chord:
            elapsed = (time.monotonic_ns() // 1_000_000) - chord_start_ms
            remaining = CHORD_WINDOW_MS - elapsed
            if remaining > 0:
                time.sleep(remaining / 1000)
                accumulated = merge_chord(accumulated, debounce_read())
            send_chord(accumulated)
            accumulated = dict(BLANK_CHORD)
            chord_start_ms = None
            in_chord = False

    time.sleep(0.001)