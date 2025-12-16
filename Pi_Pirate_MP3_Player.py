#!/usr/bin/env python3

"""Copyright (c) 2025
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE."""

from gpiozero import Button
import glob
import subprocess
import os, sys
import time
import datetime
import random
from random import shuffle
from mutagen.mp3 import MP3
import alsaaudio
from signal import signal, SIGTERM, SIGHUP, pause
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont
import ST7789

version  = "1.07"

# set default variables (saved in config_file and overridden at future startups)
MP3_Play     = 0   # set to 1 to start playing MP3s at boot, else 0
radio        = 0   # set to 1 to start playing Radio at boot, else 0
radio_stn    = 0   # selected radio station at startup 
shuffled     = 0   # 0 = Unshuffled, 1 = Shuffled
album_mode   = 0   # set to 1 for Album Mode, will play an album then stop
gapless      = 0   # set to 1 for gapless play
volume       = 40  # range 0 - 100
Track_No     = 0   # start track number

# variables set once
use_USB      = 1   # set to 0 if you ONLY use /home/pi/Music/... on SD card
usb_timer    = 6   # seconds to find USB present
sleep_timer  = 0   # sleep_timer timer in minutes, use 15,30,45,60 etc...set to 0 to disable
sleep_shutdn = 0   # set to 1 to shutdown Pi when sleep times out
Disp_timer   = 60  # Display timeout in seconds, set to 0 to disable
show_clock   = 1   # set to 1 to show clock, only use if on web or using RTC
gaptime      = 2   # set pre-start time for gapless, in seconds

Radio_Stns = ["Radio Paradise Rock","http://stream.radioparadise.com/rock-192",
              "Radio Paradise Main","http://stream.radioparadise.com/mp3-320",
              "Radio Paradise Mellow","http://stream.radioparadise.com/mellow-192",
              "Radio Caroline","http://sc6.radiocaroline.net:10558/",
              "BBC World Service","http://stream.live.vc.bbcmedia.co.uk/bbc_world_service"]

# GPIO BUTTONS GPIO BCM numbers (Physical pin numbers)
PLAY  = 5  # (29) PLAY / STOP / HOLD for 3 seconds for RADIO 
SLEEP = 24 # (18) Set SLEEP time, HOLD for 20 seconds to SHUTDOWN, set GAPLESS/SHUTDOWN whilst stopped.
VOLUP = 6  # (31) Adjust volume UP whilst playing, set ALBUM MODE/RANDOM ON/OFF whilst stopped
NEXT  = 16 # (36) HOLD for NEXT TRACK / STATION (whilst playing) / NEXT ALBUM (whilst stopped) - quick press for PREVIOUS 

#display_type = "square"
disp = ST7789.ST7789(
        height=240, 
        rotation=90,
        port=0,
        cs=1,
        dc=9,
        backlight=13,               
        spi_speed_hz=80 * 1000 * 1000,
        offset_left=0,
        offset_top=0, 
    )

# Initialize display.
disp.begin()
WIDTH = disp.width
HEIGHT = disp.height
img = Image.new('RGB', (WIDTH, HEIGHT), color=(0, 0, 0))
draw = ImageDraw.Draw(img)
font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)

# check config file exists, if not then write default values
config_file = "OLEDconfig.txt"
if not os.path.exists(config_file):
    defaults = [MP3_Play,radio,radio_stn,shuffled,album_mode,volume,gapless,Track_No]
    with open(config_file, 'w') as f:
        for item in defaults:
            f.write("%s\n" % item)

# read config file
config = []
with open(config_file, "r") as file:
   line = file.readline()
   while line:
      config.append(line.strip())
      line = file.readline()
config = list(map(int,config))

MP3_Play   = config[0]
radio      = config[1]
radio_stn  = config[2]
shuffled   = config[3]
album_mode = config[4]
volume     = config[5]
gapless    = config[6]
Track_No   = config[7]

if Track_No < 0:
    Track_No = 0

# read Radio_Stns.txt - format: Station Name,Station URL,0
if os.path.exists ("radio_stns.txt"): 
    with open("radio_stns.txt","r") as textobj:
        line = textobj.readline()
        while line:
           if line.count(",") == 2:
               a,b,c = line.split(",")
               Radio_Stns.append(a)
               Radio_Stns.append(b.strip())
           line = textobj.readline()

# setup GPIO for buttons
buttonPLAY  = Button(PLAY)
buttonNEXT  = Button(NEXT)
buttonVOLUP = Button(VOLUP)
buttonSLEEP = Button(SLEEP)

# initialise parameters
old_album   = 0
old_artist  = 0
titles      = [0,0,0,0,0,0,0]
itles       = [0,0,0,0,0,0,0]
sleep_timer = sleep_timer * 60
freedisk    = ["0","0","0","0"]
old_secs    = "00"
old_secs2   = "00"
Disp_on     = 1
album       = 0
stimer      = 0
ctracks     = 0
cplayed     = 0
stopped     = 0
atimer      = time.monotonic()
played_pc   = 0
synced      = 0
reloading   = 0
msg1        = "MP3 Player: v" + version
msg2        = ""
msg3        = ""
msg4        = ""
msg5        = ""
msg6        = ""
msg7        = ""
msg8        = ""
abort_sd    = 1
usb_found   = 0

# find username
h_user  = []
h_user.append(os.getlogin())

def display():
    global image,top,msg1,msg2,msg3,msg4,msg5,msg6,msg7,msg8,font,img,MP3_Play,radio
    # Display image.
    draw.rectangle((0, 0, 240, 240), (0, 0, 0))
    draw.text((0, 0),msg1, font=font, fill=(0, 255, 0))
    draw.text((0,30),msg2, font=font, fill=(255, 2, 255))
    draw.text((0,60),msg3, font=font, fill=(255, 2, 255))
    draw.text((0,90),msg4, font=font, fill=(255, 2, 255))
    draw.text((0,120),msg5, font=font, fill=(255, 255, 255))
    draw.text((0,150),msg6, font=font, fill=(255, 255, 255))
    draw.text((0,180),msg7, font=font, fill=(255, 255, 255))
    draw.text((0,210),msg8, font=font, fill=(0, 255, 0))
    disp.display(img)
display()
time.sleep(1)
stop = 0

def reload():
  global tracks,x,top,msg1,msg2,Track_No,stop
  if stop == 0:
    tracks  = []
    msg1 = "Tracks: " + str(len(tracks))
    msg2 = "Reloading tracks... "
    display()
    usb_tracks  = glob.glob("/media/" + h_user[0] + "/*/*/*/*.mp3")
    sd_tracks = glob.glob("/home/" + h_user[0] + "/Music/*/*/*.mp3")
    titles = [0,0,0,0,0,0,0]
    if len(sd_tracks) > 0:
      for xx in range(0,len(sd_tracks)):
        titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = sd_tracks[xx].split("/")
        track = titles[4] + "/" + titles[5] + "/" + titles[6] + "/" + titles[0] + "/" + titles[1] + "/" + titles[2] + "/" + titles[3]
        tracks.append(track)
    if len(usb_tracks) > 0:
      for xx in range(0,len(usb_tracks)):
        titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = usb_tracks[xx].split("/")
        track = titles[4] + "/" + titles[5] + "/" + titles[6] + "/" + titles[0] + "/" + titles[1] + "/" + titles[2] + "/" + titles[3]
        tracks.append(track)
    if len(tracks) > 0:
        tracks.sort()
    with open('tracks.txt', 'w') as f:
        for item in tracks:
            f.write("%s\n" % item)
    msg1 = ("Tracks: " + str(len(tracks)))
    Track_No = 0
    defaults = [MP3_Play,radio,radio_stn,shuffled,album_mode,volume,gapless,Track_No]
    with open(config_file, 'w') as f:
        for item in defaults:
            f.write("%s\n" % item)
    display()
    if len(tracks) == 0:
        msg1 = "Tracks: " + str(len(tracks))
        msg2 = "Stopped Checking"
        display()
        stop = 1
    time.sleep(1)

