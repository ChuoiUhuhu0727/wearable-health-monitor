# Jetson WiFi AP setup (Option 4)

One-time setup so the Jetson Orin Nano hosts its own WiFi network for the
wearable device to connect to — this sidesteps the campus network's
firewall entirely (that's what broke Option 2), since the device and the
Jetson talk directly over a private hotspot instead of routing through
any campus infrastructure.

## 1. Create the hotspot

Run on the Jetson (needs a WiFi adapter that supports AP mode — the
Jetson's onboard WiFi usually does):

```bash
nmcli device wifi hotspot ifname wlan0 ssid JetsonWearableAP password wearable123
```

This must match `JETSON_SSID` / `JETSON_PASS` in `firmware_main/http_client.h`
exactly — if you change one, change the other (WiFi connection setup is
shared between the HTTP and UDP telemetry options; only the send/transport
part differs, see `firmware_main/udp_client.h`).

## 2. Confirm the Jetson's own IP on the hotspot

NetworkManager's default "Shared" hotspot mode assigns the Jetson itself
`10.42.0.1` as the gateway, handing out `10.42.0.x` addresses to anything
that connects (including the wearable). Confirm with:

```bash
ip addr show wlan0
```

If it's *not* `10.42.0.1`, update `JETSON_HOST` (http_client.h) **and**
`JETSON_UDP_HOST` (udp_client.h) to match whatever it actually is — both
must point at the Jetson's real hotspot IP.

## 3. Make the hotspot persistent across reboots (optional)

By default the hotspot connection profile is saved but not auto-started.
To have it come up automatically:

```bash
nmcli connection modify JetsonWearableAP connection.autoconnect yes
```

## 4. Allow the telemetry port through the firewall (if `ufw` is active)

```bash
sudo ufw allow 8001/udp
```

(Port 8001/UDP is what's actually in use now — see `udp_server.py` /
`udp_client.h`. Port 8000/TCP was for the HTTP option, kept but unused;
allow it too only if you plan to switch back and compare.)

Check whether `ufw` is even active first with `sudo ufw status` — many
Jetson images don't enable it by default, in which case this step is a
no-op.

## 5. Run the server

```bash
cd jetson_server
python udp_server.py
```

No dependencies to install for this one — it's plain Python `socket`,
no Flask needed (that's only required for `server.py`, the unused HTTP
alternative). You should see `Listening for UDP telemetry on port 8001...`.
Power on the wearable — once it joins the hotspot and starts recording,
telemetry lines should start appearing here within a few seconds.

## Troubleshooting

- **Device never shows up in telemetry**: check `nmcli device wifi hotspot`
  actually started successfully (`nmcli connection show --active`), and
  that the SSID/password in `http_client.h` match exactly (case-sensitive).
- **Server runs but nothing connects**: the wearable only *attempts* a
  WiFi connection — it never blocks waiting for one (`WiFi.begin()` is
  async, by design, see http_client.h). If the hotspot isn't up yet when
  the device boots, it'll keep retrying in the background; no need to
  reset the device once the hotspot comes up.
- **Nothing arrives even though WiFi looks connected**: since UDP has no
  delivery confirmation, a wrong `JETSON_UDP_HOST`/port is a *silent*
  failure — the device thinks it sent successfully either way. Double
  check `JETSON_UDP_HOST` in `udp_client.h` matches the Jetson's real IP
  (step 2 above), and that it's a unicast address, not a broadcast one.
- **This is a live-view convenience layer only** — if none of the above
  works, the device is still recording everything to its own flash
  regardless. Retrieve with `log_serial.py` as usual; nothing about data
  collection depends on this server working. See `OBSERVATION_CHECKLIST.md`
  (repo root) for the full list of what can fail silently in this system.
