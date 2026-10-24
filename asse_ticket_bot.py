#!/usr/bin/env python3
"""
ASSE Billetterie Sniper - Surveillance ASSE vs Nantes
- Surveillance ultra-rapide de la billetterie officielle ASSE (curl_cffi)
- Détection instantanée dès qu'une place se libère ou qu'un réassort est injecté
- Alertes instantanées dans le salon Discord 'Places' avec mention @everyone
- Optimisé pour Garmin Watch & iPhone
"""

import os
import sys
import time
import random
import re
from datetime import datetime, timezone
try:
    from curl_cffi import requests
    USE_CURL_CFFI = True
except ImportError:
    import requests
    USE_CURL_CFFI = False
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DISCORD_TICKETING_WEBHOOK_URL = os.environ.get(
    "DISCORD_TICKETING_WEBHOOK_URL",
    "https://discord.com/api/webhooks/1473436352942182463/Rg1DSUAVNVbFBBKS83ixDYu2xmOSBY7W1D9Y-HweIBTj1uWDrRCQ4wc5i1fKFCcV5iiM"
)

CATALOGUE_URL = "https://billetterie.asse.fr/fr/catalogue/match-asse-vs-nantes"
MATCH_URL = "https://billetterie.asse.fr/fr/asse-vs-nantes"
SECOND_MARKET_URL = "https://billetterie.asse.fr/fr/second/match-asse-vs-nantes/#bk2a5d846a-zone"

CHECK_INTERVAL_MIN = 10
CHECK_INTERVAL_MAX = 15

# Indicateurs stricts de fermeture / indisponibilité
CLOSED_SIGNALS = [
    "la vente n'est pas ouverte pour cette séance",
    "la vente n’est pas ouverte pour cette séance",
    "vente non ouverte",
    "séance fermée"
]

def log(msg):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] [Ticketing] {msg}", flush=True)

def send_ticketing_alert(details=""):
    if not DISCORD_TICKETING_WEBHOOK_URL:
        log("⚠️ Aucun DISCORD_TICKETING_WEBHOOK_URL configuré !")
        return

    desc_lines = [
        "🏟️ **Stade Geoffroy-Guichard — ASSE vs NANTES**",
        "⚡ **Une ou plusieurs places viennent d'apparaître sur la billetterie officielle !**",
    ]
    if details:
        desc_lines.append(f"\n📋 **Détails détectés :** {details}")

    desc_lines.extend([
        "\n🔗 **Liens d'accès direct pour réserver :**",
        f"👉 [Billetterie Catalogue ASSE]({CATALOGUE_URL})",
        f"👉 [Bourse d'Échange Second Marché]({SECOND_MARKET_URL})"
    ])

    embed = {
        "title": "🚨 PLACES DISPONIBLES : ASSE vs NANTES !",
        "url": CATALOGUE_URL,
        "description": "\n".join(desc_lines),
        "color": 0x00FF00,  # Vert Alerte Vif
        "image": {
            "url": "https://billetterie.asse.fr/media/asse-vs-nantes.png"
        },
        "footer": {"text": "ASSE Ticket Sniper • Geoffroy-Guichard"},
        "timestamp": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    }

    payload = {
        "content": "@everyone 🚨 **DES PLACES SONT DISPONIBLES POUR ASSE vs NANTES !** Foncez : " + CATALOGUE_URL,
        "username": "ASSE Billetterie Sniper",
        "avatar_url": "https://billetterie.asse.fr/build/asse-ticketing/img/meta/favicon.ea95ccea.ico",
        "embeds": [embed]
    }

    try:
        r = requests.post(DISCORD_TICKETING_WEBHOOK_URL, json=payload, timeout=8)
        if r.status_code in (200, 204):
            log("🚨 ALERTE DISCORD ENVOYÉE DANS LE SALON 'PLACES' !")
        else:
            log(f"⚠️ Erreur Discord (HTTP {r.status_code}) : {r.text[:200]}")
    except Exception as e:
        log(f"❌ Erreur envoi webhook Discord: {e}")

def check_catalogue_availability(session, headers):
    """Vérifie si des places / offres sont ouvertes sur la page catalogue"""
    try:
        kwargs = {"headers": headers, "timeout": 12}
        if USE_CURL_CFFI:
            kwargs["impersonate"] = "chrome124"
        r = session.get(CATALOGUE_URL, **kwargs)
        if r.status_code != 200:
            log(f"⚠️ Réponse catalogue HTTP {r.status_code}")
            return False, ""

        text_lower = r.text.lower()

        # 1. Si le message de fermeture explicite est toujours là -> 0 place
        is_closed = any(sig in text_lower for sig in CLOSED_SIGNALS)
        if is_closed:
            return False, "Vente non ouverte"

        # 2. Si le message de fermeture a disparu, vérifions la présence d'offres ou de boutons réserver
        found_signals = []
        if "réserver" in text_lower or "reserver" in text_lower:
            found_signals.append("Bouton Réserver actif")
        if "offres ouvertes" in text_lower or "offre ouverte" in text_lower:
            found_signals.append("Offres ouvertes")
        if "place à l'unité" in text_lower or "place a l'unite" in text_lower:
            found_signals.append("Places à l'unité")
        if "choisir mes places" in text_lower:
            found_signals.append("Choix des places disponible")

        # Extraction des noms de tribunes si mentionnées
        for tribune in ["kop nord", "kop sud", "henri point", "pierre faurand", "jean snella"]:
            if tribune in text_lower:
                found_signals.append(f"Tribune {tribune.title()}")

        details_str = ", ".join(found_signals) if found_signals else "Statut vente ouvert"
        return True, details_str

    except Exception as e:
        log(f"⚠️ Erreur vérification catalogue: {e}")
        return False, ""

def run_bot():
    log("🚀 Démarrage du Sniper Billetterie ASSE vs Nantes")
    log(f"🎯 Surveillance : {CATALOGUE_URL}")

    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    already_alerted = False
    cycle_count = 0

    while True:
        cycle_count += 1
        try:
            available, details = check_catalogue_availability(session, headers)

            if available:
                if not already_alerted:
                    log(f"🎯 PLACES DÉTECTÉES ! ({details})")
                    send_ticketing_alert(details)
                    already_alerted = True
                else:
                    log(f"⚡ Places toujours ouvertes ({details}), en attente...")
            else:
                if already_alerted:
                    log("ℹ️ Les places sont de nouveau épuisées / fermées. Réarmement du sniper.")
                    already_alerted = False

            if cycle_count % 30 == 1:
                log(f"💓 Heartbeat #{cycle_count} : Billetterie surveillée, 0 place actuellement.")

        except Exception as e:
            log(f"🚨 Erreur cycle billetterie: {e}")

        # Pause courte entre 10 et 15 secondes
        sleep_sec = random.uniform(CHECK_INTERVAL_MIN, CHECK_INTERVAL_MAX)
        time.sleep(sleep_sec)

if __name__ == "__main__":
    run_bot()
