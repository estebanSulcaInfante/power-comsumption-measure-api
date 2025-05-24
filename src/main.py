import wmi
import psutil
import time
import pandas as pd
from datetime import datetime
import subprocess
import threading
import os
import platform
import subprocess
import requests

try:
    from py3nvml import py3nvml
    py3nvml.nvmlInit()
    gpu_available = True
except Exception:
    gpu_available = False

c = wmi.WMI(namespace="root\\CIMV2")

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "benchmarks"))
API_URL = "http://localhost:5000/api/energy_data"  

max_cpu_power_global = 30  # Benchmark para CPU
max_gpu_power_global = 40  # Valor fijo, no benchmark

def get_battery_info():
    batteries = c.Win32_Battery()
    if not batteries:
        return None
    b = batteries[0]
    status_map = {
        1: "Desconocido",
        2: "Cargando",
        3: "Descargando",
        4: "No en uso",
        5: "En espera",
        6: "Hibernando"
    }
    return {
        "status": status_map.get(b.BatteryStatus, "Desconocido"),
        "charge": b.EstimatedChargeRemaining,
        "run_time": b.EstimatedRunTime
    }

def get_cpu_usage():
    return psutil.cpu_percent(interval=1)

def get_gpu_usage():
    if not gpu_available:
        return None
    handle = py3nvml.nvmlDeviceGetHandleByIndex(0)
    util = py3nvml.nvmlDeviceGetUtilizationRates(handle)
    return util.gpu

def get_gpu_power_watts():
    if not gpu_available:
        return None
    handle = py3nvml.nvmlDeviceGetHandleByIndex(0)
    power_mw = py3nvml.nvmlDeviceGetPowerUsage(handle)
    return power_mw / 1000  # convertir miliwatts a watts

def get_temperature():
    temp_data = []
    try:
        hw_monitor = wmi.WMI(namespace="root\\OpenHardwareMonitor")
        sensors = hw_monitor.Sensor()
        for sensor in sensors:
            if sensor.SensorType == "Temperature":
                temp_data.append((sensor.Name, sensor.Value))
    except:
        pass
    return temp_data

def get_active_network():
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    for iface, stat in stats.items():
        if stat.isup:
            lname = iface.lower()
            if lname.startswith("wi-fi") or lname.startswith("wlan"):
                ssid = get_wifi_ssid()
                return f"WiFi ({ssid}) - {iface}" if ssid else f"WiFi - {iface}"
            elif lname.startswith("ethernet"):
                return f"Ethernet - {iface}"
    return "Desconocida"

def get_wifi_ssid():
    """
    Obtiene el SSID de la red WiFi a la que está conectado (solo Windows).
    """
    try:
        if platform.system() == "Windows":
            output = subprocess.check_output("netsh wlan show interfaces", shell=True, text=True, encoding="utf-8")
            for line in output.splitlines():
                if "SSID" in line and "BSSID" not in line:
                    ssid = line.split(":", 1)[1].strip()
                    if ssid != "":
                        return ssid
    except Exception:
        pass
    return None

