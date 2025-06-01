> [!NOTE]
> This project is a WIP fork of a tool originally developed for use with X-Plane and Toliss aircraft.
> This fork adapts it for Microsoft Flight Simulator 2020 (MSFS20) with FlyByWire A32NX and SimBridge for Linux.
> You do not need X-Plane for this version.


# winwing_mcdu (MSFS20 fork)

Use the Winwing MCDU on Linux with the FlyByWire Airbus A32NX in MSFS2020, using SimBridge for data integration.

Some text might not display correctly (wrong size/color), but every thing you see in the sim, should also be visible on the Winwing MCDU.

This is a fork of the original winwing_mcdu project for X-Plane, adapted for use with MSFS2020.
Credits to the original author (schenlap/memo5) for the base implementation.

![mcdu demo image](./documentation/A32NX-FBW-MCDU1.jpg)

## Status

The script fetches relevant data from the MCDU via SimBridge and mirrors the text output to the Winwing MCDU hardware display.


## Installation
### Debian-based systems

Clone the repository.

Copy udev rules:

    sudo cp udev/71-winwing.rules /etc/udev/rules.d/

Install dependencies:

    sudo apt install python3-hid libhidapi-hidraw0 websocket-client

Run the script:

    python3 ./simbridge.py

# Usage

Start MSFS2020 and load the FlyByWire A32NX.

Ensure SimBridge is running and correctly configured (reachable on localhost:8380).

Run the script as outlined above.

The MCDU output will be mirrored to the hardware and console.


This project is experimental. Use at your own risk.

Updates to MSFS20 or FlyByWire A32NX may break compatibility.

# Next Steps / TODO
Improve font rendering accuracy (size, color)

# Sponsoring
Support the original developer:\
![Buy them a coffee](https://github.com/user-attachments/assets/d0a94d75-9ad3-41e4-8b89-876c0a2fdf36)\
[http://buymeacoffee.com/schenlap](http://buymeacoffee.com/schenlap)
