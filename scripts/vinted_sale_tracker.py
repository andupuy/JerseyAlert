#!/usr/bin/env python3
"""
Vinted Sale Velocity Tracker (Cycle de vie par article - Moteur HTTP Ultra-Léger)
- Consomme ~12 Mo de RAM (0 navigateur Chromium permanent en mémoire).
- Priorité CPU basse (os.nice(15)) pour laisser 100% du processeur au sniper Vinted principal.
- Suit le statut de vente et la popularité (favoris ❤️) de chaque article alerté jusqu'à 7 jours :
    * 0h à 1h  : toutes les 10 min
    * 1h à 6h  : toutes les 30 min
    * 6h à 24h : toutes les 2h
    * 24h à 7j : 1 fois par jour
    * > 7j     : statut EXPIRED (fin de suivi, 100% de l'historique conservé)
- Met à jour silencieusement le message Discord d'origine via PATCH webhook (0 notification) :
    * 🔴 VENDU [en {durée}] (Embed Rouge #ED4245) + compteur final de favoris ❤️
    * 🟠 RÉSERVÉ (Embed Orange #FAA61A) + retour automatique au Vert si remis en vente
    * ⚫ SUPPRIMÉ / RETIRÉ (Embed Gris #747F8D)
    * ❤️ Mise à jour du compteur de favoris dans le footer et la description dès qu'il évolue
"""

import os
import re
import sys
import time
import json
import fcntl
import requests
from datetime import datetime, timezone
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = os.environ.get(
    "JERSEY_ALERT_DIR",
    "/root/JerseyAlert" if os.path.exists("/root/JerseyAlert") else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
TRACKED_ITEMS_FILE = os.path.join(BASE_DIR, "tracked_items.json")
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9",
}

def log(msg):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{ts}] {msg}", flush=True)

def format_duration(seconds):
    """Formate une durée en secondes en texte lisible (ex: '14 min', '2h15', '2j 4h')"""
    seconds = max(0, int(seconds))
    if seconds < 3600:
        mins = max(1, seconds // 60)
        return f"{mins} min"
    elif seconds < 86400:
        hours = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hours}h{mins:02d}"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        if hours > 0:
            return f"{days}j {hours}h"
        return f"{days}j"

def parse_price_num(price_str):
    """Extrait la valeur numérique d'un prix (ex: '80.00 €' -> 80.0)"""
    if not price_str:
        return None
    m = re.search(r"(\d+(?:[\.,]\d+)?)", str(price_str))
    if m:
        try:
            return float(m.group(1).replace(",", "."))
        except ValueError:
            return None
    return None

def get_next_interval(age_seconds):
    """Calcule l'intervalle dégressif en secondes selon l'âge de l'article"""
    if age_seconds < 360:
        return 420       # Après le 1er pointage rapide à t+3 min -> prochain à t+10 min (+7 min)
    elif age_seconds < 3600:
        return 600       # 0h à 1h : toutes les 10 minutes
    elif age_seconds < 21600:
        return 1800      # 1h à 6h : toutes les 30 minutes
    elif age_seconds < 86400:
        return 7200      # 6h à 24h : toutes les 2 heures
    elif age_seconds < 7 * 86400:
        return 86400     # 24h à 7 jours : 24 heures (1x / jour)
    else:
        return None      # > 7 jours : Expiré

def load_tracked_items():
    """Charge le dictionnaire des articles suivis avec verrou partagé"""
    if not os.path.exists(TRACKED_ITEMS_FILE):
        return {}
    lock_file = TRACKED_ITEMS_FILE + ".lock"
    try:
        with open(lock_file, "a") as lf:
            fcntl.flock(lf, fcntl.LOCK_SH)
            try:
                with open(TRACKED_ITEMS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)
    except Exception as e:
        log(f"⚠️ Erreur lecture tracked_items: {e}")
        return {}

