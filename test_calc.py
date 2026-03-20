import subprocess
import os

print(f"os.name: {os.name}")
print(f"Testing subprocess.Popen with calc...")

try:
    proc = subprocess.Popen(
        ["calc"],
        shell=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"Success! PID: {proc.pid}")
except FileNotFoundError as e:
    print(f"FileNotFoundError: {e}")
except Exception as e:
    print(f"Error: {e}")

print("Done")
