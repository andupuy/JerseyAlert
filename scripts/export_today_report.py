#!/usr/bin/env python3
"""
Exporte un rapport d'activité du VPS (matches, scans, alertes, erreurs)
vers un fichier JSON exploitable par GitHub Actions et l'assistant.
"""
import subprocess
import json
import os
import re
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

    # 2. Lecture des logs journalctl des dernières 24h
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
        print(f"Erreur journalctl: {e}")

    # 3. Métriques système
    ram_info = {}
    try:
        free_res = subprocess.run(["free", "-m"], capture_output=True, text=True, timeout=5)
        for l in free_res.stdout.splitlines():
            if "Mem:" in l:
                p = l.split()
                ram_info = {"total_mb": p[1], "used_mb": p[2], "free_mb": p[3]}
    except Exception:
        pass

    # Trier et formater les articles suivis (les plus récents en premier)
    recent_tracked = []
    if isinstance(tracked_items, dict):
        items_list = list(tracked_items.values())
        # Tri si created_at présent
        items_list.sort(key=lambda x: str(x.get("created_at") or x.get("timestamp") or ""), reverse=True)
        recent_tracked = items_list[:25]

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "bot_status": "active",
        "system": {
            "ram": ram_info,
        },
        "stats_24h": {
            "matches_count": len(matches),
            "scan_flux_count": scan_count_flux,
            "scan_filet_count": scan_count_filet,
            "bot_restarts_count": bot_restarts,
            "errors_count": len(errors),
            "tracked_total": len(tracked_items)
        },
        "matches_24h": matches[-30:],
        "recent_tracked_items": recent_tracked,
        "recent_errors": errors[-10:]
    }

    output_path = os.environ.get("REPORT_OUTPUT_PATH", "/tmp/vps_activity_report.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"✅ Rapport généré avec succès dans {output_path} ({len(matches)} matches, {len(tracked_items)} articles suivis)")

if __name__ == "__main__":
    generate_report()
