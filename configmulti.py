import os
import sys
import json
import sqlite3
import subprocess
import shutil
import requests
from pathlib import Path

CONFIG_FILE = "config.json"

def print_header():
    print("\n" + "="*50)
    print("  🍪 Roblox Cookie Extractor")
    print("="*50 + "\n")

def check_root():
    try:
        result = subprocess.run(['su', '-c', 'id'], 
                              capture_output=True, 
                              timeout=5)
        return result.returncode == 0
    except:
        return False

def run_root_cmd(cmd):
    try:
        result = subprocess.run(['su', '-c', cmd],
                              capture_output=True,
                              text=True,
                              timeout=10)
        return result.returncode == 0, result.stdout.strip()
    except Exception as e:
        return False, str(e)

def check_package_installed(package_name):
    success, output = run_root_cmd(f'pm list packages | grep {package_name}')
    return success and package_name in output

def find_roblox_packages():
    browsers = {}
    
    try:
        cmd = ['su', '-c', 'pm list packages']
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if 'com.roblox' in line and 'package:' in line:
                    pkg = line.replace('package:', '').strip()
                    name = f"Roblox ({pkg})"
                    browsers[name] = pkg
    except:
        browsers['Roblox App'] = 'com.roblox.client'
    
    installed = {}
    print("🔍 Detecting installed Roblox apps...\n")
    
    for name, package in browsers.items():
        if check_package_installed(package):
            print(f"   ✓ {name}: Installed")
            installed[name] = package
    
    return installed

def find_cookie_databases(package_name):
    """Find all possible cookie database locations for a package."""
    base_path = f"/data/data/{package_name}"
    found_paths = []
    
    print(f"   🔎 Searching inside: {base_path}...")
    
    find_cmds = [
        f'find {base_path} -type f -name "Cookies" 2>/dev/null',
        f'find {base_path} -type f -name "cookies.sqlite" 2>/dev/null',
        f'find {base_path} -type f -name "*cookie*" 2>/dev/null'
    ]
    
    for cmd in find_cmds:
        success, output = run_root_cmd(cmd)
        if success and output:
            for line in output.split('\n'):
                path = line.strip()
                if path and path not in found_paths:
                    if not path.endswith('-journal') and not path.endswith('.tmp'):
                        print(f"      → Found potential DB: {os.path.basename(path)}")
                        found_paths.append(path)
    
    if not found_paths:
        print("      ⚠️ No cookie files found.")

    return found_paths

def copy_database(db_path, temp_path):
    try:
        success, _ = run_root_cmd(f'cp "{db_path}" "{temp_path}"')
        if not success:
            return False
        
        run_root_cmd(f'chmod 666 "{temp_path}"')
        return True
    except:
        return False

def extract_cookie_chromium(db_path):
    temp_db = "/sdcard/temp_cookies_chromium.db"
    
    try:
        if not copy_database(db_path, temp_db):
            return None
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT name, value, host_key 
                FROM cookies 
                WHERE (host_key LIKE '%roblox.com%' OR host_key LIKE '%www.roblox.com%')
                AND name = '.ROBLOSECURITY'
            """)
            result = cursor.fetchone()
        except:
            try:
                cursor.execute("""
                    SELECT name, value 
                    FROM cookies 
                    WHERE name = '.ROBLOSECURITY'
                """)
                result = cursor.fetchone()
            except:
                result = None
        
        conn.close()
        
        if os.path.exists(temp_db):
            os.remove(temp_db)
        
        if result:
            return result[1] if len(result) > 1 else result[0]
        
        return None
        
    except Exception as e:
        if os.path.exists(temp_db):
            os.remove(temp_db)
        return None

def extract_cookie_firefox(db_path):
    temp_db = "/sdcard/temp_cookies_firefox.db"
    
    try:
        if not copy_database(db_path, temp_db):
            return None
        
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT name, value, host 
            FROM moz_cookies 
            WHERE host LIKE '%roblox.com%' 
            AND name = '.ROBLOSECURITY'
        """)
        
        result = cursor.fetchone()
        conn.close()
        
        if os.path.exists(temp_db):
            os.remove(temp_db)
        
        if result:
            return result[1]
        
        return None
        
    except Exception as e:
        if os.path.exists(temp_db):
            os.remove(temp_db)
        return None

