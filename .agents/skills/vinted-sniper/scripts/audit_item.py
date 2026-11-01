#!/usr/bin/env python3
"""
Outil d'audit et diagnostic d'une annonce Vinted pour JerseyAlert (ASSE).
Utilisation : python3 audit_item.py <ITEM_ID_OU_URL>
"""

import sys
import os
import re
import json
import urllib.request
import urllib.error

# Importer vinted_bot_oracle depuis la racine du projet
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    import vinted_bot_oracle as bot
except ImportError:
    # Essayer les chemins classiques
    for p in ["/Users/laismoreno/test dev", "/root/JerseyAlert", os.getcwd()]:
        if p not in sys.path:
            sys.path.insert(0, p)
    import vinted_bot_oracle as bot


def fetch_vinted_item_data(item_id):
    """Tente de récupérer les données de l'annonce par plusieurs méthodes."""
    url = f"https://www.vinted.fr/items/{item_id}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "fr-FR,fr;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
    )
    
    html = ""
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"⚠️ [Audit] Erreur fetch direct Web ({e}). Recherche dans les caches locaux...")

    # Extraire depuis le HTML
    title = ""
    desc = ""
    brand = "N/A"
    size = "N/A"
    price = "0.00"

    if html:
        # Titre (meta og:title ou <title>)
        m_t = re.search(r'<meta property="og:title" content="([^"]+)"', html)
        if m_t:
            title = m_t.group(1).split(" - Vinted")[0].strip()
        else:
            m_t2 = re.search(r'<title>([^<]+)</title>', html)
            if m_t2:
                title = m_t2.group(1).split(" - Vinted")[0].strip()

        # Description
        m_d = re.search(r'<meta property="og:description" content="([^"]+)"', html)
        if m_d:
            desc = m_d.group(1).strip()
        else:
            m_d2 = re.search(r'itemprop="description">([^<]+)<', html)
            if m_d2:
                desc = m_d2.group(1).strip()

        # Détails (Marque & Taille)
        for m in re.finditer(r'<div class="details-list__item-title">([^<]+)</div>\s*<div class="details-list__item-value"[^>]*>(.*?)</div>', html, re.DOTALL):
            key = m.group(1).strip().lower()
            val = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            if "marque" in key or "brand" in key:
                brand = val
            elif "taille" in key or "size" in key:
                size = val

        # Prix
        m_p = re.search(r'data-testid="item-price"[^>]*>([^<]+)<', html)
        if m_p:
            price = m_p.group(1).strip()
        else:
            m_p2 = re.search(r'"price":"([^"]+)"', html)
            if m_p2:
                price = m_p2.group(1).strip()

    return {
        "id": item_id,
        "title": title or f"Article #{item_id}",
        "description": desc,
        "brand": brand,
        "size": size,
        "price": price,
        "url": url,
        "html_fetched": bool(html)
    }