def update_tracked_item(item_id, update_dict):
    """Met à jour un article de manière atomique et thread/process-safe"""
    lock_file = TRACKED_ITEMS_FILE + ".lock"
    try:
        with open(lock_file, "a") as lf:
            fcntl.flock(lf, fcntl.LOCK_EX)
            try:
                data = {}
                if os.path.exists(TRACKED_ITEMS_FILE):
                    try:
                        with open(TRACKED_ITEMS_FILE, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    except Exception:
                        data = {}
                if item_id in data:
                    data[item_id].update(update_dict)
                else:
                    data[item_id] = update_dict
                tmp_file = TRACKED_ITEMS_FILE + f".tmp.{os.getpid()}"
                with open(tmp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp_file, TRACKED_ITEMS_FILE)
            finally:
                fcntl.flock(lf, fcntl.LOCK_UN)
    except Exception as e:
        log(f"⚠️ Erreur mise à jour #{item_id}: {e}")

def patch_discord_message(item, state_type, duration_str=None, fav_count=0):
    """
    Met à jour silencieusement le message Discord d'origine (0 notification).
    state_type: 'SOLD' | 'RESERVED' | 'REMOVED' | 'AVAILABLE'
    """
    msg_id = item.get("discord_message_id")
    if not msg_id:
        log(f"ℹ️ Pas de message_id Discord pour #{item.get('item_id')}, maj Discord ignorée ({state_type})")
        return False
    if not DISCORD_WEBHOOK_URL:
        log("⚠️ DISCORD_WEBHOOK_URL non configuré")
        return False

    patch_url = f"{DISCORD_WEBHOOK_URL}/messages/{msg_id}"
    title = item.get("title", "Article Vinted")
    price = item.get("price", "")
    initial_price = item.get("initial_price") or price
    size = item.get("size", "")
    brand = item.get("brand", "")
    url = item.get("url", "")
    photos = item.get("photos", [])
    base_desc = item.get("description", "")
    item_id = item.get("item_id", "")

    curr_p_num = parse_price_num(price)
    init_p_num = parse_price_num(initial_price)
    if curr_p_num is not None and init_p_num is not None and curr_p_num < init_p_num - 0.05:
        price_display = f"{price} (↘ au lieu de {initial_price})"
        price_desc_bold = f"**{price}** *(↘ au lieu de {initial_price})*"
    else:
        price_display = price
        price_desc_bold = f"**{price}**"

    fav_count = max(0, int(fav_count or 0))
    fav_badge = f" • ❤️ {fav_count} favori{'s' if fav_count > 1 else ''}"

    # Injection / mise à jour propre du prix et de la ligne favoris en haut de la description
    desc = base_desc
    if desc:
        desc = re.sub(r"💰 \*\*[^\|]+\*\*(?: \*\(↘ au lieu de [^\)]+\)\*)?", f"💰 {price_desc_bold}", desc, count=1)
    fav_line = f"❤️ **{fav_count} favori{'s' if fav_count > 1 else ''}** sur Vinted"
    if "❤️ **" in desc:
        desc = re.sub(r"❤️ \*\*\d+ favoris?\*\* sur Vinted", fav_line, desc)
    elif desc:
        lines = desc.split("\n")
        insert_idx = min(2, len(lines))
        lines.insert(insert_idx, fav_line)
        desc = "\n".join(lines)
    else:
        desc = fav_line

    if state_type == "SOLD":
        dur_label = duration_str or "quelques min"
        new_title = f"🔴 VENDU [en {dur_label}] • {title}"
        new_color = 0xED4245  # Rouge vif Discord
        footer_text = f"Vinted Sniper • ID: {item_id} • Vendu en {dur_label}{fav_badge}"
        new_content = f"~~@everyone | {title}~~\n🔴 **VENDU** en **{dur_label}**{fav_badge} | 💰 {price_display} | 📏 {size} | 🏷️ {brand}"

    elif state_type == "RESERVED":
        new_title = f"🟠 RÉSERVÉ • {title}"
        new_color = 0xFAA61A  # Orange Discord
        footer_text = f"Vinted Sniper • ID: {item_id} • Article réservé{fav_badge}"
        new_content = f"🟠 **RÉSERVÉ**{fav_badge} | {title}\n💰 {price_display} | 📏 {size} | 🏷️ {brand}"

    elif state_type == "REMOVED":
        new_title = f"⚫ SUPPRIMÉ / RETIRÉ • {title}"
        new_color = 0x747F8D  # Gris sombre Discord
        footer_text = f"Vinted Sniper • ID: {item_id} • Annonce retirée{fav_badge}"
        new_content = f"~~@everyone | {title}~~\n⚫ **ANNONCE SUPPRIMÉE / RETIRÉE** | 💰 {price_display} | 📏 {size} | 🏷️ {brand}"

    else:  # AVAILABLE
        new_title = f"🔔 {title}"
        new_color = 0x09B83E  # Vert d'origine
        footer_text = f"Vinted Sniper • ID: {item_id}{fav_badge}"
        new_content = f"@everyone | {title}\n💰 {price_display} | 📏 {size} | 🏷️ {brand}{fav_badge}"

    embed1 = {
        "title": new_title,
        "url": url,
        "description": desc,
        "color": new_color,
        "footer": {"text": footer_text},
        "timestamp": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    }
    if photos:
        embed1["image"] = {"url": photos[0]}

    embeds = [embed1]
    for photo_url in photos[1:10]:
        embeds.append({"url": url, "image": {"url": photo_url}})

    payload = {
        "content": new_content,
        "allowed_mentions": {"parse": []},  # Strictement silencieux : 0 ping
        "embeds": embeds
    }

    try:
        r = requests.patch(patch_url, json=payload, timeout=8)
        if r.status_code in [200, 204]:
            log(f"✅ Discord mis à jour ({state_type}{fav_badge}) pour #{item_id}")
            return True
        else:
            log(f"⚠️ Erreur Discord PATCH #{item_id}: HTTP {r.status_code} - {r.text[:100]}")
            return False
    except Exception as e:
        log(f"❌ Exception Discord PATCH #{item_id}: {e}")
        return False

def patch_telegram_message(item, state_type, duration_str=None, fav_count=0):
    """
    Met à jour silencieusement le message Telegram d'origine (légende + boutons).
    state_type: 'SOLD' | 'RESERVED' | 'REMOVED' | 'AVAILABLE'
    """
    tg_msg_id = item.get("telegram_message_id")
    if not tg_msg_id:
        return False
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    title = item.get("title", "Article Vinted")
    clean_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    price = item.get("price", "")
    size = item.get("size", "")
    brand = item.get("brand", "")
    url = item.get("url", "")
    clean_url = url.split("?")[0] if url else f"https://www.vinted.fr/items/{item.get('item_id')}"
    buy_url = clean_url

    if state_type == "SOLD":
        dur_txt = f" en {duration_str}" if duration_str else ""
        caption = f"🔴 <b>[VENDU{dur_txt}] {clean_title}</b>\n\n💰 Prix : <b>{price}</b> | 📏 Taille : <b>{size}</b>\n🏷️ Marque : <b>{brand}</b>\n❤️ {fav_count} favori(s)"
        btn_text = f"🔴 ARTICLE VENDU ({price})"
        btn_url = clean_url
    elif state_type == "RESERVED":
        caption = f"🟠 <b>[RÉSERVÉ] {clean_title}</b>\n\n💰 Prix : <b>{price}</b> | 📏 Taille : <b>{size}</b>\n🏷️ Marque : <b>{brand}</b>\n❤️ {fav_count} favori(s)"
        btn_text = "🟠 ARTICLE RÉSERVÉ"
        btn_url = clean_url
    elif state_type == "REMOVED":
        caption = f"⚫ <b>[RETIRÉ] {clean_title}</b>\n\n💰 Prix : <b>{price}</b> | 📏 Taille : <b>{size}</b>\n🏷️ Marque : <b>{brand}</b>"
        btn_text = "⚫ ANNONCE RETIRÉE"
        btn_url = clean_url
    else:
        caption = f"🟢 <b>{clean_title}</b>\n\n💰 Prix : <b>{price}</b> | 📏 Taille : <b>{size}</b>\n🏷️ Marque : <b>{brand}</b>\n❤️ {fav_count} favori(s)"
        btn_text = f"⚡ ACHETER SUR VINTED ({price})"
        btn_url = clean_url

    reply_markup = {
        "inline_keyboard": [
            [{"text": btn_text, "url": btn_url}]
        ]
    }

    tg_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageCaption"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "message_id": tg_msg_id,
        "caption": caption,
        "parse_mode": "HTML",
        "reply_markup": reply_markup
    }
    try:
        r = requests.post(tg_url, json=payload, timeout=6)
        if r.status_code == 200:
            log(f"✅ Telegram mis à jour ({state_type}) pour #{item.get('item_id')}")
            return True
        else:
            log(f"⚠️ Erreur Telegram PATCH #{item.get('item_id')}: HTTP {r.status_code}")
            return False
    except Exception as e:
        log(f"❌ Exception Telegram PATCH #{item.get('item_id')}: {e}")
        return False

