#!/usr/bin/env python3
"""
Bilan de santé instantané de l'infrastructure JerseyAlert ASSE sur le VPS.
Usage : python3 healthcheck.py
"""

import subprocess
import json
import re
import sys

VPS_HOST = "root@151.115.67.153"

def run_ssh(cmd, timeout=8):
    try:
        res = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", VPS_HOST, cmd],
            capture_output=True, text=True, timeout=timeout
        )
        return res.stdout.strip(), res.returncode
    except Exception as e:
        return f"Erreur SSH: {e}", 1

def main():
    print("\n==================================================")
    print("🩺 BILAN DE SANTÉ VPS - JERSEYALERT ASSE")
    print("==================================================")

    # 1. État des services systemd
    services = ["vinted-bot", "vinted-tracker", "vinted-dashboard"]
    cmd_services = "systemctl is-active " + " ".join(services)
    out_services, code = run_ssh(cmd_services)

    if code != 0 and "Erreur SSH" in out_services:
        print(f"❌ Impossible de joindre le serveur VPS ({VPS_HOST})")
        print(f"Détail: {out_services}\n")
        sys.exit(1)

    statuses = out_services.splitlines() if out_services else []
    print("📦 Services Systemd :")
    for s_name, s_stat in zip(services, statuses):
        if s_stat == "active":
            print(f"   🟢 {s_name:<20} : ACTIF (Running)")
        else:
            print(f"   🔴 {s_name:<20} : INACTIF ({s_stat})")

    # 2. Données Système & Dashboard API
    api_cmd = "curl -s -u admin:asse2026 http://127.0.0.1/api/status && echo '---' && curl -s -u admin:asse2026 http://127.0.0.1/api/errors"
    api_out, _ = run_ssh(api_cmd)
    
    parts = api_out.split("---")
    status_json = {}
    errors_json = {}

    if len(parts) >= 2:
        try:
            status_json = json.loads(parts[0].strip())
        except Exception:
            pass
        try:
            errors_json = json.loads(parts[1].strip())
        except Exception:
            pass

    print("\n💻 Ressources VPS :")
    if status_json:
        ram = f"{status_json.get('ram_used', '?')} / {status_json.get('ram_total', '?')}"
        swap = f"{status_json.get('swap_used', '?')} / {status_json.get('swap_total', '?')}"
        uptime = status_json.get('uptime', 'N/A')
        print(f"   🧠 RAM Utilisée      : {ram}")
        print(f"   💾 Swap Utilisé     : {swap}")
        print(f"   ⏱️  Load Average     : {uptime}")
    else:
        print("   ⚠️ Impossible d'interroger les métriques système via le Dashboard")

    print("\n🛡️  Historique des Erreurs :")
    err_count = errors_json.get("count", 0)
    if err_count == 0:
        print("   🟢 0 erreur enregistrée (Tout est propre)")
    else:
        print(f"   ⚠️ {err_count} erreur(s) détectée(s) :")
        raw_errs = errors_json.get("errors", "")
        for line in raw_errs.splitlines()[-3:]:
            if line.strip():
                print(f"      • {line}")

    # 3. Activité récente (Derniers scans)
    last_scans_cmd = "journalctl -u vinted-bot.service -n 20 --no-pager | grep -E '(Scan Flux Direct Foot|Scan Filet|Match|Démarrage)' | tail -n 4"
    scans_out, _ = run_ssh(last_scans_cmd)

    print("\n⚡ Activité Récente du Bot (Derniers Scans) :")
    if scans_out:
        for l in scans_out.splitlines():
            # Simplifier la ligne pour lisibilité
            clean_l = re.sub(r'^[A-Z][a-z]{2}\s+\d+\s+[\d:]+\s+\S+\s+python3\[\d+\]:\s*', '', l)
            print(f"   📡 {clean_l}")
    else:
        print("   ⚠️ Aucun log récent disponible")

    print("==================================================\n")

if __name__ == "__main__":
    main()
