import os, signal, subprocess
# Find and kill python processes that are running main.py (the bot)
result = subprocess.run(["ps"], capture_output=True, text=True)
for line in result.stdout.splitlines():
    if "python" in line and "main.py" in line.lower():
        parts = line.strip().split()
        if parts:
            pid = int(parts[0])
            os.kill(pid, signal.SIGKILL)
            print(f"Killed PID {pid}")
print("Done")
