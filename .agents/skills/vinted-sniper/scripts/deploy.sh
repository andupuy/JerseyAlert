#!/usr/bin/env bash
set -e

VPS_HOST="root@151.115.67.153"
VPS_DIR="/root/JerseyAlert"
LOCAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"

echo "🚀 [Deploy] Début de la procédure de déploiement sécurisé..."

# 1. Vérification de la syntaxe Python locale
echo "🔍 1. Vérification syntaxique Python..."
python3 -m py_compile "$LOCAL_DIR/vinted_bot_oracle.py"
echo "✅ Syntaxe Python valide !"

# 2. Synchronisation SCP vers le VPS
echo "📤 2. Envoi du fichier vinted_bot_oracle.py vers le VPS ($VPS_HOST)..."
scp "$LOCAL_DIR/vinted_bot_oracle.py" "$VPS_HOST:$VPS_DIR/vinted_bot_oracle.py"

# 3. Redémarrage du service systemd
echo "🔄 3. Redémarrage du service vinted-bot..."
ssh "$VPS_HOST" "systemctl restart vinted-bot.service"

# 4. Vérification de santé (status)
echo "🩺 4. Contrôle du statut du service..."
ssh "$VPS_HOST" "systemctl status vinted-bot.service --no-pager"

echo "✨ Déploiement terminé avec succès !"
