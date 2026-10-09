#!/usr/bin/env python3
"""
Vinted Bot optimisé pour Oracle Cloud
- Utilise Playwright pour éviter la détection
- Délais aléatoires pour paraître humain
- Gestion robuste des erreurs
- Notifications Discord
"""

import os
import sys
import time
import json
import random
import requests
import signal
from urllib.parse import quote_plus
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# Configuration
# Configuration des recherches
PRIORITY_QUERIES = ["Maillot Asse", "Maillot Saint-Etienne", "Maillot St Etienne"]
SECONDARY_QUERIES = ["Jersey Asse", "Jersey Saint-Etienne", "Maglia Asse", "Camiseta Asse", "Ensemble Asse", "Trikot Asse"]
# Liste combinée pour l'initialisation
SEARCH_QUERIES = PRIORITY_QUERIES + SECONDARY_QUERIES

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
STATE_FILE = "last_seen_id.txt"
BLACKLIST_FILE = "blacklisted_sellers.json"
FILTER_ADULT_ONLY = os.environ.get("FILTER_ADULT_ONLY", "true").lower() == "true"
CHECK_INTERVAL_MIN = 10
CHECK_INTERVAL_MAX = 20

def load_blacklisted_sellers():
    """Charge la liste noire des vendeurs Vinted"""
    sellers = set()
    env_blocked = os.environ.get("BLOCKED_SELLERS", "")
    if env_blocked:
        for s in env_blocked.split(","):
            if s.strip():
                sellers.add(s.strip().lower().replace("@", ""))
                
    if os.path.exists(BLACKLIST_FILE):
        try:
            with open(BLACKLIST_FILE, "r") as f:
                data = json.load(f)
                for s in data:
                    sellers.add(str(s).strip().lower().replace("@", ""))
        except Exception:
            pass
    return sellers

def save_blacklisted_sellers(sellers_set):
    """Sauvegarde la liste noire des vendeurs Vinted"""
    try:
        with open(BLACKLIST_FILE, "w") as f:
            json.dump(sorted(list(sellers_set)), f, indent=2)
    except Exception as e:
        log(f"⚠️ Erreur sauvegarde blacklist: {e}")

def add_blacklisted_seller(username):
    """Ajoute un vendeur à la liste noire"""
    cleaned = username.strip().lower().replace("@", "")
    if "vinted." in cleaned and "/member/" in cleaned:
        cleaned = cleaned.split("/member/")[1].split("?")[0].split("-")[-1]
    sellers = load_blacklisted_sellers()
    sellers.add(cleaned)
    save_blacklisted_sellers(sellers)
    log(f"⛔ Vendeur '{cleaned}' ajouté à la liste noire Vinted.")
    return cleaned

def remove_blacklisted_seller(username):
    """Retire un vendeur de la liste noire"""
    cleaned = username.strip().lower().replace("@", "")
    if "vinted." in cleaned and "/member/" in cleaned:
        cleaned = cleaned.split("/member/")[1].split("?")[0].split("-")[-1]
    sellers = load_blacklisted_sellers()
    if cleaned in sellers:
        sellers.remove(cleaned)
        save_blacklisted_sellers(sellers)
        log(f"✅ Vendeur '{cleaned}' retiré de la liste noire Vinted.")
        return True
    return False

