# Nexora Silence

**Nexora Silence** es una herramienta académica desarrollada para estudiantes de
Ingeniería en Ciberseguridad que practican ejercicios Red Team vs Blue Team en
entornos controlados. A diferencia de las herramientas tradicionales de pentesting
WiFi, Nexora Silence se enfoca en **evasión y sigilo**, minimizando la huella
detectable del atacante.

> ⚠️ **Solo para uso educativo en laboratorios autorizados.**
> El acceso no autorizado a redes inalámbricas es ilegal.

---

## Características

- **Gestión dinámica de identidad**: rotación automática de MAC (con prefijo
  localmente administrado `02:...`) y de hostname para evitar correlación de tráfico.
- **Escaneo pasivo inteligente**: escaneo en canal fijo para evitar el patrón
  detectable de *channel hopping* típico de `airodump-ng`.
- **Captura sigilosa de handshake**: prioriza ataques **PMKID** (sin clientes,
  pasivos) sobre la desautenticación tradicional.
- **Fake AP sigiloso**: despliega Evil Twins en canales adyacentes con frecuencia
  de beacon reducida para dificultar la detección por WIDS.
- **Contra-vigilancia**: detección de interfaces en modo monitor y de procesos
  de monitoreo (Kismet, Wireshark, tshark) en el sistema.
- **Cracking integrado**: interfaz directa con `hashcat` para PMKID (modo 16800)
  y handshakes WPA (modo 22000).

---

## Requisitos

### Sistema operativo

Diseñado y probado para **Kali Linux**. Debería funcionar también en Debian y
derivados (Ubuntu, Parrot, Raspbian) siempre que `apt-get` esté disponible.

### Dependencias del sistema

Las siguientes herramientas deben estar instaladas:

| Paquete        | Proporciona                                             |
|----------------|---------------------------------------------------------|
| `aircrack-ng`  | `airmon-ng`, `airodump-ng`, `aireplay-ng`               |
| `hcxdumptool`  | Captura de PMKID y handshakes                          |
| `hcxtools`     | `hcxpcapngtool` / `hcxpcaptool` (conversión a hashcat) |
| `hashcat`      | Cracking de hashes WPA/PMKID                           |
| `macchanger`   | Rotación de direcciones MAC                            |
| `hostapd`      | Despliegue del Fake AP                                 |
| `iw`           | Configuración de interfaces WiFi                       |
| `iproute2`     | Comando `ip`                                           |
| `procps`       | Comando `pgrep` (usado por la contra-vigilancia)       |

**Instalación manual:**

```bash
sudo apt update
sudo apt install aircrack-ng hcxdumptool hcxtools hashcat \
                 macchanger hostapd iw iproute2 procps