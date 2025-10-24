# Mamakhub - PPM

A host-side Python application that listens for packets from Portect Vessel Modules (PVM), parses them, indicates events via GPIO LEDs, and optionally writes GPS / SOS data to InfluxDB. This PPM instance is intended to run on a Raspberry Pi 5 wired to an RA-02 (SX1278/SX1276) LoRa module.

## Project overview

`PPM` (Portect Port Module) performs the host responsibilities for the Portect system:

- Receives fixed-size packets from PVM devices over LoRa
- Validates CRC and parses payload/timestamp
- Extracts GPS coordinates and SOS flags and optionally writes points to InfluxDB
- Provides an optional periodic transmit helper for testing and development

The device firmware (Portect Vessel Module) lives in the sibling `PVM` repository and uses the same packet layout and CRC algorithm.

## Hardware requirements

- Raspberry Pi 5 (Linux with SPI/GPIO enabled)
- RA-02 LoRa module (SX1278 / SX1276 family)
- Two indicator LEDs (optional) with current-limiting resistors
- Network access (optional, for InfluxDB)

## Hardware connections (Raspberry Pi 5 + RA-02)

Suggested wiring (BCM pin numbers):

```
RA-02       -> Raspberry Pi (BCM)
VCC         -> 3.3V
GND         -> GND
SCK         -> GPIO 11
MISO        -> GPIO 9
MOSI        -> GPIO 10
Nss/Enable  -> GPIO 8
RST         -> GPIO 22
DIO0        -> GPIO 4
DIO1        -> GPIO 17
DIO2        -> GPIO 18
DIO3        -> GPIO 27
```

Default LED pins in `main.py` (change if needed):

```
RX LED  -> GPIO 23
SOS LED -> GPIO 19
```

> Important: use 3.3V for the RA-02. SX127x modules are not 5V-tolerant.

## Software setup

### Prerequisites

- Python 3.8+
- `pip` (package manager)
- SPI/GPIO enabled on the Raspberry Pi (enable via raspi-config or distribution tools)

### Python dependencies

Install recommended packages (use a virtualenv if preferred):

```bash
python3 -m pip install --user python-dotenv influxdb-client gpiozero
```

Install the SX127x Python library according to its documentation (it may be a separate package or local module). If you're developing on Windows, you can use similar commands with `py -3 -m pip install ...` but SPI/GPIO access is platform dependent.

If you will write to InfluxDB, ensure you have an InfluxDB 2.x server available and credentials (token, org, bucket).

## Installation

1. Place or clone this repository on your Raspberry Pi (e.g., `/home/pi/marinehack`).
2. Install the Python dependencies above.
3. (Optional) Create a `.env` file in the `PPM/` directory with InfluxDB credentials:

```
INFLUXDB_TOKEN=your-token
INFLUXDB_ORG=your-org
INFLUXDB_URL=your-url-to-influxdb-service
INFLUXDB_BUCKET=your-bucket-name
```

## Running the application

From the `PPM` folder on the Raspberry Pi:

```bash
cd /your/path/to/PPM
python3 main.py
```

What the application does:

- Initializes GPIO and the SX127x radio via the `SX127x` Python library
- Configures the radio with PVM defaults (default: 433 MHz, SF7, BW125kHz, CR4/5, sync word 0xA5)
- Enters continuous receive mode and prints parsed packets to the console

To enable periodic test transmissions, edit `main.py` and set `ENABLE_PERIODIC_SEND = True`.

## Configuration

- `main.py` runtime options:
  - `DEVICE_ID` — ID used for periodic TX (host-side test)
  - `SEND_INTERVAL` — periodic TX interval (seconds)
  - `ENABLE_PERIODIC_SEND` — enable/disable periodic TX
  - `VERBOSE` — verbose logging
- Change LED pins in `main.py` if your wiring differs.

## Packet format (PVM)

The PVM packet is a fixed 126-byte structure shared between firmware and host:

- struct layout (little-endian): `<H B B 100s 20s H`
  - `uint16_t device_id` (2 bytes)
  - `uint8_t packet_type` (1 byte) — 0x01 = GPS, 0x02 = SOS, 0x03 = KEEPALIVE
  - `uint8_t priority` (1 byte)
  - `char payload[100]` (100 bytes) — UTF-8 string, padded or truncated
  - `char timestamp[20]` (20 bytes) — `DD-MM-YYYY HH:MM:SS`, padded/truncated
  - `uint16_t crc` (2 bytes) — CRC-16 of the first 124 bytes (algorithm: LSB-first poly 0xA001)

Total: 126 bytes.

Conventions:

- GPS payload: `lat,lon` or `lat,lon,alt` (comma-separated floats)
- SOS packet: `packet_type == 0x02` and `priority` indicates urgency

## Integration with `PVM` firmware

Firmware for the Portect Vessel Module (ESP32) is in the `PVM/` folder (PlatformIO). Keep these aligned:

- Update `PPM/LoRa.py` if you change the firmware packet struct (`PVM/include/LoRaPacket.h`).
- Ensure radio parameters (frequency, SF, BW, sync word) match on both sides.

## Troubleshooting

- CRC mismatch: verify both firmware and host use the same CRC implementation. The host prints calculated vs received CRC for debugging.
- No packets: check wiring, antenna, radio frequency, and sync word. Confirm SPI/GPIO access and that the `SX127x` Python library initializes correctly.
- InfluxDB write failures: verify `.env` values, token, bucket, and network connectivity to the InfluxDB server.
- Permission errors: run under a user with SPI/GPIO access (or use `sudo` on Linux).

## Project structure

```
PPM/
├── InfluxDB.py        # InfluxDB client wrapper
├── LoRa.py            # LoRaPacket class: create, parse, CRC, radio config
├── main.py            # Entrypoint and receive loop
└── README.md          # This file

PVM/                  # Firmware counterpart (ESP32, PlatformIO)
```

## Features

- Receive and parse fixed-size PVM packets (GPS, SOS, keepalive)
- CRC-16 verification compatible with ESP32 firmware
- Optional InfluxDB integration for storing GPS points
- Optional periodic TX helper for testing

## Support

If you run into issues:

1. Check the Troubleshooting section above
2. Inspect serial logs and host console output
3. Open an issue with wiring, logs and configuration details

---

**Note**: PPM is a development tool for receiving and inspecting PVM packets — it should not replace certified maritime emergency equipment.