def clean_text(text):
    """Nettoyage radical des parasites Vinted (Enlevé, Nouveau, etc)"""
    if not text: return ""
    import re
    # Supprime les badges publicitaires et parasites
    text = re.sub(r'(?i)enlevé\s*!?', '', text)
    text = re.sub(r'(?i)nouveau\s*!?', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def is_excluded_size(size_str, title_str="", desc_str=""):
    """
    Filtre les tailles enfants (âges, cm, mots-clés) ainsi que XS et S.
    Conserve les tailles adultes M, L, XL, XXL+, tailles uniques et N/A non identifiés comme enfant.
    """
    import re
    s = (size_str or "").strip().upper()
    t = (title_str or "").strip().lower()

    # 1. Détection des tailles enfants
    # Mots-clés dans la taille (ex: '10 ans', '12 ans', '14 ans / 164 cm', '6 mois')
    child_size_keywords = ['ans', 'mois', 'yr', 'year', 'anni', 'anos', 'enfant', 'kid', 'junior', 'jr', 'cm']
    if any(k in s.lower() for k in child_size_keywords):
        return True, f"Taille enfant ({size_str})"

    # Mots-clés enfants dans le titre (ex: 'Maillot ASSE Enfant 10 ans')
    if any(re.search(rf'\b{re.escape(kw)}\b', t) for kw in ['enfant', 'enfants', 'kids', 'junior', 'bebe', 'bébé', 'garcon', 'garçon', 'fille', 'baby', 'youth']):
        return True, "Mot-clé enfant dans le titre"

    # Âge enfant dans le titre (ex: '10 ans', '8a', '12 ans')
    if re.search(r'\b\d{1,2}\s*(?:ans|a|mois|m|years|yrs)\b', t):
        return True, "Âge enfant dans le titre"

    # Tailles jeunesse internationales type YXS, YS, YM, YL, YXL
    if re.match(r'^Y[SMLX]+$', s):
        return True, f"Taille Youth ({size_str})"

    # Tailles en cm (ex: 128, 140, 152, 164 cm)
    if re.search(r'\b(1[0-7][0-9])\s*cm\b', s.lower()) or re.search(r'\b(1[0-7][0-9])\s*cm\b', t):
        return True, "Taille en cm (enfant)"

    # Tailles numériques enfant pures (tailles standards Vinted enfant)
    if re.match(r'^(104|110|116|122|128|134|140|146|152|158|164|170|176)$', s):
        return True, f"Taille numérique enfant ({size_str})"

    # 2. Exclusion des tailles XS et S
    # Strictement XS, XXS, XXXS
    if re.match(r'^(X{1,3}S|EXTRA\s*SMALL)$', s):
        return True, f"Taille XS ({size_str})"

    # Strictement S
    if re.match(r'^(S|SMALL)$', s):
        return True, f"Taille S ({size_str})"

    # Combinaison type XS/S ou S/XS
    if re.match(r'^(XS\s*/\s*S|S\s*/\s*XS)$', s):
        return True, f"Taille XS/S ({size_str})"

    # Tailles numériques équivalentes à XS/S (32, 34, 36)
    if re.match(r'^(32|34|36)(?:\s*/\s*(?:XS|S))?$', s) or re.match(r'^(?:XS|S)\s*/\s*(32|34|36)$', s):
        return True, f"Taille numérique XS/S ({size_str})"

    return False, "OK"

def is_asse_jersey_match(title):
    """Filtrage strict ASSE avec limites de mots (évite les faux positifs type Borussia/Strasbourg tout en capturant tous les produits ASSE/St-Etienne)"""
    if not title: return False
    import re
    title_low = title.lower()
    team_pattern = r'\b(asse|saint[- \.]*etienne|st[- \.]*etienne|sainté|saint[- \.]*étienne|st[- \.]*étienne)\b'
    return bool(re.search(team_pattern, title_low))

def get_api_search_url(query, color_id=None):
    """Génère l'URL d'API directe Vinted pour une recherche texte"""
    url = f"https://www.vinted.fr/api/v2/catalog/items?search_text={quote_plus(query)}&order=newest_first&page=1&per_page=48"
    if color_id:
        url += f"&color_ids[]={color_id}"
    return url

def get_paris_time():
    """Retourne l'heure courante exacte de Paris (été/hiver garanti)"""
    if ZoneInfo:
        try:
            return datetime.now(ZoneInfo("Europe/Paris"))
        except Exception:
            pass
    import time
    os.environ['TZ'] = 'Europe/Paris'
    if hasattr(time, 'tzset'):
        time.tzset()
    return datetime.now()

def get_search_url(query, color_id=None):
    url = f"https://www.vinted.fr/catalog?search_text={query.replace(' ', '+')}&order=newest_first"
    if color_id:
        url += f"&color_ids[]={color_id}"
    return url

def log(message):
    """Log avec timestamp heure de Paris"""
    timestamp = get_paris_time().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {message}", flush=True)

def load_last_seen_id():
    """Charge le dernier ID vu depuis le fichier"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return int(f.read().strip())
        except:
            pass
    return 0

def save_last_seen_id(item_id):
    """Sauvegarde le dernier ID vu"""
    with open(STATE_FILE, "w") as f:
        f.write(str(item_id))

def scrape_item_details(page, item_url):
    """Va sur la page de l'article pour récupérer infos détaillées via API interne (V3.0 API Call)"""
    try:
        log(f"🔎 Scraping détails: {item_url}")
        
        # Extraire l'ID de l'item depuis l'URL
        import re
        id_match = re.search(r'/items/(\d+)', item_url)
        item_id = id_match.group(1) if id_match else None
        
        if not item_id:
            log("❌ Impossible d'extraire l'ID de l'URL")
            return {"description": "", "photos": [], "brand": "N/A", "size": "N/A", "status": "N/A"}

        # On va sur une page "neutre" (la page d'accueil ou la recherche) pour avoir le contexte de session
        # Pas besoin d'aller sur la page détail lourde, on peut juste fetch l'API
        # Mais pour être sûr d'avoir les cookies, restons sur la page actuelle ou allons sur la home
        # Si on est déjà dans un contexte ouvert, on peut juste faire fetch
        # Le contexte appelant ouvre déjà une page vide, allons sur Vinted Home pour initialiser la session si besoin
        # page.goto("https://www.vinted.fr", wait_until='domcontentloaded') 
        # (Optimisation: on suppose qu'on a déjà les cookies de la recherche précédente)
        
        # Pour être sûr, on va quand même sur la page de l'item (ça génère les cookies spécifiques item)
        page.goto(item_url, wait_until='domcontentloaded', timeout=15000)

        # Récupération de TOUTES les photos haute résolution (/f800/) depuis les scripts Next.js ou le DOM
        photos = page.evaluate("""() => {
            const photos = [];
            const scripts = document.querySelectorAll('script');
            scripts.forEach(s => {
                const txt = s.textContent || '';
                const parts = txt.split('https://images1.vinted.net/');
                for (let i = 1; i < parts.length; i++) {
                    const urlPart = parts[i].split('"')[0].split('\\\\')[0];
                    if (urlPart.includes('/f800/')) {
                        photos.push('https://images1.vinted.net/' + urlPart);
                    }
                }
            });
            if (photos.length > 0) return Array.from(new Set(photos));
            
            const imgs = Array.from(document.querySelectorAll('img'))
                                 .map(i => i.src || i.getAttribute('data-src') || '')
                                 .filter(s => s && s.includes('vinted.net') && (s.includes('/f800/') || s.includes('/full/') || s.includes('/1500/')));
            return Array.from(new Set(imgs));
        }""")
        photos = list(dict.fromkeys(photos))

        # APPEL API DIRECT via le navigateur
        log(f"📡 Appel API interne pour l'item {item_id}...")
        api_data = page.evaluate(f"""async () => {{
            try {{
                const response = await fetch('/api/v2/items/{item_id}?localize=false', {{
                    headers: {{
                        'Accept': 'application/json, text/plain, */*'
                    }}
                }});
                if (response.ok) {{
                    return await response.json();
                }}
                return null;
            }} catch (e) {{
                return null;
            }}
        }}""")
        
        description = ""
        brand = "N/A"
        size = "N/A"
        status = "N/A"
        
        if api_data and 'item' in api_data:
            item = api_data['item']
            log("✅ Réponse API reçue !")
            
            description = item.get('description', '')
            brand = item.get('brand_title', 'N/A')
            size = item.get('size_title', 'N/A')
            status = item.get('status', 'N/A') # Parfois c'est status_id, il faut mapper, mais essayons title
            
            # Si status est vide, parfois c'est pas envoyé
            if status == 'N/A' and 'status' in item:
                 # Vinted API change parfois
                 pass
            
        else:
            log("⚠️ API Vinted muette ou erreur")

        # Si l'API n'a pas tout renvoyé ou a échoué, on extrait depuis les scripts / le DOM de la page
        if not description or brand == 'N/A' or size == 'N/A' or status in ['N/A', 'Non spécifié']:
            try:
                dom_details = page.evaluate("""() => {
                    let dBrand = 'N/A', dSize = 'N/A', dStatus = 'N/A', dDesc = '';
                    
                    const descEl = document.querySelector('[itemprop="description"]');
                    if (descEl) dDesc = descEl.innerText.trim();

                    // Recherche dans les scripts Next.js (hydratation JSON)
                    try {
                        const scripts = Array.from(document.querySelectorAll('script'));
                        for (const s of scripts) {
                            const txt = s.textContent || '';
                            if (txt.includes('code') && (txt.includes('size') || txt.includes('brand') || txt.includes('status'))) {
                                if (dSize === 'N/A') {
                                    const m = txt.match(/["\\\\]+code["\\\\]+:\s*["\\\\]+size["\\\\]+.*?["\\\\]+value["\\\\]+:\s*["\\\\]+([^"\\\\]+)["\\\\]+/);
                                    if (m) dSize = m[1].trim();
                                }
                                if (dStatus === 'N/A') {
                                    const m = txt.match(/["\\\\]+code["\\\\]+:\s*["\\\\]+status["\\\\]+.*?["\\\\]+value["\\\\]+:\s*["\\\\]+([^"\\\\]+)["\\\\]+/);
                                    if (m) dStatus = m[1].trim();
                                }
                                if (dBrand === 'N/A') {
                                    const m = txt.match(/["\\\\]+code["\\\\]+:\s*["\\\\]+brand["\\\\]+.*?["\\\\]+title["\\\\]+:\s*["\\\\]+([^"\\\\]+)["\\\\]+/);
                                    if (m) dBrand = m[1].trim();
                                }
                            }
                        }
                    } catch (e) {}

                    // Recherche dans les éléments DOM
                    if (dSize === 'N/A' || dBrand === 'N/A' || dStatus === 'N/A') {
                        const items = document.querySelectorAll('.details-list__item, [data-testid*="item-attributes"]');
                        items.forEach(el => {
                            const t = el.innerText || '';
                            const valEl = el.querySelector('.details-list__item-value, [data-testid*="value"]');
                            const val = valEl ? valEl.innerText.trim() : '';
                            if (val) {
                                if (/taille|size/i.test(t) && dSize === 'N/A') dSize = val;
                                if (/marque|brand/i.test(t) && dBrand === 'N/A') dBrand = val;
                                if (/état|status|condition/i.test(t) && dStatus === 'N/A') dStatus = val;
                            }
                        });
                    }

                    return { description: dDesc, brand: dBrand, size: dSize, status: dStatus };
                }""")
                if not description and dom_details.get('description'):
                    description = dom_details['description']
                if brand == 'N/A' and dom_details.get('brand') != 'N/A':
                    brand = dom_details['brand']
                if size == 'N/A' and dom_details.get('size') != 'N/A':
                    size = dom_details['size']
                if status in ['N/A', 'Non spécifié'] and dom_details.get('status') not in ['N/A', 'Non spécifié']:
                    status = dom_details['status']
            except Exception as e:
                log(f"⚠️ Erreur fallback DOM/Scripts item: {e}")
        
        log(f"✅ Détails finaux: {brand} | {size} | {status}")
        
        return {
            "description": description,
            "photos": photos,
            "brand": brand,
            "size": size,
            "status": status
        }
    except Exception as e:
        log(f"⚠️ Erreur scraping détails (API Mode): {e}")
        return {"description": "", "photos": [], "brand": "N/A", "size": "N/A", "status": "N/A"}

def fetch_direct_catalog_api(page, api_url):
    """Interroge directement l'API catalogue Vinted via fetch() dans le navigateur"""
    try:
        data = page.evaluate(f"""async () => {{
            try {{
                const res = await fetch('{api_url}', {{
                    headers: {{ 'Accept': 'application/json, text/plain, */*' }}
                }});
                if (res.status === 429) return {{ rate_limited: true, status: 429 }};
                if (res.status === 401 || res.status === 403) return {{ auth_error: true, status: res.status }};
                if (res.ok) return await res.json();
                return null;
            }} catch(e) {{
                return null;
            }}
        }}""")
        if not data:
            return []
        
        if isinstance(data, dict):
            if data.get('rate_limited'):
                log("⚠️ Vinted Rate Limit (429) détecté ! Pause de sécurité de 90s...")
                time.sleep(90)
                return []
            if data.get('auth_error'):
                log(f"⚠️ Erreur statut Vinted ({data.get('status')}). Pause courte...")
                time.sleep(5)
                return []

        if 'items' not in data:
            return []
        
        items = []
        for raw in data.get('items', []):
            try:
                item_id = raw.get('id')
                if not item_id: continue
                title = raw.get('title') or ''
                price_data = raw.get('price')
                if isinstance(price_data, dict):
                    price = f"{price_data.get('amount', 'N/A')} €"
                elif price_data is not None:
                    price = f"{price_data} €"
                else:
                    price = 'N/A'
                
                size = raw.get('size_title') or 'N/A'
                brand = raw.get('brand_title') or 'N/A'
                status = raw.get('status') or 'Non spécifié'
                url = raw.get('url') or f"https://www.vinted.fr/items/{item_id}"
                
                photo = ''
                if raw.get('photo') and isinstance(raw['photo'], dict):
                    photo = raw['photo'].get('url', '')
                
                items.append({
                    'id': item_id,
                    'title': title,
                    'price': price,
                    'size': size,
                    'brand': brand,
                    'status': status,
                    'url': url,
                    'photo': photo
                })
            except Exception:
                pass
        return items
    except Exception as e:
        log(f"⚠️ Erreur fetch API catalogue direct: {e}")
        return []

def extract_items_from_page(page):
    """Extrait les articles avec Parsing Intelligent du Titre (V5.0)"""
    try:
        page.wait_for_selector('div[data-testid*="item"]', timeout=10000)
        time.sleep(0.4)
        
        items = page.evaluate("""
            () => {
                const items = [];
                const itemElements = document.querySelectorAll('div[data-testid*="item"], div[class*="feed-grid__item"]');
                
                itemElements.forEach((el) => {
                    try {
                        const link = el.querySelector('a');
                        if (!link) return;
                        
                        const url = link.href;
                        const idMatch = url.match(/items\\/(\\d+)/);
                        if (!idMatch) return;
                        const itemId = parseInt(idMatch[1]);
                        
                        // RECUPERATION DU TITRE COMPLET (contient souvent marque, taille, état)
                        let rawTitle = link.getAttribute('title') || '';
                        if (!rawTitle) {
                             const img = el.querySelector('img');
                             if (img) rawTitle = img.alt;
                        }
                        
                        // Valeurs par défaut
                        let price = 'N/A';
                        let size = 'N/A';
                        let brand = 'N/A';
                        let status = 'Non spécifié';
                        let title = rawTitle; // Par défaut on prend tout

                        // ANALYSE DU TITRE (Parsing V9.0 - Insensible à la casse)
                        // Exemple: "Veste ASSE, Marque: Le Coq Sportif, État: Très bon état, Taille: M, 15.00 €, 16.45 €"
                        const hasMeta = /(?:marque|brand|taille|size|taglia|talla|état|etat|condition)\s*:/i.test(rawTitle);
                        if (hasMeta) {
                            // Nettoyage du titre réel : on retire la chaîne de métadonnées Vinted
                            const cleanT = rawTitle.replace(/,\s*(?:marque|brand|taille|size|taglia|talla|état|etat|condition)\s*:.*$/i, '').trim();
                            if (cleanT) title = cleanT;
                            
                            // Extraction par Regex JS insensible à la casse
                            const brandMatch = rawTitle.match(/(?:marque|brand|marca|marke)\s*:\s*([^,]+)/i);
                            if (brandMatch) brand = brandMatch[1].trim();
                            
                            const sizeMatch = rawTitle.match(/(?:taille|size|taglia|talla|maat)\s*:\s*([^,]+)/i);
                            if (sizeMatch) size = sizeMatch[1].trim();
                            
                            const statusMatch = rawTitle.match(/(?:état|etat|condition|stato|estado)\s*:\s*([^,]+)/i);
                            if (statusMatch) status = statusMatch[1].trim();

                            const priceMatch = rawTitle.match(/,\s*(\d+(?:[.,]\d+)?\s*€)/i);
                            if (priceMatch) price = priceMatch[1].trim();
                        }
                        
                        // Récupération de TOUS les textes (morceaux + bloc complet)
                        const texts = Array.from(el.querySelectorAll('p, h3, h4, span, div'))
                                           .map(e => e.innerText.trim())
                                           .filter(t => t.length > 0);
                        
                        // On ajoute le texte brut complet de l'élément pour voir les lignes concaténées
                        texts.push(el.innerText.trim());
                        
                        const uniqueTexts = [...new Set(texts)];
                        
                        // Extraction d'un prix propre s'il manque ou est pollué
                        if (price === 'N/A' || price.length > 20 || price.includes('·') || price.includes('incl')) {
                            const priceRegex = /(\d+[\d\s]*[.,]\d{2}\s*€|\d+\s*€)/;
                            const pText = uniqueTexts.find(t => priceRegex.test(t));
                            if (pText) {
                                const m = pText.match(priceRegex);
                                if (m) price = m[1].trim();
                            } else {
                                price = uniqueTexts.find(t => t.includes('€') || t.includes('$')) || 'N/A';
                            }
                        }
                        
                        // Si la taille est encore N/A, on tente l'heuristique avancée sur uniqueTexts
                        if (size === 'N/A') {
                            const sizeRegex = /^(XS|S|M|L|XL|XXL|XXXL|[0-9]{1,3}(?:\s*ans)?|Unique|[0-9]{2}\s*\/\s*[0-9]{2})$/i;
                            for (const t of uniqueTexts) {
                                if (t.includes('€') || t.includes('$')) continue;
                                if (sizeRegex.test(t)) {
                                    size = t;
                                    break;
                                }
                                // Découpage des éléments composites comme "M · Très bon état"
                                const parts = t.split(/[·•|]/).map(p => p.trim());
                                for (const p of parts) {
                                    if (sizeRegex.test(p)) {
                                        size = p;
                                        break;
                                    }
                                }
                                if (size !== 'N/A') break;
                            }
                        }

                        // 4. Heuristique "État" ULTIME (V6.3)
                        if (status === 'Non spécifié') {
                            const statusKeywords = [
                                "neuf avec étiquette", "neuf sans étiquette", "neuf",
                                "très bon état", "très bon", "bon état", "satisfaisant", 
                                "jamais porté", "porté"
                            ];
                            const stateText = uniqueTexts.find(t => 
                                statusKeywords.some(kw => t.toLowerCase().includes(kw))
                            );
                            if (stateText) {
                                const lowState = stateText.toLowerCase();
                                const found = statusKeywords.find(kw => lowState.includes(kw));
                                if (found) {
                                    status = found.charAt(0).toUpperCase() + found.slice(1);
                                }
                            }
                        }

                        // 5. Heuristique "Marque" de secours (V6.3 Ultra-Strict)
                        if (brand === 'N/A' || brand.toLowerCase().includes('enlevé')) {
                             const ignored = ['vinted', 'enlevé', 'nouveau', 'neuf', '€', 'recommandé', 'boosté', 'protection', 'avis', 'favori'];
                             const potentialBrand = uniqueTexts.find(t => {
                                 const low = t.toLowerCase();
                                 if (t.length < 2 || t.length > 25) return false;
                                 if (ignored.some(i => low.includes(i))) return false;
                                 if (/(neuf|état|porté|taille|size)/i.test(low)) return false;
                                 if (/^(XS|S|M|L|XL|XXL|[0-9]{2})$/i.test(t)) return false;
                                 if (t.includes('€')) return false;
                                 return true;
                             });
                             if (potentialBrand) brand = potentialBrand;
                        }

                        // 6. Nettoyage final du Titre (V8.2 AGRESSIF)
                        title = title.replace(/enlevé/gi, '').replace(/nouveau/gi, '').replace(/!/g, '').replace(/\\s*,\\s*$/, '').trim();
                        title = title.replace(/\\s{2,}/g, ' ');
                        if (!title || title.length < 3) title = 'Maillot ASSE';

                        const imgEl = el.querySelector('img');
                        const photo = imgEl?.src || '';
                        
                        items.push({
                            id: itemId,
                            title: title,
                            price: price,
                            size: size,
                            brand: brand,
                            status: status,
                            url: url,
                            photo: photo
                        });

                    } catch (e) {
                         // Silent
                    }
                });
                return items;
            }
        """)
        return items
    except Exception as e:
        log(f"❌ Erreur extraction liste: {e}")
        return []

def send_discord_alert(context, item):
    """Envoie une alerte Discord intelligente (fallback liste)"""
    if not DISCORD_WEBHOOK_URL: return

    # 1. On essaie d'avoir les détails riches (Photos + Desc)
    # Mais on ne fait plus confiance au brand/size du scraping détail s'il échoue
    # On garde les infos "liste" (item) comme base solide
    
    details = {"description": "", "photos": [], "brand": "N/A", "size": "N/A", "status": "N/A"}
    try:
        detail_page = context.new_page()
        detail_page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        details = scrape_item_details(detail_page, item['url'])
        detail_page.close()
    except Exception as e:
        log(f"⚠️ Mode Simple (Détails échoués): {e}")

    try:
        # FUSION ET NETTOYAGE (V8.4 TOTAL CLEAN)
        price_raw = item.get('price', 'N/A')
        brand_raw = details['brand'] if details['brand'] != 'N/A' else item.get('brand', 'N/A')
        size_raw = details['size'] if details['size'] != 'N/A' else item.get('size', 'N/A')
        status_raw = details['status'] if details['status'] not in ['N/A', 'Non spécifié'] else item.get('status', 'Non spécifié')
        desc_raw = details['description']
        
        # Photos
        photos = details['photos'] if details['photos'] else ([item['photo']] if item.get('photo') else [])
        
        import re

        # Nettoyage radical
        raw_title_val = clean_text(item.get('title'))
        # Enlever les métadonnées Vinted collées au titre
        clean_title = re.sub(r',\s*(?:marque|brand|taille|size|taglia|talla|état|etat|condition)\s*:.*$', '', raw_title_val, flags=re.IGNORECASE)
        clean_title = re.sub(r'\s*·.*$', '', clean_title)  # Enlève tout après le "·"
        clean_title = re.sub(r'\d+[,\.]\d+\s*€.*$', '', clean_title)  # Enlève les prix
        clean_title = clean_title.strip()
        final_title = clean_title if clean_title else "Maillot ASSE"

        final_brand = clean_text(brand_raw)
        final_price = clean_text(price_raw)
        # Assainissement du prix si texte composite
        if '·' in final_price or 'incl' in final_price or len(final_price) > 20:
            p_match = re.search(r'(\d+[\d\s]*[.,]\d{2}\s*€|\d+\s*€)', final_price)
            if p_match:
                final_price = p_match.group(1).strip()

        final_size = clean_text(size_raw)
        final_status = clean_text(status_raw)
        final_desc = clean_text(desc_raw)
        
        # Fallback ultime pour la taille : extraction depuis le titre ou la description
        if final_size == 'N/A':
            size_search = re.search(r'\btaille\s*[:\s]\s*([XSLM0-9/ ]+?)(?:\s+[a-z]{3,}|\s*[,;·\n]|\s*$)', raw_title_val, re.IGNORECASE)
            if not size_search and final_desc:
                size_search = re.search(r'\btaille\s*[:\s]\s*([XSLM0-9/ ]+?)(?:\s+[a-z]{3,}|\s*[,;·\n.]|\s*$)', final_desc, re.IGNORECASE)
            if size_search:
                cand = size_search.group(1).strip().upper()
                if cand and len(cand) <= 10:
                    final_size = cand

        # Filtrage des tailles enfants et XS/S
        if FILTER_ADULT_ONLY:
            is_excl, reason = is_excluded_size(final_size, raw_title_val, final_desc)
            if is_excl:
                log(f"🚫 Alerte filtrée ({reason}) : {final_title} (Taille: {final_size})")
                return

        if len(final_desc) > 300: final_desc = final_desc[:300] + "..."

        description_text = f"**{final_price}** | Taille: **{final_size}**\nMarque: **{final_brand}**\nÉtat: {final_status}\n\n{final_desc}"
        
        # Un dernier coup de balai sur l'ensemble du bloc au cas où
        description_text = description_text.replace("  ", " ").strip()

        embed1 = {
            "title": f"🔔 {final_title}",
            "url": item.get('url'),
            "description": description_text,
            "color": 0x09B83E,
            "footer": {"text": f"Vinted Bot • ID: {item.get('id')}"},
            "timestamp": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        }
        
        if photos:
            embed1["image"] = {"url": photos[0]}

        embeds = [embed1]
        for photo_url in photos[1:4]:
            embeds.append({"url": item.get('url'), "image": {"url": photo_url}})

        # EXTRAIT DE DESCRIPTION (COMPLÈTE jusqu'à 1000 caractères)
        desc_preview = final_desc[:1000] if final_desc else "Pas de description"
        if len(final_desc) > 1000:
            desc_preview += "..."

        # TEXTE DE NOTIFICATION (Pour montres et écrans verrouillés)
        notif_text = f"""@everyone | {clean_title}
💰 {final_price} | 📏 {final_size} | 🏷️ {final_brand}
📝 {desc_preview}"""

        payload = {
            "content": notif_text,
            "username": "Vinted ASSE Bot", 
            "avatar_url": "https://images.vinted.net/assets/icon-76x76-precomposed-3e6e4c5f0b8c7e5a5c5e5e5e5e5e5e5e.png", 
            "embeds": embeds
        }
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        log(f"✅ Alerte envoyée #{item.get('id')}")

    except Exception as e:
        log(f"❌ Erreur Discord: {e}")

def watchdog_handler(signum, frame):
    """Tue le bot si un cycle prend trop de temps (Freeze detection)"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] 🚨 WATCHDOG: Bot figé depuis trop longtemps ! Redémarrage forcé...", flush=True)
    os._exit(1) # Sortie brutale pour forcer Railway à relancer

def process_incoming_items(items, seen_ids, last_seen_id, is_initial_cycle, context, source_label="Flux"):
    """Traite une liste d'articles récupérés (filtrage et alertes Discord)"""
    new_found = []
    for item in items:
        if item['id'] not in seen_ids and item['id'] > (last_seen_id - 100000):
            new_found.append(item)
            seen_ids.add(item['id'])
    
    if not new_found:
        return last_seen_id
    
    if is_initial_cycle:
        new_max = max(last_seen_id, max(x['id'] for x in new_found))
        return new_max
    
    log(f"🆕 {len(new_found)} nouvel/nouveaux article(s) détecté(s) ({source_label}) !")
    new_found.sort(key=lambda x: x['id'])
    
    for item in new_found:
        if FILTER_ADULT_ONLY and item.get('size') and item.get('size') != 'N/A':
            is_excl, reason = is_excluded_size(item['size'], item.get('title', ''))
            if is_excl:
                log(f"🚫 Article ignoré dès la liste ({reason}) : '{item.get('title')}' (Taille: {item['size']})")
                continue
        if is_asse_jersey_match(item.get('title')):
            log(f"🎯 MATCH {source_label} : '{item.get('title')}' ({item.get('price')})")
            send_discord_alert(context, item)
    
    new_max = max(last_seen_id, max(x['id'] for x in new_found))
    save_last_seen_id(new_max)
    return new_max

def run_bot():
    """Boucle principale du bot V12.0 SNIPER VINTED EXCLUSIF"""
    log("🚀 [Vinted] Démarrage du bot V12.0 SNIPER (100% Vinted, 0% LeBonCoin)")
    log("⚡ [Vinted] Cadence : Scan ultra-rapide (~4s) + Session persistante + Fuseau Paris garanti")
    
    seen_ids = set()
    last_seen_id = load_last_seen_id()
    is_initial_cycle = True
    
    last_green_check = 0
    last_secondary_check = 0
    priority_query_index = 0
    
    FOOTBALL_CATALOG_URL = "https://www.vinted.fr/catalog?catalog_ids[]=3267&order=newest_first"
    
    try:
        while True:
            # 1. Gestion des heures (Europe/Paris garanti)
            paris_now = get_paris_time()
            current_hour = paris_now.hour

            if 1 <= current_hour < 7:
                log(f"🌙 [Vinted] Mode Veille Silencieuse activé ({paris_now.strftime('%H:%M:%S')} heure de Paris). Reprise automatique à 07:00.")
                time.sleep(60)
                continue

            # 2. Démarrage session Playwright persistante
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(
                        headless=True,
                        args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
                    )
                    context = browser.new_context(
                        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        viewport={'width': 1280, 'height': 720},
                        locale='fr-FR',
                        timezone_id='Europe/Paris'
                    )

                    # Bloquer les ressources lourdes (images/CSS/polices) pour RAM et CPU minimaux
                    def block_aggressively(route):
                        if route.request.resource_type in ["image", "stylesheet", "font", "media"]:
                            route.abort()
                        else:
                            route.continue_()
                    context.route("**/*", block_aggressively)

                    page = context.new_page()
                    page.set_default_timeout(20000)

                    session_start_time = time.time()
                    cycle_count = 0

                    while True:
                        now = time.time()
                        cycle_count += 1

                        # Watchdog 3 minutes
                        signal.signal(signal.SIGALRM, watchdog_handler)
                        signal.alarm(180)

                        # Vérification de l'heure de Paris
                        paris_now = get_paris_time()
                        if 1 <= paris_now.hour < 7:
                            log(f"🌙 [Vinted] Passage en Veille Silencieuse ({paris_now.strftime('%H:%M:%S')} heure de Paris).")
                            signal.alarm(0)
                            break

                        # Recyclage préventif mémoire (toutes les 2h ou 1200 scans)
                        if (now - session_start_time) > 7200 or cycle_count > 1200:
                            log("♻️ [Vinted] Recyclage de maintenance de la session Playwright...")
                            signal.alarm(0)
                            break

                        # Choix de la cible pour cette itération :
                        # Alternance : 1 tour sur 2 = Flux Football Direct, 1 tour sur 2 = Recherche Prioritaire texte
                        scan_label = ""
                        target_url = ""

                        # A. Scan Vert (Toutes les 5 minutes)
                        if (now - last_green_check) > 300:
                            scan_label = "Maillot Asse [VERT]"
                            target_url = get_search_url("Maillot Asse", color_id=10)
                            last_green_check = now

                        # B. Scan International (Toutes les 20 minutes)
                        elif (now - last_secondary_check) > 1200:
                            sec_q = SECONDARY_QUERIES[cycle_count % len(SECONDARY_QUERIES)]
                            scan_label = f"Inter '{sec_q}'"
                            target_url = get_search_url(sec_q)
                            if (cycle_count % len(SECONDARY_QUERIES)) == 0:
                                last_secondary_check = now

                        # C. Alternance normale (Flux Direct Foot vs Recherche Prioritaire)
                        elif cycle_count % 2 == 1:
                            scan_label = "Flux Direct Football"
                            target_url = FOOTBALL_CATALOG_URL
                        else:
                            query = PRIORITY_QUERIES[priority_query_index % len(PRIORITY_QUERIES)]
                            priority_query_index += 1
                            scan_label = f"Recherche '{query}'"
                            target_url = get_search_url(query)

                        # Exécution du scan
                        try:
                            page.goto(target_url, wait_until='domcontentloaded', timeout=20000)
                            items = extract_items_from_page(page)
                            log(f"🔎 [Vinted] Scan {scan_label} : {len(items)} annonces analysées")
                            if items:
                                last_seen_id = process_incoming_items(
                                    items, seen_ids, last_seen_id, is_initial_cycle, context, scan_label
                                )
                        except Exception as e:
                            log(f"⚠️ [Vinted] Erreur locale sur {scan_label}: {e}")

                        # Premier cycle terminé
                        is_initial_cycle = False

                        # Nettoyage cache IDs
                        if len(seen_ids) > 2500:
                            seen_ids_list = sorted(list(seen_ids), reverse=True)
                            seen_ids = set(seen_ids_list[:1800])

                        # Désactivation watchdog
                        signal.alarm(0)

                        # Pause aléatoire humaine anti-ban (3.5 à 5.5 secondes)
                        delay = random.uniform(3.5, 5.5)
                        time.sleep(delay)

                    try:
                        browser.close()
                    except Exception:
                        pass

            except Exception as e:
                log(f"🚨 [Vinted] Incident moteur Playwright : {e}. Redémarrage dans 10s...")
                signal.alarm(0)
                time.sleep(10)

    except KeyboardInterrupt:
        log("\n⛔ [Vinted] Arrêt du bot demandé")
    finally:
        log("👋 [Vinted] Bot éteint proprement")

if __name__ == "__main__":
    run_bot()
