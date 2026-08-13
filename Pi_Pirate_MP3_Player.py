#!/usr/bin/env python3

"""Copyright (c) 2026
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

version  = "1.16"

# set default variables (saved in config_file and overridden at future startups)
MP3_Play     = 0   # set to 1 to start playing MP3s at boot, else 0
radio        = 0   # set to 1 to start playing Radio at boot, else 0
radio_stn    = 0   # selected radio station at startup (Note 0,3,6 etc)
shuffled     = 0   # 0 = Unshuffled, 1 = Shuffled
album_mode   = 0   # set to 1 for Album Mode, will play an album then stop
gapless      = 0   # set to 1 for gapless play
volume       = 40  # range 0 - 100
Track_No     = 0   # start track number

# variables set once
use_USB      = 1   # set to 0 if you ONLY use /home/<USERNAME>/Music/... on SD card
usb_timer    = 6   # seconds to find USB present
sleep_timer  = 0   # sleep_timer timer in minutes, use 15,30,45,60 etc...set to 0 to disable
sleep_shutdn = 0   # set to 1 to shutdown Pi when sleep times out
Disp_timer   = 60  # Display timeout in seconds, set to 0 to disable
show_clock   = 1   # set to 1 to show clock, only use if on web or using RTC
gaptime      = 2   # set pre-start time for gapless, in seconds
screen       = 0   # for testing, 0 = ST7789, 1 = pygame screen

Radio_Stns = ["Radio Paradise Rock","http://stream.radioparadise.com/rock-192",0,
              "Radio Paradise Main","http://stream.radioparadise.com/mp3-320",0,
              "Radio Paradise Mellow","http://stream.radioparadise.com/mellow-192",0,
              "Radio Caroline","http://sc6.radiocaroline.net:10558/",0,
              "BBC World Service","http://stream.live.vc.bbcmedia.co.uk/bbc_world_service",0]

# GPIO BUTTONS GPIO BCM numbers (Physical pin numbers)
PLAY  = 5  # (29) PLAY / STOP / HOLD for 3 seconds for RADIO 
VOLUP = 6  # (31) Adjust volume UP whilst playing, set ALBUM MODE/RANDOM ON/OFF whilst stopped
NEXT  = 16 # (36) HOLD for NEXT TRACK / STATION (whilst playing) / NEXT ALBUM (whilst stopped) - quick press for PREVIOUS 
SLEEP = 24 # (18) Set SLEEP time, HOLD for 20 seconds to SHUTDOWN, set GAPLESS/SHUTDOWN whilst stopped.

if screen == 0: # st7789 screen
    import st7789
    disp = st7789.ST7789(height=240,rotation=90,port=0,cs=1,dc=9,backlight=13,spi_speed_hz=80 * 1000 * 1000,offset_left=0,offset_top=0,)
    disp.begin()
    WIDTH  = disp.width
    HEIGHT = disp.height
    img    = Image.new('RGB', (WIDTH, HEIGHT), color=(0, 0, 0))
    font   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
    disp.set_backlight(1)
    
elif screen == 1: # for testing with pygame, and pirate buttons
    import pygame
    from pygame.locals import *
    pygame.init()
    font_size = 30
    windowSurfaceObj = pygame.display.set_mode((240,240),1, 24)
    pygame.display.set_caption("MP3 / Radio Player" )

# check config file exists, if not then write default values
config_file = "PirateConfig.txt"
if not os.path.exists(config_file) or os.stat(config_file).st_size == 0:
    headers  = ['MP3_Play  ','radio     ','radio_stn ','shuffled  ','album_mode','volume    ','gapless   ','Track_No  ']
    defaults = [MP3_Play,radio,radio_stn,shuffled,album_mode,volume,gapless,Track_No]
    with open(config_file, 'w') as f:
        for item in range(0,len(headers)):
            f.write(headers[item] + " : " + str(defaults[item]) + "\n")

# read config file
config = []
with open(config_file, "r") as file:
   line = file.readline()
   while line:
       line = line.strip()
       item = line.split(" : ")
       config.append(item[1])
       line = file.readline()
config = list(map(int,config))

if len(config) < 8:
    headers  = ['MP3_Play  ','radio     ','radio_stn ','shuffled  ','album_mode','volume    ','gapless   ','Track_No  ']
    defaults = [MP3_Play,radio,radio_stn,shuffled,album_mode,volume,gapless,Track_No]
    with open(config_file, 'w') as f:
        for item in range(0,len(headers)):
            f.write(headers[item] + " : " + str(defaults[item]) + "\n")
    # read config file
    config = []
    with open(config_file, "r") as file:
        line = file.readline()
        while line:
            line = line.strip()
            item = line.split(" : ")
            config.append(item[1])
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
    
# read radio_stns.txt (Station Name,URL,X)
if os.path.exists ("radio_stns.txt"): 
    with open("radio_stns.txt","r") as textobj:
        line = textobj.readline()
        while line:
            if line.count(",") == 2:
                a,b,c = line.split(",")
                if a[0:1] != "#":
                    Radio_Stns.append(a)
                    Radio_Stns.append(b)
                    Radio_Stns.append(int(c.strip()))
            elif line.count(",") == 1:
                a,b = line.split(",")
                if a[0:1] != "#":
                    Radio_Stns.append(a)
                    Radio_Stns.append(b.strip())
                    Radio_Stns.append(0)
            line = textobj.readline()
            
if radio_stn > len(Radio_Stns) - 3:
    radio_stn = 0

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
msg         = [""] * 8
msg[0]      = "MP3 Player: v" + version
abort_sd    = 1
usb_found   = 0
relno       = 0
stop        = 0
pfiles      = []
showit      = 1

# find username
h_user  = []
h_user.append(os.getlogin())

def display_screen():
    global image,top,msg,font,img,WIDTH,HEIGHT
    global MP3_Play,radio,screen,font_size,radio,Radio_Stns,radio_stn,pfiles,Disp_on
    clrs = [(255,255,0),(255,255,255),(255,255,255),(255,255,255),(255,255,255),(255,255,255),(255,255,255),(255,255,0)]
    if screen == 0: # st7789 screen
        if Disp_on == 1:
            disp.set_backlight(1)
        if radio == 1 and os.path.exists(Radio_Stns[radio_stn] + ".jpg") and Disp_on == 1:
            with Image.open(Radio_Stns[radio_stn] + ".jpg") as img:
                img  = img.resize((240,240),resample=Image.LANCZOS)
                draw = ImageDraw.Draw(img)
                for x in range(0,8):
                    draw.text((0, x * 30), msg[x], font=font, fill=clrs[x])
        elif radio == 0 and len(pfiles) > 0 and os.path.exists(pfiles[0]) and Disp_on == 1:
            with Image.open(pfiles[0]) as img:
                img  = img.resize((240,240),resample=Image.LANCZOS)
                draw = ImageDraw.Draw(img)
                for x in range(0,8):
                    draw.text((0, x * 30), msg[x], font=font, fill=clrs[x])
        else:
            img  = Image.new('RGB', (WIDTH, HEIGHT), color=(0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.rectangle((0, 0, 240, 240), (0, 0, 0))
            for x in range(0,8):
                draw.text((0, x * 30), msg[x], font=font, fill=clrs[x])
        disp.display(img)
    elif screen == 1: # pygame screen
        fontObj = pygame.font.Font(None,font_size)
        pygame.draw.rect(windowSurfaceObj,(0,0,0),Rect(0,0,240,240))
        if radio == 1 and os.path.exists(Radio_Stns[radio_stn] + ".jpg") and Disp_on == 1:
            image = pygame.image.load(Radio_Stns[radio_stn] + ".jpg")
            image = pygame.transform.scale(image,(240,240))
            windowSurfaceObj.blit(image,(0,0))
        elif radio == 0 and len(pfiles) > 0 and os.path.exists(pfiles[0]) and Disp_on == 1:
            image = pygame.image.load(pfiles[0])
            image = pygame.transform.scale(image,(240,240))
            windowSurfaceObj.blit(image,(0,0))
        for x in range(0,8):
            msgSurfaceObj = fontObj.render(data[x], False,clrs[x])
            msgRectobj = msgSurfaceObj.get_rect()
            msgRectobj.topleft = (10,x * font_size)
            windowSurfaceObj.blit(msgSurfaceObj, msgRectobj)
        pygame.display.update()
		
display_screen()
time.sleep(1)

def reload():
  global tracks,x,top,msg,Track_No,stop,relno
  if stop == 0:
    tracks  = []
    msg[0] = "Tracks: " + str(len(tracks))
    msg[1] = "Reloading tracks... "
    msg[2] = "" 
    display_screen()
    usb_tracks = glob.glob("/media/" + h_user[0] + "/*/*/*/*.mp3")
    sd_tracks  = glob.glob("/home/" + h_user[0] + "/Music/*/*/*.mp3")
    titles     = [0,0,0,0,0,0,0]
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
    msg[0] = ("Tracks: " + str(len(tracks)))
    Track_No = 0
    save_config()
    display_screen()
    if len(tracks) == 0:
        msg[0] = "Tracks: " + str(len(tracks))
        msg[1] = "Stopped Checking"
        stop = 1
    display_screen()
    time.sleep(1)
    
def save_config():
    global MP3_Play,radio,radio_stn,shuffled,album_mode,volume,gapless,Track_No,config_file
    headers  = ['MP3_Play  ','radio     ','radio_stn ','shuffled  ','album_mode','volume    ','gapless   ','Track_No  ']
    defaults = [MP3_Play,radio,radio_stn,shuffled,album_mode,volume,gapless,Track_No]
    with open(config_file, 'w') as f:
        for item in range(0,len(headers)):
            f.write(headers[item] + " : " + str(defaults[item]) + "\n")

def Set_Volume():
    global mixername,m,msg,MP3_Play,radio,radio_stn,shuffled,album_mode,volume,gapless,buttonVOLUP,lver
    msg[0] = "Volume " + str(volume)
    display_screen()
    timer1 = time.monotonic()
    while buttonVOLUP.is_pressed and time.monotonic() - timer1 < 0.5:
        pass
    while buttonVOLUP.is_pressed:
        if time.monotonic() - timer1 > 0.5:
            volume -= 2
            volume = max(volume,0)
            msg[0] = "Volume " + str(volume)
            display_screen()
            if len(alsaaudio.mixers()) > 0 and lver < 13:
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
    if len(alsaaudio.mixers()) > 0 and lver < 13:
        m.setvolume(volume)
    msg[0] = "Volume " + str(volume)
    display_screen()
    time.sleep(0.5)
    if len(alsaaudio.mixers()) > 0 and lver < 13:
        os.system("amixer -D pulse sset Master " + str(volume) + "%")
        if mixername == "DSP Program":
            os.system("amixer set 'Digital' " + str(volume + 107))
    else:
        os.system("wpctl set-volume @DEFAULT_AUDIO_SINK@ " + str(volume/100))
    save_config()

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
    msg[3] = str(line) + " " + str(total_size)
    display_screen()
    with open("freeSD.txt", "w") as f:
        f.write(str(total_size))
    reloading = 1
    relno     = 1

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
msg[0] = "Tracks: " + str(len(tracks))

if Track_No > len(tracks) - 1:
    Track_No = 0
display_screen()

# check if USB mounted and find USB storage
if use_USB == 1:
    start = time.monotonic()
    msg[0] = ("Checking for USB")
    display_screen()
    while time.monotonic() - start < usb_timer:
        usb = glob.glob("/media/" +  h_user[0] + "/*")
        usb_found = len(usb)
        msg[1] = "Found: " + str(usb_found) + " USBs"
        msg[2] = str(int(usb_timer -(time.monotonic() - start)))
        display_screen()
        time.sleep(1)
    msg[1] = ""
    msg[2] = ""
    display_screen()
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
                relno +=2
    else:
        freedisk = ["0","0","0","0"]
        with open("freedisk.txt", "w") as f:
            for item in freedisk:
                f.write("%s\n" % item)
        msg[1] = "No USB Found !!"
        display_screen()
        sd_tracks = glob.glob("/home/" + h_user[0] + "/Music/*/*/*.mp3")
        time.sleep(2)
        if len(sd_tracks) != len(tracks):
            reloading = 1
        msg[1] = ""
        display_screen()

if reloading == 1 and stop == 0:
    reload()
  
#check linux version.
lv = os.popen("cat /etc/os-release").read()
lva = lv.split("\n")
for w in range(0,len(lva)):
    title = lva[w].split("=")
    if title[0] == "VERSION_ID":
        lver = int(title[1][1:3])

# check for audio mixers
if len(alsaaudio.mixers()) > 0 and lver < 13:
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
    msg[0] = "Waiting for Radio..."
    display_screen()
    time.sleep(10)
    q = subprocess.Popen(["cvlc",Radio_Stns[radio_stn + 1]] ,shell=False)
    msg[0] = (Radio_Stns[radio_stn])
    msg[1] = ""
    display_screen()
else:
    msg[0] = "Initialising..."
    display_screen()

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
msg[0] = "Checking clock..."
msg[1] = ""
msg[2] = ""
display_screen()
if os.path.exists ("/run/shm/sync.txt"):
    os.remove("/run/shm/sync.txt")
display_screen()
os.system("timedatectl >> /run/shm/sync.txt")
display_screen()
# read sync.txt file
try:
    sync = []
    display_screen()
    with open("/run/shm/sync.txt", "r") as file:
        line = file.readline()
        while line:
            sync.append(line.strip())
            line = file.readline()
    display_screen()
    if sync[4] == "System clock synchronized: yes":
        synced = 1
        msg[1] = "Clock: Synced"
        time.sleep(1)
    else:
        synced = 0
        msg[1] = "Clock: NOT Synced"
        time.sleep(2)
    display_screen()
except:
    msg[1] = "Clock Error"
    display_screen()

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
        if Disp_on == 1 and showit == 1:
          showit = 0
          msg = [""] * 8
          msg[0] = "PLAY/Radio  PRE/NXT"
          if len(tracks) > 0:
            msg[1] = titles[0][0:19] # Artist
            msg[2] = titles[1][0:19] # Album
            msg[3] = titles[2][0:19] # Track
            # find album cover image
            ptrack = titles[3] + "/" + titles[4] + "/" + titles[5] + "/" + titles[6] + "/" + titles[0] + "/" + titles[1] + "/"
            pfiles = glob.glob(ptrack + "*.jpg")
            status()
          msg[5] = "Status...  "  +  txt
          msg[7] = "ALB/RNDM    GAP/SD"
          if sleep_timer != 0:
              time_left = int((sleep_timer - (time.monotonic() - sleep_timer_start))/60)
              if sleep_shutdn == 1:
                  msg[6] = "Shutdown: " + str(time_left) + "mins"
              else:
                  msg[6] = "Stopping: " + str(time_left) + "mins"
          display_screen()

        # display clock (if enabled and synced) when timed out
        if show_clock == 1 and Disp_on == 0 and synced == 1 and stopped == 0 and abort_sd == 1:
            now = datetime.datetime.now()
            clock = now.strftime("%H:%M:%S")
            secs = now.strftime("%S")
            t = ""
            for r in range (0,random.randint(0,10)):
                t += " "
            clock = t + clock
            if secs != old_secs2 :
              vp = random.randint(0,7)
              msg = [""] * 8
              msg[vp] = clock
              display_screen()
              old_secs2 = secs

        # DISPLAY OFF timer
        if time.monotonic() - Disp_start > Disp_timer and Disp_timer > 0 and Disp_on == 1:
            msg = [""] * 8
            Disp_on = 0
            showit = 0
            if show_clock == 0 and screen == 0:
                disp.set_backlight(0)
            display_screen()
            
        # sleep_timer timer
        if time.monotonic() - sleep_timer_start > sleep_timer and sleep_timer > 0:
            Disp_start = time.monotonic()
            abort_sd = 0
            t = 30
            while t > 0 and abort_sd == 0:
                if sleep_shutdn == 1:
                    msg[1] = "SHUTDOWN in " + str(t)
                else:
                    msg[1] = "STOPPING in " + str(t)
                display_screen()
                if buttonSLEEP.is_pressed or buttonPLAY.is_pressed:
                    sleep_timer_start = time.monotonic()
                    sleep_timer = 900
                    abort_sd = 1
                t -=1
                time.sleep(1)
            if abort_sd == 0:
                msg = [""] * 8
                if sleep_shutdn == 1:
                    msg[0] = "SHUTTING DOWN..."
                else:
                    msg[0] = "STOPPING........"
                display_screen()
                time.sleep(3)
                msg[0] = ""
                display_screen()
                sleep_timer = 0 
                if sleep_shutdn == 1:
                    os.system("sudo shutdown -h now")
            else:
                status()
                msg[0] = "PLAY/Radio  PRE/NXT"
                display_screen()
            Disp_start = time.monotonic()
            
        # check for PLAY/STOP/RADIO key
        if buttonPLAY.is_pressed and Disp_on == 0:
            Disp_on = 1
            Disp_start = time.monotonic()
            status()
            msg[0] = "PLAY/Radio  PRE/NXT"
            time.sleep(0.5)
            timer2 = time.monotonic()
        elif buttonPLAY.is_pressed:
            stopped = 0
            Disp_on = 1
            Disp_start = time.monotonic()
            timer1 = time.monotonic()
            msg = [""] * 8
            msg[0] = "PLAY/Radio  PRE/NXT"
            msg[1] = "HOLD 3s for RADIO"
            display_screen()
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
                save_config()
            else:
                msg[1] = ""
                msg[2] = ""
                msg[3] = ""
                q = subprocess.Popen(["cvlc",Radio_Stns[radio_stn + 1]] ,shell=False)
                time.sleep(0.05)
                msg[0] = (Radio_Stns[radio_stn])
                display_screen()
                rs = Radio_Stns[radio_stn]
                while buttonPLAY.is_pressed:
                    pass
                radio    = 1
                MP3_Play = 0
                save_config()
                
        # check NEXT/PREVIOUS ALBUM/ARTIST/A-Z key
        if buttonNEXT.is_pressed and Disp_on == 0:
            Disp_on = 1
            showit  = 1
            Disp_start = time.monotonic()
            status()
            msg[0] = "PLAY/Radio  PRE/NXT"
            time.sleep(0.5)
            timer2 = time.monotonic()
        elif buttonNEXT.is_pressed and len(tracks) > 1:
            Disp_on = 1
            showit  = 1
            time.sleep(0.2)
            timer1 = time.monotonic()
            while buttonNEXT.is_pressed and time.monotonic() - timer1 < 1:
                pass
            # NEXT TRACK
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
                    pfiles = []
                    ptrack = stitles[3] + "/" + stitles[4] + "/" + stitles[5] + "/" + stitles[6] + "/" + stitles[0] + "/" + stitles[1] + "/"
                    pfiles = glob.glob(ptrack + "*.jpg")
                    msg[0] = "PLAY/Radio  PRE/NXT" 
                    time.sleep(0.05)
                    msg[1] = titles[0][0:19]
                    msg[2] = titles[1][0:19]
                    msg[3] = titles[2][0:19]
                    display_screen()
                    time.sleep(0.05)
                    timer3 = time.monotonic()
                    album = 1
                    time.sleep(0.5)
            if time.monotonic() - timer1 > 1:
                # NEXT ALBUM
                showit = 1
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
                    msg[0] = "PLAY/Radio  PRE/NXT" 
                    msg[1] = titles[0][0:19]
                    msg[2] = titles[1][0:19]
                    msg[3] = titles[2][0:19]
                    pfiles = []
                    ptrack = titles[3] + "/" + titles[4] + "/" + titles[5] + "/" + titles[6] + "/" + titles[0] + "/" + titles[1] + "/"
                    pfiles = glob.glob(ptrack + "*.jpg")
                    display_screen()
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
                    msg[1] = titles[0][0:19]
                    msg[2] = titles[1][0:19]
                    msg[3] = titles[2][0:19]
                    pfiles = []
                    ptrack = titles[3] + "/" + titles[4] + "/" + titles[5] + "/" + titles[6] + "/" + titles[0] + "/" + titles[1] + "/"
                    pfiles = glob.glob(ptrack + "*.jpg")
                    display_screen()
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
                    msg[1] = titles[0][0:19]
                    msg[2] = titles[1][0:19]
                    msg[3] = titles[2][0:19]
                    pfiles = []
                    ptrack = titles[3] + "/" + titles[4] + "/" + titles[5] + "/" + titles[6] + "/" + titles[0] + "/" + titles[1] + "/"
                    pfiles = glob.glob(ptrack + "*.jpg")
                    display_screen()
                    time.sleep(0.5)
            timer3 = time.monotonic()
            album = 1
                        
        # check for GAPLESS/SHUTDOWN (SLEEP)  key
        if buttonSLEEP.is_pressed and Disp_on == 0:
            Disp_on = 1
            showit  = 1
            Disp_start = time.monotonic()
            status()
            msg[0] = "PLAY/Radio  PRE/NXT"
            time.sleep(0.5)
            timer2 = time.monotonic()
        elif buttonSLEEP.is_pressed:
            time.sleep(0.5)
            showit = 1
            timer1 = time.monotonic()
            timer = time.monotonic()
            if gapless == 0:
                    gap = gaptime
                    gapless = 1
                    msg = [""] * 8
                    msg[0] = "PLAY/Radio  PRE/NXT"
                    msg[1] = "Gapless ON"
                    display_screen()
                    time.sleep(1)
            else:
                    gap = 0
                    gapless = 0
                    msg = [""] * 8
                    msg[0] = "PLAY/Radio  PRE/NXT"
                    msg[1] = "Gapless OFF"
                    display_screen()
                    time.sleep(1)
            status()
            if album_mode == 0:
                    track_n = str(Track_No + 1) + "     "
            else:
                    track_n = "1/" + str(ctracks) + "       "
            msg[0] = "PLAY/Radio  PRE/NXT"
            display_screen()
            save_config()
            time.sleep(0.5)
            timer2 = time.monotonic()
            xt = 2
            while buttonSLEEP.is_pressed:
                if time.monotonic() - timer1 > 10:
                    msg[1] = "SHUTDOWN in " + str(20-int(time.monotonic() - timer1))
                    display_screen()
                if time.monotonic() - timer1 > 20:
                    # shutdown if pressed for 20 seconds
                    msg = [""] * 8
                    msg[0] = "SHUTTING DOWN..."
                    time.sleep(0.05)
                    display_screen()
                    time.sleep(2)
                    msg[0] = ""
                    display_screen()
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
            showit  = 1
            Disp_start = time.monotonic()
            status()
            msg[0] = "PLAY/Radio  PRE/NXT"
            time.sleep(0.5)
            timer2 = time.monotonic()
        elif buttonVOLUP.is_pressed:
            showit = 1
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
                    msg = [""] * 8
                    msg[0] = "PLAY/Radio  PRE/NXT"
                    msg[1] = "Album Mode ON "
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
                    msg = [""] * 8
                    msg[1] = "Album Mode OFF "
                    track_n  = str(Track_No) + "     "
                save_config()
                ptrack = titles[3] + "/" + titles[4] + "/" + titles[5] + "/" + titles[6] + "/" + titles[0] + "/" + titles[1] + "/"
                pfiles = glob.glob(ptrack + "*.jpg")
                display_screen()
                time.sleep(1)

            else:  
                msg = [""] * 8
                msg[0] = "PLAY/Radio  PRE/NXT"  
                if shuffled == 0:
                    shuffled = 1
                    shuffle(tracks)
                    Track_No = 0
                    album_mode = 0
                    track_n  = str(Track_No + 1) + "     "
                    msg[1] = "Random Mode ON "
                   
                else:
                    shuffled = 0
                    msg[1] = "Random Mode OFF "
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
                display_screen()
                save_config()
                time.sleep(1)
                timer2 = time.monotonic()
                xt = 2
            status()
            if album_mode == 0:
                track_n = str(Track_No + 1) + "     "
            else:
                track_n = "1/" + str(ctracks) + "       "
            msg[0] = "PLAY/Radio  PRE/NXT"
            ptrack = titles[3] + "/" + titles[4] + "/" + titles[5] + "/" + titles[6] + "/" + titles[0] + "/" + titles[1] + "/"
            pfiles = glob.glob(ptrack + "*.jpg")
            display_screen()
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
            msg = [""] * 8
            Disp_on = 0
            if show_clock == 0 and screen == 0:
                disp.set_backlight(0)
            display_screen()
            
        # sleep_timer timer
        if time.monotonic() - sleep_timer_start > sleep_timer and sleep_timer > 0:
            Disp_start = time.monotonic()
            abort_sd = 0
            t = 30
            Disp_on = 1
            while t > 0 and abort_sd == 0:
                if sleep_shutdn == 1:
                    msg[1] = "SHUTDOWN in " + str(t)
                    display_screen()
                else:
                    msg[1] = "STOPPING in " + str(t)
                    display_screen()
                if buttonSLEEP.is_pressed:
                    sleep_timer_start = time.monotonic()
                    sleep_timer = 900
                    abort_sd = 1
                t -=1
                time.sleep(1)
            if abort_sd == 0:
                msg = [""] * 8
                if sleep_shutdn == 1:
                    msg[0] = "SHUTTING DOWN..."
                    display_screen()
                else:
                    msg[0] = "STOPPING........"
                display_screen()
                msg[1] = ""
                time.sleep(1)
                Disp_on = 0
                msg[0] = ""
                display_screen()
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
        if Radio_Stns[radio_stn + 2] == 0:
            msg[1] = (Radio_Stns[radio_stn])
        else:
            msg[1] = ""
        if sleep_timer > 0:
            if sleep_shutdn == 1:
                msg[3] = "Shutdown: " + str(time_left) + "mins"
            else:
                msg[3] = "Stopping: " + str(time_left) + "mins"
        if show_clock == 1 and synced == 1:
            msg[2] = "      " + clock
        t = ""
        for r in range (0,random.randint(0,10)):
            t += " "
        clock = t + clock
        if Disp_on == 1:
            msg[0] = "STOP         PRE/NEXT"
            msg[7] = "VOL+/-       SLEEP/SD"
            display_screen()
        if show_clock == 1 and Disp_on == 0 and synced == 1 and stopped == 0:
            if secs != old_secs:
                if sleep_timer > 0:
                    clock = clock + " " + str(time_left)
                vp = random.randint(0,7)
                msg = [""] * 8
                msg[vp] = clock
                display_screen()
                old_secs = secs
            
        # check for VOLUME UP/DOWN  key
        if buttonVOLUP.is_pressed and Disp_on == 0:
            Disp_on = 1
            Disp_start = time.monotonic()
            status()
            msg = [""] * 8
            msg[0] = "STOP            PRE/NXT"
            msg[7] = "VOL+/-        SLEEP/SD"
            time.sleep(0.5)
            display_screen()
            timer2 = time.monotonic()
        elif buttonVOLUP.is_pressed:
            Set_Volume()
            status()
            time.sleep(0.5)
            msg = [""] * 8
            msg[0] = "STOP           PRE/NXT"
            msg[7] = "VOL+/-       SLEEP/SD"
            display_screen()
            Disp_start = time.monotonic()
            timer2 = time.monotonic()
                
           
        # check NEXT/PREVIOUS key
        if buttonNEXT.is_pressed and Disp_on == 0:
            Disp_on = 1
            Disp_start = time.monotonic()
            status()
            msg = [""] * 8
            msg[0] = "STOP       PRE/NEXT"
            display_screen()
            time.sleep(0.5)
            timer2 = time.monotonic()
        elif buttonNEXT.is_pressed:
            Disp_on = 1
            Disp_start = time.monotonic()
            timer1 = time.monotonic()
            while buttonNEXT.is_pressed and time.monotonic() - timer1 < 1:
                pass
            while buttonNEXT.is_pressed:
                if time.monotonic() - timer1 > 1:
                    radio_stn +=3
                    if radio_stn > len(Radio_Stns) - 3:
                        radio_stn = 0
                    if Radio_Stns[radio_stn + 2] == 0:
                        msg[1] = (Radio_Stns[radio_stn])
                    else:
                        msg[1] = ""
                    display_screen()
                    time.sleep(0.5)
            if time.monotonic() - timer1 < 1:        
                radio_stn -=3
                if radio_stn < 0:
                    radio_stn = len(Radio_Stns) - 3
                if Radio_Stns[radio_stn + 2] == 0:
                    msg[1] = (Radio_Stns[radio_stn])
                else:
                    msg[1] = ""
                display_screen()
            q.kill()
            q = subprocess.Popen(["cvlc",Radio_Stns[radio_stn + 1]] ,shell=False)
            time.sleep(1)
            #rs = Radio_Stns[radio_stn] + "               "[0:19]
            save_config()
            timer2 = time.monotonic()
            time.sleep(1)

          
        # check PLAY/STOP/Radio key
        if buttonPLAY.is_pressed and Disp_on == 0:
            Disp_on = 1
            Disp_start = time.monotonic()
            status()
            msg = [""] * 8
            msg[0] = "STOP       PRE/NEXT"
            time.sleep(0.5)
            timer2 = time.monotonic()
        elif buttonPLAY.is_pressed:
            Disp_on = 1
            Disp_start = time.monotonic()
            q.kill()
            radio = 0
            msg = [""] * 8
            if len(tracks) > 0:
                msg[0] = "PLAY/Radio  PRE/NXT"
            else:
                msg[0] = "Radio Stopped      "
            showit = 1
            display_screen()
            save_config()
            time.sleep(2)
            

        # check for sleep_timer key
        if buttonSLEEP.is_pressed and Disp_on == 0:
            Disp_on = 1
            Disp_start = time.monotonic()
            status()
            msg = [""] * 8
            msg[0] = "STOP       PRE/NEXT"
            display_screen()
            time.sleep(0.5)
            timer2 = time.monotonic()
        
        elif buttonSLEEP.is_pressed:
            Disp_on = 1
            Disp_start = time.monotonic()
            timer1 = time.monotonic()
            sleep_timer_start = time.monotonic()
            msg = [""] * 8
            msg[0] = "Set SLEEP.. " + str(int(sleep_timer/60))
            msg[1] = "HOLD for 20 to SHUTDOWN "
            display_screen()
            while buttonSLEEP.is_pressed:
                sleep_timer +=900
                if sleep_timer > 7200:
                     sleep_timer = 0
                sleep_timer_start = time.monotonic()
                msg = [""] * 8
                msg[0] = "Set SLEEP.. " + str(int(sleep_timer/60))
                display_screen()
                time.sleep(1)
                if time.monotonic() - timer1 > 10:
                    msg[1] = "SHUTDOWN in " + str(20-int(time.monotonic() - timer1))
                    display_screen()
                if time.monotonic() - timer1 > 20:
                    # shutdown if pressed for 20 seconds
                    msg = [""] * 8
                    msg[0] = "SHUTTING DOWN..."
                    display_screen()
                    time.sleep(2)
                    msg[0] = ""
                    display_screen()
                    MP3_Play = 0
                    radio = 0
                    time.sleep(1)
                    os.system("sudo shutdown -h now")
            Disp_start = time.monotonic()
            time.sleep(0.5)
            msg[0] = Radio_Stns[radio_stn]
            msg[1] = ""
            display_screen()
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
            msg[0] = "PLAY/Radio  PRE/NXT"
            msg[1] = titles[0][0:19]
            msg[2] = titles[1][0:19]
            msg[3] = titles[2][0:19]
            display_screen()
            MP3_Play = 0
            
        # sleep_timer timer
        if time.monotonic() - sleep_timer_start > sleep_timer and sleep_timer > 0:
            Disp_on = 1
            Disp_start = time.monotonic()
            abort_sd = 0
            t = 30
            while t > 0 and abort_sd == 0:
                msg = [""] * 8
                if sleep_shutdn == 1:
                    msg[1] = "SHUTDOWN in " + str(t)
                    display_screen()
                else:
                    msg[1] = "STOPPING in " + str(t)
                    display_screen()
                if buttonSLEEP.is_pressed:
                    sleep_timer_start = time.monotonic()
                    sleep_timer = 900
                    abort_sd = 1
                t -=1
                time.sleep(1)
            if abort_sd == 0:
                msg = [""] * 8
                if sleep_shutdn == 1:
                    msg[0] = "SHUTTING DOWN..."
                else:
                    msg[0] = "STOPPING........"
                time.sleep(0.05)
                display_screen()
                time.sleep(3)
                Disp_on = 0
                msg[0] = ""
                display_screen()
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
                msg[0] = "Play.." + str(track_n)[0:5] + txt
                display_screen()
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
              msg[0] = "STOP/Radio  PRE/NXT"
          else:
              msg[0] = "STOP/Radio  PRE/NXT"
          rpistr = "mplayer" + " -quiet " +  '"' + track + '"'
          msg[1] = titles[0][0:19]
          msg[2] = titles[1][0:19]
          msg[3] = titles[2][0:19]
          msg[7] = "VOL+/-      SLEEP/SD"
          if Disp_on == 1:
              ptrack = titles[3] + "/" + titles[4] + "/" + titles[5] + "/" + titles[6] + "/" + titles[0] + "/" + titles[1] + "/"
              pfiles = glob.glob(ptrack + "*.jpg")
              display_screen()
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
                  vp = random.randint(0,7)
                  msg = [""] * 8
                  msg[vp] = clock
                  display_screen()
                  old_secs2 = secs
                
            time.sleep(0.2)
            played  = time.monotonic() - timer1
            played_pc = int((played/track_len) *100)

            # DISPLAY OFF timer
            if time.monotonic() - Disp_start > Disp_timer and Disp_timer > 0 and Disp_on == 1:
                msg = [""] * 8
                Disp_on = 0
                if show_clock == 0 and screen == 0:
                    disp.set_backlight(0)
                display_screen()
           
            # display titles, status etc
            if Disp_on == 1:
                msg[1] = titles[0][0:19]
                msg[2] = titles[1][0:19]
                msg[3] = titles[2][0:19]
                played_pc =  "     " + str(played_pc)
                msg[0] = "STOP/Radio  PRE/NXT"
                status()
                msg[5] = "Status...  " +  txt
                msg[6] = ""
                if sleep_timer != 0:
                    time_left = int((sleep_timer - (time.monotonic() - sleep_timer_start))/60)
                    if sleep_shutdn == 1:
                        msg[6] = "Shutdown: " + str(time_left) + "mins"
                    else:
                        msg[6] = "Stopping: " + str(time_left) + "mins"
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
                msg[4] = " " + str(pmin) + ":" + str(psec2) + " of " + str(lmin) + ":" + str(lsec2)
                msg[7] = "VOL+/-       SLEEP/SD"
                ptrack = titles[3] + "/" + titles[4] + "/" + titles[5] + "/" + titles[6] + "/" + titles[0] + "/" + titles[1] + "/"
                pfiles = glob.glob(ptrack + "*.jpg")
                display_screen()
                   
            # check for PLAY/STOP/RADIO key
            if buttonPLAY.is_pressed and Disp_on == 0:
                Disp_on = 1
                Disp_start = time.monotonic()
                status()
                msg[0] = "STOP/Radio  PRE/NXT"
                display_screen()
                time.sleep(0.5)
                timer2 = time.monotonic()
            elif  buttonPLAY.is_pressed:
                Disp_on = 1
                Disp_start = time.monotonic()
                timer1 = time.monotonic()
                os.killpg(p.pid, SIGTERM)
                msg[0] = "Track Stopped"
                display_screen()
                time.sleep(2)
                status()
                msg = [""] * 8
                msg[0] = "PLAY/Radio  PRE/NXT"
                showit = 1
                display_screen()
                go = 0
                MP3_Play = 0
                save_config()
                timer2 = time.monotonic()
                
            # check for NEXT/PREVIOUS TRACK key
            elif buttonNEXT.is_pressed and Disp_on == 0:
                Disp_on = 1
                Disp_start = time.monotonic()
                status()
                msg[0] = "STOP/Radio  PRE/NXT"
                display_screen()
                time.sleep(0.5)
                timer2 = time.monotonic()
            elif buttonNEXT.is_pressed:
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
                            msg[0] = "STOP/Radio  PRE/NXT"
                            titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
                            msg[1] = titles[0][0:19]
                            msg[2] = titles[1][0:19]
                            msg[3] = titles[2][0:19]
                            ptrack = titles[3] + "/" + titles[4] + "/" + titles[5] + "/" + titles[6] + "/" + titles[0] + "/" + titles[1] + "/"
                            pfiles = glob.glob(ptrack + "*.jpg")
                            display_screen()
                            time.sleep(0.5)
                if time.monotonic() - timer1 < 1:
                    if go == 1:
                        Track_No -= 1
                        if Track_No < 0:
                            Track_No = len(tracks) + Track_No
                    msg[0] = "STOP/Radio  PRE/NXT"
                    titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
                    msg[1] = titles[0][0:19]
                    msg[2] = titles[1][0:19]
                    msg[3] = titles[2][0:19]
                    ptrack = titles[3] + "/" + titles[4] + "/" + titles[5] + "/" + titles[6] + "/" + titles[0] + "/" + titles[1] + "/"
                    pfiles = glob.glob(ptrack + "*.jpg")
                    display_screen()
                timer2 = time.monotonic()
                go = 0

            # check for VOLUME UP/DOWN  key
            elif buttonVOLUP.is_pressed and Disp_on == 0:
                Disp_on = 1
                Disp_start = time.monotonic()
                status()
                msg[0] = "STOP/Radio  PRE/NXT"
                display_screen()
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
                msg[0] = "STOP/Radio  PRE/NXT" 
                display_screen()
                Disp_start = time.monotonic()
                timer2 = time.monotonic()
 
                           
            # check for SLEEP/SHUTDOWN key
            elif  buttonSLEEP.is_pressed and Disp_on == 0:
                Disp_start = time.monotonic()
                Disp_on = 1
                status()
                msg[0] = "STOP/Radio  PRE/NXT"
                display_screen()
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
                msg = [""] * 8
                msg[0] = "Set SLEEP.. " + str(int(sleep_timer/60))
                msg[1] = "HOLD for 20 to SHUTDOWN "
                display_screen()
                time.sleep(1)
                while buttonSLEEP.is_pressed:
                    if album_mode == 0:
                        sleep_timer +=900
                        if sleep_timer > 7200:
                            sleep_timer = 0
                        sleep_timer_start = time.monotonic()
                        msg[0] = "Set SLEEP.. " + str(int(sleep_timer/60))
                        display_screen()
                        time.sleep(1)
                    if time.monotonic() - timer1 > 10:
                        msg[1] = "SHUTDOWN in " + str(20-int(time.monotonic() - timer1))
                    if time.monotonic() - timer1 > 20:
                        # shutdown if pressed for 20 seconds
                        msg = [""] * 8
                        msg[0] = "SHUTTING DOWN..."
                        time.sleep(0.05)
                        display_screen()
                        time.sleep(2)
                        msg[0] = ""
                        display_screen()
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
        





            
