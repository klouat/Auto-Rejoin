import os
import sys
import json
import sqlite3
import subprocess
import shutil
import requests
import time
import math
import re
from pathlib import Path

CONFIG_FILE = "config.json"

def clear_screen():
    print("\033[H\033[2J", end="")
    sys.stdout.flush()


def print_header():
    print("\n" + "="*50)
    print("  🍪 Roblox Auto-Rejoin Tool")
    print("="*50 + "\n")

def check_root():
    try:
        result = subprocess.run(['su', '-c', 'id'], capture_output=True, timeout=5)
        return result.returncode == 0
    except:
        return False

def run_root_cmd(cmd):
    try:
        result = subprocess.run(['su', '-c', cmd], capture_output=True, text=True, timeout=10)
        return result.returncode == 0, result.stdout.strip()
    except Exception as e:
        return False, str(e)

# --- CONFIG CREATION FUNCTIONS ---
def check_package_installed(package_name):
    success, output = run_root_cmd(f'pm list packages')
    return success and package_name in output

def find_roblox_packages():
    browsers = {}
    success, output = run_root_cmd('pm list packages')
    if success:
        for line in output.splitlines():
            if 'com.roblox' in line and 'package:' in line:
                pkg = line.replace('package:', '').strip()
                browsers[f"Roblox ({pkg})"] = pkg
    
    if not browsers:
        browsers['Roblox App'] = 'com.roblox.client'
        
    installed = {}
    print("🔍 Detecting installed Roblox apps...\n")
    for name, package in browsers.items():
        if check_package_installed(package):
            print(f"   ✓ {name}: Installed")
            installed[name] = package
    return installed

def find_cookie_databases(package_name):
    base_path = f"/data/data/{package_name}"
    found_paths = []
    print(f"   🔎 Searching inside: {base_path}...")
    
    cmds = [
        f'find {base_path} -type f -name "Cookies" 2>/dev/null',
        f'find {base_path} -type f -name "cookies.sqlite" 2>/dev/null',
        f'find {base_path} -type f -name "*cookie*" 2>/dev/null'
    ]
    
    for cmd in cmds:
        success, output = run_root_cmd(cmd)
        if success and output:
            for path in output.split('\n'):
                path = path.strip()
                if path and path not in found_paths and not path.endswith('-journal') and not path.endswith('.tmp'):
                    print(f"      → Found potential DB: {os.path.basename(path)}")
                    found_paths.append(path)
    if not found_paths:
        print("      ⚠️ No cookie files found.")
    return found_paths

def copy_database(db_path, temp_path):
    success, _ = run_root_cmd(f'cp "{db_path}" "{temp_path}" && chmod 666 "{temp_path}"')
    return success

def extract_cookie_chromium(db_path):
    temp_db = "/sdcard/temp_cookies_chromium.db"
    if not copy_database(db_path, temp_db): return None
    try:
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT name, value FROM cookies WHERE (host_key LIKE '%roblox.com%' OR host_key LIKE '%www.roblox.com%') AND name = '.ROBLOSECURITY'")
            result = cursor.fetchone()
        except:
            try:
                cursor.execute("SELECT name, value FROM cookies WHERE name = '.ROBLOSECURITY'")
                result = cursor.fetchone()
            except:
                result = None
        conn.close()
        run_root_cmd(f'rm "{temp_db}"')
        return result[1] if result and len(result) > 1 else (result[0] if result else None)
    except:
        run_root_cmd(f'rm "{temp_db}"')
        return None

def extract_cookie_firefox(db_path):
    temp_db = "/sdcard/temp_cookies_firefox.db"
    if not copy_database(db_path, temp_db): return None
    try:
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name, value FROM moz_cookies WHERE host LIKE '%roblox.com%' AND name = '.ROBLOSECURITY'")
        result = cursor.fetchone()
        conn.close()
        run_root_cmd(f'rm "{temp_db}"')
        return result[1] if result else None
    except:
        run_root_cmd(f'rm "{temp_db}"')
        return None

