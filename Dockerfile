FROM mcr.microsoft.com/playwright/python:v1.41.0-jammy

WORKDIR /app

# Copie des fichiers
COPY requirements.txt .
COPY vinted_bot_oracle.py main.py

# Installation des dépendances Python supplémentaires
RUN pip install --no-cache-dir -r requirements.txt

# Commande de démarrage
CMD ["python", "main.py"]
# Force Update Sun Dec 28 23:23:38 CET 2025 (Details Fix)