def run_prime95(duration=60):
    prime95_path = os.path.join(BASE_DIR, "prime95", "prime95.exe")
    if not os.path.exists(prime95_path):
        print(f"ERROR: No se encontró prime95.exe en {prime95_path}")
        return
    proc = subprocess.Popen([prime95_path, "-t"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print("Prime95 iniciado para estrés CPU")
    time.sleep(duration)
    proc.terminate()
    print("Prime95 detenido")

def benchmark_cpu(duration=60):
    global max_cpu_power_global

    t_cpu = threading.Thread(target=run_prime95, args=(duration,))
    t_cpu.start()

    max_cpu_load = 0
    max_power = 0

    start_time = time.time()
    while time.time() - start_time < duration:
        cpu = get_cpu_usage()
        gpu = get_gpu_usage() or 0  # Se usa para cálculo power pero sin benchmark GPU
        battery = get_battery_info() or {"status": "No Battery"}
        power = estimate_power(cpu, gpu, battery["status"])

        if cpu > max_cpu_load:
            max_cpu_load = cpu
        if power > max_power:
            max_power = power

        print(f"[Benchmark CPU] CPU: {cpu:.1f}%, Potencia estimada: {power:.2f} W")

    t_cpu.join()

    print(f"\nBenchmark CPU terminado. Máximos detectados:")
    print(f"CPU load max: {max_cpu_load:.1f}%")
    print(f"Potencia estimada max: {max_power:.2f} W")

    # Ajuste constante CPU
    max_cpu_power_global = max_power
    print(f"Constante ajustada max_cpu_power_global = {max_cpu_power_global:.2f} W")


def save_constants_and_summary(max_cpu_power, max_gpu_power, data_records):
    save_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(save_dir, exist_ok=True)

    with open(os.path.join(save_dir, "benchmark_constants.txt"), "w") as f:
        f.write(f"Timestamp: {datetime.now()}\n")
        f.write(f"max_cpu_power_global={max_cpu_power:.2f}\n")
        f.write(f"max_gpu_power_global={max_gpu_power:.2f}\n")

    df = pd.DataFrame(data_records)
    avg_power = df["power_estimated_watts"].mean()
    max_power = df["power_estimated_watts"].max()
    total_time = len(df) * 5  # intervalo en segundos

    with open(os.path.join(save_dir, "monitor_summary.txt"), "w") as f:
        f.write(f"Monitoreo desde: {df['timestamp'].iloc[0]}\n")
        f.write(f"Monitoreo hasta: {df['timestamp'].iloc[-1]}\n")
        f.write(f"Duración total (s): {total_time}\n")
        f.write(f"Potencia estimada promedio (W): {avg_power:.2f}\n")
        f.write(f"Potencia estimada máxima (W): {max_power:.2f}\n")
        f.write(f"Red activa (último registro): {df['network_connection'].iloc[-1]}\n")

def post_data_chunk(data_chunk):
    try:
        response = requests.post(API_URL, json=data_chunk)
        if response.status_code == 200:
            print(f"Chunk enviado correctamente: {len(data_chunk)} registros")
        else:
            print(f"Error al enviar chunk: {response.status_code}, {response.text}")
    except Exception as e:
        print(f"Error al enviar chunk: {e}")

def estimate_power(cpu_load, gpu_power_watts, battery_status):
    base_idle = 10
    battery_penalty = 5 if battery_status == "Cargando" else 0

    cpu_power = (cpu_load / 100) * max_cpu_power_global
    gpu_power = gpu_power_watts if gpu_power_watts is not None else ((get_gpu_usage() or 0) / 100) * max_gpu_power_global

    power = base_idle + cpu_power + gpu_power + battery_penalty
    power_corrected = power * 1.2  # Corrección empírica
    return power_corrected

def main_monitor(interval=5, total_duration=300, chunk_size=10):
    data_records = []
    print("Iniciando monitor continuo...")
    start_time = time.time()

    while time.time() - start_time < total_duration:
        battery = get_battery_info() or {"status": "No Battery", "charge": None, "run_time": None}
        cpu = get_cpu_usage()
        gpu_power = get_gpu_power_watts()  # usa el valor real de potencia GPU
        gpu_load = get_gpu_usage()  # opcional, si quieres mostrar uso

        temps = get_temperature()
        power = estimate_power(cpu, gpu_power, battery["status"])
        network = get_active_network()

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        record = {
            "timestamp": timestamp,
            "battery_status": battery["status"],
            "battery_charge": battery["charge"],
            "battery_run_time": battery["run_time"],
            "cpu_usage": cpu,
            "gpu_usage": gpu_load,
            "gpu_power_watts": gpu_power,
            "power_estimated_watts": power,
            "temperature_samples": temps[:3],
            "network_connection": network
        }
        data_records.append(record)

        print(f"[{timestamp}] Batería: {battery['status']} {battery['charge']}% | CPU: {cpu}% | GPU Load: {gpu_load if gpu_load is not None else 'N/A'}% | GPU Power: {gpu_power if gpu_power is not None else 'N/A'} W | Potencia corregida: {power:.2f} W | Red: {network}")

        if len(data_records) >= chunk_size:
            post_data_chunk(data_records)
            data_records = []

        time.sleep(interval)

    # Enviar cualquier dato restante
    if data_records:
        post_data_chunk(data_records)

    # Guardar localmente
    save_dir = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(save_dir, exist_ok=True)
    df = pd.DataFrame(data_records)
    df.to_csv(os.path.join(save_dir, "energy_monitoring_data.csv"), index=False)
    print(f"Datos guardados en {os.path.join(save_dir, 'energy_monitoring_data.csv')}")

    save_constants_and_summary(max_cpu_power_global, max_gpu_power_global, data_records)
    print("Resumen y constantes guardados.")
            
if __name__ == "__main__":
    benchmark_cpu(duration=30)  # Benchmark CPU
    main_monitor(interval=5, total_duration=100, chunk_size=10)  # Monitoreo y envío por chunks
