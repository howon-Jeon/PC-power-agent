# PC Power Agent

Python UDP agent for the PC remote power-control design in `docs/PC_UDP_Control_v3.md`.

## Quick test

1. Install dependencies:

```bat
python -m pip install -r requirements.txt
```

2. Create local config with a fixed test key:

```bat
python installer.py --manual --port 47001 --key-hex 00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff
```

3. Run the listener:

```bat
python pc_agent.py --foreground
```

4. In another terminal, send a status request:

```bat
python udp_sender_test.py --host 127.0.0.1 --port 47001 --key-hex 00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff --command 1002
```

Shutdown command `1001` is dry-run by default. Enable real shutdown only after LAN testing:

```bat
python installer.py --manual --port 47001 --key-hex 00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff --enable-shutdown
```

## EXE test on another Windows PC

1. Build on the development PC:

```bat
build.bat
```

2. Copy the `dist` folder to the target PC.

3. On the target PC, run Command Prompt as administrator and execute:

```bat
install.bat
```

4. Enter only the PC number or UDP port when prompted. Shutdown handling is enabled by the installer.

The installer uses these fixed controller settings:

- AES key: `tCF2fFU8827lb23wEXzbZhB3IMHT09zM`
- Controller notify IP/broadcast: `255.255.255.255`
- Controller notify UDP port: same as the entered PC UDP port

The installer registers `PcPowerAgent` as an automatic Windows service, so it starts again after reboot.
The service files and configuration are copied to `%ProgramFiles%\PC Power Agent`.
The original deployment folder can be moved or deleted after installation.

5. From another PC on the same LAN, send a test command:

```bat
udp_sender_test.exe --host <target-pc-ip> --port 47001 --key-hex <same-64-hex-key> --command 1002
```

Use `--host 255.255.255.255` for a broadcast-style test on the same subnet.

## Packet format

Encrypted UDP payload:

```text
nonce(12 bytes) + ciphertext + tag(16 bytes)
```

Plaintext accepts either JSON or a raw numeric command string.

Default command codes:

- `1001`: shutdown
- `1002`: status request

Default response codes:

- `2001`: online
- `2002`: shutdown accepted
- `4001`: unknown command
- `5001`: command failed

## Shutdown replay protection

Accepted shutdown packet fingerprints are stored in
`%ProgramFiles%\PC Power Agent\replay_cache.log`. An exact encrypted shutdown
packet is executed only once, including across service or PC restarts.

## Log retention

The Windows service writes `pc_agent.log` in its installation folder. Each log
file is limited to 5 MB, with up to three rotated backup files retained.