def get_user_info(cookie):
    try:
        url = "https://users.roblox.com/v1/users/authenticated"
        response = requests.get(url, cookies={".ROBLOSECURITY": cookie}, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get('id'), data.get('name')
    except: pass
    return None, None

def clean_input(prompt):
    try:
        subprocess.run(['stty', 'sane'], stderr=subprocess.DEVNULL)
    except: pass
    print("\033[?25h", end="")
    sys.stdout.flush()
    
    print(prompt, end='')
    sys.stdout.flush()
    try:
        raw_val = input().strip()
    except EOFError:
        return ""
        
    chars = []
    for c in raw_val:
        if c == '\x7f' or c == '\x08':
            if chars: chars.pop()
        else:
            chars.append(c)
    return "".join(chars)

def create_config():
    clear_screen()
    print_header()
    if not check_root():
        print("❌ Root access required!")
        input("\nPress Enter to return...")
        return
        
    installed_browsers = find_roblox_packages()
    if not installed_browsers:
        print("\n❌ No Roblox apps found!")
        input("\nPress Enter to return...")
        return
        
    print("\n  🔎 Searching for Roblox cookies...\n")
    found_accounts = []
    for browser_name, package_name in installed_browsers.items():
        print(f"📱 Checking {browser_name}...")
        db_paths = find_cookie_databases(package_name)
        if not db_paths:
            print(f"   ✗ No database found")
            continue
            
        for db_path in db_paths:
            cookie = extract_cookie_firefox(db_path) if 'firefox' in package_name else extract_cookie_chromium(db_path)
            if cookie:
                print(f"   ✓ Cookie found! Package: {package_name}")
                uid, name = get_user_info(cookie)
                if uid:
                    print(f"   👤 User: {name} | 🆔 ID: {uid}\n")
                    found_accounts.append({
                        "name": name,
                        "user_id": uid,
                        "package": package_name,
                        "roblox_cookie": cookie
                    })
                else:
                    print("   ⚠️ Could not fetch user (invalid cookie?)\n")
                break
                
    if not found_accounts:
        print("❌ No cookies found in installed apps.")
        input("\nPress Enter to return...")
        return
        
    print(f"✅ Found {len(found_accounts)} account(s)!\n")
    
    current_config = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                current_config = json.load(f)
        except: pass

    current_webhook = current_config.get("webhook_url", "")
    print(f"Current Webhook: {current_webhook[:40]}...")
    webhook_input = clean_input("Enter Discord Webhook URL (Enter to keep): ")
    final_webhook = webhook_input if webhook_input else current_webhook
    
    ps_mode = clean_input("🔗 Use same PS Link for all? (Y/n): ").lower()
    if not ps_mode: ps_mode = 'y'
    global_link = "EDIT_LINK_IN_CONFIG_JSON"
    if ps_mode == 'y':
        val = clean_input("Paste PS Link (Enter to skip): ")
        if val: global_link = val
        
    new_accounts = []
    for acc in found_accounts:
        ps_link = global_link
        if ps_mode != 'y':
            print(f"\n👤 Account: {acc['name']} ({acc['package']})")
            val = clean_input("   Paste PS Link for this account: ")
            if val: ps_link = val
        acc["ps_link"] = ps_link
        new_accounts.append(acc)
        
    def_interval = current_config.get("check_interval", 30)
    def_restart = current_config.get("restart_delay", 15)
    
    i_val = clean_input(f"Check Interval [keep {def_interval}s]: ")
    r_val = clean_input(f"Restart Delay [keep {def_restart}s]: ")
    
    final_config = {
        "check_interval": int(i_val) if i_val.isdigit() else def_interval,
        "restart_delay": int(r_val) if r_val.isdigit() else def_restart,
        "webhook_url": final_webhook,
        "accounts": new_accounts
    }
    
    with open(CONFIG_FILE, 'w') as f:
        json.dump(final_config, f, indent=2)
    print("\n✅ Config saved successfully!")
    time.sleep(2)

def edit_config():
    if not os.path.exists(CONFIG_FILE):
        print("No config file found! Please run 'Create Config' first.")
        input("\nPress Enter to return...")
        return
        
    print("Opening config.json in nano...")
    time.sleep(1)
    os.system(f"nano {CONFIG_FILE}")

# --- APP RUNNER FUNCTIONS ---
def get_current_resolution():
    w, h = 1080, 2400
    success, output = run_root_cmd("dumpsys window displays")
    if success and output:
        m = re.search(r"cur=(\d+)x(\d+)", output)
        if m: return int(m.group(1)), int(m.group(2))
    success, output = run_root_cmd("wm size")
    if success and output:
        m = re.search(r"(\d+)x(\d+)", output)
        if m: return int(m.group(1)), int(m.group(2))
    return w, h

def get_grid_bounds(index, total, screen_w, screen_h):
    cols = math.ceil(math.sqrt(total))
    rows = math.ceil(total / cols)
    if screen_w > screen_h:
        while cols < rows:
            cols += 1
            rows = math.ceil(total / cols)
    cell_w = screen_w // cols
    cell_h = screen_h // rows
    
    idx = index - 1
    r = idx // cols
    c = idx % cols
    return f"{c*cell_w},{r*cell_h},{(c+1)*cell_w},{(r+1)*cell_h}"

def get_memory_info():
    try:
        with open("/proc/meminfo", "r") as f:
            content = f.read()
            m_tot = re.search(r"MemTotal:\s+(\d+)\s+kB", content)
            m_av = re.search(r"MemAvailable:\s+(\d+)\s+kB", content)
            if not m_av: m_av = re.search(r"MemFree:\s+(\d+)\s+kB", content)
            if m_tot and m_av:
                tot = int(m_tot.group(1))
                av = int(m_av.group(1))
                return f"{av//1024}MB", int((av/tot)*100)
    except: pass
    return "N/A", 0

def draw_ui(accounts, sys_status, check_prog, next_wh=""):
    sys.stdout.write("\033[2J\033[H\033[?25l")
    C_RES, C_CYA, C_GRE, C_YEL, C_RED, C_GRY = "\033[0m", "\033[36m", "\033[32m", "\033[33m", "\033[31m", "\033[90m"
    
    mem, m_pct = get_memory_info()
    cols = 65
    c1 = 34
    c2 = cols - 4 - c1
    
    def trunc(s, l):
        s = str(s).replace('\n', '').replace('\r', '')
        return s[:l-1] + "." if len(s) > l else s
    def sep(l, m, r, c='─'):
        sys.stdout.write(f"{C_CYA}{l}{c*(c1+1)}{m}{c*(c2+1)}{r}{C_RES}\n")
    def row(t1, t2, col=C_RES):
        sys.stdout.write(f"{C_CYA}│{C_RES} {trunc(t1, c1):<{c1}}{C_CYA}│{C_RES} {col}{trunc(t2, c2):<{c2}}{C_RES}{C_CYA}│{C_RES}\n")
        
    sep('┌', '┬', '┐')
    row("PACKAGE", "STATUS")
    sep('├', '┼', '┤')
    
    sys_txt = check_prog if check_prog else sys_status
    if next_wh: sys_txt += f" | {next_wh}"
    row("System", sys_txt or "Idle", C_YEL)
    row("Memory", f"Free: {mem} ({m_pct}%)", C_GRY)
    sep('├', '┼', '┤')
    
    for a in accounts:
        st = a.get('status', 'Unknown')
        c = C_GRE
        if any(x in st for x in ['Restarting','Initializing','Waiting']): c = C_YEL
        elif any(x in st for x in ['Error','Stopped','Failed']): c = C_RED
        elif 'Checking' in st: c = C_GRY
        row(f"{a['package']} ({a.get('name', '?')})", st, c)
        
    sep('└', '┴', '┘')
    sys.stdout.flush()

def is_roblox_running(pkg):
    ok, out = run_root_cmd(f"pidof {pkg}")
    if ok and out.strip(): return True
    ok, out = run_root_cmd(f"ps -A | grep {pkg}")
    return ok and bool(out.strip())

def check_user_presence(uid, cookie):
    try:
        r = requests.post(
            "https://presence.roblox.com/v1/presence/users",
            json={'userIds': [uid]},
            cookies={".ROBLOSECURITY": cookie} if cookie else {},
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=5
        )
        if r.status_code == 200 and r.json().get('userPresences'):
            p = r.json()['userPresences'][0]
            return (p.get('userPresenceType') == 2), p.get('gameId')
    except: pass
    return True, None

def open_ps_link(link, pkg, bounds=None):
    flags = f"--windowingMode 5 --bounds {bounds}" if bounds else ""
    cmd1 = f'am start {flags} -n {pkg}/com.roblox.client.ActivityProtocolLaunch -a android.intent.action.VIEW -d "{link}"'
    ok, out = run_root_cmd(cmd1)
    if ok and "Error:" not in out and "does not exist" not in out: return True
    ok, out = run_root_cmd(f'am start {flags} -a android.intent.action.VIEW -d "{link}" -p {pkg}')
    return ok and "Error:" not in out and "does not exist" not in out

def log_activity(msg, lvl="INFO"):
    try:
        with open("activity.log", "a") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] [{lvl}] {msg}\n")
    except: pass

