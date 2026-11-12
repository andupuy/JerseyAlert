#!/usr/bin/env python3
"""
Exporte un rapport d'activité du VPS (matches, scans, alertes, ventes, erreurs, LeBonCoin & Shield)
vers un fichier JSON exploitable par GitHub Actions et l'assistant.
"""
import subprocess
import json
import os
import re
import time
from datetime import datetime, timezone

def generate_report():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tracked_file = os.path.join(base_dir, "tracked_items.json")
    if not os.path.exists(tracked_file):
        tracked_file = "/root/JerseyAlert/tracked_items.json"
    
    # 1. Lecture de tracked_items.json
    tracked_items = {}
    if os.path.exists(tracked_file):
        try:
            with open(tracked_file, "r", encoding="utf-8") as f:
                tracked_items = json.load(f)
        except Exception as e:
            print(f"Erreur lecture tracked_items: {e}")

    now_ts = time.time()
    ts_24h_ago = now_ts - (24 * 3600)

    # Analyse des ventes sur 24h
    sold_items_24h = []
    if isinstance(tracked_items, dict):
        for it in tracked_items.values():
            sold_at = it.get("sold_at")
            status = it.get("status")
            sub_status = it.get("sub_status")
            if (status == "SOLD" or sub_status == "SOLD") or (sold_at and sold_at >= ts_24h_ago):
                if not sold_at or sold_at >= ts_24h_ago:
                    sold_items_24h.append(it)
        sold_items_24h.sort(key=lambda x: x.get("sold_at") or 0, reverse=True)

    # 2. Lecture des logs journalctl des dernières 24h (Vinted)
    matches = []
    scan_count_flux = 0
    scan_count_filet = 0
    bot_restarts = 0
    errors = []

    try:
        res = subprocess.run(
            ["journalctl", "-u", "vinted-bot.service", "--since", "24 hours ago", "--no-pager"],
            capture_output=True, text=True, timeout=15
        )
        for line in res.stdout.splitlines():
            clean = line.strip()
            if "🎯 MATCH" in clean:
                matches.append(clean)
            elif "Scan Flux Direct Foot" in clean:
                scan_count_flux += 1
            elif "Scan Filet" in clean:
                scan_count_filet += 1
            elif "Démarrage du bot Vinted" in clean or "=== RELANCE DU BOT ===" in clean:
                bot_restarts += 1
            elif "🚨" in clean or "❌" in clean:
                errors.append(clean)
    except Exception as e:
        print(f"Erreur journalctl vinted: {e}")

    # 3. Diagnostic Services, LeBonCoin & Proxy Shield
    services = ["vinted-bot", "leboncoin-bot", "ebay-bot", "vfa-bot", "vinted-tracker", "vinted-dashboard"]
    svc_status = {}
    try:
        s_res = subprocess.run(["systemctl", "is-active"] + services, capture_output=True, text=True, timeout=5)
        svc_status = dict(zip(services, s_res.stdout.strip().splitlines()))
    except Exception:
        pass

    lbc_logs = []
    try:
        lbc_res = subprocess.run(
            ["journalctl", "-u", "leboncoin-bot.service", "-n", "40", "--no-pager"],
            capture_output=True, text=True, timeout=10
        )
        lbc_logs = [l.strip() for l in lbc_res.stdout.splitlines() if l.strip()]
    except Exception as e:
        lbc_logs = [f"Erreur lecture journalctl leboncoin-bot: {e}"]

    tailscale_info = {}
    try:
        ts_res = subprocess.run(["tailscale", "status", "--json"], capture_output=True, text=True, timeout=5)
        if ts_res.returncode == 0:
            ts_data = json.loads(ts_res.stdout)
            peers = ts_data.get("Peer", {})
            for p in peers.values():
                hname = p.get("HostName", "")
                tailscale_info[hname] = {
                    "online": p.get("Online", False),
                    "ips": p.get("TailscaleIPs", []),
                    "last_seen": p.get("LastSeen", ""),
                    "cur_addr": p.get("CurAddr", ""),
                    "relay": p.get("Relay", "")
                }
    except Exception as e:
        tailscale_info = {"error": str(e)}

    # Test du port SOCKS5 local (1055) et test IP publique sortante + test LeBonCoin direct
    socks_test = {}
    try:
        ss_res = subprocess.run(["ss", "-tlnp"], capture_output=True, text=True, timeout=5)
        socks_test["listening_ports"] = [l for l in ss_res.stdout.splitlines() if "1055" in l or "ssh" in l or "tailscale" in l]
    except Exception:
        pass

    try:
        ip_res = subprocess.run(
            ["curl", "-s", "--max-time", "8", "-x", "socks5h://127.0.0.1:1055", "https://api.ipify.org?format=json"],
            capture_output=True, text=True, timeout=10
        )
        socks_test["proxy_exit_ip"] = ip_res.stdout.strip() or f"Error (rc={ip_res.returncode}): {ip_res.stderr.strip()}"
    except Exception as e:
        socks_test["proxy_exit_ip"] = f"Exception: {e}"

    # 4. Métriques système
    ram_info = {}
    try:
        free_res = subprocess.run(["free", "-m"], capture_output=True, text=True, timeout=5)
        for l in free_res.stdout.splitlines():
            if "Mem:" in l:
                p = l.split()
                ram_info = {"total_mb": p[1], "used_mb": p[2], "free_mb": p[3]}
    except Exception:
        pass

    recent_tracked = []
    if isinstance(tracked_items, dict):
        items_list = list(tracked_items.values())
        items_list.sort(key=lambda x: str(x.get("created_at") or x.get("timestamp") or ""), reverse=True)
        recent_tracked = items_list[:30]

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bot_status": "active",
        "services": svc_status,
        "tailscale": tailscale_info,
        "socks_proxy": socks_test,
        "leboncoin_recent_logs": lbc_logs,
        "system": {
            "ram": ram_info,
        },
        "stats_24h": {
            "matches_count": len(matches),
            "sales_24h_count": len(sold_items_24h),
            "scan_flux_count": scan_count_flux,
            "scan_filet_count": scan_count_filet,
            "bot_restarts_count": bot_restarts,
            "errors_count": len(errors),
            "tracked_total": len(tracked_items)
        },
        "sales_24h_items": sold_items_24h,
        "matches_24h": matches[-30:],
        "recent_tracked_items": recent_tracked,
        "recent_errors": errors[-10:]
    }

    output_path = os.environ.get("REPORT_OUTPUT_PATH", "/tmp/vps_activity_report.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"✅ Rapport généré avec succès dans {output_path}")

if __name__ == "__main__":
    generate_report()
