from machine import Pin, UART
import sys
import time

# GPIO pin mapping for each steno key
PINS = {
    "STN_S":    Pin(1, Pin.IN, Pin.PULL_UP), # BTN 0
    "STN_TL":   Pin(2, Pin.IN, Pin.PULL_UP), # BTN 1
    "STN_PL":   Pin(4, Pin.IN, Pin.PULL_UP), # BTN 2
    "STN_HL":   Pin(5, Pin.IN, Pin.PULL_UP), # BTN 3
    "STN_ST1":  Pin(6, Pin.IN, Pin.PULL_UP), # BTN 4
    "STN_KL":   Pin(7, Pin.IN, Pin.PULL_UP), # BTN 11
    "STN_WL":   Pin(9, Pin.IN, Pin.PULL_UP), # BTN 12
    "STN_RL":   Pin(10, Pin.IN, Pin.PULL_UP), # BTN 13
    "NUML":     Pin(11, Pin.IN, Pin.PULL_UP), # BTN 19
    "STN_A":    Pin(12, Pin.IN, Pin.PULL_UP), # BTN 20
    "STN_O":    Pin(14, Pin.IN, Pin.PULL_UP), # BTN 21
    "STN_E":    Pin(15, Pin.IN, Pin.PULL_UP), # BTN 22
    "STN_U":    Pin(16, Pin.IN, Pin.PULL_UP), # BTN 23
    "NUMR":     Pin(17, Pin.IN, Pin.PULL_UP), # BTN 24
    "STN_ZR":   Pin(19, Pin.IN, Pin.PULL_UP), # BTN 18
    "STN_SR":   Pin(20, Pin.IN, Pin.PULL_UP), # BTN 17
    "STN_GR":   Pin(21, Pin.IN, Pin.PULL_UP), # BTN 16
    "STN_BR":   Pin(22, Pin.IN, Pin.PULL_UP), # BTN 15
    "STN_RR":   Pin(24, Pin.IN, Pin.PULL_UP), # BTN 14
    "STN_ST3":  Pin(25, Pin.IN, Pin.PULL_UP), # BTN 5
    "STN_FR":   Pin(26, Pin.IN, Pin.PULL_UP), # BTN 6
    "STN_PR":   Pin(27, Pin.IN, Pin.PULL_UP), # BTN 7
    "STN_LR":   Pin(29, Pin.IN, Pin.PULL_UP), # BTN 8
    "STN_TR":   Pin(32, Pin.IN, Pin.PULL_UP), # BTN 9
    "STN_DR":   Pin(34,Pin.IN, Pin.PULL_UP) # BTN 10
}

DEBOUNCE_MS = 10 # debounce time in milliseconds for the keys
CHORD_WINDOW_MS = 50 # time window in milliseconds to consider keys as part of the same chord
serial = sys.stdout.buffer

def is_pressed(pin):
    return pin.value() == 0

# Return which keys are currently pressed
def read_keys():
    return {name: is_pressed(pin) for name, pin in PINS.items()}

# Debounce logic, counts a key as pressed only if it's still pressed after DEBOUNCE_MS milliseconds
def debounce_read():
    first  = read_keys()
    time.sleep_ms(DEBOUNCE_MS)
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
    serial.write(build_gemini_report(chord))





# MAIN LOOP
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
            chord_start_ms = time.ticks_ms()
        accumulated = merge_chord(accumulated, current)
    else:
        if in_chord:
            assert chord_start_ms is not None # small little safety check
            
            elapsed = time.ticks_diff(time.ticks_ms(), chord_start_ms)
            remaining = CHORD_WINDOW_MS - elapsed
            if remaining > 0:
                time.sleep_ms(remaining)
                accumulated = merge_chord(accumulated, debounce_read())

            send_chord(accumulated)

            # Reset for next chord
            accumulated = dict(BLANK_CHORD)
            chord_start_ms = None
            in_chord = False

    time.sleep_ms(1)