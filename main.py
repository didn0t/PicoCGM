import network
import rp2
import time
import machine
import requests
import ntptime
from pimoroni import Button
from picographics import PicoGraphics, DISPLAY_PICO_DISPLAY_2, PEN_P4
 

def wifi_connect():
    display_message('Connecting...')

    rp2.country('GB')
    wlan = network.WLAN(network.STA_IF)
    wlan.config(hostname = 'PicoCGM')
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASSWORD)
    timeout = 15
    while timeout > 0:
        if wlan.status() < 0 or wlan.status() >= 3:
            break
        timeout -= 1
        print(f'[*] Waiting for connection... {timeout}')
        time.sleep(1)    
    if wlan.status() != 3:
        machine.reset()
    else:
        display_message('WIFI Up')
        print(f"[+] Connected to {WIFI_SSID} with IP address {wlan.ifconfig()[0]}")
        print("[+] Setting Time via NTP...")
        ntptime.settime()
        print("[+] UTC time after synchronization：%s" %str(time.localtime()))
    return wlan


def scale_to_range(number, old_min, old_max, new_min, new_max):
    if number < old_min:
        number = old_min
    elif number > old_max:
        number = old_max
    old_range = old_max - old_min
    new_range = new_max - new_min
    scaled_number = int(((number - old_min) / old_range) * new_range + new_min)
    return scaled_number


def severity(BG):
    if BG <= 72:
        return BLUE
    elif BG <= 180:
        return GREEN
    elif BG <= 260:
        return YELLOW
    else:
        return RED


def fetch_nightscout_data(delta):
    api = f"/api/v1/entries/sgv.json?find[date][$gte]={delta}&count={WIDTH//8}"
    url = NIGHTSCOUT_URL + api
    print(f"[*] Requesting data from NightScout API: {url}")
    headers = {"API-SECRET": f"{NIGHTSCOUT_TOKEN}"}
    try:
        response = requests.get(url, headers=headers)
        return response.json()
    except Exception as err:
        print(f"[-] Unexpected {err=}, {type(err)=}")
        return None
    
    
def draw_arrow(direction, x, y, pen):
    direction_map = {           
        "SingleUp": 	(0,2,1,0,2,2),
        "FortyFiveUp": 	(0,0,2,0,2,2),
        "Flat": 		(0,0,1,1,0,2),
        "FortyFiveDown":(0,2,2,0,2,2),
        "SingleDown": 	(0,0,1,2,2,0),
    }
    scale = 12
    x1, y1, x2, y2, x3, y3 = direction_map[direction]
    display.set_pen(pen)
    display.triangle(x+x1*scale, y+y1*scale, x+x2*scale, y+y2*scale, x+x3*scale, y+y3*scale)


def display_text(bg, obg, direction, end):
    scale = 4
    prefix=""
    display.set_pen(severity(bg))
    diff = bg-obg
    if mmol:
        bg = round(bg/18, 1)
        diff = round(diff/18, 1)
    display.text(str(bg), 0, 0, 0, scale)
    pad = display.measure_text(str(bg), scale) 
    draw_arrow(direction, pad, 0, BLUE)
    if diff > 0:
        prefix = "+"        
    diff = prefix + str(diff)
    display.text(diff, pad+25, 0, 0, scale)
    # Display Time
    _, _, _, hour, min, _, _, _ = time.gmtime()
    if DST:
        hour += 1
    hour += UTC_OFFSET
    hour %= 24
    last = round((time.time() - end) / 60)
    if last > 60:
        last = str(round(last / 60)) + "h"
    else:
        last = str(last) + "m"
    text = (f"{hour}:{min:02d} {last}")
    pad = display.measure_text(text, scale)
    display.set_pen(GREY)
    display.text(text, WIDTH-pad, 0, -1, scale)

    
