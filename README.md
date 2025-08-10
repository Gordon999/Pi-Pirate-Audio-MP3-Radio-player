# Pi-Pirate-Audio-MP3-Radio-player

![Image](image.jpg)

TESTED with RaspiOS 32bit BOOKWORM

# To install...

ensure SPI and I2C interfaces ON

sudo pip3 install st7789 --break-system-packages

sudo apt install python3-alsaaudio

sudo apt install mplayer

sudo pip3 install mutagen --break-system-packages

# To /boot/firmware/config.txt add...

dtoverlay=hifiberry-dac

gpio=25=op,dh

then

copy Pi_Pirate_MP3_Player.py to home directory

# To run at boot if using labwc

Add /usr/bin/python ~/Pi_Pirate_MP3_Player.py to ~./config/labwc/autostart