def check_item_http(session, url):
    """
    Vérifie le statut réel, le nombre de favoris (❤️) et le prix actuel via simple requête HTTP (~0.18s, 0 Chromium).
    Purge automatiquement les cookies expirés (access_token_web Vinted expire au bout de 2h).
    Retourne (status, fav_count, price_val).
    """
    for attempt in range(2):
        try:
            if attempt > 0:
                session.cookies.clear()
                time.sleep(1.0)

            resp = session.get(url, timeout=10, allow_redirects=True)
            if resp.status_code == 404:
                return "SUPPRIMÉ", None, None
            if resp.status_code in [401, 403, 429] or resp.status_code >= 500:
                if resp.status_code == 429:
                    log(f"⏳ Rate-limit Vinted (HTTP 429) sur {url}, pause 15s avant nouvel essai...")
                    session.cookies.clear()
                    time.sleep(15.0)
                if attempt == 0:
                    continue
                log(f"⚠️ HTTP {resp.status_code} sur {url}")
                return "ERROR", None, None

            resp.encoding = "utf-8"
            html = resp.text

            # Extraction du nombre de favoris ❤️ (supporte JSON normal et échappé Next.js)
            fav_count = 0
            m_fav = (
                re.search(r'\\?"favourite_count\\?"\s*:\s*(\d+)', html)
                or re.search(r"ajouté aux favoris par (\d+) utilisateur", html, re.I)
            )
            if m_fav:
                try:
                    fav_count = int(m_fav.group(1))
                except ValueError:
                    fav_count = 0

            # Extraction du prix actuel hors protection acheteur
            price_val = None
            m_price = re.search(r'\\?"price\\?"\s*:\s*\{[^\}]{0,120}\\?"amount\\?"\s*:\s*\\?"([0-9\.]+)', html)
            if m_price:
                try:
                    price_val = float(m_price.group(1))
                except ValueError:
                    price_val = None

            has_buy = 'data-testid="item-buy-button"' in html or '"item-buy-button"' in html

            is_vendu = (
                '<div class="web_ui__Cell__body">Vendu</div>' in html
                or '"title":"Vendu"},{"exposures":[],"name":"buyer_item_status"' in html
                or "Cet article a été vendu" in html
                or "Cet article est vendu" in html
            ) and not has_buy

            is_reserve = (
                '<div class="web_ui__Cell__body">Réservé</div>' in html
                or '"title":"Réservé"},{"exposures":[],"name":"buyer_item_status"' in html
            ) and not has_buy

            is_supprime = not has_buy and (
                "Page introuvable" in html
                or "Page not found" in html
                or "Cet article n'existe plus" in html
            )

            if is_vendu:
                return "VENDU", fav_count, price_val
            if is_reserve:
                return "RÉSERVÉ", fav_count, price_val
            if is_supprime:
                return "SUPPRIMÉ", fav_count, price_val
            if has_buy:
                return "DISPONIBLE", fav_count, price_val

            # Si ni bouton acheter ni marqueur vendu (ex: cookie access_token_web expiré), on purge et réessaie
            if attempt == 0:
                continue
            return "ERROR", None, None

        except requests.Timeout:
            if attempt == 0:
                continue
            return "TIMEOUT", None, None
        except Exception as e:
            if attempt == 0:
                continue
            log(f"⚠️ Erreur HTTP {url}: {e}")
            return "ERROR", None, None
    return "ERROR", None, None

