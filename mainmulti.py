import os
import time
import json
import subprocess
import sys

try:
    import requests
except ImportError:
    print("❌ Missing 'requests' library. Run: pip install requests")
    sys.exit(1)

CONFIG_FILE = "config.json"

def acquire_wakelock():
    try:
        subprocess.run(['termux-wake-lock'], check=False)
        print("⚡ Wake lock acquired (CPU will stay awake)")
    except FileNotFoundError:
        print("⚠️ 'termux-wake-lock' command not found (Are you in Termux?)")

def release_wakelock():
    try:
        subprocess.run(['termux-wake-unlock'], check=False)
        print("💤 Wake lock released")
    except:
        pass

def check_root():
    try:
        result = subprocess.run(['su', '-c', 'id'], 
                              capture_output=True, 
                              timeout=5)
        return result.returncode == 0
    except:
        return False

def run_shell_cmd(cmd_str, use_root=False, silent=False):
    if use_root:
        full_cmd = ['su', '-c', cmd_str]
    else:
        full_cmd = cmd_str.split()
    
    try:
        result = subprocess.run(full_cmd, 
                              capture_output=True, 
                              text=True, 
                              timeout=10)
        if result.returncode == 0:
            return True, result.stdout.strip()
        else:
            return False, result.stderr.strip()
    except Exception as e:
        return False, str(e)

def get_installed_roblox_packages():
    packages = []
    try:
        cmd = ['su', '-c', 'pm list packages']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith('package:'):
                    pkg = line.replace('package:', '')
                    if 'com.roblox' in pkg:
                        packages.append(pkg)
    except Exception as e:
        print(f"⚠️ Error detecting packages: {e}")
    
    if not packages:
        packages.append("com.roblox.client")
        
    return sorted(list(set(packages)))

def load_config():
    if not os.path.exists(CONFIG_FILE):
        print(f"❌ Error: {CONFIG_FILE} not found!")
        sys.exit(1)
    
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
        
    if "accounts" not in config:
        detected = get_installed_roblox_packages()
        default_pkg = detected[0] if detected else "com.roblox.client"
        
        if config.get("user_id"):
            config["accounts"] = [{
                "user_id": config.get("user_id"),
                "roblox_cookie": config.get("roblox_cookie"),
                "ps_link": config.get("ps_link"),
                "package": config.get("package", default_pkg)
            }]
        else:
            config["accounts"] = []
            
    return config

def force_stop_roblox(package_name):
    cmd = f"am force-stop {package_name}"
    run_shell_cmd(cmd, use_root=True, silent=True)

def is_roblox_running(package_name):
    cmd = f"ps -A | grep {package_name}"
    success, output = run_shell_cmd(cmd, use_root=True, silent=True)
    return success and len(output) > 0

def open_ps_link(link, package_name):
    cmd = f'am start -n {package_name}/com.roblox.client.ActivityProtocolLaunch -a android.intent.action.VIEW -d "{link}"'
    
    success, _ = run_shell_cmd(cmd, use_root=True, silent=True)
    if not success:
        cmd = f'am start -a android.intent.action.VIEW -d "{link}" -p {package_name}'
        success, _ = run_shell_cmd(cmd, use_root=True, silent=True)
        
    return success

def check_user_presence(user_id, roblox_cookie=None):
    url = "https://presence.roblox.com/v1/presence/users"
    payload = {"userIds": [user_id]}
    headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    cookies = {}
    if roblox_cookie:
        cookies[".ROBLOSECURITY"] = roblox_cookie
    
    try:
        r = requests.post(url, json=payload, headers=headers, cookies=cookies, timeout=10)
        if r.status_code == 200:
            data = r.json()
            user_presences = data.get("userPresences", [])
            if user_presences:
                presence = user_presences[0]
                presence_type = presence.get("userPresenceType")
                game_id = presence.get("gameId")
                is_ingame = presence_type == 2
                return is_ingame, game_id
    except:
        pass
    return True, None

