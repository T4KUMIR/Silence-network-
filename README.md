# Silence-network-
The function of Nexora silence  is that during the network attack we are undetectable obiously it will not only serve in network attack but in attack of all kinds, to camouflage ourselves and not leave traces during our attacks 

## 🚀 Features

- **Dynamic Identity Management**: Automatic rotation of MAC addresses (using locally administered prefixes) and hostnames to avoid correlation.
- **Intelligent Passive Scanning**: Fixed-channel scanning to avoid the detectable "channel hopping" pattern typical of `airodump-ng`.
- **Stealthy Handshake Capture**: Prioritizes PMKID attacks (clientless and passive) over traditional deauthentication.
- **Stealthy Fake AP**: Deploys Evil Twins on adjacent channels with reduced beacon frequency to avoid WIDS detection.
- **Counter-Surveillance**: Built-in detection for Blue Team monitoring tools (Kismet, Wireshark).
- **Integrated Cracking**: Direct interface with `hashcat` for PMKID and WPA handshakes.

## 🛠️ Requirements

This tool is designed for **Kali Linux**.

### System Dependencies
```bash
sudo apt update
sudo apt install aircrack-ng hcxdumptool hcxtools hashcat macchanger hostapd
```

### Python Requirements
- Python 3.8+

## 💻 Usage

1. Clone the repository:
   ```bash
   git clone https://github.com/[YOUR_USERNAME]/NEXORA-Stealth.git
   cd NEXORA-Stealth
   ```

2. Run the tool with root privileges:
   ```bash
   sudo python3 nexora_stealth.py
   ```

## ⚠️ Disclaimer

**FOR EDUCATIONAL PURPOSES ONLY.**
This tool is intended for use in authorized laboratory environments. Unauthorized access to wireless networks is illegal. The developers assume no liability for misuse of this software.

## 🎓 Project Details
- **Course**: Cybersecurity Engineering
- **Focus**: Offensive Security & Evasion Techniques
