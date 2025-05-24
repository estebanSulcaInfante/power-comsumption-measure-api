import time
import pandas as pd
from datetime import datetime
from HardwareMonitor.Hardware import IComputer, IHardware, IParameter, IVisitor, Computer
import psutil

class UpdateVisitor(IVisitor):
    __namespace__ = "TestHardwareMonitor"
    def VisitComputer(self, computer: IComputer):
        computer.Traverse(self)

    def VisitHardware(self, hardware: IHardware):
        hardware.Update()
        for sub in hardware.SubHardware:
            sub.Update()

    def VisitParameter(self, parameter: IParameter):
        pass

def extract_cpu_power_load(hardware_list):
    cpu_power = None
    cpu_load = None

    for hw in hardware_list:
        if hw.HardwareType == 0:  # CPU
            for sensor in hw.Sensors:
                name = sensor.Name.lower()
                if 'power' in name and cpu_power is None:
                    cpu_power = sensor.Value
                if ('load' in name or 'usage' in name) and cpu_load is None:
                    cpu_load = sensor.Value
    return cpu_power, cpu_load

def list_cpu_sensors(hardware_list):
    for hw in hardware_list:
        if hw.HardwareType == 0:  # CPU
            print(f"Hardware: {hw.Name}")
            for sensor in hw.Sensors:
                print(f"  Sensor: {sensor.Name}, Valor: {sensor.Value}")

def list_all_sensors(hardware_list):
    for hw in hardware_list:
        print(f"Hardware: {hw.Name}, Tipo: {hw.HardwareType}")
        for sensor in hw.Sensors:
            print(f"  Sensor: {sensor.Name}, Valor: {sensor.Value}")
        for sub in hw.SubHardware:
            print(f" Subhardware: {sub.Name}")
            for sensor in sub.Sensors:
                print(f"    Sensor: {sensor.Name}, Valor: {sensor.Value}")

def extract_cpu_temp(hardware_list):
    temps = []
    for hw in hardware_list:
        if hw.HardwareType == 0:  # CPU
            for sensor in hw.Sensors:
                if 'temp' in sensor.Name.lower() or 'temperature' in sensor.Name.lower():
                    temps.append(sensor.Value)
    return temps

def main():
    computer = Computer()
    computer.IsCpuEnabled = True
    computer.Open()

    data_records = []
    duration = 60  # segundos
    interval = 5   # segundos
    iterations = duration // interval

    computer.Accept(UpdateVisitor())
    list_cpu_sensors(computer.Hardware)
    
    computer.Accept(UpdateVisitor())
    list_all_sensors(computer.Hardware)
    
    cpu_load = psutil.cpu_percent(interval=1)  # carga %
    cpu_temps = extract_cpu_temp(computer.Hardware)  # lista temperaturas

    print(f"CPU Load: {cpu_load}% | CPU Temps: {cpu_temps}")
    
    
    for _ in range(iterations):
        computer.Accept(UpdateVisitor())
        cpu_power, cpu_load = extract_cpu_power_load(computer.Hardware)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        print(f"[{timestamp}] CPU Power: {cpu_power} W | CPU Load: {cpu_load} %")

        data_records.append({
            "timestamp": timestamp,
            "cpu_power_watts": cpu_power,
            "cpu_load_percent": cpu_load
        })

        time.sleep(interval)

    computer.Close()

    df = pd.DataFrame(data_records)
    df.to_csv("cpu_power_monitor.csv", index=False)
    print("Datos guardados en cpu_power_monitor.csv")

if __name__ == "__main__":
    main()