def get_user_info(cookie):
    try:
        url = "https://users.roblox.com/v1/users/authenticated"
        cookies = {".ROBLOSECURITY": cookie}
        response = requests.get(url, cookies=cookies, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get('id'), data.get('name')
    except Exception as e:
        pass
    return None, None

def update_config_with_cookie(cookie_value):
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
        else:
            config = {
                "ps_link": "https://www.roblox.com/share?code=YOUR_CODE&type=Server",
                "user_id": 0,
                "check_interval": 10,
                "restart_delay": 30
            }
        
        config["roblox_cookie"] = cookie_value
        
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        
        return True
    except Exception as e:
        print(f"❌ Failed to update config: {e}")
        return False

def clean_input(prompt):
    print(prompt, end='')
    sys.stdout.flush()
    
    try:
        raw_val = input().strip()
    except EOFError:
        return ""

    chars = []
    for c in raw_val:
        if c == '\x7f' or c == '\x08':
            if chars:
                chars.pop()
        else:
            chars.append(c)
    
    return "".join(chars)

def main():
    print_header()
    
    if not check_root():
        print("❌ Root access required!")
        print("   This script needs root to access browser data.\n")
        return
    
    print("✓ Root access granted\n")
    
    installed_browsers = find_roblox_packages()
    
    if not installed_browsers:
        print("\n❌ No Roblox apps found!\n")
        return
    
    print("\n" + "="*50)
    print("  🔎 Searching for Roblox cookies...")
    print("="*50 + "\n")
    
    found_accounts = []
    
    for browser_name, package_name in installed_browsers.items():
        print(f"📱 Checking {browser_name}...")
        
        db_paths = find_cookie_databases(package_name)
        
        if not db_paths:
            print(f"   ✗ No cookie database found")
            continue
        
        for db_path in db_paths:
            if 'firefox' in package_name:
                cookie = extract_cookie_firefox(db_path)
            else:
                cookie = extract_cookie_chromium(db_path)
            
            if cookie:
                print(f"   ✓ Cookie found!")
                print(f"   📦 Package: {package_name}")
                
                uid, name = get_user_info(cookie)
                if uid:
                    print(f"   👤 User: {name}")
                    print(f"   🆔 ID: {uid}")
                    
                    found_accounts.append({
                        "name": name,
                        "user_id": uid,
                        "package": package_name,
                        "roblox_cookie": cookie
                    })
                else:
                    print("   ⚠️ Could not fetch user info (invalid cookie?)")
                print("")
                break 
    
    print("="*50 + "\n")
    
    if not found_accounts:
        print("❌ No cookies found in any installed app.")
        return

    print(f"✅ Found {len(found_accounts)} account(s)!\n")
    
    if len(sys.argv) > 1:
        ps_link_mode = 'y'
        global_ps_link = sys.argv[1]
        print(f"🔗 Using link from command line: {global_ps_link[:30]}...")
    else:
        try:
            subprocess.run(['stty', 'sane'], stderr=subprocess.DEVNULL)
        except:
            pass

        print("🔗 Use the same Private Server link for all accounts? (Y/n): ", end='')
        sys.stdout.flush()
        
        try:
            ps_link_mode = input().strip().lower()
        except EOFError:
            ps_link_mode = ""
            
        if not ps_link_mode:
            ps_link_mode = 'y' 
        
        print(f" -> Selected: {ps_link_mode.upper()}")
        
        global_ps_link = "EDIT_LINK_IN_CONFIG_JSON"
        if ps_link_mode == 'y':
            print("   Paste Private Server Link (press Enter to skip): ", end='')
            sys.stdout.flush()
            
            try:
                val = input().strip()
                if val: global_ps_link = val
            except EOFError:
                pass
            
            if global_ps_link == "EDIT_LINK_IN_CONFIG_JSON":
                print("\n   ⚠️  No link detected. You can edit config.json manually later.")

    current_config = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                current_config = json.load(f)
        except:
            pass
            
    new_accounts = []
    for acc in found_accounts:
        ps_link = global_ps_link
        
        if ps_link_mode != 'y':
            print(f"\n👤 Account: {acc['name']} ({acc['package']})")
            val = clean_input("   Paste Private Server Link for this account: ")
            
            if val:
                ps_link = val
            else:
                ps_link = "EDIT_LINK_IN_CONFIG_JSON"
            
        acc_entry = {
            "name": acc['name'],
            "user_id": acc['user_id'],
            "package": acc['package'],
            "ps_link": ps_link,
            "roblox_cookie": acc['roblox_cookie']
        }
        new_accounts.append(acc_entry)
        
    print("\n" + "="*50)
    print("  ⏱️  Timing Settings")
    print("="*50 + "\n")
    
    default_interval = current_config.get("check_interval", 30)
    default_restart = current_config.get("restart_delay", 15)
    
    print(f"Current Check Interval: {default_interval}s")
    sys.stdout.flush()
    interval_input = input(f"Enter new interval (press Enter to keep {default_interval}): ").strip()
    final_interval = int(interval_input) if interval_input.isdigit() else default_interval
    
    print(f"\nCurrent Restart Delay: {default_restart}s")
    sys.stdout.flush()
    restart_input = input(f"Enter new delay (press Enter to keep {default_restart}): ").strip()
    final_restart = int(restart_input) if restart_input.isdigit() else default_restart

    final_config = {
        "check_interval": final_interval,
        "restart_delay": final_restart,
        "accounts": new_accounts
    }
    
    print("\n" + "="*50)
    
    print("\n💾 Updating config.json...")
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(final_config, f, indent=2)
        print("✅ Config updated successfully!")
        print("\n✨ You can now run main.py to start farming!")
    except Exception as e:
        print(f"❌ Failed to save config: {e}")

if __name__ == "__main__":
    main()