def should_rejoin(user_id, expected_game_id, package_name, roblox_cookie=None):
    if not is_roblox_running(package_name):
        return True, "Process stopped", None
    
    is_ingame, current_game_id = check_user_presence(user_id, roblox_cookie)
    
    if not is_ingame:
        return True, "Not in-game", current_game_id

    if expected_game_id and current_game_id and current_game_id != expected_game_id:
        return True, "Server switched", current_game_id
    
    return False, "OK", current_game_id 

def set_selinux_permissive():
    success, mode = run_shell_cmd('getenforce', use_root=True, silent=True)
    if success and mode.strip() == "Enforcing":
        run_shell_cmd('setenforce 0', use_root=True, silent=True)

def main():
    print("\n" + "="*50)
    print("  🎮 Auto Rejoin Roblox (Android Fix)")
    print("="*50 + "\n")
    
    acquire_wakelock()
    
    if not check_root():
        print("❌ Root access required! Please allow Root for Termux.")
        return
    
    print("✓ Root access granted")
    set_selinux_permissive()
    
    config = load_config()
    accounts = config.get("accounts", [])
    
    if not accounts:
        print("❌ No accounts configured in config.json\n")
        return

    interval = config.get("check_interval", 30)
    restart_delay = config.get("restart_delay", 15)
    
    print(f"📋 Loaded {len(accounts)} account(s)")

    active_accounts = []
    
    for i, acc in enumerate(accounts):
        user_id = acc.get("user_id")
        ps_link = acc.get("ps_link")
        cookie = acc.get("roblox_cookie")
        pkg = acc.get("package")
        
        if not pkg:
            installed = get_installed_roblox_packages()
            pkg = installed[i] if i < len(installed) else installed[0]
            
        print(f"👤 Account {i+1}: User {user_id} ({pkg})")
        
        if not ps_link or "YOUR_CODE" in ps_link:
            print(f"   ⚠️ Skipping (Invalid PS Link)")
            continue
            
        print(f"   🔄 Starting Roblox...")
        force_stop_roblox(pkg)
        time.sleep(2) 
        
        if open_ps_link(ps_link, pkg):
            active_accounts.append({
                "user_id": user_id,
                "package": pkg,
                "cookie": cookie,
                "ps_link": ps_link,
                "expected_game_id": None,
                "name": f"User {user_id}"
            })
        
        print(f"   ⏳ Staggering start ({restart_delay}s)...")
        time.sleep(restart_delay)
            
    if not active_accounts:
        print("\n❌ No active accounts started.")
        release_wakelock()
        return
        
    print(f"\n⏳ Final wait for games to load...")
    time.sleep(10)

    print("\n🔍 Detecting initial game states...")
    for acc in active_accounts:
        _, game_id = check_user_presence(acc["user_id"], acc["cookie"])
        acc["expected_game_id"] = game_id
        if game_id:
            print(f"   ✓ {acc['name']}: Game ID {str(game_id)[:12]}...")

    print("\n" + "="*50)
    print("  📊 Monitoring Status")
    print("="*50 + "\n")

    try:
        while True:
            timestamp = time.strftime("%H:%M:%S")
            print(f"[{timestamp}] Checking {len(active_accounts)} accounts...")
            
            for acc in active_accounts:
                needs_rejoin, reason, current_game_id = should_rejoin(
                    acc["user_id"], 
                    acc["expected_game_id"], 
                    acc["package"],
                    acc["cookie"]
                )
                
                if needs_rejoin:
                    print(f"   🔴 {acc['name']}: {reason}")
                    print(f"      ⟳ Restarting {acc['package']} ONLY...")
                    
                    force_stop_roblox(acc["package"])
                    time.sleep(2)
                    
                    open_ps_link(acc["ps_link"], acc["package"])
                    
                    print(f"      ⏳ Waiting 25s for launch...") 
                    time.sleep(25) 
                    
                    acc["expected_game_id"] = None
                else:
                    if current_game_id:
                        acc["expected_game_id"] = current_game_id
                        
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\n👋 Script stopped by user")
    except Exception as e:
        print(f"❌ Error in loop: {e}")
    finally:
        release_wakelock()

if __name__ == "__main__":
    main()