def Set_Volume():
    global mixername,m,msg1,msg2,msg3,msg4,MP3_Play,radio,radio_stn,shuffled,album_mode,volume,gapless,buttonVOLUP
    msg1 = "Volume " + str(volume)
    display()
    timer1 = time.monotonic()
    while buttonVOLUP.is_pressed and time.monotonic() - timer1 < 0.5:
        pass
    while buttonVOLUP.is_pressed:
        if time.monotonic() - timer1 > 0.5:
            volume -= 2
            volume = max(volume,0)
            msg1 = "Volume " + str(volume)
            display()
            if len(alsaaudio.mixers()) > 0:
                m.setvolume(volume)
                os.system("amixer -D pulse sset Master " + str(volume) + "%")
                if mixername == "DSP Program":
                    os.system("amixer set 'Digital' " + str(volume + 107))
            else:
                os.system("wpctl set-volume @DEFAULT_AUDIO_SINK@ " + str(volume/100))
            time.sleep(0.5)
    if time.monotonic() - timer1 < 1:
        volume += 10
        time.sleep(0.5)
    if len(alsaaudio.mixers()) > 0:
        m.setvolume(volume)
    msg1 = "Volume " + str(volume)
    display()
    time.sleep(0.5)
    if len(alsaaudio.mixers()) > 0:
        os.system("amixer -D pulse sset Master " + str(volume) + "%")
        if mixername == "DSP Program":
            os.system("amixer set 'Digital' " + str(volume + 107))
    else:
        os.system("wpctl set-volume @DEFAULT_AUDIO_SINK@ " + str(volume/100))
    
    defaults = [MP3_Play,radio,radio_stn,shuffled,album_mode,volume,gapless,Track_No]
    with open(config_file, 'w') as f:
        for item in defaults:
            f.write("%s\n" % item)

def status():
    global txt,shuffled,gapless,album_mode,sleep_timer
    txt = " "
    if shuffled == 1:
        txt +="R"
    else:
        txt +=" "
    if gapless == 1:
        txt +="G"
    else:
        txt +=" "
    if album_mode == 1:
        txt +="A"
    else:
        txt +=" "
    if sleep_timer > 0:
        txt +="S"
    else:
        txt +=" "

# read previous usb free space of upto 4 usb devices, to see if usb data has changed
if not os.path.exists('freedisk.txt'):
    with open("freedisk.txt", "w") as f:
        for item in freedisk:
            f.write("%s\n" % item)
freedisk = []            
with open("freedisk.txt", "r") as file:
    line = file.readline()
    while line:
         freedisk.append(line.strip())
         line = file.readline()
         
# check if SD Card ~/Music has changed
if not os.path.exists('freeSD.txt'):
    with open("freeSD.txt", "w") as f:
            f.write("0")
with open("freeSD.txt", "r") as file:
    line = file.readline()

def get_dir_size(dir_path):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(dir_path):
        for file in filenames:
            file_path = os.path.join(dirpath, file)
            if not os.path.islink(file_path):
                total_size += os.path.getsize(file_path)
    return total_size

total_size = get_dir_size("/home/" +  h_user[0] + "/Music")
if line != str(total_size):
    with open("freeSD.txt", "w") as f:
        f.write(str(total_size))
    reloading = 1

# load MP3 tracks
tracks  = []
if not os.path.exists('tracks.txt') and stop == 0:
    reload()
else:
    with open("tracks.txt", "r") as file:
        line = file.readline()
        while line:
             tracks.append(line.strip())
             line = file.readline()
msg1 = "Tracks: " + str(len(tracks))
display()

# check if USB mounted and find USB storage
if use_USB == 1:
    start = time.monotonic()
    msg1 = ("Checking for USB")
    display()
    while time.monotonic() - start < usb_timer:
        usb = glob.glob("/media/" +  h_user[0] + "/*")
        usb_found = len(usb)
        msg2 = "Found: " + str(usb_found) + " USBs"
        msg3 = str(int(usb_timer -(time.monotonic() - start)))
        display()
        time.sleep(1)
    msg2 = ""
    msg3 = ""
    display()
    if usb_found > 0:
        # check if usb contents have changed, if so then reload tracks
        free = ["0","0","0","0"]
        for xy in range(0,len(usb)):
            st3 = os.statvfs(usb[xy])
            free[xy] = str((st3.f_bavail * st3.f_frsize)/1100000)
        for xy in range(0,3):
            if str(free[xy]) != freedisk[xy]:
                with open("freedisk.txt", "w") as f:
                    for item in free:
                        f.write("%s\n" % item)
                reloading = 1
    else:
        freedisk = ["0","0","0","0"]
        with open("freedisk.txt", "w") as f:
            for item in freedisk:
                f.write("%s\n" % item)
        msg2 = "No USB Found !!"
        display()
        sd_tracks = glob.glob("/home/" + h_user[0] + "/Music/*/*/*.mp3")
        time.sleep(2)
        if len(sd_tracks) != len(tracks):
            reloading = 1
        msg2 = ""
        display()

if reloading == 1 and stop == 0:
    reload()

# check for audio mixers
if len(alsaaudio.mixers()) > 0:
    for mixername in alsaaudio.mixers():
        if str(mixername) == "PCM" or str(mixername) == "DSP Program" or str(mixername) == "Master" or str(mixername) == "Capture" or str(mixername) == "Headphone" or str(mixername) == "HDMI":
            m = alsaaudio.Mixer(mixername)
        else:
            m = alsaaudio.Mixer(alsaaudio.mixers()[0])
    m.setvolume(volume)
    os.system("amixer -D pulse sset Master " + str(volume) + "%")
    if mixername == "DSP Program":
        os.system("amixer set 'Digital' " + str(volume + 107))
else:
    os.system("wpctl set-volume @DEFAULT_AUDIO_SINK@ " + str(volume/100))
        

# disable Radio Play if MP3 Play set
if MP3_Play == 1:
    radio = 0
    
# wait for internet connection
if radio == 1:
    msg1 = "Waiting for Radio..."
    display()
    time.sleep(10)
    q = subprocess.Popen(["mplayer", "-nocache", Radio_Stns[radio_stn+1]] ,shell=False)
    msg1 = (Radio_Stns[radio_stn])
    msg2 = ""
    display()
else:
    msg1 = "Initialising..."
    display()

# try reloading tracks if one selected not found
if len(tracks) > 0:
    titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
    track = titles[3] + "/" + titles[4] + "/" + titles[5] + "/" + titles[6] + "/" + titles[0] + "/" + titles[1] + "/" + titles[2]
    if not os.path.exists(track) and stop == 0:
        reload()

if album_mode == 1 and len(tracks) > 0:
    # determine album length and number of tracks
    cplayed = 0
    shuffled = 0
    if album_mode == 1:
        Tack_No = Track_No
        stimer  = 0
        stitles = [0,0,0,0,0,0,0]
        stitles[0],stitles[1],stitles[2],stitles[3],stitles[4],stitles[5],stitles[6] = tracks[Tack_No].split("/")
        talbum  = stitles[1]
        tartist = stitles[0]
        while stitles[1] == talbum and stitles[0] == tartist and Tack_No < len(tracks):
            stitles[0],stitles[1],stitles[2],stitles[3],stitles[4],stitles[5],stitles[6] = tracks[Tack_No].split("/")
            strack = stitles[3] + "/" + stitles[4] + "/" + stitles[5] + "/" + stitles[6] + "/" + stitles[0] + "/" + stitles[1] + "/" + stitles[2]
            audio = MP3(strack)
            stimer += audio.info.length
            Tack_No +=1
        audio = MP3(strack)
        stimer -= audio.info.length
        ctracks = Tack_No - Track_No - 1

