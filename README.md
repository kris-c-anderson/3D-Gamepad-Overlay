# 3D Controller Overlay

3D Controller Overlay is a simple program for content creaters to show what their controller is doing in 3D space without the need for a handcam.

How to Compile:
- Download and extract this repository or clone it using git.

Windows:
- If you want to compile using my batch file you need to have command line access to the gcc/g++ compiler. I use MinGW, you can download it from https://winlibs.com/ extract it somewhere then add the path to the bin folder inside mingw32 (eg. C:\mingw32\bin) to your PATH in Environment Variables. 
- Run windows_build.bat

Linux: (Debian based, Ubuntu, Mint, etc.) 
- If you want to use my build script you will need bear (it just updates the compile_commands.json each time it builds)\
    sudo apt-get install bear\
    Or, you can just take bear out of the build script.

- You will need to install glfw3 and SDL 3.4 or newer (unless you get libraries and link them yourself)\
    sudo apt-get install libsdl3-dev libglfw3-dev

- chmod +x linux_build.sh

- ./linux_build

Linux: (Arch based, Manjaro, SteamOS, etc.)
- All the same things for ubuntu but using Pacman or some package installer like yay or yum. Hopefully if you're using arch based linux you already kinda know what you're doing.

Mac:
- I got this built and running on an Intel based mac without too much headache. I believe I needed brew and maybe a couple other things but it wans't too bad. I don't have access to a mac atm but when I get one again I'll update these instructions.
- Haven't tried any apple silicon macs but if I get my hands on one I'll try it out and update the instructions.

## Steam Controller (2026) support

This fork runs on **SDL 3.4** (instead of SDL2), which talks to Valve's 2026
Steam Controller directly over USB or through its Puck, with no Steam client required:

- Both trackpads: finger position (touch points 1/2) and click (`touchpad` = left pad, `touchpad 2` = right pad)
- Gyro (integrated at the controller's own sensor rate, frame-rate independent)
- L4 / R4 / L5 / R5 grip buttons (paddles 2 / 1 / 4 / 3) and the Quick Access (…) button (`misc`)
- Capacitive thumbstick touch: the stick top glows faintly while your thumb rests on it

The `Steam Controller (2026)` model is converted from
[Valve's official CAD files](https://gitlab.steamos.cloud/SteamHardware/SteamController)
(CC BY-NC-SA 4.0, see `models/Steam Controller (2026)/LICENSE.txt`) with
`tools/steam_controller_model/convert_valve_cad.py`.

Enjoy!

Kris
