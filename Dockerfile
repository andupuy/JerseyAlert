FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

WORKDIR /app

# Copie des fichiers
COPY requirements.txt .

# Installation des dépendances Python supplémentaires
RUN pip install --no-cache-dir -r requirements.txt

# Copie des scripts du bot (alias multiples pour garantir la compatibilité avec Railway)
COPY vinted_bot_oracle.py .
COPY vinted_bot_oracle.py main.py
COPY vinted_bot_oracle.py vinted_bot.py
COPY leboncoin_bot.py .

# Commande de démarrage
CMD ["python3", "main.py"]
# Fix start command resilience (vinted_bot.py / main.py) 🛡️🚀

