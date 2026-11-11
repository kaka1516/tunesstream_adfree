# Make Music Stream public (use it from anywhere)

After you install Music Stream it only works **at home**: on the same computer or phone, or on your home Wi-Fi.
"Making it public" gives it an **https web address** so you can open it from mobile data, at work, or anywhere.

Nobody can use it without signing in. The tools below **refuse to go public** until:
- an **admin account** exists (you create it at `http://127.0.0.1:8125/setup` on the device itself), and
- `MUSIC_OPEN` is **off** in `music.env` (it is off unless someone changed it).

## Two choices

| | **A. Instant link** | **B. Your own permanent address** |
|---|---|---|
| Looks like | `https://random-words.trycloudflare.com` | `https://music.yourname.com` |
| Account needed | none | a free Cloudflare account **and** a domain name in it |
| Time to set up | about 30 seconds | about 10 minutes, once |
| After a restart | **the address changes** (read the new one from the saved text file) | stays the same |
| Good for | trying it out, "I need it right now", emergencies | everyday use, sharing with family |

Both use **Cloudflare Tunnel** (a free program called `cloudflared`). It makes an outgoing connection from your device to
Cloudflare, so you don't need to change your router, open ports, or know your home IP address.
The tools download `cloudflared` for you if it's missing.

## Windows: one double-click

1. Make sure Music Stream is installed (double-click `install.cmd`) and you've created the admin account.
2. Double-click **Make Music Stream public** on your desktop.
   (It's also in `%LOCALAPPDATA%\MusicStream`, and in the downloaded folder as `Make Music Stream public.cmd`.)
3. Type **A** and press Enter for the instant link, or **B** for your own address.
4. For **A**: the link opens in your browser and is saved in `%LOCALAPPDATA%\MusicStream\PUBLIC LINK.txt`.
   Answer **y** to "start by itself every time you log in" if you want it back after restarts.
5. To turn it off: double-click **Stop public link** on the desktop.
6. To see if it's on: run **Make Music Stream public** and type **S**.

## Linux, Raspberry Pi, Android phone (Termux): one command

1. Make sure Music Stream is installed (`sh install.sh --yes --start`) and you've created the admin account.
2. Type: `ms-public`
   (If it says "command not found", use `sh ~/music-stream/ms-public` (or wherever you put the folder), or close and reopen the terminal.)
3. Type **A** for the instant link or **B** for your own address. The address is printed and saved in `PUBLIC_LINK.txt` in the app folder.
4. Other commands: `ms-public status`, `ms-public off`, `ms-public quick --autostart` (instant link that comes back after a reboot).
   On a phone, auto-start needs the **Termux:Boot** app installed and opened once.

## Choice B step by step (your own permanent address)

You need:
1. A **free Cloudflare account**: https://dash.cloudflare.com/sign-up
2. A **domain name** added to that account. A domain is a name like `yourname.com`. You can buy one (about $10 a year)
   from Cloudflare or any registrar, or use a free one. In Cloudflare click **Add a domain** and follow the steps.
   This part is done once in the Cloudflare website.

Then run **Make Music Stream public** → **B** (Windows) or `ms-public permanent` (Linux/phone):
1. Type the address you want, for example `music.yourname.com`.
2. A Cloudflare page opens (on a phone or a server, copy the link it prints into a browser). Log in, click your domain, click **Authorize**.
3. The tool then does the rest by itself: it creates a tunnel called `music-stream`, points your address at it,
   writes the settings and makes it start automatically after every reboot.
4. Wait 1–2 minutes and open `https://music.yourname.com`.

Where the private bits are kept (never in this repo, never share them):
- `~/.cloudflared/cert.pem` (Windows: `C:\Users\<you>\.cloudflared\cert.pem`): proof you logged in to Cloudflare.
- `~/.cloudflared/<tunnel-id>.json`: the tunnel's key. Anyone with it could serve your address.
- `.public/config.yml` (Windows: `%LOCALAPPDATA%\MusicStream\public\config.yml`): which address goes to which port.

**Back up** the `.cloudflared` folder together with your Music Stream data (see FAILOVER.md / NEW_PHONE_SETUP.md).

## If your device is wiped (or you move to a new one)

1. **Install again in one step.**
   - Windows: download the ZIP from GitHub (green **Code** button → **Download ZIP**), unzip, double-click `install.cmd`.
   - Linux / phone: `curl -fsSL https://raw.githubusercontent.com/kaka1516/tunesstream_adfree/main/get.sh | sh`
     (on a new Android phone install **Termux** from F-Droid first, then paste that line).
2. **Bring back your accounts and settings** if you have a backup: copy `users.json`, `sessions.json`, `user_data/`
   and `music.env` into the app folder (Windows: `%LOCALAPPDATA%\MusicStream\app`) **before** creating a new admin.
   See NEW_PHONE_SETUP.md (backups) and FAILOVER.md (a second device that keeps a copy).
   No backup? Just create a new admin at `http://127.0.0.1:8125/setup`. You start fresh but everything works.
3. **Make it public again:**
   - You only need it working now? Choose **A**. You get a new link in 30 seconds and need no account.
   - You had a **permanent address** before? Choose **B** and type the **same address**.
     - If you restored your `.cloudflared` folder, it just reconnects.
     - If not, the tool logs you in to Cloudflare again (`cloudflared tunnel login`). It then sees that the old tunnel `music-stream` has no key on this device and offers to **delete and recreate it**. Say **Y**.
       Your address stays the same because the tool points it at the new tunnel (`--overwrite-dns`).
     - Make sure the **old device is off or wiped**. Two devices must not serve the same address at once.

## Stuck? What to do

1. **Use choice A.** It works almost everywhere and needs no account, so you can keep listening while you sort out B.
2. **"Not safe yet: there is no admin account"**: open `http://127.0.0.1:8125/setup` **on the device itself** and create the admin.
3. **"could not connect … port 7844"**: your network (an office, school or some hotels) blocks Cloudflare tunnels.
   Try another network, like a phone hotspot, or run it at home.
4. **The page says 502 / "Bad gateway"**: Music Stream isn't running. Start it (Windows: **Music Stream** shortcut;
   Linux/phone: `./start.sh`), then refresh.
5. **The instant link stopped working**: it changed after a restart. Run it again, or look in `PUBLIC LINK.txt` / `PUBLIC_LINK.txt`.
6. **Choice B says the domain isn't in your account**: add the domain in the Cloudflare website first (Add a domain).
7. **Ask any AI assistant**: paste this file (`docs/MAKE_PUBLIC.md`), say which device you're on, and paste the exact
   error message. **Never paste** `music.env`, `cert.pem` or any `.json` key file: they're private keys.
8. **Turn it all off**: Windows **Stop public link**, Linux/phone `ms-public off`. Music Stream keeps working at home.
