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

version  = "1.38"

# set default variables (saved in config_file and overridden at future startups)
MP3_Play     = 0   # set to 1 to start playing MP3s at boot, else 0
radio        = 0   # set to 1 to start playing Radio at boot, else 0
radio_stn    = 0   # selected radio station at startup (Note 0,3,6 etc)
shuffled     = 0   # 0 = Unshuffled, 1 = Shuffled
album_mode   = 0   # set to 1 for Album Mode, will play an album then stop
gapless      = 0   # set to 1 for gapless play
volume       = 40  # range 0 - 100
Track_No     = 0   # selected MP3 track number at startup

# variables set once
config_file  = "PirateConfig.txt"
use_USB      = 1   # set to 0 if you ONLY use /home/<USERNAME>/Music/... on SD card
usb_timer    = 6   # seconds to find USB present
sleep_time   = 0   # sleep_time timer in minutes, use 15,30,45,60 etc...set to 0 to disable
sleep_shutdn = 0   # set to 1 to shutdown Pi when sleep times out
Disp_time    = 60  # Display timeout in seconds, set to 0 to disable
show_clock   = 1   # set to 1 to show clock, only use if on web or using RTC
gaptime      = 2   # set pre-start time for gapless, in seconds
screen       = 0   # for testing, 0 = ST7789, 1 = pygame screen
banners      = 0   # set to 1 to add black backgrounds on rows 1 and 8

#RADIO STATIONS, "Name","URL",0 or 1 - 1 means don't show name if you have a logo image.
Radio_Stns = ["Radio Paradise Rock","http://stream.radioparadise.com/rock-192",1,
              "Radio Paradise Main","http://stream.radioparadise.com/mp3-320",0,
              "Radio Paradise Mellow","http://stream.radioparadise.com/mellow-192",0,
              "Radio Caroline","http://sc6.radiocaroline.net:10558/",0,
              "BBC World Service","http://stream.live.vc.bbcmedia.co.uk/bbc_world_service",0]

# GPIO BUTTONS GPIO BCM numbers (Physical pin numbers) [Pirate button]
PLAY  = 5  # (29) [A] PLAY / STOP / HOLD for 3 seconds for RADIO 
VOLUP = 6  # (31) [B] Adjust volume UP whilst playing, set ALBUM MODE/RANDOM ON/OFF whilst stopped
NEXT  = 16 # (36) [X] HOLD for NEXT TRACK / STATION (whilst playing) / NEXT ALBUM (whilst stopped) - quick press for PREVIOUS ALBUM
SLEEP = 24 # (18) [Y] Set SLEEP time, HOLD for 20 seconds to SHUTDOWN whilst playing, set GAPLESS/SHUTDOWN whilst stopped.

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
sleep_time  = sleep_time * 60
freedisk    = ["0","0","0","0"]
old_secs    = "00"
old_secs2   = "00"
Disp_on     = 1
stopped     = 0
synced      = 0
reloading   = 0
msg         = [""] * 8
msg[0]      = "MP3 Player: v" + version
abort_sd    = 1
usb_found   = 0
stop        = 0
pfiles      = []
ptrack      = ""
alength     = 0
atracks     = 0
asofar      = 0
astrack     = 0
aitracks    = [0] * 70
scroll      = 0
old_volume  = volume
old_radio   = ""

# find username
h_user  = []
h_user.append(os.getlogin())

def display_screen():
    global image,top,msg,font,img,WIDTH,HEIGHT
    global MP3_Play,radio,screen,font_size,radio,Radio_Stns,radio_stn,pfiles,Disp_on,ptrack,banners
    clrs = [(255,255,0),(255,255,255),(255,255,255),(255,255,255),(255,255,255),(255,255,255),(255,255,255),(255,255,0)]
    if screen == 0: # st7789 screen
        if Disp_on == 1:
            disp.set_backlight(1)
        if radio == 1 and os.path.exists(Radio_Stns[radio_stn] + ".jpg") and Disp_on == 1:
            with Image.open(Radio_Stns[radio_stn] + ".jpg") as img:
                img  = img.resize((240,240),resample=Image.LANCZOS)
                draw = ImageDraw.Draw(img)
                if banners == 1:
                    draw.rectangle((0, 0, 240, 20), (0, 0, 0))
                    draw.rectangle((0, 212, 240, 240), (0, 0, 0))
                for x in range(0,8):
                    draw.text((0, x * 30), msg[x], font=font, fill=clrs[x])
        elif radio == 0 and len(pfiles) > 0 and os.path.exists(pfiles[0]) and Disp_on == 1:
            with Image.open(pfiles[0]) as img:
                img  = img.resize((240,240),resample=Image.LANCZOS)
                draw = ImageDraw.Draw(img)
                if banners == 1:
                    draw.rectangle((0, 0, 240, 20), (0, 0, 0))
                    draw.rectangle((0, 212, 240, 240), (0, 0, 0))
                for x in range(0,8):
                    if os.path.exists(ptrack + "colors.txt"):
                        tclrs = []
                        with open(ptrack + "colors.txt", "r") as file:
                             line = file.readline()
                             while line:
                                 line = line.strip()
                                 r,g,b = line.split(",")
                                 tclrs.append(tuple((int(r),int(g),int(b))))
                                 line = file.readline()
                        if len(tclrs) < 8:
                            draw.text((0, x * 30), msg[x], font=font, fill=(tclrs[0]))
                        else:
                            draw.text((0, x * 30), msg[x], font=font, fill=(tclrs[x]))
                    else:
                        draw.text((0, x * 30), msg[x], font=font, fill=clrs[x])
        else:
            img  = Image.new('RGB', (WIDTH, HEIGHT), color=(0, 0, 0))
            draw = ImageDraw.Draw(img)
            if os.path.exists(ptrack + "backgnd.txt"):
                with open(ptrack + "backgnd.txt", "r") as file:
                    line = file.readline()
                    r,g,b = line.split(",")
                    draw.rectangle((0, 0, 240, 240), (int(r),int(g),int(b)))
            else:
                draw.rectangle((0, 0, 240, 240), (0, 0, 0))
            for x in range(0,8):
                draw.text((0, x * 30), msg[x], font=font, fill=clrs[x])
        disp.display(img)
    elif screen == 1: # pygame screen
        fontObj = pygame.font.Font(None,font_size)
        if os.path.exists(ptrack + "backgnd.txt"):
            with open(ptrack + "backgnd.txt", "r") as file:
                line = file.readline()
                r,g,b = line.split(",")
                pygame.draw.rect(windowSurfaceObj,(int(r),int(g),int(b)),Rect(0,0,240,240))
        else:
                pygame.draw.rect(windowSurfaceObj,(0,0,0),Rect(0,0,240,240))
        if radio == 1 and os.path.exists(Radio_Stns[radio_stn] + ".jpg") and Disp_on == 1:
            image = pygame.image.load(Radio_Stns[radio_stn] + ".jpg")
            image = pygame.transform.scale(image,(240,240))
            windowSurfaceObj.blit(image,(0,0))
            if banners == 1:
                pygame.draw.rect(windowSurfaceObj,(0,0,0),Rect(0,0,240,19))
                pygame.draw.rect(windowSurfaceObj,(0,0,0),Rect(0,210,240,240))
        elif radio == 0 and len(pfiles) > 0 and os.path.exists(pfiles[0]) and Disp_on == 1:
            image = pygame.image.load(pfiles[0])
            image = pygame.transform.scale(image,(240,240))
            windowSurfaceObj.blit(image,(0,0))
            if banners == 1:
                pygame.draw.rect(windowSurfaceObj,(0,0,0),Rect(0,0,240,19))
                pygame.draw.rect(windowSurfaceObj,(0,0,0),Rect(0,210,240,240))
        for x in range(0,8):
            if os.path.exists(ptrack + "colors.txt"):
                with open(ptrack + "colors.txt", "r") as file:
                    tclrs = []
                    with open(ptrack + "colors.txt", "r") as file:
                         line = file.readline()
                         while line:
                             line = line.strip()
                             r,g,b = line.split(",")
                             tclrs.append(tuple((int(r),int(g),int(b))))
                             line = file.readline()
                    if len(tclrs) < 8:
                        msgSurfaceObj = fontObj.render(msg[x], False,(tclrs[0]))
                    else:
                        msgSurfaceObj = fontObj.render(msg[x], False,(tclrs[x]))
            else:
                msgSurfaceObj = fontObj.render(msg[x], False,clrs[x])
            msgRectobj = msgSurfaceObj.get_rect()
            msgRectobj.topleft = (10,x * font_size)
            windowSurfaceObj.blit(msgSurfaceObj, msgRectobj)
        pygame.display.update()
		
