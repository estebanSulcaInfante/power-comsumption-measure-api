import subprocess
import time
import psutil
import os

try:
    from py3nvml import py3nvml
    py3nvml.nvmlInit()
    gpu_available = True
except Exception:
    gpu_available = False

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "benchmarks"))

max_cpu_power_global = 30
max_gpu_power_global = 40

def estimate_power(cpu_load, gpu_load):
    base_idle = 10
    cpu_power = (cpu_load / 100) * max_cpu_power_global
    gpu_power = ((gpu_load or 0) / 100) * max_gpu_power_global
    return base_idle + cpu_power + gpu_power

def get_gpu_load():
    if not gpu_available:
        return 0
    handle = py3nvml.nvmlDeviceGetHandleByIndex(0)
    util = py3nvml.nvmlDeviceGetUtilizationRates(handle)
    return util.gpu

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

def get_discrete_gpu_index():
    """
    Retorna el índice de la GPU discreta NVIDIA.
    Asumimos que la discreta tiene la mayor memoria dedicada.
    """
    if not gpu_available:
        return None
    device_count = py3nvml.nvmlDeviceGetCount()
    max_mem = 0
    discrete_gpu_index = 0
    for i in range(device_count):
        handle = py3nvml.nvmlDeviceGetHandleByIndex(i)
        mem_info = py3nvml.nvmlDeviceGetMemoryInfo(handle)
        if mem_info.total > max_mem:
            max_mem = mem_info.total
            discrete_gpu_index = i
    return discrete_gpu_index

def get_gpu_load(discrete_gpu_index=None):
    if not gpu_available:
        return 0
    if discrete_gpu_index is None:
        discrete_gpu_index = 0
    try:
        handle = py3nvml.nvmlDeviceGetHandleByIndex(discrete_gpu_index)
        util = py3nvml.nvmlDeviceGetUtilizationRates(handle)
        return util.gpu
    except Exception as e:
        print(f"Error obteniendo carga GPU: {e}")
        return 0

def get_furmark_gpuinfo():
    furmark_path = os.path.join(BASE_DIR, "furmark.exe")
    if not os.path.exists(furmark_path):
        print(f"ERROR: No se encontró furmark.exe en {furmark_path}")
        return None
    result = subprocess.run([furmark_path, "--gpuinfo"], capture_output=True, text=True)
    return result.stdout




def run_furmark(duration=60):
    furmark_path = os.path.join(BASE_DIR, "furmark", "furmark.exe")
    if not os.path.exists(furmark_path):
        print(f"ERROR: No se encontró furmark.exe en {furmark_path}")
        return
    args = [
        furmark_path,
        "--nogui",
        "--no-score-box",
        "--no-gpumon",
        "--hpgfx", "1"  # Forzar uso GPU dedicada en laptops híbridas
    ]
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print("FurMark iniciado para estrés GPU")
    time.sleep(duration)
    proc.terminate()
    print("FurMark detenido")


def benchmark_combined(duration=60):
    import threading

    discrete_gpu_index = get_discrete_gpu_index()
    if discrete_gpu_index is None:
        print("No se detectó GPU discreta NVIDIA, usando índice 0 por defecto")
        discrete_gpu_index = 0

    t_cpu = threading.Thread(target=run_prime95, args=(duration,))
    t_gpu = threading.Thread(target=run_furmark, args=(duration,))

    t_cpu.start()
    t_gpu.start()

    max_cpu_load = 0
    max_gpu_load = 0
    max_power = 0

    start_time = time.time()
    while time.time() - start_time < duration:
        cpu_load = psutil.cpu_percent(interval=1)
        gpu_load = get_gpu_load(discrete_gpu_index)

        power = estimate_power(cpu_load, gpu_load)

        if cpu_load > max_cpu_load:
            max_cpu_load = cpu_load
        if gpu_load > max_gpu_load:
            max_gpu_load = gpu_load
        if power > max_power:
            max_power = power

        print(f"[Benchmark] CPU: {cpu_load:.1f}%, GPU: {gpu_load:.1f}%, Potencia estimada: {power:.2f} W")

    t_cpu.join()
    t_gpu.join()

    print("\n===== Resultados del Benchmark =====")
    print(f"Máximo uso CPU: {max_cpu_load:.2f}%")
    print(f"Máximo uso GPU: {max_gpu_load:.2f}%")
    print(f"Máxima potencia estimada: {max_power:.2f} W")
    print("====================================")

if __name__ == "__main__":
    get_furmark_gpuinfo()
   # benchmark_combined(duration=60)