def audit(item_arg):
    # Extraire l'ID depuis un lien ou un nombre
    m = re.search(r'(\d{8,12})', str(item_arg))
    if not m:
        print(f"❌ Impossible d'extraire l'ID Vinted depuis: {item_arg}")
        sys.exit(1)
    item_id = int(m.group(1))

    print(f"\n==================================================")
    print(f"🔍 AUDIT COMPLET ANNONCE VINTED #{item_id}")
    print(f"==================================================")

    data = fetch_vinted_item_data(item_id)
    title = data["title"]
    desc = data["description"]
    brand = data["brand"]
    size = data["size"]
    price = data["price"]

    print(f"📌 Titre       : {title}")
    print(f"💶 Prix        : {price}")
    print(f"🏷️  Marque      : {brand}")
    print(f"📏 Taille      : {size}")
    print(f"📝 Description : {desc[:150]}..." if len(desc) > 150 else f"📝 Description : {desc or '(Vide)'}")
    print(f"🔗 URL         : {data['url']}")
    print(f"--------------------------------------------------")

    # 1. Vérification Mot-clé Maillot
    has_shirt_kw = bool(re.search(
        r'\b(maillots?|jerseys?|trikots?|camisetas?|maglias?|tenues?|ensembles?|t-?shirts?|tee[- ]?shirts?|shirts?|hauts?)\b',
        title, re.IGNORECASE
    ))
    print(f"1️⃣ Mot-clé Maillot (Titre)      : {'✅ OUI' if has_shirt_kw else '❌ NON'}")

    # 2. Vérification Club Concurrent
    is_conf_t, team_t = bot.is_conflicting_team(title)
    is_conf_d, team_d = bot.is_conflicting_team(desc)
    if is_conf_t:
        print(f"2️⃣ Club Concurrent (Titre)     : 🚫 OUI ({team_t}) -> BLOQUÉ")
    elif is_conf_d:
        print(f"2️⃣ Club Concurrent (Desc)      : 🚫 OUI ({team_d}) -> BLOQUÉ")
    else:
        print(f"2️⃣ Club Concurrent             : ✅ AUCUN (Validé)")

    # 3. Vérification Signal ASSE
    is_sig_direct, sig_reason_direct = bot.is_asse_signal(title, is_filet=False)
    is_sig_filet, sig_reason_filet = bot.is_asse_signal(title, is_filet=True)
    is_sig_desc, sig_reason_desc = bot.is_asse_signal(desc, is_filet=True)

    print(f"3️⃣ Signal ASSE Direct (Titre)   : {'🎯 ' + sig_reason_direct if is_sig_direct else '❌ Aucun'}")
    print(f"   Signal ASSE Filet (Titre)    : {'🎯 ' + sig_reason_filet if is_sig_filet else '❌ Aucun'}")
    print(f"   Signal ASSE Description      : {'🎯 ' + sig_reason_desc if is_sig_desc else '❌ Aucun'}")

    # 4. Filtre d'exclusion produit (vélos, nba, training, etc.)
    is_excl_p, reason_p = bot.is_excluded_product(title, brand, desc)
    print(f"4️⃣ Exclusion Produit / Sport    : {'🚫 EXCLU (' + reason_p + ')' if is_excl_p else '✅ Valide'}")

    # 5. Filtre de taille
    is_excl_s, reason_s = bot.is_excluded_size(size, title, desc)
    print(f"5️⃣ Exclusion Taille / Enfant   : {'🚫 EXCLU (' + reason_s + ')' if is_excl_s else '✅ Valide'}")

    # VERDICT FINAL
    print(f"\n==================================================")
    print(f"⚖️ VERDICT DU BOT SNIPER")
    print(f"==================================================")

    # Flux Direct Foot
    foot_match = has_shirt_kw and not is_conf_t and is_sig_direct and not is_excl_p and not is_excl_s
    filet_match = not is_conf_t and not is_conf_d and (is_sig_filet or is_sig_desc) and not is_excl_p and not is_excl_s

    if foot_match:
        print(f"🚀 [Flux Direct Foot] : 🎯 ALERTÉ IMMÉDIATEMENT ({sig_reason_direct})")
    else:
        reasons = []
        if not has_shirt_kw: reasons.append("Pas de mot-clé maillot")
        if is_conf_t: reasons.append(f"Club adverse dans titre ({team_t})")
        if not is_sig_direct: reasons.append("Aucun signal ASSE direct dans le titre")
        if is_excl_p: reasons.append(f"Produit exclu ({reason_p})")
        if is_excl_s: reasons.append(f"Taille exclue ({reason_s})")
        print(f"⏩ [Flux Direct Foot] : 🚫 IGNORÉ ({', '.join(reasons)})")

    if filet_match:
        sig = sig_reason_filet or sig_reason_desc
        print(f"🛡️  [Filet Sécurité]   : 🎯 ALERTÉ ({sig})")
    else:
        reasons = []
        if is_conf_t: reasons.append(f"Club adverse dans titre ({team_t})")
        if is_conf_d: reasons.append(f"Club adverse dans description ({team_d})")
        if not (is_sig_filet or is_sig_desc): reasons.append("Aucun signal ASSE")
        if is_excl_p: reasons.append(f"Produit exclu ({reason_p})")
        if is_excl_s: reasons.append(f"Taille exclue ({reason_s})")
        print(f"🛡️  [Filet Sécurité]   : 🚫 IGNORÉ ({', '.join(reasons)})")
    print(f"==================================================\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 audit_item.py <ITEM_ID_OU_URL>")
        sys.exit(1)
    audit(sys.argv[1])
