import subprocess
import sys
import time

def run_cmd(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def show_connections():
    print("\n=== ACTIVE NETWORK CONNECTIONS ===\n")
    result = run_cmd("netstat -ano")
    print(result.stdout)

def list_adapters():
    result = run_cmd('netsh interface show interface')
    adapters = []
    lines = result.stdout.splitlines()
    for line in lines:
        if "Connected" in line or "Disconnected" in line:
            parts = line.split()
            adapters.append(parts[-1])
    return adapters

def disable_internet():
    adapters = list_adapters()
    print("\n[!] DISABLING INTERNET CONNECTIONS...\n")
    for adapter in adapters:
        run_cmd(f'netsh interface set interface "{adapter}" admin=disable')
        print(f"Disabled: {adapter}")
    print("\n[✔] INTERNET DISCONNECTED")

def enable_internet():
    adapters = list_adapters()
    print("\n[!] RESTORING INTERNET CONNECTIONS...\n")
    for adapter in adapters:
        run_cmd(f'netsh interface set interface "{adapter}" admin=enable')
        print(f"Enabled: {adapter}")
    print("\n[✔] INTERNET RESTORED")

def menu():
    while True:
        print("""
===============================
 INTERNET CONTROL PANEL
===============================
1. Show active connections
2. Kill internet (KILL SWITCH)
3. Restore internet
4. Exit
""")
        choice = input("Select option: ").strip()

        if choice == "1":
            show_connections()
        elif choice == "2":
            disable_internet()
        elif choice == "3":
            enable_internet()
        elif choice == "4":
            print("Exiting.")
            sys.exit()
        else:
            print("Invalid option.")

if __name__ == "__main__":
    if not subprocess.run("net session", shell=True, capture_output=True).returncode == 0:
        print("ERROR: This script MUST be run as Administrator.")
        sys.exit(1)

    menu()
