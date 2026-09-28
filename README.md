### Setup
1. Update packages  
```sudo apt-get update -y && sudo apt-get upgrade -y```
2. install requirements  
```sudo apt-get install -y python3 python3-tk python3-pil.imagetk```
3. install HEIF/HEIC support, for photos sent from an iPhone  
```sudo apt-get install -y libheif1 && pip3 install pillow-heif```  
Optional. Without it everything else still works, HEIC attachments are skipped with a note in the log.

### Pictures
`readmail.py` converts every incoming attachment it recognises as a picture to jpg and stores
only that, the original file is never written to disk. Attachments it cannot convert are skipped.  
`main.py` only displays, it never converts. It shows the picture formats in `DISPLAYABLE` and
ignores everything else in `img/`, so a file it cannot read never interrupts the slideshow.

### Testing
The container mirrors the Debian base current Raspberry Pi OS is built on, so
nothing has to be installed on your own machine.
```
podman build -t frame-test .    # docker build works the same
podman run --rm frame-test      # attachment handling + display, exits non-zero on failure
```

To watch the frame itself, it runs on a virtual screen inside the container and
is served to your browser, no X server needed on the host:
```
podman run --rm -p 8080:8080 frame-test sh tests/gui.sh
```
then open <http://localhost:8080/vnc.html?autoconnect=1&resize=scale>

Mount your own pictures to see those instead, heic included, they are converted
on the way in exactly like mail attachments:
```
podman run --rm -p 8080:8080 -v ~/Pictures:/pictures:ro frame-test sh tests/gui.sh
```
`SCREEN=1920x1080` picks a different resolution, useful to check how a picture
fits the screen the frame will really run on.

### Configuration
1. Apply a server-side rue in your mail-program, to move mails with a specific subject to a folder  
eg. Where \[subject] = 'Picture' | move to folder 'Pictures'
2. Create your own config from the example, it is not tracked by git so your
   mail password stays out of the repository  
```cp Config.example.json Config.json```
3. Edit Config.json  
set mail.settings.folder to the same name, you gave on 1.  
`files.path` may be relative to this directory (`img/`) or an absolute path.

### Running it on the pi
Clone to `~/Frame`, so the scripts end up at `~/Frame/main.py`.

Fetch mail hourly, via `crontab -e`:
```
0 * * * * /usr/bin/python3 /home/pi/Frame/readmail.py >> /home/pi/readmail.log 2>&1
```

Start the frame with the desktop session, `~/.config/autostart/frame.desktop`:
```
[Desktop Entry]
Type=Application
Name=Frame
Exec=/usr/bin/python3 /home/pi/Frame/main.py
X-GNOME-Autostart-enabled=true
```
This needs the pi to log in automatically (`raspi-config` → System Options →
Boot / Auto Login → Desktop Autologin).


tbd...