def display_graph(data):
    if data != None:
        start = data[-1]['date']//1000
        end = data[0]['date']//1000
        display.set_pen(BLACK)
        display.clear()
        for entry in data:
            sgv = entry.get('sgv', 0)
            date = (entry.get('date', 0)//1000) - start 
            if date < 0:   # We need enough data for the width but it may return data before the time we asked for!
                continue
            y_scaled = scale_to_range(sgv, y_scale_min, y_scale_max, 2, HEIGHT-10)
            x_scaled = scale_to_range(date, 0, time.time()-start, 0, WIDTH-1)
            y = HEIGHT - y_scaled
            #print(f"[DEBUG] {date}->{x_scaled}: {sgv}->{y_scaled} ({y})")
            display.set_pen(severity(sgv))
            display.circle(x_scaled, y, 2)  
        display_text(data[0]['sgv'], data[1]['sgv'], data[0]['direction'], end)
        display.update()
    
    
def display_message(message):    
    width = display.measure_text(message,4)
    print(f"[+] Displaying Message: {message} with length {width}")
    display.set_pen(BLACK)
    display.clear()
    display.set_pen(YELLOW)
    pad = int((WIDTH - width) / 2) # Center Text
    display.text(message, pad, 20, -1, 4)
    display.update()
    time.sleep(1)


def check_buttons(data):
    global mmol, DST, backlight
    
    if button_x.read():
        mmol = not mmol    # Toggle
        if mmol:
            display_message("mmol/L")
        else:
            display_message("mg/dL")
        display_graph(data)
    elif button_y.read():
        DST = not DST    # Toggle
        if DST:
            display_message("DST Enabled")
        else:
            display_message("DST Disabled")
        display_graph(data)
    elif button_a.read() and backlight <= 0.9:
        backlight += 0.1
        display.set_backlight(backlight)
    elif button_b.read() and backlight >= 0.1:
        backlight -= 0.1
        display.set_backlight(backlight)

        
################################################################
# Main Program
################################################################

# Configure Display Buttons
button_a = Button(12)
button_b = Button(13)
button_x = Button(14)
button_y = Button(15)

# create the rtc object
rtc = machine.RTC()

# Initialize PicoGraphics for Display
backlight = 0.5
display = PicoGraphics(display=DISPLAY_PICO_DISPLAY_2, pen_type=PEN_P4, rotate=0)
display.set_backlight(backlight)
display.set_font("bitmap8")
WIDTH, HEIGHT = display.get_bounds()

BLACK = display.create_pen(0, 0, 0)
GREY = display.create_pen(150, 150, 150)
RED = display.create_pen(255, 0, 0)
GREEN = display.create_pen(0, 255, 0)
BLUE = display.create_pen(0, 0, 255)
YELLOW = display.create_pen(255, 255, 0)

################################################################
# User Configurable Settings
################################################################
# Wi-FI Settings
WIFI_SSID = 'Your_SSID'
WIFI_PASSWORD = 'Your_Password'
# NightScout Settings
NIGHTSCOUT_URL = "https://nightscout.YourDomain.org"
NIGHTSCOUT_TOKEN = "Pico-0000111122223333"
# TimeZone Configuration
UTC_OFFSET = -5
DST = False  # Daylight Saving Time
# Min/Max Scale for Blood Glucose in mg/dL
y_scale_min = 54    #  3mmol
y_scale_max = 414   # 23mmol 
mmol = False   # Controls if to display mmol/L instead of mg/dL

wlan = wifi_connect()

last_execution_time = 0
interval_ms = 60 * 1000
data = None

# Main loop
while True:
    current_time = time.ticks_ms()
    if current_time - last_execution_time >= interval_ms:
        end = time.time()
        start = end - (WIDTH * 300)      # Libre logs every 5m so grab data going back that far...
        data = fetch_nightscout_data(start)
        display_graph(data)
        last_execution_time = current_time
    check_buttons(data)
    time.sleep_ms(100)
    


################################################################
# User Configurable Settings
################################################################
# Wi-FI Settings
WIFI_SSID = 'Your_SSID'
WIFI_PASSWORD = 'Your_Wifi_Password'
# NightScout Settings
NIGHTSCOUT_URL = "https://nightscout.mydomain.org"
NIGHTSCOUT_TOKEN = "mytoken-25b31fd888888882"
# TimeZone Configuration
UTC_OFFSET = 0
DST = True  # Daylight Saving Time
# Min/Max Scale for Blood Glucose in mg/dL
y_scale_min = 54    #  3mmol
y_scale_max = 414   # 23mmol 
mmol = True   # Controls if to display mmol/L instead of mg/dL