def run_tracker():
    # Priorité CPU basse pour ne jamais concurrencer le sniper temps réel sur un VPS 1 vCPU
    try:
        os.nice(15)
    except Exception:
        pass

    log("🚀 [Tracker] Démarrage du Vinted Sale Velocity Tracker (Moteur HTTP Ultra-Léger ~12 Mo RAM | nice=15)")

    session = requests.Session()
    session.headers.update(HTTP_HEADERS)

    while True:
        try:
            now = time.time()
            tracked = load_tracked_items()
            active_items = [item for item in tracked.values() if item.get("status") == "ACTIVE"]

            due_items = []
            for item in active_items:
                next_check = item.get("next_check_at", 0)
                if now >= next_check:
                    due_items.append(item)

            if not due_items:
                if active_items:
                    min_next = min(item.get("next_check_at", now + 30) for item in active_items)
                    sleep_time = max(5, min(30, int(min_next - now)))
                else:
                    sleep_time = 20
                time.sleep(sleep_time)
                continue

            # Priorité absolue aux annonces les plus récentes (0h-6h) et plafonnement à 10 articles par lot
            due_items.sort(key=lambda x: float(x.get("created_at", 0)), reverse=True)
            batch_items = due_items[:10]

            log(f"🔍 [Tracker] {len(batch_items)}/{len(due_items)} article(s) à vérifier (sur {len(active_items)} actifs)")
            session.cookies.clear()

            for item in batch_items:
                item_id = str(item.get("item_id") or item.get("id"))
                created_at = float(item.get("created_at", now))
                age = now - created_at
                prev_fav = int(item.get("fav_count") or 0)
                prev_sub = item.get("sub_status", "AVAILABLE")

                # 1. Vérification d'expiration (> 7 jours) - conserve 100% de l'historique dans le fichier
                if age >= 7 * 86400:
                    log(f"⌛ [Tracker] Article #{item_id} expiré (> 7 jours). Arrêt du suivi (historique conservé).")
                    update_tracked_item(item_id, {
                        "status": "EXPIRED",
                        "last_checked_at": now
                    })
                    continue

                # 2. Vérification HTTP ultra-légère sur Vinted
                url = item.get("url") or f"https://www.vinted.fr/items/{item_id}"
                status, fav_count, price_val = check_item_http(session, url)

                current_fav = fav_count if fav_count is not None else prev_fav
                initial_price = item.get("initial_price") or item.get("price", "")
                prev_price_str = item.get("price", "")
                prev_price_num = parse_price_num(prev_price_str)
                price_changed = False
                if price_val is not None and prev_price_num is not None and abs(price_val - prev_price_num) >= 0.05:
                    new_price_str = f"{price_val:.2f} €"
                    item["price"] = new_price_str
                    item["initial_price"] = initial_price
                    price_changed = True
                    log(f"💰 [Tracker] Changement de prix détecté pour #{item_id} : {prev_price_str} -> {new_price_str} (initial: {initial_price})")

                if status == "VENDU":
                    duration = now - created_at
                    dur_str = format_duration(duration)
                    log(f"🎯 [Tracker] Article #{item_id} VENDU en {dur_str} (❤️ {current_fav}) ! ({item.get('title')})")
                    
                    patch_discord_message(item, "SOLD", duration_str=dur_str, fav_count=current_fav)
                    patch_telegram_message(item, "SOLD", duration_str=dur_str, fav_count=current_fav)

                    update_tracked_item(item_id, {
                        "status": "SOLD",
                        "sub_status": "SOLD",
                        "price": item.get("price", prev_price_str),
                        "initial_price": initial_price,
                        "fav_count": current_fav,
                        "sold_at": now,
                        "sold_duration_seconds": duration,
                        "sold_duration_str": dur_str,
                        "last_checked_at": now
                    })

                elif status == "SUPPRIMÉ":
                    log(f"🗑️ [Tracker] Article #{item_id} SUPPRIMÉ de Vinted (❤️ {current_fav}). Fin du suivi.")
                    patch_discord_message(item, "REMOVED", fav_count=current_fav)
                    patch_telegram_message(item, "REMOVED", fav_count=current_fav)
                    update_tracked_item(item_id, {
                        "status": "REMOVED",
                        "sub_status": "REMOVED",
                        "fav_count": current_fav,
                        "last_checked_at": now
                    })

                elif status == "RÉSERVÉ":
                    log(f"⏳ [Tracker] Article #{item_id} RÉSERVÉ (❤️ {current_fav}). Prochain check dans 10 min.")
                    if prev_sub != "RESERVED" or current_fav != prev_fav or price_changed:
                        patch_discord_message(item, "RESERVED", fav_count=current_fav)
                        patch_telegram_message(item, "RESERVED", fav_count=current_fav)
                    update_tracked_item(item_id, {
                        "sub_status": "RESERVED",
                        "price": item.get("price", prev_price_str),
                        "initial_price": initial_price,
                        "fav_count": current_fav,
                        "check_count": item.get("check_count", 0) + 1,
                        "last_checked_at": now,
                        "next_check_at": now + 600
                    })

                elif status == "DISPONIBLE":
                    interval = get_next_interval(age)
                    if interval is None:
                        update_tracked_item(item_id, {"status": "EXPIRED", "last_checked_at": now})
                    else:
                        dur_age_str = format_duration(age)
                        dur_next_str = format_duration(interval)
                        log(f"✅ [Tracker] #{item_id} DISPONIBLE (💰 {item.get('price')} | ❤️ {current_fav} fav | âge: {dur_age_str} | prochain check: {dur_next_str})")
                        
                        if prev_sub == "RESERVED" or current_fav != prev_fav or price_changed or int(item.get("check_count") or 0) == 0:
                            patch_discord_message(item, "AVAILABLE", fav_count=current_fav)
                            patch_telegram_message(item, "AVAILABLE", fav_count=current_fav)

                        update_tracked_item(item_id, {
                            "sub_status": "AVAILABLE",
                            "price": item.get("price", prev_price_str),
                            "initial_price": initial_price,
                            "fav_count": current_fav,
                            "check_count": item.get("check_count", 0) + 1,
                            "last_checked_at": now,
                            "next_check_at": now + interval
                        })

                else:  # TIMEOUT ou ERROR
                    log(f"⚠️ [Tracker] Statut indéterminé ({status}) pour #{item_id}. Nouvelle tentative dans 5 min.")
                    update_tracked_item(item_id, {
                        "last_checked_at": now,
                        "next_check_at": now + 300
                    })

                time.sleep(4.5)

        except Exception as e:
            log(f"❌ [Tracker] Erreur boucle principale: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run_tracker()
