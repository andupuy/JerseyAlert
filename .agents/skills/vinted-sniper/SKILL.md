---
name: vinted-sniper
description: >-
  Specialized assistant for the Vinted ASSE Discord Sniper Bot (JerseyAlert).
  Use this skill whenever auditing an item (why an item triggered an alert or was missed/late),
  deploying code updates to the VPS, checking systemd service health, or maintaining ASSE detection rules
  (players, sponsors, rival clubs, product exclusions).
---

# Vinted Sniper Assistant (JerseyAlert ASSE)

Ce guide opérationnel régit la maintenance, le diagnostic et le déploiement du bot sniper Vinted dédié aux maillots et objets de collection de l'AS Saint-Étienne (ASSE).

---

## 1. Infrastructure & Architecture

| Composant | Détails |
| :--- | :--- |
| **Serveur VPS** | `root@151.115.67.153` (Scaleway Debian) |
| **Dossier distant** | `/root/JerseyAlert` |
| **Dossier local** | `/Users/laismoreno/test dev` |
| **Service Bot Sniper** | `vinted-bot.service` (`vinted_bot_oracle.py`) |
| **Service Dashboard Web** | `vinted-dashboard.service` (`/root/dashboard.py` sur port 80) |
| **Service Tracker Vente** | `vinted-tracker.service` |

---

## 2. Contrôle de Santé Instantané (Healthcheck)

Pour vérifier l'état complet du système en 1 clic :
```bash
python3 ".agents/skills/vinted-sniper/scripts/healthcheck.py"
```
Il vérifie :
* L'état des 3 services systemd (`vinted-bot`, `vinted-tracker`, `vinted-dashboard`).
* La RAM, le Swap et la charge processeur du VPS.
* Le compteur d'erreurs réelles du dashboard.
* La cadence et les timestamps des derniers scans Vinted en direct.

---

## 3. Procédure d'Audit d'une Annonce Vinted

Lorsqu'un utilisateur demande **"Pourquoi j'ai reçu ça ?"** ou signale une annonce ratée / doublée :

1. **Exécuter le script de diagnostic :**
   ```bash
   python3 ".agents/skills/vinted-sniper/scripts/audit_item.py" <ITEM_ID_OU_URL>
   ```
2. **Analyser les 5 points de contrôle :**
   * **Mot-clé maillot :** Présence de `maillot`, `jersey`, `camiseta`, `t-shirt`, etc.
   * **Club concurrent (`is_conflicting_team`) :** Vérifier si un club rival ou étranger est mentionné dans le titre ou la description (ex: Sedan, OM, Lyon, PSG, Betis, etc.).
   * **Signal ASSE (`is_asse_signal`) :** Détection d'un joueur historique (`ASSE_PLAYERS_FULL`), d'un sponsor (`ASSE_SPONSORS_PATTERNS`), ou de la mention explicite `asse` / `saint etienne`.
   * **Exclusion produit / sport (`is_excluded_product`) :** Exclusion des sports US (NBA, basket, NFL), cyclisme, rugby, vêtements d'entraînement (training).
   * **Exclusion taille (`is_excluded_size`) :** Exclusion des tailles enfants (XS, 12 ans, etc.) et tailles non souhaitées.
3. **Fournir un verdict clair :** Expliquer le mécanisme exact qui a validé ou bloqué l'annonce, et proposer le correctif si nécessaire.

---

## 4. Procédure de Déploiement Sécurisé sur le VPS

Ne jamais déployer sans tester la syntaxe locale.

1. **Vérifier et compiler localement :**
   ```bash
   python3 -m py_compile vinted_bot_oracle.py
   ```
2. **Exécuter le script de déploiement automatique :**
   ```bash
   bash ".agents/skills/vinted-sniper/scripts/deploy.sh"
   ```
3. **Vérifier les logs récents du bot :**
   ```bash
   ssh root@151.115.67.153 "journalctl -u vinted-bot.service -n 25 --no-pager"
   ```

---

## 5. Règles Métier de Détection ASSE

### A. Flux Direct Foot (Temps Réel - 90% des scans)
* Balaye le catalogue Vinted football (maillots + t-shirts de sport) trié par nouveautés.
* **Critères stricts :** Mot-clé maillot requis + signal ASSE direct dans le titre + **aucun** club adverse + aucune exclusion taille/sport.

### B. Filet de Sécurité & Collectors (10% des scans)
* Recherche spécifique sur *"Maillot Asse"*, *"Maillot Saint Etienne"*, *"Livre Magic Fans"*, *"SNK Magic Fans"*.
* Scanne à la fois le titre et la description détaillée.
* Vérifie que la couleur verte (`is_green_color`) ou un sponsor historique est bien associé aux mentions plus larges.

### C. Gestion des Clubs Rivaux (`OTHER_TEAMS_PATTERNS`)
* Situé dans `vinted_bot_oracle.py`.
* Doit contenir les clubs français de Ligue 1, Ligue 2, National (ex: Sedan, Tours, Châteauroux, Le Mans, Red Star, Niort).
* **Attention aux doublons de clés dans le dictionnaire :** Toujours vérifier qu'une nouvelle entrée n'écrase pas une règle existante.