def send_webhook(webhook_url, accounts):
    if not webhook_url: return
    
    local_img = os.path.join(os.getcwd(), "screen.png")
    temp_img = "/data/local/tmp/screen.png"
    ok, _ = run_root_cmd(f"screencap -p {temp_img} && cp {temp_img} {local_img} && chmod 666 {local_img}")
    
    embed_fields = []
    for a in accounts:
        embed_fields.append({
            "name": f"{a.get('name', '?')} | {a.get('package', '?')}",
            "value": f"**Status:** {a.get('status', '?')}",
            "inline": False
        })
        
    payload = {
        "embeds": [{
            "title": "Roblox Account Status",
            "color": 3447003,
            "fields": embed_fields,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }]
    }
    
    files = {}
    if ok and os.path.exists(local_img):
        f = open(local_img, "rb")
        files["file"] = ("screen.png", f, "image/png")
        payload["embeds"][0]["image"] = {"url": "attachment://screen.png"}
        
    try:
        if files:
            requests.post(webhook_url, data={"payload_json": json.dumps(payload)}, files=files, timeout=15)
        else:
            requests.post(webhook_url, json=payload, timeout=10)
    except: pass
    finally:
        if "file" in files: files["file"][1].close()

def start_rejoin_app():
    if not os.path.exists(CONFIG_FILE):
        print("Config file not found! Please run 'Create Config' first.")
        input("\nPress Enter to return...")
        return
        
    if not check_root():
        print("Root access required to manage packages and take screenshots!")
        input("\nPress Enter to return...")
        return
        
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
        
    accounts_cfg = config.get("accounts", [])
    if not accounts_cfg:
        print("No accounts configured.")
        time.sleep(2)
        return
        
    clear_screen()
    os.system('termux-wake-lock')
    run_root_cmd("setenforce 0")
    
    interval = config.get("check_interval", 30)
    restart_delay = config.get("restart_delay", 15)
    wh_url = config.get("webhook_url", "")
    
    sw, sh = get_current_resolution()
    tot = len(accounts_cfg)
    
    accounts = []
    for i, a in enumerate(accounts_cfg):
        accounts.append({
            'index': i+1,
            'name': a.get('name', f"User {a.get('user_id')}"),
            'user_id': a.get('user_id'),
            'package': a.get('package'),
            'cookie': a.get('roblox_cookie'),
            'ps_link': a.get('ps_link'),
            'status': 'Pending Start',
            'expected_game': None
        })
        
    draw_ui(accounts, "Starting Up...", "")
    
    for i, acc in enumerate(accounts):
        acc['status'] = 'Starting...'
        draw_ui(accounts, "Launching Accounts", f"[{i+1}/{tot}]")
        
        run_root_cmd(f"am force-stop {acc['package']}")
        time.sleep(1)
        
        bounds = get_grid_bounds(acc['index'], tot, sw, sh)
        if open_ps_link(acc['ps_link'], acc['package'], bounds):
            acc['status'] = 'Launched (Wait)'
        else:
            acc['status'] = 'Launch Failed'
            
        if i < tot - 1:
            for t in range(restart_delay, 0, -1):
                draw_ui(accounts, "Launching Accounts", f"Next in {t}s")
                time.sleep(1)
                
    for t in range(10, 0, -1):
        draw_ui(accounts, "Initializing", f"Wait {t}s")
        time.sleep(1)
        
    for a in accounts:
        ingame, gid = check_user_presence(a['user_id'], a['cookie'])
        a['expected_game'] = gid
        a['status'] = "Online" if gid else "Waiting Game"
        
    last_wh = time.time()
    try:
        while True:
            nxt_wh = ""
            if wh_url:
                wh_diff = int(600 - (time.time() - last_wh))
                if wh_diff <= 0:
                    draw_ui(accounts, "Webhook", "Sending Update...")
                    send_webhook(wh_url, accounts)
                    last_wh = time.time()
                    wh_diff = 600
                nxt_wh = f"WH in {wh_diff//60}m"
                
            for i, a in enumerate(accounts):
                draw_ui(accounts, "Monitoring", f"Check [{i+1}/{tot}]", nxt_wh)
                
                if not is_roblox_running(a['package']):
                    needs_rejoin, reason = True, "App closed"
                else:
                    ingame, cg = check_user_presence(a['user_id'], a['cookie'])
                    if not ingame:
                        needs_rejoin, reason = True, "Not in game"
                    elif a['expected_game'] and cg and str(cg) != str(a['expected_game']):
                        needs_rejoin, reason = True, "Server switch"
                    else:
                        needs_rejoin, reason = False, ""
                        if cg: a['expected_game'] = cg
                        
                if needs_rejoin:
                    log_activity(f"{a['name']}: {reason}", "WARN")
                    a['status'] = "Restarting..."
                    draw_ui(accounts, "Monitoring", f"Fix {a['name']}", nxt_wh)
                    
                    run_root_cmd(f"am force-stop {a['package']}")
                    time.sleep(2)
                    open_ps_link(a['ps_link'], a['package'], get_grid_bounds(a['index'], tot, sw, sh))
                    
                    for t in range(25, 0, -1):
                        a['status'] = f"Wait Start ({t}s)"
                        draw_ui(accounts, "Monitoring", "Wait Launch", nxt_wh)
                        time.sleep(1)
                        
                    a['status'] = "Online"
                    a['expected_game'] = None
                else:
                    a['status'] = "Online"
                    
            with open("status.json", "w") as f:
                json.dump([{'name': x['name'], 'status': x['status']} for x in accounts], f)
                
            for t in range(interval, 0, -1):
                draw_ui(accounts, "Idle", f"Next Check: {t}s", nxt_wh)
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        os.system('termux-wake-unlock')
        sys.stdout.write("\033[?25h")

def main():
    while True:
        clear_screen()
        print_header()
        print("  1. Create Config")
        print("  2. Start Rejoin App")
        print("  3. Edit Config")
        print("  4. Exit")
        print("\n" + "="*50)
        
        c = input("\nSelect an option: ").strip()
        if c == '1': create_config()
        elif c == '2': start_rejoin_app()
        elif c == '3': edit_config()
        elif c == '4':
            clear_screen()
            break

if __name__ == "__main__":
    main()
