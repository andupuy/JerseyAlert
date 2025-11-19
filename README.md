# Vinted Alert System (Ligue 2)

Ce projet surveille Vinted pour les nouveaux articles "Maillot Asse" et envoie une alerte sur Discord.

## Installation & Déploiement

### 1. Prérequis
- Un compte GitHub.
- Un serveur Discord (pour le Webhook).

### 2. Configuration GitHub
1.  Créez un **nouveau dépôt Public** sur GitHub.
2.  Allez dans **Settings** > **Secrets and variables** > **Actions**.
3.  Ajoutez un secret :
    - Nom : `DISCORD_WEBHOOK_URL`
    - Valeur : Votre URL de Webhook Discord.

### 3. Pousser le code (Terminal)
Ouvrez votre terminal dans ce dossier et lancez :

```bash
# Initialiser Git
git init

# Ajouter les fichiers
git add .

# Faire le premier commit
git commit -m "Initial commit - Vinted Bot"

# Lier à votre dépôt GitHub (remplacez URL_DU_REPO)
git remote add origin URL_DU_REPO

# Pousser
git push -u origin main
```

### 4. Vérification
Allez dans l'onglet **Actions** de votre dépôt GitHub. Vous devriez voir le workflow "Vinted Alert" démarrer.
