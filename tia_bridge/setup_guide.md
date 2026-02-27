# TIA Portal V19 — Openness API Setup Guide

This guide walks you through enabling the TIA Portal Openness API on your Windows 11 machine (running in Parallels) so that LADX can automate TIA Portal remotely.

## Prerequisites

- Windows 11 (in Parallels or standalone)
- TIA Portal V19 installed
- Admin access on the Windows machine

---

## Step 1: Add Your User to the "Siemens TIA Openness" Group

TIA Portal requires your Windows user to be a member of the **Siemens TIA Openness** security group.

1. Press `Win + R`, type `compmgmt.msc`, press Enter
2. Navigate to **System Tools → Local Users and Groups → Groups**
3. Find and double-click **Siemens TIA Openness**
4. Click **Add...** → type your Windows username → **Check Names** → **OK**
5. Click **OK** to close the group dialog
6. **Log out and log back in** (or restart) for the group change to take effect

> **Important:** If you skip this step, pythonnet will throw an "Access denied" error when trying to use the Openness API.

---

## Step 2: Locate the Siemens.Engineering.dll

The TIA Openness API is exposed through a .NET DLL. Verify it exists at:

```
C:\Program Files\Siemens\Automation\Portal V19\PublicAPI\V19\Siemens.Engineering.dll
```

If your installation path is different, note the actual path — you'll need it for configuration.

You may also find these helpful DLLs in the same directory:
- `Siemens.Engineering.Hmi.dll` — for HMI automation
- `Siemens.Engineering.AddIn.dll` — for add-in development

---

## Step 3: Install Python on Windows

1. Download Python 3.10 or later from [python.org](https://www.python.org/downloads/)
2. During installation, check **"Add Python to PATH"**
3. Verify: open Command Prompt and run:
   ```
   python --version
   ```

---

## Step 4: Install Bridge Dependencies

Open Command Prompt (or PowerShell) and run:

```
cd C:\path\to\Ladx\tia_bridge
pip install -r requirements.txt
```

This installs:
- **Flask** — lightweight web server for the bridge API
- **pythonnet** — allows Python to call .NET assemblies (Siemens.Engineering.dll)

---

## Step 5: Configure Parallels Networking

For your Mac (running LADX) to reach the Windows VM (running the TIA bridge):

### Option A: Shared Network (Default — Recommended)
1. In Parallels, go to your VM settings → **Hardware → Network**
2. Set Source to **Shared Network**
3. In Windows, open Command Prompt and run:
   ```
   ipconfig
   ```
4. Note the IPv4 address (typically `10.211.55.x`)
5. On your Mac, update the LADX `.env` file:
   ```
   TIA_BRIDGE_URL=http://10.211.55.x:5050
   ```

### Option B: Bridged Network
1. Set Source to **Default Adapter** (bridged mode)
2. Both Mac and Windows will be on the same local network
3. Use the Windows IP from `ipconfig`

### Verify Connectivity
From your Mac terminal:
```bash
ping 10.211.55.x
```

---

## Step 6: Configure Windows Firewall

Allow the bridge server through the Windows firewall:

1. Open **Windows Defender Firewall with Advanced Security**
2. Click **Inbound Rules → New Rule...**
3. Select **Port** → **TCP** → Specific port: **5050**
4. Allow the connection → apply to all profiles
5. Name it: `LADX TIA Bridge`

Or from an elevated Command Prompt:
```
netsh advfirewall firewall add rule name="LADX TIA Bridge" dir=in action=allow protocol=TCP localport=5050
```

---

## Step 7: Start the Bridge Server

```
cd C:\path\to\Ladx\tia_bridge
python tia_bridge_server.py
```

You should see:
```
============================================================
  TIA Portal Bridge Server (Openness API)
  Listening on: http://0.0.0.0:5050
============================================================
```

---

## Step 8: Test the Connection

From your Mac, run:
```bash
curl http://10.211.55.x:5050/api/status
```

Expected response:
```json
{
  "bridge": "online",
  "tia_portal_connected": false,
  "project_open": false
}
```

Then connect to TIA Portal:
```bash
curl -X POST http://10.211.55.x:5050/api/connect
```

TIA Portal V19 should launch on the Windows machine.

---

## Troubleshooting

### "Access denied" when connecting to TIA Portal
- Ensure your user is in the "Siemens TIA Openness" group (Step 1)
- Log out and log back in after adding to the group

### "Could not load Siemens.Engineering.dll"
- Verify the DLL path in Step 2
- Update `TIA_DLL_PATH` environment variable if non-standard install

### "Connection refused" from Mac
- Check Windows Firewall allows port 5050 (Step 6)
- Verify the Windows VM IP with `ipconfig`
- Ensure Parallels networking is configured (Step 5)

### pythonnet import error
- Make sure you installed with `pip install pythonnet`
- Use Python 3.10+ (older versions may have issues with pythonnet 3.x)

### TIA Portal hangs on launch
- Close any existing TIA Portal instances first
- Try launching TIA Portal manually once before using the bridge
- Check if another Openness session is already attached
