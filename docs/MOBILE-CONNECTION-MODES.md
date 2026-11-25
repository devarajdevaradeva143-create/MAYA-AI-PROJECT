# Maya Mobile — Connection Modes (Phase 11)

Maya phone app supports three ways to reach the laptop.

## Wi-Fi (default)
1. Both devices on the same Wi-Fi network.
2. Phone: Laptop tab → Pair laptop (PIN flow).
3. Auto-connect uses saved host/port.

## USB (cable)
1. Connect phone to laptop via USB cable.
2. On the laptop, run:
   ```powershell
   adb reverse tcp:8420 tcp:8420
   ```
   (adb ships with Android Studio / platform-tools.)
3. Phone: Settings → Connection mode → USB. This sets the laptop host to `127.0.0.1`.
4. Pair once over USB (PIN flow still works over the tunnel).
5. Chat/monitor/control work over the cable; no Wi-Fi needed.

Wrong mode → clear connection error on the Laptop tab ("No response from laptop").

## Bluetooth PAN
1. Pair phone and laptop over Bluetooth.
2. On the laptop, enable Bluetooth tethering / PAN (Network & Internet → Mobile hotspot → Bluetooth tethering on Windows).
3. Phone: connect to the laptop's Bluetooth PAN network (Android auto-connects after pairing + tethering enabled).
4. Phone: Settings → Connection mode → Bluetooth. Enter the laptop's PAN IP (shown by `ipconfig` / `ip addr` on the laptop) in the Laptop tab host field.
5. Pair once over PAN.

Note: Bluetooth PAN setup is manual in v1; RFCOMM transport is a v2 item.
