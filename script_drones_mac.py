import subprocess
import signal
import os
import time

def create_process(i):
    folder_path = "/Users/bruno/Desktop/SD/Prac/P2"
    command = f"osascript -e 'tell application \"Terminal\" to do script \"cd {folder_path} && python AD_Dron.py localhost 8002 localhost 29092 {i} localhost 8000\"'"
    return subprocess.Popen(command, shell=True)

num_drones = 3
processes = []

# Crear los procesos
for i in range(1, num_drones + 1):
    process = create_process(i)
    processes.append(process)

try:
    # Esperar a que se presione Ctrl+C
    while True:
        time.sleep(1)

except KeyboardInterrupt:
    # Manejar la interrupción (Ctrl+C)
    print("Ctrl+C detectado.")
