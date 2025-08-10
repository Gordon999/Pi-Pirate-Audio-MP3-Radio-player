# Pi-Pirate-Audio-MP3-Radio-player

![Image](image.jpg)

TESTED with RaspiOS 32bit BOOKWORM

to install...

ensure SPI and I2C interfaces ON

sudo pip3 install st7789 --break-system-packages

sudo apt install python3-alsaaudio

sudo apt install mplayer

sudo pip3 install mutagen --break-system-packages

copy Pi_Pirate_MP3_Player.py to home directory

to run at boot if using labwc

add /usr/bin/python /home/USERNAME/Pi_Pirate_MP3_Player.py to ~./config/labwc/autostart