status()
    
if shuffled == 1 and gapless == 0:
    gap = 0
    shuffle(tracks)
elif shuffled == 0 and gapless == 0:
    gap = 0
elif shuffled == 1 and gapless != 0:
    gap = gaptime
    shuffle(tracks)
elif shuffled == 0 and gapless != 0:
    gap = gaptime

if len(tracks) > 0:
    titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")

sleep_timer_start = time.monotonic()
Disp_start        = time.monotonic()
timer2            = time.monotonic()
sync_timer        = time.monotonic()
xt                = 0

# check if clock synchronised
msg1 = "Checking clock..."
display()
if os.path.exists ("/run/shm/sync.txt"):
    os.remove("/run/shm/sync.txt")
os.system("timedatectl >> /run/shm/sync.txt")
# read sync.txt file
try:
    sync = []
    with open("/run/shm/sync.txt", "r") as file:
        line = file.readline()
        while line:
            sync.append(line.strip())
            line = file.readline()
    if sync[4] == "System clock synchronized: yes":
        synced = 1
    else:
        synced = 0
except:
    pass

while True:
    # loop while stopped
    while MP3_Play == 0 and radio == 0:
        time.sleep(0.1)
        # check if clock synchronised
        if time.monotonic() - sync_timer > 30:
            sync_timer = time.monotonic()
            if os.path.exists ("/run/shm/sync.txt"):
                os.remove("/run/shm/sync.txt")
            os.system("timedatectl >> /run/shm/sync.txt")
            try:
                sync = []
                with open("/run/shm/sync.txt", "r") as file:
                    line = file.readline()
                    while line:
                        sync.append(line.strip())
                        line = file.readline()
                if sync[4] == "System clock synchronized: yes":
                    synced = 1
                else:
                    synced = 0
            except:
                pass
            
        # display Artist / Album / Track names
        if Disp_on == 1:
          msg1 = "<PLAY/Radio   NEXT>"
          if len(tracks) > 0:
            msg2 = titles[0][0:19]
            msg3 = titles[1][0:19]
            msg4 = titles[2][0:19]
            try:
                if int(titles[2][0:2]) > 0:
                    msg4 = titles[2][3:22]
            except:
                pass
            status()
          msg6 = "Status...  "  +  txt
          msg8 = "<ALB/RNDM     GAP>"
          if sleep_timer != 0:
              time_left = int((sleep_timer - (time.monotonic() - sleep_timer_start))/60)
              if sleep_shutdn == 1:
                  msg7 = "Shutdown: " + str(time_left) + "mins"
              else:
                  msg7 = "Stopping: " + str(time_left) + "mins"
          display()

        # display clock (if enabled and synced)
        if show_clock == 1 and Disp_on == 0 and synced == 1 and stopped == 0 and abort_sd == 1:
            now = datetime.datetime.now()
            clock = now.strftime("%H:%M:%S")
            secs = now.strftime("%S")
            t = ""
            for r in range (0,random.randint(0,10)):
                t += " "
            clock = t + clock
            if secs != old_secs2 :
              vp = random.randint(0,3)
              msg1 = ""
              msg2 = ""
              msg3 = ""
              msg4 = ""
              msg5 = ""
              msg6 = ""
              msg7 = ""
              msg8 = ""
              if vp == 0:
                msg1 = clock
              elif vp == 1:
                msg2 = clock
              elif vp == 2:
                msg3 = clock
              elif vp == 3:
                msg4 = clock
              elif vp == 4:
                msg5 = clock
              elif vp == 5:
                msg6 = clock
              elif vp == 6:
                msg7 = clock
              elif vp == 7:
                msg8 = clock
              display()
              old_secs2 = secs

        # DISPLAY OFF timer
        if time.monotonic() - Disp_start > Disp_timer and Disp_timer > 0 and Disp_on == 1:
            msg1 = ""
            msg2 = ""
            msg3 = ""
            msg4 = ""
            msg5 = ""
            msg6 = ""
            msg7 = ""
            msg8 = ""
            Disp_on = 0
            display()
            
        # sleep_timer timer
        if time.monotonic() - sleep_timer_start > sleep_timer and sleep_timer > 0:
            Disp_start = time.monotonic()
            abort_sd = 0
            t = 30
            while t > 0 and abort_sd == 0:
                if sleep_shutdn == 1:
                    msg2 = "SHUTDOWN in " + str(t)
                else:
                    msg2 = "STOPPING in " + str(t)
                display()
                if buttonSLEEP.is_pressed or buttonPLAY.is_pressed:
                    sleep_timer_start = time.monotonic()
                    sleep_timer = 900
                    abort_sd = 1
                t -=1
                time.sleep(1)
            if abort_sd == 0:
                if sleep_shutdn == 1:
                    msg1 = "SHUTTING DOWN..."
                else:
                    msg1 = "STOPPING........"
                msg2 = ""
                msg3 = ""
                msg4 = ""
                msg5 = ""
                msg6 = ""
                msg7 = ""
                msg8 = ""
                display()
                time.sleep(3)
                msg1 = ""
                display()
                sleep_timer = 0 
                if sleep_shutdn == 1:
                    os.system("sudo shutdown -h now")
            else:
                status()
                msg1 = "<PLAY/Radio   NEXT>"
                display()
            Disp_start = time.monotonic()
            
        # check for PLAY/STOP/RADIO key
        if buttonPLAY.is_pressed and Disp_on == 0:
            Disp_on = 1
            Disp_start = time.monotonic()
            status()
            msg1 = "<PLAY/Radio   NEXT>"
            time.sleep(0.5)
            timer2 = time.monotonic()
        elif buttonPLAY.is_pressed:
            stopped = 0
            Disp_on = 1
            Disp_start = time.monotonic()
            timer1 = time.monotonic()
            msg1 = "<PLAY/Radio   NEXT>"
            msg2 = "HOLD 3s for RADIO"
            msg3 = ""
            msg4 = ""
            msg5 = ""
            msg6 = ""
            msg7 = ""
            msg8 = ""
            display()
            time.sleep(0.5)
            sleep_timer = 0
            while buttonPLAY.is_pressed and time.monotonic() - timer1 < 3:
                pass
            if time.monotonic() - timer1 < 3 and len(tracks) > 0:
                # determine album length and number of tracks
                cplayed = 0
                if album_mode == 1:
                    Tack_No = Track_No
                    stimer  = 0
                    stitles = [0,0,0,0,0,0,0]
                    stitles[0],stitles[1],stitles[2],stitles[3],stitles[4],stitles[5],stitles[6] = tracks[Tack_No].split("/")
                    talbum = stitles[1]
                    tartist = stitles[0]
                    ptrack = stitles[3] + "/" + stitles[4] + "/" + stitles[5] + "/" + stitles[6] + "/" + stitles[0] + "/" + stitles[1] + "/"
                    pfiles = glob.glob(ptrack + "*.jpg")
                    if len(pfiles) > 0:
                        image=Image.open(pfiles[0])  
                        image=image.resize((240,240),resample=Image.LANCZOS)
                        disp.display(image)
                        time.sleep(1)
                        
                    while stitles[1] == talbum and stitles[0] == tartist and Tack_No < len(tracks):
                        stitles[0],stitles[1],stitles[2],stitles[3],stitles[4],stitles[5],stitles[6] = tracks[Tack_No].split("/")
                        strack = stitles[3] + "/" + stitles[4] + "/" + stitles[5] + "/" + stitles[6] + "/" + stitles[0] + "/" + stitles[1] + "/" + stitles[2]
                        audio = MP3(strack)
                        stimer += audio.info.length
                        Tack_No +=1
                    audio = MP3(strack)
                    stimer -= audio.info.length
                    ctracks = Tack_No - Track_No - 1
                    
                atimer = time.monotonic()
                MP3_Play = 1
                radio    = 0
                              
                time.sleep(2)
                defaults = [MP3_Play,radio,radio_stn,shuffled,album_mode,volume,gapless,Track_No]
                with open(config_file, 'w') as f:
                    for item in defaults:
                        f.write("%s\n" % item)
            else:
                msg2 = ""
                msg3 = ""
                msg4 = ""
                q = subprocess.Popen(["mplayer", "-nocache", Radio_Stns[radio_stn+1]] , shell=False)
                time.sleep(0.05)
                msg1 = (Radio_Stns[radio_stn])
                display()
                rs = Radio_Stns[radio_stn]
                while buttonPLAY.is_pressed:
                    pass
                if os.path.exists (rs + ".jpg"):
                    image=Image.open(rs + ".jpg")  
                    image=image.resize((240,240),resample=Image.LANCZOS)
                    disp.display(image)
                    time.sleep(1)
                radio    = 1
                MP3_Play = 0
                defaults = [MP3_Play,radio,radio_stn,shuffled,album_mode,volume,gapless,Track_No]
                with open(config_file, 'w') as f:
                    for item in defaults:
                        f.write("%s\n" % item)
                
        # check NEXT/PREVIOUS ALBUM/ARTIST/A-Z key
        if buttonNEXT.is_pressed and Disp_on == 0:
            Disp_on = 1
            Disp_start = time.monotonic()
            status()
            msg1 = "<PLAY/Radio   NEXT>"
            time.sleep(0.5)
            timer2 = time.monotonic()
        elif buttonNEXT.is_pressed and len(tracks) > 1:
            Disp_on = 1
            time.sleep(0.2)
            timer1 = time.monotonic()
            while buttonNEXT.is_pressed and time.monotonic() - timer1 < 1:
                pass
            if time.monotonic() - timer1 < 1:
                    while titles[1] == old_album and titles[0] == old_artist and Track_No > -1:
                        Track_No -=1
                        titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
                    old_album = titles[1]
                    old_artist = titles[0]
                    while titles[1] == old_album and titles[0] == old_artist and Track_No > -1:
                        Track_No -=1
                        titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
                    Track_No +=1
                    if Track_No > len(tracks) - 1:
                        Track_No = Track_No - len(tracks)
                    titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
                    old_album  = titles[1]
                    old_artist = titles[0]
                    Tack_No = Track_No
                    stitles = [0,0,0,0,0,0,0]
                    stitles[0],stitles[1],stitles[2],stitles[3],stitles[4],stitles[5],stitles[6] = tracks[Tack_No].split("/")
                    talbum = stitles[1]
                    tartist = stitles[0]
                    while stitles[1] == talbum and stitles[0] == tartist and Tack_No < len(tracks):
                        stitles[0],stitles[1],stitles[2],stitles[3],stitles[4],stitles[5],stitles[6] = tracks[Tack_No].split("/")
                        strack = stitles[3] + "/" + stitles[4] + "/" + stitles[5] + "/" + stitles[6] + "/" + stitles[0] + "/" + stitles[1] + "/" + stitles[2]
                        Tack_No +=1
                    ctracks = Tack_No - Track_No - 1
                    msg1 = "<PLAY/Radio   NEXT>" 
                    time.sleep(0.05)
                    msg2 = titles[0][0:19]
                    msg3 = titles[1][0:19]
                    msg4 = titles[2][0:19]
                    try:
                        if int(titles[2][0:2]) > 0:
                            msg4 = titles[2][3:22]
                    except:
                        pass
                    display()
                    time.sleep(0.05)
                    timer3 = time.monotonic()
                    album = 1
                    time.sleep(0.5)
            if time.monotonic() - timer1 > 1:
                # NEXT ALBUM
                while buttonNEXT.is_pressed and buttonSLEEP.is_pressed == 0 and buttonVOLUP.is_pressed == 0:
                    while titles[1] == old_album and titles[0] == old_artist and Track_No < len(tracks) - 1:
                        Track_No +=1
                        titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
                    old_album  = titles[1]
                    old_artist = titles[0]
                    Tack_No = Track_No
                    stitles = [0,0,0,0,0,0,0]
                    stitles[0],stitles[1],stitles[2],stitles[3],stitles[4],stitles[5],stitles[6] = tracks[Tack_No].split("/")
                    talbum = stitles[1]
                    tartist = stitles[0]
                    while stitles[1] == talbum and stitles[0] == tartist and Tack_No < len(tracks):
                        stitles[0],stitles[1],stitles[2],stitles[3],stitles[4],stitles[5],stitles[6] = tracks[Tack_No].split("/")
                        strack = stitles[3] + "/" + stitles[4] + "/" + stitles[5] + "/" + stitles[6] + "/" + stitles[0] + "/" + stitles[1] + "/" + stitles[2]
                        Tack_No +=1
                    ctracks = Tack_No - Track_No - 1
                    msg1 = "<PLAY/Radio   NEXT>" 
                    msg2 = titles[0][0:19]
                    msg3 = titles[1][0:19]
                    msg4 = titles[2][0:19]
                    try:
                        if int(titles[2][0:2]) > 0:
                            msg4 = titles[2][3:22]
                    except:
                        pass
                    display()
                    time.sleep(0.5)
                # NEXT ARTIST
                while buttonNEXT.is_pressed and buttonSLEEP.is_pressed:
                    while titles[0] == old_artist and Track_No < len(tracks) - 1:
                        Track_No +=1
                        titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
                    old_artist = titles[0]
                    Tack_No = Track_No
                    stitles[0],stitles[1],stitles[2],stitles[3],stitles[4],stitles[5],stitles[6] = tracks[Tack_No].split("/")
                    talbum = stitles[1]
                    tartist = stitles[0]
                    while stitles[1] == talbum and stitles[0] == tartist and Tack_No < len(tracks):
                        stitles[0],stitles[1],stitles[2],stitles[3],stitles[4],stitles[5],stitles[6] = tracks[Tack_No].split("/")
                        strack = stitles[3] + "/" + stitles[4] + "/" + stitles[5] + "/" + stitles[6] + "/" + stitles[0] + "/" + stitles[1] + "/" + stitles[2]
                        Tack_No +=1
                    ctracks = Tack_No - Track_No - 1
                    msg2 = titles[0][0:19]
                    msg3 = titles[1][0:19]
                    msg4 = titles[2][0:19]
                    try:
                        if int(titles[2][0:2]) > 0:
                            msg4 = titles[2][3:22]
                    except:
                        pass
                    display()
                    time.sleep(0.5)
                # NEXT A-Z ARTIST    
                while buttonNEXT.is_pressed and buttonVOLUP.is_pressed:
                    while titles[0][0:1] == old_artist[0:1] and Track_No < len(tracks) - 1:
                        Track_No +=1
                        titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
                    old_artist = titles[0]
                    Tack_No = Track_No
                    stitles[0],stitles[1],stitles[2],stitles[3],stitles[4],stitles[5],stitles[6] = tracks[Tack_No].split("/")
                    talbum = stitles[1]
                    tartist = stitles[0]
                    while stitles[1] == talbum and stitles[0] == tartist and Tack_No < len(tracks):
                        stitles[0],stitles[1],stitles[2],stitles[3],stitles[4],stitles[5],stitles[6] = tracks[Tack_No].split("/")
                        strack = stitles[3] + "/" + stitles[4] + "/" + stitles[5] + "/" + stitles[6] + "/" + stitles[0] + "/" + stitles[1] + "/" + stitles[2]
                        Tack_No +=1
                    ctracks = Tack_No - Track_No - 1
                    msg2 = titles[0][0:19]
                    msg3 = titles[1][0:19]
                    msg4 = titles[2][0:19]
                    try:
                        if int(titles[2][0:2]) > 0:
                            msg4 = titles[2][3:22]
                    except:
                        pass
                    display()
                    time.sleep(0.5)
            timer3 = time.monotonic()
            album = 1
                        
        # check for GAPLESS/SHUTDOWN (SLEEP)  key
        if buttonSLEEP.is_pressed and Disp_on == 0:
            Disp_on = 1
            Disp_start = time.monotonic()
            status()
            msg1 = "<PLAY/Radio   NEXT>"
            time.sleep(0.5)
            timer2 = time.monotonic()
        elif buttonSLEEP.is_pressed:
            time.sleep(0.5)
            timer1 = time.monotonic()
            timer = time.monotonic()
            if gapless == 0:
                    gap = gaptime
                    gapless = 1
                    msg2 = "Gapless ON"
                    msg3 = ""
                    msg4 = ""
                    msg5 = ""
                    msg6 = ""
                    msg7 = ""
                    msg8 = ""
                    display()
                    time.sleep(1)
            else:
                    gap = 0
                    gapless = 0
                    msg2 = "Gapless OFF"
                    msg3 = ""
                    msg4 = ""
                    msg5 = ""
                    msg6 = ""
                    msg7 = ""
                    msg8 = ""
                    display()
                    time.sleep(1)
            status()
            if album_mode == 0:
                    track_n = str(Track_No + 1) + "     "
            else:
                    track_n = "1/" + str(ctracks) + "       "
            msg1 = "<PLAY/Radio   NEXT>"
            display()
            defaults = [MP3_Play,radio,radio_stn,shuffled,album_mode,volume,gapless,Track_No]
            with open(config_file, 'w') as f:
                    for item in defaults:
                        f.write("%s\n" % item)
            time.sleep(0.5)
            timer2 = time.monotonic()
            xt = 2
            while buttonSLEEP.is_pressed:
                if time.monotonic() - timer1 > 10:
                    msg2 = "SHUTDOWN in " + str(20-int(time.monotonic() - timer1))
                    display()
                if time.monotonic() - timer1 > 20:
                    # shutdown if pressed for 20 seconds
                    msg1 = "SHUTTING DOWN..."
                    time.sleep(0.05)
                    msg2 = ""
                    msg3 = ""
                    msg4 = ""
                    msg5 = ""
                    msg6 = ""
                    msg7 = ""
                    msg8 = ""
                    display()
                    time.sleep(2)
                    msg1 = ""
                    display()
                    MP3_Play = 0
                    radio = 0
                    time.sleep(1)
                    os.system("sudo shutdown -h now")
            Disp_start = time.monotonic()
            timer2 = time.monotonic()
            xt = 2
           
        # check for ALBUM MODE/RANDOM (VOLUP) key
        if  buttonVOLUP.is_pressed and Disp_on == 0:
            Disp_on = 1
            Disp_start = time.monotonic()
            status()
            msg1 = "<PLAY/Radio   NEXT>"
            time.sleep(0.5)
            timer2 = time.monotonic()
        elif buttonVOLUP.is_pressed:
            timer1 = time.monotonic()
            while buttonVOLUP.is_pressed and time.monotonic() - timer1 < 2:
                pass
            if time.monotonic() - timer1 < 1:
                if album_mode == 0:
                    album_mode = 1
                    shuffled    = 0
                    titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
                    new_artist = titles[0]
                    new_album  = titles[1]
                    tracks.sort()
                    Track_No = 0
                    titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
                    while new_artist != titles[0] or new_album != titles[1]:
                        titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
                        Track_No +=1
                    Track_No -=1
                    msg2 = "Album Mode ON "
                    msg3 = ""
                    msg4 = ""
                    msg5 = ""
                    msg6 = ""
                    msg7 = ""
                    msg8 = ""
                    Tack_No = Track_No 
                    stimer  = 0
                    stitles = [0,0,0,0,0,0,0]
                    stitles[0],stitles[1],stitles[2],stitles[3],stitles[4],stitles[5],stitles[6] = tracks[Tack_No].split("/")
                    talbum = stitles[1]
                    tartist = stitles[0]
                    while stitles[1] == talbum and stitles[0] == tartist and Tack_No < len(tracks):
                        stitles[0],stitles[1],stitles[2],stitles[3],stitles[4],stitles[5],stitles[6] = tracks[Tack_No].split("/")
                        strack = stitles[3] + "/" + stitles[4] + "/" + stitles[5] + "/" + stitles[6] + "/" + stitles[0] + "/" + stitles[1] + "/" + stitles[2]
                        audio = MP3(strack)
                        stimer += audio.info.length
                        Tack_No +=1
                    audio = MP3(strack)
                    stimer -= audio.info.length
                    ctracks = Tack_No - Track_No - 1
                    track_n = str(cplayed) + "/" + str(ctracks) + "       "
                else:
                    album_mode = 0
                    msg2 = "Album Mode OFF "
                    msg3 = ""
                    msg4 = ""
                    msg5 = ""
                    msg6 = ""
                    msg7 = ""
                    msg8 = ""
                    track_n  = str(Track_No) + "     "
                defaults = [MP3_Play,radio,radio_stn,shuffled,album_mode,volume,gapless,Track_No]
                with open(config_file, 'w') as f:
                    for item in defaults:
                        f.write("%s\n" % item)
                display()
                time.sleep(1)

            else:    
                msg2 = ""
                msg3 = ""
                msg4 = ""
                msg5 = ""
                msg6 = ""
                msg7 = ""
                msg8 = ""
                if shuffled == 0:
                    shuffled = 1
                    shuffle(tracks)
                    Track_No = 0
                    album_mode = 0
                    track_n  = str(Track_No + 1) + "     "
                    msg2 = "Random Mode ON "
                   
                else:
                    shuffled = 0
                    msg2 = "Random Mode OFF "
                    itles[0],itles[1],itles[2],itles[3],itles[4],itles[5],itles[6] = tracks[Track_No].split("/")
                    tracks.sort()
                    Track_No = 0
                    titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
                    while titles[0] != itles[0] or titles[1] != itles[1]:
                        Track_No +=1
                        titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
                    track_n  = str(Track_No) + "     "
                    if album_mode == 1:
                        Tack_No = Track_No
                        stitles[0],stitles[1],stitles[2],stitles[3],stitles[4],stitles[5],stitles[6] = tracks[Tack_No].split("/")
                        talbum = stitles[1]
                        tartist = stitles[0]
                        while stitles[1] == talbum and stitles[0] == tartist and Tack_No < len(tracks):
                            stitles[0],stitles[1],stitles[2],stitles[3],stitles[4],stitles[5],stitles[6] = tracks[Tack_No].split("/")
                            strack = stitles[3] + "/" + stitles[4] + "/" + stitles[5] + "/" + stitles[6] + "/" + stitles[0] + "/" + stitles[1] + "/" + stitles[2]
                            Tack_No +=1
                        ctracks = Tack_No - Track_No - 1
                        album_mode = 1
                        track_n = "1/" + str(ctracks) + "       "
                display()
                defaults = [MP3_Play,radio,radio_stn,shuffled,album_mode,volume,gapless,Track_No]
                with open(config_file, 'w') as f:
                    for item in defaults:
                        f.write("%s\n" % item)
                time.sleep(1)
                timer2 = time.monotonic()
                xt = 2
            status()
            if album_mode == 0:
                track_n = str(Track_No + 1) + "     "
            else:
                track_n = "1/" + str(ctracks) + "       "
            msg1 = "<PLAY/Radio   NEXT>"
            display()
            timer2 = time.monotonic()
            xt = 2
            
    # loop while playing Radio
    while radio == 1:
        time.sleep(0.2)
        # check if clock synchronised
        if time.monotonic() - sync_timer > 60:
            sync_timer = time.monotonic()
            if os.path.exists ("/run/shm/sync.txt"):
                os.remove("/run/shm/sync.txt")
            os.system("timedatectl >> /run/shm/sync.txt")
            try:
                sync = []
                with open("/run/shm/sync.txt", "r") as file:
                    line = file.readline()
                    while line:
                        sync.append(line.strip())
                        line = file.readline()
                if sync[4] == "System clock synchronized: yes":
                    synced = 1
                else:
                    synced = 0
            except:
                pass
        # DISPLAY OFF timer
        if time.monotonic() - Disp_start > Disp_timer and Disp_timer > 0 and Disp_on == 1:
            msg1 = ""
            msg2 = ""
            msg3 = ""
            msg4 = ""
            msg5 = ""
            msg6 = ""
            msg7 = ""
            msg8 = ""
            Disp_on = 0
            display()
            
        # sleep_timer timer
        if time.monotonic() - sleep_timer_start > sleep_timer and sleep_timer > 0:
            Disp_start = time.monotonic()
            abort_sd = 0
            t = 30
            Disp_on = 1
            while t > 0 and abort_sd == 0:
                if sleep_shutdn == 1:
                    msg2 = "SHUTDOWN in " + str(t)
                    display()
                else:
                    msg2 = "STOPPING in " + str(t)
                    display()
                if buttonSLEEP.is_pressed:
                    sleep_timer_start = time.monotonic()
                    sleep_timer = 900
                    abort_sd = 1
                t -=1
                time.sleep(1)
            if abort_sd == 0:
                if sleep_shutdn == 1:
                    msg1 = "SHUTTING DOWN..."
                    display()
                else:
                    msg1 = "STOPPING........"
                display()
                msg2 = ""
                time.sleep(1)
                Disp_on = 0
                msg1 = ""
                msg3 = ""
                msg4 = ""
                msg5 = ""
                msg6 = ""
                msg7 = ""
                msg8 = ""
                display()
                q.kill()
                if sleep_shutdn == 1:
                    os.system("sudo shutdown -h now")
                sleep_timer = 0
                stopped = 1
                radio = 0
                time.sleep(1)
            Disp_start = time.monotonic()

            
        # display sleep_timer time left and clock (if enabled and synced)
        now = datetime.datetime.now()
        clock = now.strftime("%H:%M:%S")
        secs = now.strftime("%S")
        time_left = int((sleep_timer - (time.monotonic() - sleep_timer_start))/60)
        msg2 = Radio_Stns[radio_stn]
        if sleep_timer > 0:
            if sleep_shutdn == 1:
                msg4 = "Shutdown: " + str(time_left) + "mins"
            else:
                msg4 = "Stopping: " + str(time_left) + "mins"
        if show_clock == 1 and synced == 1:
            msg3 = "      " + clock
        t = ""
        for r in range (0,random.randint(0,10)):
            t += " "
        clock = t + clock
        if Disp_on == 1:
            msg1 = "<STOP             NEXT>"
            msg8 = "<VOLUME       SLEEP>"
            display()
        if show_clock == 1 and Disp_on == 0 and synced == 1 and stopped == 0:
            if secs != old_secs:
                if sleep_timer > 0:
                    clock = clock + " " + str(time_left)
                vp = random.randint(0,8)
                msg1 = ""
                msg2 = ""
                msg3 = ""
                msg4 = ""
                msg5 = ""
                msg6 = ""
                msg7 = ""
                msg8 = ""
                if vp == 0:
                    msg1 = clock
                elif vp == 1:
                    msg2 = clock
                elif vp == 2:
                    msg3 = clock
                elif vp == 3:
                    msg4 = clock
                elif vp == 4:
                    msg5 = clock
                elif vp == 5:
                    msg6 = clock
                elif vp == 6:
                    msg7 = clock
                elif vp == 7:
                    msg8 = clock
                display()
                old_secs = secs
            
        # check for VOLUME UP/DOWN  key
        if buttonVOLUP.is_pressed and Disp_on == 0:
            Disp_on = 1
            Disp_start = time.monotonic()
            status()
            if album_mode == 0:
                track_n = str(Track_No + 1) + "     "
            else:
                track_n = "1/" + str(ctracks) + "       "
            msg1 = "<PLAY/Radio   NEXT>"
            msg8 = "<VOLUME      SLEEP>"
            time.sleep(0.5)
            timer2 = time.monotonic()
        elif buttonVOLUP.is_pressed:
            Set_Volume()
            status()
            time.sleep(0.5)
            if album_mode == 0:
                track_n = str(Track_No + 1) + "     "
            else:
                track_n = "1/" + str(ctracks) + "       "
            msg1 = "<PLAY/Radio   NEXT>"
            msg8 = "<VOLUME      SLEEP>"
            display()
            Disp_start = time.monotonic()
            timer2 = time.monotonic()
                
           
        # check NEXT/PREVIOUS key
        if buttonNEXT.is_pressed and Disp_on == 0:
            Disp_on = 1
            Disp_start = time.monotonic()
            status()
            msg1 = "<STOP         NEXT>"
            time.sleep(0.5)
            timer2 = time.monotonic()
        elif buttonNEXT.is_pressed:
            Disp_on = 1
            Disp_start = time.monotonic()
            timer1 = time.monotonic()
            while buttonNEXT.is_pressed:
              if time.monotonic() - timer1 > 1:
                radio_stn +=2
                if radio_stn > len(Radio_Stns)- 2:
                   radio_stn = 0
                msg1 = (Radio_Stns[radio_stn])
                display()
                time.sleep(1)
              else:
                radio_stn -=2
                if radio_stn < 0:
                    radio_stn = len(Radio_Stns) - 2
                msg2 = (Radio_Stns[radio_stn])
                display()
                time.sleep(1)
            q.kill()
            q = subprocess.Popen(["mplayer", "-nocache", Radio_Stns[radio_stn+1]] , shell=False)
            time.sleep(1)
            rs = Radio_Stns[radio_stn] + "               "[0:19]
            defaults = [MP3_Play,radio,radio_stn,shuffled,album_mode,volume,gapless,Track_No]
            with open(config_file, 'w') as f:
                for item in defaults:
                    f.write("%s\n" % item)
            timer2 = time.monotonic()
            time.sleep(1)

          
        # check PLAY/STOP/Radio key
        if buttonPLAY.is_pressed and Disp_on == 0:
            Disp_on = 1
            Disp_start = time.monotonic()
            status()
            msg1 = "<STOP         NEXT>"
            time.sleep(0.5)
            timer2 = time.monotonic()
        elif buttonPLAY.is_pressed:
            Disp_on = 1
            Disp_start = time.monotonic()
            q.kill()
            radio = 0
            if len(tracks) > 0:
                msg1 = "<PLAY/Radio   NEXT>"
            else:
                msg1 = "Radio Stopped      "
            display()
            defaults = [MP3_Play,radio,radio_stn,shuffled,album_mode,volume,gapless,Track_No]
            with open(config_file, 'w') as f:
                for item in defaults:
                    f.write("%s\n" % item)
            time.sleep(2)
            

        # check for sleep_timer key
        if buttonSLEEP.is_pressed and Disp_on == 0:
            Disp_on = 1
            Disp_start = time.monotonic()
            status()
            msg1 = "<STOP         NEXT>"
            time.sleep(0.5)
            timer2 = time.monotonic()
        
        elif buttonSLEEP.is_pressed:
            Disp_on = 1
            Disp_start = time.monotonic()
            timer1 = time.monotonic()
            sleep_timer_start = time.monotonic()
            msg1 = "Set SLEEP.. " + str(int(sleep_timer/60))
            msg2 = "HOLD for 20 to SHUTDOWN "
            msg3 = ""
            msg5 = ""
            msg6 = ""
            msg7 = ""
            msg8 = ""
            display()
            while buttonSLEEP.is_pressed:
                sleep_timer +=900
                if sleep_timer > 7200:
                     sleep_timer = 0
                sleep_timer_start = time.monotonic()
                msg1 = "Set SLEEP.. " + str(int(sleep_timer/60))
                display()
                time.sleep(1)
                if time.monotonic() - timer1 > 10:
                    msg2 = "SHUTDOWN in " + str(20-int(time.monotonic() - timer1))
                    display()
                if time.monotonic() - timer1 > 20:
                    # shutdown if pressed for 20 seconds
                    msg1 = "SHUTTING DOWN..."
                    msg2 = ""
                    msg3 = ""
                    msg4 = ""
                    msg5 = ""
                    msg6 = ""
                    msg7 = ""
                    msg8 = ""
                    display()
                    time.sleep(2)
                    msg1 = ""
                    display()
                    MP3_Play = 0
                    radio = 0
                    time.sleep(1)
                    os.system("sudo shutdown -h now")
            Disp_start = time.monotonic()
            time.sleep(0.5)
            msg1 = Radio_Stns[radio_stn]
            msg2 = ""
            display()
            timer2 = time.monotonic()
            xt = 2
                    
    # loop while playing MP3 tracks
    while MP3_Play == 1 :
        time.sleep(0.1)
        # check if clock synchronised
        if time.monotonic() - sync_timer > 60:
            sync_timer = time.monotonic()
            if os.path.exists ("/run/shm/sync.txt"):
                os.remove("/run/shm/sync.txt")
            os.system("timedatectl >> /run/shm/sync.txt")
            try:
                sync = []
                with open("/run/shm/sync.txt", "r") as file:
                    line = file.readline()
                    while line:
                        sync.append(line.strip())
                        line = file.readline()
                if sync[4] == "System clock synchronized: yes":
                    synced = 1
                else:
                    synced = 0
            except:
                pass
        # stop playing if end of album, in album mode
        cplayed +=1
        if cplayed > ctracks and album_mode == 1:
            status()
            msg1 = "<PLAY/Radio   NEXT>"
            msg2 = titles[0][0:19]
            msg3 = titles[1][0:19]
            msg4 = titles[2][0:19]
            try:
                if int(titles[2][0:2]) > 0:
                    msg4 = titles[2][3:22]
            except:
                pass
            display()
            MP3_Play = 0
            
        # sleep_timer timer
        if time.monotonic() - sleep_timer_start > sleep_timer and sleep_timer > 0:
            Disp_on = 1
            Disp_start = time.monotonic()
            abort_sd = 0
            t = 30
            while t > 0 and abort_sd == 0:
                if sleep_shutdn == 1:
                    msg2 = "SHUTDOWN in " + str(t)
                    msg3 = ""
                    msg4 = ""
                    msg5 = ""
                    msg6 = ""
                    msg7 = ""
                    msg8 = ""
                    display()
                else:
                    msg2 = "STOPPING in " + str(t)
                    msg3 = ""
                    msg4 = ""
                    msg5 = ""
                    msg6 = ""
                    msg7 = ""
                    msg8 = ""
                    display()
                if buttonSLEEP.is_pressed:
                    sleep_timer_start = time.monotonic()
                    sleep_timer = 900
                    abort_sd = 1
                t -=1
                time.sleep(1)
            if abort_sd == 0:
                if sleep_shutdn == 1:
                    msg1 = "SHUTTING DOWN..."
                else:
                    msg1 = "STOPPING........"
                time.sleep(0.05)
                msg2 = ""
                msg3 = ""
                msg4 = ""
                msg5 = ""
                msg6 = ""
                msg7 = ""
                msg8 = ""
                display()
                time.sleep(3)
                Disp_on = 0
                msg1 = ""
                display()
                poll = p.poll()
                if poll == None:
                    os.killpg(p.pid, SIGTERM)
                if sleep_shutdn == 1:
                    os.system("sudo shutdown -h now")
                sleep_timer = 0
                stopped = 1
                MP3_Play = 0
            else:
                status()
                msg1 = "Play.." + str(track_n)[0:5] + txt
                display()
                time.sleep(0.05)
                Disp_start = time.monotonic()
            poll = p.poll()
            if poll == None:
                os.killpg(p.pid, SIGTERM)
                time.sleep(1)
                
        # try reloading tracks if none found
        if len(tracks) == 0 and stop == 0:
            reload()
            
        # try reloading tracks if one selected not found
        if len(tracks) > 0:
            titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
            track = titles[3] + "/" + titles[4] + "/" + titles[5] + "/" + titles[6] + "/" + titles[0] + "/" + titles[1] + "/" + titles[2]
            if not os.path.exists(track) and stop == 0 :
                reload()
            
        # play selected track
        if MP3_Play == 1 and len(tracks) > 0:
          titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
          track = titles[3] + "/" + titles[4] + "/" + titles[5] + "/" + titles[6] + "/" + titles[0] + "/" + titles[1] + "/" + titles[2]
          if album_mode == 0:
              msg1 = "<STOP/Radio   NEXT>"
          else:
              msg1 = "<STOP/Radio   NEXT>"
          rpistr = "mplayer" + " -quiet " +  '"' + track + '"'
          msg2 = titles[0][0:19]
          msg3 = titles[1][0:19]
          msg4 = titles[2][0:19]
          msg8 = "<VOLUME     SLEEP>"
          try:
              if int(titles[2][0:2]) > 0:
                  msg4 = titles[2][3:22]
          except:
              pass
          if Disp_on == 1:
              display()
          audio = MP3(track)
          track_len = audio.info.length
          p = subprocess.Popen(rpistr, shell=True, preexec_fn=os.setsid)
          poll = p.poll()
          while poll != None:
            poll = p.poll()
          timer2 = time.monotonic()
          timer1 = time.monotonic()
          xt = 0
          go = 1
          played = time.monotonic() - timer1
          
          # loop while playing selected MP3 track
          while poll == None and track_len - played > gap and (time.monotonic() - sleep_timer_start < sleep_timer or sleep_timer == 0):
            time_left = int((sleep_timer - (time.monotonic() - sleep_timer_start))/60)
                
            # display clock (if enabled and synced)
            if show_clock == 1 and Disp_on == 0 and synced == 1:
                now = datetime.datetime.now()
                clock = now.strftime("%H:%M:%S")
                secs = now.strftime("%S")
                t = ""
                for r in range (0,random.randint(0,10)):
                    t += " "
                clock = t + clock
                time_left = int((sleep_timer - (time.monotonic() - sleep_timer_start))/60)
                if sleep_timer > 0:
                    clock += " " + str(time_left)
                if secs != old_secs2 :
                  vp = random.randint(0,8)
                  msg1 = ""
                  msg2 = ""
                  msg3 = ""
                  msg4 = ""
                  msg5 = ""
                  msg6 = ""
                  msg7 = ""
                  msg8 = ""
                  if vp == 0:
                    msg1 = clock
                  elif vp == 1:
                    msg2 = clock
                  elif vp == 2:
                    msg3 = clock
                  elif vp == 3:
                    msg4 = clock
                  elif vp == 4:
                    msg5 = clock
                  elif vp == 5:
                    msg6 = clock
                  elif vp == 6:
                    msg7 = clock
                  elif vp == 7:
                    msg8 = clock
                  display()
                  old_secs2 = secs
                
            time.sleep(0.2)

            played  = time.monotonic() - timer1
            played_pc = int((played/track_len) *100)

            # DISPLAY OFF timer
            if time.monotonic() - Disp_start > Disp_timer and Disp_timer > 0 and Disp_on == 1:
                msg1 = ""
                msg2 = ""
                msg3 = ""
                msg4 = ""
                msg5 = ""
                msg6 = ""
                msg7 = ""
                msg8 = ""
                Disp_on = 0
                display()
           
            # display titles, status etc
            if Disp_on == 1:
                msg2 = titles[0][0:19]
                msg3 = titles[1][0:19]
                msg4 = titles[2][0:19]
                try:
                    if int(titles[2][0:2]) > 0:
                        msg4 = titles[2][3:22]
                except:
                    pass
                played_pc =  "     " + str(played_pc)
                msg1 = "<STOP/Radio   NEXT>"
                status()
                msg6 = "Status...  " +  txt
                if sleep_timer != 0:
                    time_left = int((sleep_timer - (time.monotonic() - sleep_timer_start))/60)
                    if sleep_shutdn == 1:
                        msg7 = "Shutdown: " + str(time_left) + "mins"
                    else:
                        msg7 = "Stopping: " + str(time_left) + "mins"
                pmin = int(played/60)
                psec = int(played - (pmin * 60))
                psec2 = str(psec)
                if psec < 10:
                    psec2 = "0" + psec2
                lmin = int(track_len/60)
                lsec = int(track_len - (lmin * 60))
                lsec2 = str(lsec)
                if lsec < 10:
                    lsec2 = "0" + lsec2
                msg5 = " " + str(pmin) + ":" + str(psec2) + " of " + str(lmin) + ":" + str(lsec2)
                msg8 = "<VOLUME      SLEEP>"
                display()
                   
            # check for PLAY/STOP/RADIO key
            if buttonPLAY.is_pressed and Disp_on == 0:
                Disp_on = 1
                Disp_start = time.monotonic()
                status()
                msg1 = "<STOP/Radio   NEXT>"
                time.sleep(0.5)
                timer2 = time.monotonic()
            elif  buttonPLAY.is_pressed:
                Disp_on = 1
                Disp_start = time.monotonic()
                timer1 = time.monotonic()
                os.killpg(p.pid, SIGTERM)
                msg1 = "Track Stopped"
                display()
                time.sleep(2)
                status()
                msg1 = "<PLAY/Radio   NEXT>"
                msg2 = ""
                msg3 = ""
                msg4 = ""
                msg5 = ""
                msg6 = ""
                msg7 = ""
                msg8 = ""
                display()
                go = 0
                MP3_Play = 0
                defaults = [MP3_Play,radio,radio_stn,shuffled,album_mode,volume,gapless,Track_No]
                with open(config_file, 'w') as f:
                    for item in defaults:
                        f.write("%s\n" % item)
                timer2 = time.monotonic()
                
            # check for NEXT/PREVIOUS TRACK key
            elif buttonNEXT.is_pressed and Disp_on == 0:
                Disp_on = 1
                Disp_start = time.monotonic()
                status()
                msg1 = "<STOP/Radio   NEXT>"
                time.sleep(0.5)
                timer2 = time.monotonic()
            elif  buttonNEXT.is_pressed:
                Disp_on = 1
                Disp_start = time.monotonic()
                os.killpg(p.pid, SIGTERM)
                timer1 = time.monotonic()
                while buttonNEXT.is_pressed and time.monotonic() - timer1 < 1:
                    pass
                while buttonNEXT.is_pressed:
                    if time.monotonic() - timer1 > 1:
                        if go == 1:
                            Track_No += 1
                            if Track_No > len(tracks) - 1:
                                Track_No = Track_No - len(tracks)
                            msg1 = "<STOP/Radio   NEXT>"
                            titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
                            msg2 = titles[0][0:19]
                            msg3 = titles[1][0:19]
                            msg4 = titles[2][0:19]
                            display()
                            time.sleep(1)
                if time.monotonic() - timer1 < 1:
                    if go == 1:
                        Track_No -= 1
                        if Track_No < 0:
                            Track_No = len(tracks) + Track_No
                    msg1 = "<PLAY/Radio   NEXT>"
                    titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
                    msg2 = titles[0][0:19]
                    msg3 = titles[1][0:19]
                    msg4 = titles[2][0:19]
                    display()
                    time.sleep(1)
                timer2 = time.monotonic()
                go = 0

            # check for VOLUME UP/DOWN  key
            elif buttonVOLUP.is_pressed and Disp_on == 0:
                Disp_on = 1
                Disp_start = time.monotonic()
                status()
                msg1 = "<STOP/Radio   NEXT>"
                time.sleep(0.5)
                timer2 = time.monotonic()
            elif buttonVOLUP.is_pressed:
                time.sleep(0.5)
                Set_Volume()
                status()
                if album_mode == 0:
                    track_n = str(Track_No + 1) + "     "
                else:
                    track_n = "1/" + str(ctracks) + "       "
                msg1 = "<STOP/Radio   NEXT>" 
                display()
                Disp_start = time.monotonic()
                timer2 = time.monotonic()
 
                           
            # check for SLEEP/SHUTDOWN key
            elif  buttonSLEEP.is_pressed and Disp_on == 0:
                Disp_start = time.monotonic()
                Disp_on = 1
                status()
                msg1 = "<STOP/Radio   NEXT>"
                display()
                time.sleep(1)
                timer2 = time.monotonic()
            elif buttonSLEEP.is_pressed:
                Disp_on = 1
                timer1 = time.monotonic()
                if (sleep_timer == 0 and album_mode == 0) or (album_mode ==1 and sleep_timer == stimer + 60):
                    sleep_timer = 900
                elif sleep_timer == 0 and shuffled == 0 and album_mode == 1:
                    # determine album length to set sleep time
                    Tack_No = Track_No
                    stimer  = 0
                    stitles = [0,0,0,0,0,0,0]
                    stitles[0],stitles[1],stitles[2],stitles[3],stitles[4],stitles[5],stitles[6] = tracks[Tack_No].split("/")
                    talbum = stitles[1]
                    tartist = stitles[0]
                    while stitles[1] == talbum and stitles[0] == tartist:
                        stitles[0],stitles[1],stitles[2],stitles[3],stitles[4],stitles[5],stitles[6] = tracks[Tack_No].split("/")
                        strack = stitles[3] + "/" + stitles[4] + "/" + stitles[5] + "/" + stitles[6] + "/" + stitles[0] + "/" + stitles[1] + "/" + stitles[2]
                        audio = MP3(strack)
                        stimer += audio.info.length
                        Tack_No +=1
                    audio = MP3(strack)
                    stimer -= audio.info.length
                    sleep_timer = stimer + 60
                else:
                    sleep_timer = (time_left * 60) + 960
                    if sleep_timer > 10800:
                        sleep_timer = 0
                sleep_timer_start = time.monotonic()
                msg1 = "Set SLEEP.. " + str(int(sleep_timer/60))
                msg2 = "HOLD for 20 to SHUTDOWN "
                msg3 = ""
                msg4 = ""
                msg5 = ""
                msg6 = ""
                msg7 = ""
                msg8 = ""
                display()
                time.sleep(1)
                while buttonSLEEP.is_pressed:
                    if album_mode == 0:
                        sleep_timer +=900
                        if sleep_timer > 7200:
                            sleep_timer = 0
                        sleep_timer_start = time.monotonic()
                        msg1 = "Set SLEEP.. " + str(int(sleep_timer/60))
                        display()
                        time.sleep(1)
                    if time.monotonic() - timer1 > 10:
                        msg2 = "SHUTDOWN in " + str(20-int(time.monotonic() - timer1))
                    if time.monotonic() - timer1 > 20:
                        # shutdown if pressed for 20 seconds
                        msg1 = "SHUTTING DOWN..."
                        time.sleep(0.05)
                        msg2 = ""
                        msg3 = ""
                        msg4 = ""
                        display()
                        time.sleep(2)
                        msg1 = ""
                        display()
                        MP3_Play = 0
                        radio = 0
                        time.sleep(1)
                        os.system("sudo shutdown -h now")
                Disp_start = time.monotonic()
                timer2 = time.monotonic()
                xt = 2
                
            poll = p.poll()
          if go == 1:
               Track_No +=1
          if Track_No < 0:
              Track_No = len(tracks) + Track_No
          elif Track_No > len(tracks) - 1:
              Track_No = Track_No - len(tracks)
        





            