display_screen()
time.sleep(1)

def reload():
  global tracks,x,top,msg,Track_No,stop
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
      msg[0] = "Tracks: " + str(len(tracks))
      display_screen()
      if len(tracks) > 0:
          tracks.sort()
      with open('tracks.txt', 'w') as f:
          for item in tracks:
              f.write("%s\n" % item)
      Track_No = 0
      save_config()
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
    if volume > 0:
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
            volume = max(volume,2)
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
        volume += 5
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
    global txt,shuffled,gapless,album_mode,sleep_time
    txt = " "
    if shuffled == 1:
        if album_mode == 0:
            txt +="R"
        else:
            txt +="r"
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
    if sleep_time > 0:
        txt +="S"
    else:
        txt +=" "
    if volume > 0:
        txt +=" "
    else:
        txt +=" MUTED"

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
        time.sleep(1)
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
msg[0] = "Tracks: " + str(len(tracks))

if Track_No > len(tracks) - 1:
    Track_No = 0
display_screen()
if len(tracks) == 0:
	MP3_Play = 0

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
        time.sleep(2)
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
    msg[0] = "STOP       PRE/NEXT"
    msg[1] = (Radio_Stns[radio_stn])
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

def album_length():
	# determine album timings and number of tracks
    global tracks,Track_No,atracks,alength,astrack,aitracks
    # find first track of Album
    titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
    new_artist = titles[0]
    new_album  = titles[1]
    Track_No -= 100
    Track_No = max(Track_No,0)
    titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
    while new_artist != titles[0] or new_album != titles[1]:
        titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
        Track_No +=1
    Track_No -=1
    astrack = Track_No # first track of an album
    # find number of Album tracks and album timings
    Tack_No = Track_No 
    alength  = 0
    stitles = [0,0,0,0,0,0,0]
    stitles[0],stitles[1],stitles[2],stitles[3],stitles[4],stitles[5],stitles[6] = tracks[Tack_No].split("/")
    talbum = stitles[1]
    tartist = stitles[0]
    itr = 0
    while stitles[1] == talbum and stitles[0] == tartist and Tack_No < len(tracks):
        stitles[0],stitles[1],stitles[2],stitles[3],stitles[4],stitles[5],stitles[6] = tracks[Tack_No].split("/")
        strack = stitles[3] + "/" + stitles[4] + "/" + stitles[5] + "/" + stitles[6] + "/" + stitles[0] + "/" + stitles[1] + "/" + stitles[2]
        audio = MP3(strack)
        alength += audio.info.length
        aitracks[itr] = audio.info.length # stores individual track lengths of an album
        Tack_No +=1
        itr +=1
    audio = MP3(strack)
    alength -= audio.info.length     # full album length
    atracks = Tack_No - Track_No - 1 # number of album tracks
    
if album_mode == 1 and len(tracks) > 0:
    shuffled = 0
    tracks.sort()
    album_length()
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

# initalise timers
sleep_timer = time.monotonic()
Disp_timer  = time.monotonic()
sync_timer  = time.monotonic()
Album_timer = time.monotonic()

