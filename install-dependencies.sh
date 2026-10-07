#!/usr/bin/env bash
#
# Nexora Silence - Instalador de dependencias del sistema
# Proyecto académico - Ingeniería en Ciberseguridad
#
# Uso:
#   sudo bash install-dependencies.sh
#
# Probado en Kali Linux y Debian. Requiere apt-get.
#
set -euo pipefail

# === CONFIGURACIÓN ===
# Paquetes necesarios para Nexora Silence.
#   aircrack-ng  → airmon-ng, airodump-ng, aireplay-ng
#   hcxdumptool  → captura PMKID / handshakes
#   hcxtools     → hcxpcapngtool / hcxpcaptool (conversión a formato hashcat)
#   hashcat      → cracking de PMKID (16800) y WPA (22000)
#   macchanger   → rotación de MAC
#   hostapd      → Fake AP
#   iw           → gestión de interfaces WiFi
#   iproute2     → comando `ip` (suele venir preinstalado, pero por si acaso)
#   procps       → comando `pgrep` (usado por el módulo de contra-vigilancia)
packages=(
    aircrack-ng
    hcxdumptool
    hcxtools
    hashcat
    macchanger
    hostapd
    iw
    iproute2
    procps
)

# === COLORES (solo si la terminal los soporta) ===
if [[ -t 1 ]]; then
    C_RESET=$'\033[0m'
    C_BOLD=$'\033[1m'
    C_RED=$'\033[91m'
    C_GREEN=$'\033[92m'
    C_YELLOW=$'\033[93m'
    C_CYAN=$'\033[96m'
else
    C_RESET="" C_BOLD="" C_RED="" C_GREEN="" C_YELLOW="" C_CYAN=""
fi

info()    { printf '%s[*]%s %s\n' "$C_CYAN"   "$C_RESET" "$*"; }
ok()      { printf '%s[+]%s %s\n' "$C_GREEN"  "$C_RESET" "$*"; }
warn()    { printf '%s[!]%s %s\n' "$C_YELLOW" "$C_RESET" "$*" >&2; }
error()   { printf '%s[-]%s %s\n' "$C_RED"    "$C_RESET" "$*" >&2; }

# === VERIFICACIONES INICIALES ===
if [[ "${EUID}" -ne 0 ]]; then
    error "Ejecuta este instalador como root: sudo bash install-dependencies.sh"
    exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
    error "Este instalador requiere apt-get (Kali Linux o Debian)."
    exit 1
fi

# Detectar si estamos en un sistema basado en Debian
if [[ ! -r /etc/os-release ]]; then
    warn "No se pudo leer /etc/os-release; continuando bajo tu responsabilidad."
else
    # shellcheck disable=SC1091
    . /etc/os-release
    case "${ID:-}" in
        debian|kali|ubuntu|parrot|raspbian)
            info "Sistema detectado: ${PRETTY_NAME:-$ID}"
            ;;
        *)
            warn "Distribución no reconocida (${PRETTY_NAME:-$ID})."
            warn "Este script asume paquetes apt-get compatibles con Debian/Kali."
            ;;
    esac
fi

# === SELECCIÓN DE PAQUETES A INSTALAR ===
# Evitamos reinstalar lo que ya está presente.
declare -a to_install=()
declare -a already=()

for pkg in "${packages[@]}"; do
    # dpkg-query es más fiable que apt-cache para "¿está instalado?"
    if dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null \
         | grep -q "install ok installed"; then
        already+=("$pkg")
    else
        to_install+=("$pkg")
    fi
done

if [[ ${#already[@]} -gt 0 ]]; then
    info "Ya instalados (se omiten): ${already[*]}"
fi

if [[ ${#to_install[@]} -eq 0 ]]; then
    ok "Todas las dependencias ya están instaladas. Nada que hacer."
    exit 0
fi

# === CONFIRMACIÓN DEL USUARIO ===
printf '\n%sSe instalarán estos paquetes:%s\n' "$C_BOLD" "$C_RESET"
printf '    %s\n' "${to_install[@]}"
printf '\n'
read -r -p "¿Continuar? [y/N] " answer
if [[ ! "$answer" =~ ^([yY]|[yY][eE][sS])$ ]]; then
    info "Instalación cancelada."
    exit 0
fi

# === ACTUALIZAR ÍNDICES ===
info "Actualizando índices de apt..."
if ! apt-get update; then
    error "apt-get update falló. Revisa tu conexión y /etc/apt/sources.list."
    exit 1
fi

# === INSTALAR ===
info "Instalando paquetes..."
if ! DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        "${to_install[@]}"; then
    error "La instalación falló. Revisa los mensajes anteriores de apt."
    exit 1
fi

# === VERIFICACIÓN POST-INSTALACIÓN ===
# Binarios que Nexora Silence invoca realmente.
bins=(
    airmon-ng
    airodump-ng
    aireplay-ng
    hcxdumptool
    hashcat
    macchanger
    hostapd
    iw
    ip
    pgrep
)

# Al menos uno de los dos conversores de hcxtools debe existir.
converters=(hcxpcapngtool hcxpcaptool)

missing=()
for b in "${bins[@]}"; do
    if ! command -v "$b" >/dev/null 2>&1; then
        missing+=("$b")
    fi
done

has_converter=0
for c in "${converters[@]}"; do
    if command -v "$c" >/dev/null 2>&1; then
        has_converter=1
        break
    fi
done

if [[ ${#missing[@]} -gt 0 ]] || [[ $has_converter -eq 0 ]]; then
    warn "Algunos binarios esperados no están disponibles en PATH:"
    for m in "${missing[@]}"; do
        printf '    - %s\n' "$m" >&2
    done
    if [[ $has_converter -eq 0 ]]; then
        printf '    - hcxpcapngtool (o hcxpcaptool)\n' >&2
    fi
    warn "Verifica que /usr/sbin y /sbin estén en tu \$PATH."
    exit 2
fi

ok "Dependencias instaladas y verificadas correctamente."
printf '\nSiguiente paso:\n'
printf '    sudo python3 nexora-silence.py\n\n'