# check if clock synchronised
msg[0] = "Checking clock..."
msg[1] = ""
msg[2] = ""
display_screen()
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
         
        # Display Artist / Album / Track names
        if Disp_on == 1:
            msg = [""] * 8
            msg[0] = "PLAY/Radio PRE/NEXT"
            if len(tracks) > 0:
                msg[1] = titles[0][0:19] # Artist
                if len(titles[1]) < 21:
                    msg[2] = titles[1][0:19] # Album
                else:
                    tema = titles[1] + " - " + titles[1]
                    msg[2] = tema[scroll:scroll + 19] # Album
                    scroll +=1
                    time.sleep(0.05)
                    if scroll > len(titles[1]):
                        scroll = 0
                temt = titles[2][0:-4]
                msg[3] = temt[0:19] # Track
                if album_mode == 1:
                    msg[4] = "1 of " + str(atracks) + " : " + str(int(alength/60)) + "mins"
                # find album cover image
                ptrack = titles[3] + "/" + titles[4] + "/" + titles[5] + "/" + titles[6] + "/" + titles[0] + "/" + titles[1] + "/"
                pfiles = glob.glob(ptrack + "*.jpg")
                status()
            msg[5] = "Status...  "  +  txt
            now = datetime.datetime.now()
            clock = now.strftime("%H:%M:%S")
            secs  = now.strftime("%S")
            if show_clock == 1 and synced == 1:
                msg[6] = "         " + clock
            msg[7] = "ALB/RNDM    GAP/SD"
            if sleep_time != 0:
                time_left = int((sleep_time - (time.monotonic() - sleep_timer))/60)
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
        if time.monotonic() - Disp_timer > Disp_time and Disp_time > 0 and Disp_on == 1:
            msg = [""] * 8
            Disp_on = 0
            if show_clock == 0 and screen == 0:
                disp.set_backlight(0)
            display_screen()
            
        # check sleep_time
        if time.monotonic() - sleep_timer > sleep_time and sleep_time > 0:
            Disp_timer = time.monotonic()
            abort_sd = 0
            t = 30
            while t > 0 and abort_sd == 0:
				# count down to stop / shutdown
                if sleep_shutdn == 1:
                    msg[1] = "SHUTDOWN in " + str(t)
                else:
                    msg[1] = "STOPPING in " + str(t)
                display_screen()
                if buttonSLEEP.is_pressed or buttonPLAY.is_pressed:
					# abort stop / shutdown if button pressed
                    sleep_timer = time.monotonic()
                    sleep_time = 900
                    abort_sd = 1
                t -=1
                time.sleep(1)
            if abort_sd == 0:
				# stop or shutdown
                msg = [""] * 8
                if sleep_shutdn == 1:
                    msg[0] = "SHUTTING DOWN..."
                else:
                    msg[0] = "STOPPING........"
                display_screen()
                time.sleep(3)
                msg[0] = ""
                display_screen()
                sleep_time = 0 
                if sleep_shutdn == 1:
                    os.system("shutdown -h now")
            else:
				# aborted stop / shutdown
                status()
                msg[0] = "PLAY/Radio PRE/NEXT"
                display_screen()
            Disp_timer = time.monotonic()
            
        # check for PLAY/STOP/RADIO key
        if buttonPLAY.is_pressed and Disp_on == 0:
            Disp_on = 1
            Disp_timer = time.monotonic()
            status()
            msg = [""] * 8
            msg[0] = "PLAY/Radio PRE/NEXT"
            display_screen()
            time.sleep(0.5)
        elif buttonPLAY.is_pressed:
			# START MP3 or RADIO PLAY
            stopped = 0
            Disp_on = 1
            Disp_timer = time.monotonic()
            timer1 = time.monotonic()
            msg = [""] * 8
            msg[0] = "PLAY/Radio PRE/NEXT"
            msg[1] = "HOLD 3s for RADIO"
            display_screen()
            time.sleep(0.5)
            sleep_time = 0
            while buttonPLAY.is_pressed and time.monotonic() - timer1 < 3:
                pass
            if time.monotonic() - timer1 < 3 and len(tracks) > 0:
				# PLAY MP3
                if album_mode == 1:
                    Album_timer = time.monotonic()
                    asofar = 0
					# determine album length and number of tracks
                    album_length()
                MP3_Play = 1
                radio    = 0
                time.sleep(0.5)
                save_config()
            else:
				# PLAY RADIO
                q = subprocess.Popen(["cvlc",Radio_Stns[radio_stn + 1]] ,shell=False)
                time.sleep(0.05)
                radio    = 1
                MP3_Play = 0
                msg = [""] * 8
                msg[0] = "STOP         PRE/NEXT"
                msg[1] = (Radio_Stns[radio_stn])
                msg[7] = "VOL+/-       SLEEP/SD"
                display_screen()
                timer1 = time.monotonic()
                while buttonPLAY.is_pressed:
                    pass
                save_config()
                
        # check NEXT/PREVIOUS ALBUM/ARTIST/A-Z key
        if buttonNEXT.is_pressed and Disp_on == 0:
            Disp_on = 1
            Disp_timer = time.monotonic()
            status()
            msg[0] = "PLAY/Radio PRE/NEXT"
            display_screen()
            time.sleep(0.5)
        elif buttonNEXT.is_pressed and len(tracks) > 1:
            Disp_on = 1
            time.sleep(0.2)
            timer1 = time.monotonic()
            Disp_timer = time.monotonic()
            while buttonNEXT.is_pressed and time.monotonic() - timer1 < 1:
                pass
            if time.monotonic() - timer1 < 1:
				# PREVIOUS ALBUM
                if album_mode == 1 and shuffled == 1:
                    shuffled = 0
                    tracks.sort()
                while titles[1] == old_album and titles[0] == old_artist and Track_No > -1:
                    Track_No -=1
                    if Track_No < 0:
                        Track_No = len(tracks) - 1
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
                if album_mode == 1:
                    album_length()
                pfiles = []
                ptrack = titles[3] + "/" + titles[4] + "/" + titles[5] + "/" + titles[6] + "/" + titles[0] + "/" + titles[1] + "/"
                pfiles = glob.glob(ptrack + "*.jpg")
                msg[0] = "PLAY/Radio PRE/NEXT" 
                time.sleep(0.05)
                msg[1] = titles[0][0:19]
                msg[2] = titles[1][0:19]
                temt   = titles[2][0:-4]
                msg[3] = temt[0:19]
                if album_mode == 1:
                    msg[4] = "1 of " + str(atracks) + " : " + str(int(alength/60)) + "mins"
                display_screen()
                time.sleep(0.5)
            if time.monotonic() - timer1 > 1:
                # NEXT ALBUM
                if album_mode == 1 and shuffled == 1:
                    shuffled = 0
                    tracks.sort()
                while buttonNEXT.is_pressed and buttonSLEEP.is_pressed == 0 and buttonVOLUP.is_pressed == 0:
                    while titles[1] == old_album and titles[0] == old_artist:
                        Track_No +=1
                        if Track_No > len(tracks) - 1:
                            Track_No = 0
                        titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
                    old_album  = titles[1]
                    old_artist = titles[0]
                    if album_mode == 1:
                        album_length()
                    msg[0] = "PLAY/Radio PRE/NEXT" 
                    msg[1] = titles[0][0:19]
                    msg[2] = titles[1][0:19]
                    temt   = titles[2][0:-4]
                    msg[3] = temt[0:19]
                    if album_mode == 1:
                        msg[4] = "1 of " + str(atracks) + " : " + str(int(alength/60)) + "mins"
                    msg[7] = "NEXT A-Z     ARTIST" 
                    pfiles = []
                    ptrack = titles[3] + "/" + titles[4] + "/" + titles[5] + "/" + titles[6] + "/" + titles[0] + "/" + titles[1] + "/"
                    pfiles = glob.glob(ptrack + "*.jpg")
                    display_screen()
                    time.sleep(0.5)
                # NEXT ARTIST
                while buttonNEXT.is_pressed and buttonSLEEP.is_pressed:
                    while titles[0] == old_artist:
                        Track_No +=1
                        if Track_No > len(tracks) - 1:
                            Track_No = 0
                        titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
                    old_artist = titles[0]
                    if album_mode == 1:
                        album_length()
                    msg[1] = titles[0][0:19]
                    msg[2] = titles[1][0:19]
                    temt   = titles[2][0:-4]
                    msg[3] = temt[0:19]
                    if album_mode == 1:
                        msg[4] = "1 of " + str(atracks) + " : " + str(int(alength/60)) + "mins"
                    msg[7] = "NEXT A-Z     ARTIST"
                    pfiles = []
                    ptrack = titles[3] + "/" + titles[4] + "/" + titles[5] + "/" + titles[6] + "/" + titles[0] + "/" + titles[1] + "/"
                    pfiles = glob.glob(ptrack + "*.jpg")
                    display_screen()
                    time.sleep(0.5)
                # NEXT A-Z ARTIST    
                while buttonNEXT.is_pressed and buttonVOLUP.is_pressed:
                    while titles[0][0:1] == old_artist[0:1]: 
                        Track_No +=1
                        if Track_No > len(tracks) - 1:
                            Track_No = 0
                        titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
                    old_artist = titles[0]
                    if album_mode == 1:
                        album_length()
                    msg[1] = titles[0][0:19]
                    msg[2] = titles[1][0:19]
                    temt   = titles[2][0:-4]
                    msg[3] = temt[0:19]
                    if album_mode == 1:
                        msg[4] = "1 of " + str(atracks) + " : " + str(int(alength/60)) + "mins"
                    msg[7] = "NEXT A-Z     ARTIST"
                    pfiles = []
                    ptrack = titles[3] + "/" + titles[4] + "/" + titles[5] + "/" + titles[6] + "/" + titles[0] + "/" + titles[1] + "/"
                    pfiles = glob.glob(ptrack + "*.jpg")
                    display_screen()
                    time.sleep(0.5)
                        
        # check for GAPLESS/SHUTDOWN (SLEEP)  key
        if buttonSLEEP.is_pressed and Disp_on == 0:
            Disp_on = 1
            Disp_timer = time.monotonic()
            status()
            msg[0] = "PLAY/Radio PRE/NEXT"
            display_screen()
            time.sleep(0.5)
        elif buttonSLEEP.is_pressed:
            time.sleep(0.5)
            timer1 = time.monotonic()
            Disp_timer = time.monotonic()
            if gapless == 0:
				# switch ON GAPLESS
                gap = gaptime
                gapless = 1
                msg = [""] * 8
                msg[1] = "Gapless ON"
                display_screen()
                time.sleep(1)
            else:
				# switch OFF GAPLESS
                gap = 0
                gapless = 0
                msg = [""] * 8
                msg[1] = "Gapless OFF"
                display_screen()
                time.sleep(1)
            status()
            msg[0] = "PLAY/Radio PRE/NEXT"
            display_screen()
            save_config()
            time.sleep(0.5)
            while buttonSLEEP.is_pressed:
                if buttonVOLUP.is_pressed:
                    reload()
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
                    os.system("shutdown -h now")
           
        # check for ALBUM MODE/RANDOM (VOLUP) key
        if buttonVOLUP.is_pressed and Disp_on == 0:
            Disp_on = 1
            Disp_timer = time.monotonic()
            status()
            msg[0] = "PLAY/Radio PRE/NEXT"
            display_screen()
            time.sleep(0.5)
        elif buttonVOLUP.is_pressed:
            timer1 = time.monotonic()
            Disp_timer = time.monotonic()
            while buttonVOLUP.is_pressed and time.monotonic() - timer1 < 2:
                pass
            if time.monotonic() - timer1 < 1:
                if album_mode == 0:
					# switch ALBUM MODE ON
                    album_mode = 1
                    shuffled   = 0
                    itles[0],itles[1],itles[2],itles[3],itles[4],itles[5],itles[6] = tracks[Track_No].split("/")
                    tracks.sort()
                    Track_No = 0
                    titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
                    while titles[0] != itles[0] or titles[1] != itles[1]:
                        Track_No +=1
                        titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
                    msg    = [""] * 8
                    msg[0] = "PLAY/Radio PRE/NEXT"
                    msg[1] = "Album Mode ON "
                    album_length()
                else:
					# switch ALBUM MODE OFF
                    album_mode = 0
                    shuffled   = 0
                    tracks.sort()
                    msg = [""] * 8
                    msg[1] = "Album Mode OFF "
                save_config()
                ptrack = titles[3] + "/" + titles[4] + "/" + titles[5] + "/" + titles[6] + "/" + titles[0] + "/" + titles[1] + "/"
                pfiles = glob.glob(ptrack + "*.jpg")
                display_screen()
                time.sleep(1)
            else:  
                # RANDOMISE
                msg = [""] * 8
                msg[0] = "PLAY/Radio PRE/NEXT" 
                if shuffled == 0:
                    if album_mode == 0:
				        # shuffle tracks
                        shuffled = 1
                        shuffle(tracks)
                        Track_No = 0
                        msg[1] = "Random Mode ON "
                    else:
					    # SHUFFLE ALBUM
                        tracks[Track_No:Track_No + atracks] = random.sample(tracks[Track_No:Track_No + atracks],atracks)
                        shuffled = 1
                        msg[1] = "Random Album ON "
                        album_length()
                else:
				    # unshuffle tracks 
                    shuffled = 0
                    msg[1] = "Random OFF "
                    if album_mode == 0:
                        itles[0],itles[1],itles[2],itles[3],itles[4],itles[5],itles[6] = tracks[Track_No].split("/")
                        tracks.sort()
                        Track_No = 0
                        titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
                        while titles[0] != itles[0] or titles[1] != itles[1]:
                            Track_No +=1
                            titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
                    else:
				     	# UNSHUFFLE ALBUM
                        tracks.sort()
                        album_length()
                display_screen()
                time.sleep(1)
                while buttonVOLUP.is_pressed:
                    pass
                titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
                msg[1] = titles[0][0:19]
                msg[2] = titles[1][0:19]
                temt   = titles[2][0:-4]
                msg[3] = temt[0:19]
                display_screen()
                save_config()

            status()
            msg[0] = "PLAY/Radio PRE/NEXT"
            ptrack = titles[3] + "/" + titles[4] + "/" + titles[5] + "/" + titles[6] + "/" + titles[0] + "/" + titles[1] + "/"
            pfiles = glob.glob(ptrack + "*.jpg")
            display_screen()
                  
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
        if album_mode == 1 and len(tracks) > 0:
            if Track_No > (astrack + atracks) - 1:
                status()
                msg[0] = "PLAY/Radio PRE/NEXT"
                msg[1] = titles[0][0:19]
                msg[2] = titles[1][0:19]
                temt   = titles[2][0:-4]
                msg[3] = temt[0:19]
                display_screen()
                MP3_Play = 0
            
        # sleep_time timer
        if time.monotonic() - sleep_timer > sleep_time and sleep_time > 0:
            Disp_on = 1
            Disp_timer = time.monotonic()
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
                    sleep_timer = time.monotonic()
                    sleep_time = 900
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
                    os.system("shutdown -h now")
                sleep_time = 0
                stopped = 1
                MP3_Play = 0
            else:
                status()
                display_screen()
                time.sleep(0.05)
                Disp_timer = time.monotonic()
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
          rpistr = "mplayer" + " -quiet " +  '"' + track + '"'
          if Disp_on == 1:
              msg[0] = "STOP         PRE/NEXT"
              msg[1] = titles[0][0:19]
              msg[2] = titles[1][0:19]
              temt   = titles[2][0:-4]
              msg[3] = temt[0:19]
              msg[7] = "VOL+/-   MUTE/SLEEP"
              ptrack = titles[3] + "/" + titles[4] + "/" + titles[5] + "/" + titles[6] + "/" + titles[0] + "/" + titles[1] + "/"
              pfiles = glob.glob(ptrack + "*.jpg")
              display_screen()
          audio = MP3(track)
          track_len = audio.info.length
          p = subprocess.Popen(rpistr, shell=True, preexec_fn=os.setsid)
          poll = p.poll()
          while poll != None:
            poll = p.poll()
          timer1 = time.monotonic()
          go = 1
          played = time.monotonic() - timer1
          
          # loop while playing selected MP3 track
          while poll == None and track_len - played > gap and (time.monotonic() - sleep_timer < sleep_time or sleep_time == 0):
            time_left = int((sleep_time - (time.monotonic() - sleep_timer))/60)
                
            # display clock whilst timed out (if enabled and synced)
            if show_clock == 1 and Disp_on == 0 and synced == 1:
                now = datetime.datetime.now()
                clock = now.strftime("%H:%M:%S")
                secs = now.strftime("%S")
                t = ""
                for r in range (0,random.randint(0,10)):
                    t += " "
                clock = t + clock
                time_left = int((sleep_time - (time.monotonic() - sleep_timer))/60)
                if sleep_time > 0:
                    clock += " " + str(time_left)
                if secs != old_secs2 :
                  vp = random.randint(0,7)
                  msg = [""] * 8
                  msg[vp] = clock
                  display_screen()
                  old_secs2 = secs
                
            time.sleep(0.2)
            played  = time.monotonic() - timer1

            # DISPLAY OFF timer
            if time.monotonic() - Disp_timer > Disp_time and Disp_time > 0 and Disp_on == 1:
                msg = [""] * 8
                Disp_on = 0
                if show_clock == 0 and screen == 0:
                    disp.set_backlight(0)
                display_screen()
           
            # display titles, status etc
            if Disp_on == 1:
                msg[1] = titles[0][0:19]
                msg[2] = titles[1][0:19]
                temt   = titles[2][0:-4]
                msg[3] = temt[0:19]
                msg[0] = "STOP         PRE/NEXT"
                status()
                msg[5] = "Status.. " +  txt
                msg[6] = ""
                msg[7] = "VOL+/-   MUTE/SLEEP"
                if sleep_time != 0:
                    time_left = int((sleep_time - (time.monotonic() - sleep_timer))/60)
                    if sleep_shutdn == 1:
                        msg[6] = "Shutdown: " + str(time_left) + "mins"
                    else:
                        msg[6] = "Stopping: " + str(time_left) + "mins"
                else:
                    now = datetime.datetime.now()
                    clock = now.strftime("%H:%M:%S")
                    secs = now.strftime("%S")
                    if show_clock == 1 and synced == 1:
                        msg[6] = "        " + clock
                if album_mode == 0:
                    pmin  = int(played/60)
                    psec  = int(played - (pmin * 60))
                    psec2 = str(psec)
                    if psec < 10:
                        psec2 = "0" + psec2
                    lmin  = int(track_len/60)
                    lsec  = int(track_len - (lmin * 60))
                    lsec2 = str(lsec)
                    if lsec < 10:
                        lsec2 = "0" + lsec2
                    msg[4] = " " + str(pmin) + ":" + str(psec2) + "/" + str(lmin) + ":" + str(lsec2)
                else:
                    aplayed = (time.monotonic() - Album_timer) + asofar
                    pmin  = int(aplayed/60)
                    psec  = int(aplayed - (pmin * 60))
                    psec2 = str(psec)
                    if psec < 10:
                        psec2 = "0" + psec2
                    lmin  = int(alength/60)
                    lsec  = int(alength - (lmin * 60))
                    lsec2 = str(lsec)
                    if lsec < 10:
                        lsec2 = "0" + lsec2
                    msg[4] = str((Track_No - astrack) + 1) + "/" + str(atracks) + "  " + str(pmin) + ":" + str(psec2) + "/" + str(lmin) + ":" + str(lsec2)
                ptrack = titles[3] + "/" + titles[4] + "/" + titles[5] + "/" + titles[6] + "/" + titles[0] + "/" + titles[1] + "/"
                pfiles = glob.glob(ptrack + "*.jpg")
                display_screen()
                   
            # check for PLAY/STOP/RADIO key
            if buttonPLAY.is_pressed and Disp_on == 0:
                Disp_on = 1
                Disp_timer = time.monotonic()
                status()
                time.sleep(0.5)
            elif buttonPLAY.is_pressed:
				# STOP Play
                Disp_on = 1
                Disp_timer = time.monotonic()
                timer1 = time.monotonic()
                os.killpg(p.pid, SIGTERM)
                msg[0] = "Track Stopped"
                display_screen()
                time.sleep(2)
                status()
                msg = [""] * 8
                msg[0] = "PLAY/Radio PRE/NEXT"
                display_screen()
                go = 0
                MP3_Play = 0
                save_config()
                
            # check for NEXT/PREVIOUS TRACK key
            elif buttonNEXT.is_pressed and Disp_on == 0:
                Disp_on = 1
                Disp_timer = time.monotonic()
                status()
                time.sleep(0.5)
            elif buttonNEXT.is_pressed:
                Disp_on = 1
                Disp_timer = time.monotonic()
                os.killpg(p.pid, SIGTERM)
                timer1 = time.monotonic()
                while buttonNEXT.is_pressed and time.monotonic() - timer1 < 1:
                    pass
                while buttonNEXT.is_pressed:
                    if time.monotonic() - timer1 > 1:
                        if go == 1:
							# NEXT Track
                            Track_No += 1
                            if album_mode == 1:
                                Album_timer = time.monotonic()
                                if Track_No - astrack > atracks - 1:
                                    Track_No -=1
                                asofar = 0
                                for q in range(0,Track_No - astrack):
                                    asofar += aitracks[q]
                                # determine time left of album
                                aleft = 0
                                for q in range((Track_No - astrack),atracks):
                                    aleft += aitracks[q]
                                if sleep_time > 0:
                                    sleep_time = aleft + 60
                                msg[4] = str((Track_No - astrack) + 1) + "/" + str(atracks)
                            else:
                                msg[4] = ""
                            if Track_No > len(tracks) - 1:
                                Track_No = Track_No - len(tracks)
                            msg[0] = "STOP         PRE/NEXT"
                            titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
                            msg[1] = titles[0][0:19]
                            msg[2] = titles[1][0:19]
                            temt   = titles[2][0:-4]
                            msg[3] = temt[0:19]
                            ptrack = titles[3] + "/" + titles[4] + "/" + titles[5] + "/" + titles[6] + "/" + titles[0] + "/" + titles[1] + "/"
                            pfiles = glob.glob(ptrack + "*.jpg")
                            display_screen()
                            time.sleep(0.5)
                if time.monotonic() - timer1 < 1:
                    if go == 1:
						# PREVIOUS Track
                        Track_No -= 1
                        if album_mode == 1:
                            Album_timer  = time.monotonic()
                            if Track_No < astrack :
                                Track_No +=1
                            asofar = 0
                            for q in range(0,Track_No - astrack):
                                asofar += aitracks[q]
                            # determine time left of album
                            aleft = 0
                            for q in range((Track_No - astrack),atracks):
                                aleft += aitracks[q]
                            if sleep_time > 0:
                                sleep_time = aleft + 60
                            msg[4] = str((Track_No - astrack) + 1) + "/" + str(atracks)
                        else:
                            msg[4] = ""
                        if Track_No < 0:
                            Track_No = len(tracks) + Track_No
                    msg[0] = "STOP         PRE/NEXT"
                    titles[0],titles[1],titles[2],titles[3],titles[4],titles[5],titles[6] = tracks[Track_No].split("/")
                    msg[1] = titles[0][0:19]
                    msg[2] = titles[1][0:19]
                    temt   = titles[2][0:-4]
                    msg[3] = temt[0:19]
                    ptrack = titles[3] + "/" + titles[4] + "/" + titles[5] + "/" + titles[6] + "/" + titles[0] + "/" + titles[1] + "/"
                    pfiles = glob.glob(ptrack + "*.jpg")
                    display_screen()
                go = 0

            # check for VOLUME UP/DOWN  key
            elif buttonVOLUP.is_pressed and Disp_on == 0:
                Disp_on = 1
                Disp_timer = time.monotonic()
                status()
                time.sleep(0.5)
            elif buttonVOLUP.is_pressed:
				# set Volume
                time.sleep(0.5)
                Set_Volume()
                status()
                msg[0] = "STOP         PRE/NEXT" 
                display_screen()
                Disp_timer = time.monotonic()
                         
            # check for SLEEP/SHUTDOWN key
            elif  buttonSLEEP.is_pressed and Disp_on == 0:
                Disp_timer = time.monotonic()
                Disp_on = 1
                status()
                time.sleep(1)
            elif buttonSLEEP.is_pressed:
                timer1 = time.monotonic()
                while buttonSLEEP.is_pressed and time.monotonic() - timer1 < 2:
                    pass
                while buttonSLEEP.is_pressed:
                    if time.monotonic() - timer1 > 2:
						# set SLEEP TIME
                        Disp_timer = time.monotonic()
                        if (sleep_time == 0 and album_mode == 0) or (album_mode ==1 and sleep_time == alength + 60):
                            sleep_time = 900
                        elif sleep_time == 0 and album_mode == 1:
					        # determine time left of album
                            aleft = 0
                            for q in range((Track_No - astrack),atracks):
                                aleft += aitracks[q]
                            sleep_time = aleft + 60
                        else:
                            sleep_time = (time_left * 60) + 960
                            if sleep_time > 10800:
                                sleep_time = 0
                        time_left = int((sleep_time - (time.monotonic() - sleep_timer))/60)
                        sleep_timer = time.monotonic()
                        msg = [""] * 8
                        if sleep_time > 0:
                            msg[0] = "Set SLEEP.. " + str(int(sleep_time/60))
                        else:
                            msg[0] = "Set SLEEP.. OFF"
                        display_screen()
                        time.sleep(1)
                if time.monotonic() - timer1 <= 1:
					# MUTE
                    if volume > 0:
                        old_volume = volume
                        volume = 0 # MUTED
                    else:
                        volume = old_volume
                    if len(alsaaudio.mixers()) > 0 and lver < 13:
                        m.setvolume(volume)
                        os.system("amixer -D pulse sset Master " + str(volume) + "%")
                        if mixername == "DSP Program":
                            os.system("amixer set 'Digital' " + str(volume + 107))
                    else:
                        os.system("wpctl set-volume @DEFAULT_AUDIO_SINK@ " + str(volume/100))
                
            poll = p.poll()
          if go == 1:
			  # play next track
              Track_No +=1
          if Track_No < 0:
              Track_No = len(tracks) + Track_No
          elif Track_No > len(tracks) - 1:
              Track_No = Track_No - len(tracks)

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
        if time.monotonic() - Disp_timer > Disp_time and Disp_time > 0 and Disp_on == 1:
            msg = [""] * 8
            Disp_on = 0
            if show_clock == 0 and screen == 0:
                disp.set_backlight(0)
            display_screen()
            
        # sleep_time timeout
        if time.monotonic() - sleep_timer > sleep_time and sleep_time > 0:
            Disp_timer = time.monotonic()
            abort_sd = 0
            t = 30
            Disp_on = 1
            while t > 0 and abort_sd == 0:
                if sleep_shutdn == 1:
                    msg[1] = "SHUTDOWN in " + str(t)
                else:
                    msg[1] = "STOPPING in " + str(t)
                display_screen()
                if buttonSLEEP.is_pressed:
                    sleep_timer = time.monotonic()
                    sleep_time = 900
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
                msg[1] = ""
                time.sleep(1)
                Disp_on = 0
                msg[0] = ""
                display_screen()
                q.kill()
                if sleep_shutdn == 1:
                    os.system("shutdown -h now")
                sleep_time = 0
                stopped = 1
                radio = 0
                time.sleep(1)
            Disp_timer = time.monotonic()
            
        # display sleep_time time left and clock (if enabled and synced)
        now = datetime.datetime.now()
        clock = now.strftime("%H:%M:%S")
        secs  = now.strftime("%S")
        time_left = int((sleep_time - (time.monotonic() - sleep_timer))/60)
        if Disp_on == 1:
            if Radio_Stns[radio_stn + 2] == 0:
                msg[1] = (Radio_Stns[radio_stn])
                if len(Radio_Stns[radio_stn]) < 21:
                    msg[1] = Radio_Stns[radio_stn][0:19]
                else:
                    tema = Radio_Stns[radio_stn] + " - " + Radio_Stns[radio_stn]
                    msg[1] = tema[scroll:scroll + 19] # Album
                    scroll +=1
                    time.sleep(0.05)
                    if scroll > len(Radio_Stns[radio_stn]):
                        scroll = 0
            else:
                msg[1] = ""
            if sleep_time > 0:
                if sleep_shutdn == 1:
                    msg[2] = "Shutdown: " + str(time_left) + "mins"
                else:
                    msg[2] = "Stopping: " + str(time_left) + "mins"
            if show_clock == 1 and synced == 1:
                msg[6] = "          " + clock
            if volume == 0:
                msg[4] = "           MUTED"
            else:
                msg[4] = ""
            msg[0] = "STOP         PRE/NEXT"
            msg[7] = "VOL+/-   MUTE/SLEEP"
            display_screen()
            
        # display clock whilst timed out (if enabled and synced)
        if show_clock == 1 and Disp_on == 0 and synced == 1:
            now = datetime.datetime.now()
            clock = now.strftime("%H:%M:%S")
            secs = now.strftime("%S")
            t = ""
            for r in range (0,random.randint(0,10)):
                t += " "
            clock = t + clock
            time_left = int((sleep_time - (time.monotonic() - sleep_timer))/60)
            if sleep_time > 0:
                clock += " " + str(time_left)
            if secs != old_secs2 :
              vp = random.randint(0,7)
              msg = [""] * 8
              msg[vp] = clock
              display_screen()
              old_secs2 = secs
            
        # check for VOLUME UP/DOWN  key
        if buttonVOLUP.is_pressed and Disp_on == 0:
            Disp_on = 1
            Disp_timer = time.monotonic()
            status()
            msg = [""] * 8
            display_screen()
            time.sleep(0.5)
        elif buttonVOLUP.is_pressed:
			# set Volume
            Disp_on = 1
            Disp_timer = time.monotonic()
            Set_Volume()
            status()
            time.sleep(0.5)
            msg = [""] * 8
            msg[0] = "STOP         PRE/NXT"
            msg[7] = "VOL+/-   MUTE/SLEEP"
            display_screen()
            Disp_timer = time.monotonic()
          
        # check NEXT/PREVIOUS key
        if buttonNEXT.is_pressed and Disp_on == 0:
            Disp_on = 1
            Disp_timer = time.monotonic()
            status()
            msg = [""] * 8
            display_screen()
            time.sleep(0.5)
        elif buttonNEXT.is_pressed:
            Disp_on = 1
            Disp_timer = time.monotonic()
            timer1 = time.monotonic()
            while buttonNEXT.is_pressed and time.monotonic() - timer1 < 1:
                pass
            if time.monotonic() - timer1 > 1:
                while buttonNEXT.is_pressed and buttonSLEEP.is_pressed == 0 and buttonVOLUP.is_pressed == 0:
					# Next Radio Station
                    radio_stn +=3
                    if radio_stn > len(Radio_Stns) - 3:
                        radio_stn = 0
                    if Radio_Stns[radio_stn][0:1] == "#":
                        radio_stn +=3
                    if radio_stn > len(Radio_Stns) - 3:
                        radio_stn = 0
                    msg[1] = (Radio_Stns[radio_stn])
                    now = datetime.datetime.now()
                    clock = now.strftime("%H:%M:%S")
                    secs = now.strftime("%S")
                    if show_clock == 1 and synced == 1:
                        msg[6] = "        " + clock
                    msg[7] = "Radio A-Z "
                    display_screen()
                    time.sleep(0.5)
                while buttonNEXT.is_pressed and buttonVOLUP.is_pressed:
					# Next Radio Station A-Z
                    old_radio = Radio_Stns[radio_stn][0:1]
                    while Radio_Stns[radio_stn][0:1] == old_radio[0:1]:
                        radio_stn +=3
                        if radio_stn > len(Radio_Stns) - 3:
                            radio_stn = 0
                        if Radio_Stns[radio_stn][0:1] == "#":
                            radio_stn +=3
                        if radio_stn > len(Radio_Stns) - 3:
                            radio_stn = 0
                    msg[1] = (Radio_Stns[radio_stn])
                    now = datetime.datetime.now()
                    clock = now.strftime("%H:%M:%S")
                    secs = now.strftime("%S")
                    if show_clock == 1 and synced == 1:
                        msg[6] = "        " + clock
                    display_screen()
                    time.sleep(0.5)
            if time.monotonic() - timer1 < 1: 
				# Previous Radio Station       
                radio_stn -=3
                if radio_stn < 0:
                    radio_stn = len(Radio_Stns) - 3
                if Radio_Stns[radio_stn][0:1] == "#":
                    radio_stn -=3
                if radio_stn < 0:
                    radio_stn = len(Radio_Stns) - 3
                msg[1] = (Radio_Stns[radio_stn])
                now = datetime.datetime.now()
                clock = now.strftime("%H:%M:%S")
                secs = now.strftime("%S")
                if show_clock == 1 and synced == 1:
                    msg[6] = "        " + clock
                display_screen()
            q.kill()
            q = subprocess.Popen(["cvlc",Radio_Stns[radio_stn + 1]] ,shell=False)
            time.sleep(1)
            save_config()
          
        # check PLAY/STOP/Radio key
        if buttonPLAY.is_pressed and Disp_on == 0:
            Disp_on = 1
            Disp_timer = time.monotonic()
            status()
            time.sleep(0.5)
        elif buttonPLAY.is_pressed:
			# STOP Radio
            Disp_on = 1
            Disp_timer = time.monotonic()
            q.kill()
            radio = 0
            msg = [""] * 8
            if len(tracks) > 0:
                msg[0] = "PLAY/Radio PRE/NEXT"
                msg[1] = titles[0][0:19]
                msg[2] = titles[1][0:19]
                temt   = titles[2][0:-4]
                msg[3] = temt[0:19]
                msg[5] = "Status...  "  +  txt
                msg[7] = "ALB/RNDM    GAP/SD"
            else:
                msg[0] = "Radio Stopped      "
            display_screen()
            save_config()
            time.sleep(2)
 
        # check for sleep_time key
        if buttonSLEEP.is_pressed and Disp_on == 0:
            Disp_on = 1
            Disp_timer = time.monotonic()
            status()
            msg = [""] * 8
            display_screen()
            time.sleep(0.5)
        elif buttonSLEEP.is_pressed:
            Disp_on = 1
            Disp_timer = time.monotonic()
            timer1 = time.monotonic()
            while buttonSLEEP.is_pressed and time.monotonic() - timer1 < 2:
                pass
            while buttonSLEEP.is_pressed:
                if time.monotonic() - timer1 > 2:
        			# set SLEEP TIME
                    Disp_timer = time.monotonic()
                    if sleep_time == 0:
                        sleep_time = 900
                    else:
                        sleep_time = (time_left * 60) + 960
                        if sleep_time > 10800:
                            sleep_time = 0
                    time_left = int((sleep_time - (time.monotonic() - sleep_timer))/60)
                    sleep_timer = time.monotonic()
                    msg = [""] * 8
                    if sleep_time > 0:
                        msg[0] = "Set SLEEP.. " + str(int(sleep_time/60))
                    else:
                        msg[0] = "Set SLEEP.. OFF"
                    display_screen()
                    time.sleep(1)
            if time.monotonic() - timer1 <= 1:
				# MUTE
                if volume > 0:
                    old_volume = volume
                    volume = 0 # MUTED
                else:
                    volume = old_volume
                if len(alsaaudio.mixers()) > 0 and lver < 13:
                    m.setvolume(volume)
                    os.system("amixer -D pulse sset Master " + str(volume) + "%")
                    if mixername == "DSP Program":
                        os.system("amixer set 'Digital' " + str(volume + 107))
                else:
                    os.system("wpctl set-volume @DEFAULT_AUDIO_SINK@ " + str(volume/100))
        





            
