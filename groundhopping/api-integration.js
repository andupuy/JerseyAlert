// ============================================================================
// API FOOTBALL INTEGRATION
// Récupération automatique des matchs via API
// ============================================================================

// Configuration de l'API
const API_CONFIG = {
    // Football-Data.org (GRATUIT - 10 requêtes/minute)
    footballData: {
        baseUrl: 'https://api.football-data.org/v4',
        // L'utilisateur devra ajouter sa clé API
        apiKey: localStorage.getItem('football_api_key') || ''
    }
};

// IDs des équipes principales (Football-Data.org)
const TEAM_IDS = {
    // Ligue 1
    'PSG': 524,
    'Paris Saint-Germain': 524,
    'OM': 516,
    'Olympique de Marseille': 516,
    'Marseille': 516,
    'OL': 523,
    'Olympique Lyonnais': 523,
    'Lyon': 523,
    'ASSE': 1063,
    'AS Saint-Étienne': 1063,
    'Saint-Étienne': 1063,
    'LOSC': 521,
    'Lille': 521,
    'Monaco': 548,
    'AS Monaco': 548,
    'Rennes': 576,
    'Stade Rennais': 576,
    'Nice': 522,
    'OGC Nice': 522,
    'Lens': 546,
    'RC Lens': 546,
    'Nantes': 543,
    'FC Nantes': 543,
    'Strasbourg': 576,
    'RC Strasbourg': 576,

    // Premier League
    'Manchester United': 66,
    'Liverpool': 64,
    'Arsenal': 57,
    'Chelsea': 61,
    'Manchester City': 65,
    'Tottenham': 73,

    // La Liga
    'Real Madrid': 86,
    'Barcelona': 81,
    'Atletico Madrid': 78,

    // Bundesliga
    'Bayern Munich': 5,
    'Borussia Dortmund': 4,

    // Serie A
    'Juventus': 109,
    'AC Milan': 98,
    'Inter Milan': 108
};

// IDs des compétitions
const COMPETITION_IDS = {
    'Ligue 1': 2015,
    'Premier League': 2021,
    'La Liga': 2014,
    'Bundesliga': 2002,
    'Serie A': 2019,
    'Champions League': 2001,
    'Europa League': 2146
};

// ============================================================================
// FONCTIONS API
// ============================================================================

/**
 * Récupère tous les matchs d'une équipe pour une saison
 */
async function fetchTeamMatches(teamName, season) {
    const apiKey = API_CONFIG.footballData.apiKey;

    if (!apiKey) {
        throw new Error('Clé API manquante. Veuillez configurer votre clé API Football-Data.org');
    }

    // Trouver l'ID de l'équipe
    const teamId = TEAM_IDS[teamName];
    if (!teamId) {
        throw new Error(`Équipe "${teamName}" non trouvée. Essayez avec le nom complet.`);
    }

    const url = `${API_CONFIG.footballData.baseUrl}/teams/${teamId}/matches?season=${season}`;

    try {
        const response = await fetch(url, {
            headers: {
                'X-Auth-Token': apiKey
            }
        });

        if (!response.ok) {
            if (response.status === 403) {
                throw new Error('Clé API invalide ou non autorisée');
            }
            if (response.status === 429) {
                throw new Error('Limite de requêtes dépassée (10/minute)');
            }
            throw new Error(`Erreur API: ${response.status}`);
        }

        const data = await response.json();
        return data.matches || [];

    } catch (error) {
        console.error('Erreur lors de la récupération des matchs:', error);
        throw error;
    }
}

/**
 * Convertit un match de l'API en format Groundhopping
 */
function convertApiMatchToGroundhopping(apiMatch, attended = false) {
    // Ne convertir que les matchs terminés ou en cours
    if (apiMatch.status !== 'FINISHED' && apiMatch.status !== 'IN_PLAY') {
        return null;
    }

    // Déterminer la compétition
    let competition = 'autre';
    const competitionName = apiMatch.competition.name.toLowerCase();

    if (competitionName.includes('ligue 1')) competition = 'ligue1';
    else if (competitionName.includes('ligue 2')) competition = 'ligue2';
    else if (competitionName.includes('coupe de france')) competition = 'coupe-france';
    else if (competitionName.includes('champions')) competition = 'champions-league';
    else if (competitionName.includes('europa')) competition = 'europa-league';

    return {
        id: Date.now() + Math.random(), // ID unique
        homeTeam: apiMatch.homeTeam.name,
        awayTeam: apiMatch.awayTeam.name,
        homeScore: apiMatch.score.fullTime.home || 0,
        awayScore: apiMatch.score.fullTime.away || 0,
        date: apiMatch.utcDate.split('T')[0],
        competition: competition,
        stadium: apiMatch.venue || 'Stade non spécifié',
        city: apiMatch.homeTeam.name.split(' ').pop(), // Approximation
        country: apiMatch.area.name,
        attendance: apiMatch.attendance || null,
        notes: attended ? 'Match importé automatiquement' : '',
        addedAt: new Date().toISOString(),
        fromApi: true
    };
}

/**
 * Importe les matchs d'une équipe
 */
async function importTeamMatches(teamName, season, onlyAttended = false) {
    try {
        showLoadingOverlay('Récupération des matchs...');

        const apiMatches = await fetchTeamMatches(teamName, season);

        if (apiMatches.length === 0) {
            hideLoadingOverlay();
            showToast('Aucun match trouvé pour cette équipe et cette saison');
            return;
        }

        // Convertir les matchs
        const convertedMatches = apiMatches
            .map(m => convertApiMatchToGroundhopping(m, onlyAttended))
            .filter(m => m !== null);

        hideLoadingOverlay();

        // Afficher la modal de sélection
        showMatchSelectionModal(convertedMatches, teamName, season);

    } catch (error) {
        hideLoadingOverlay();
        showToast(`Erreur: ${error.message}`, 'error');
        console.error(error);
    }
}

/**
 * Affiche la modal de sélection des matchs
 */
function showMatchSelectionModal(apiMatches, teamName, season) {
    const modal = document.getElementById('importMatchesModal');
    const content = document.getElementById('importMatchesContent');

    const html = `
        <div style="padding: 1rem 0;">
            <div style="background: var(--bg-card); border-radius: 12px; padding: 1rem; margin-bottom: 1rem;">
                <h3 style="font-size: 1rem; font-weight: 700; margin-bottom: 0.5rem;">
                    📊 ${apiMatches.length} matchs trouvés
                </h3>
                <p style="color: var(--text-secondary); font-size: 0.875rem;">
                    ${teamName} - Saison ${season}
                </p>
            </div>
            
            <div style="margin-bottom: 1rem;">
                <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer; padding: 0.75rem; background: var(--bg-card); border-radius: 8px;">
                    <input type="checkbox" id="selectAllMatches" style="width: 20px; height: 20px; cursor: pointer;">
                    <span style="font-weight: 600;">Tout sélectionner</span>
                </label>
            </div>
            
            <div style="max-height: 400px; overflow-y: auto;">
                ${apiMatches.map((match, index) => `
                    <label class="import-match-item" data-match-index="${index}" style="display: flex; align-items: center; gap: 0.75rem; padding: 0.75rem; background: var(--bg-tertiary); border-radius: 8px; margin-bottom: 0.5rem; cursor: pointer; transition: all 0.2s;">
                        <input type="checkbox" class="match-checkbox" value="${index}" style="width: 18px; height: 18px; cursor: pointer;">
                        <div style="flex: 1;">
                            <div style="font-weight: 600; margin-bottom: 0.25rem;">
                                ${match.homeTeam} ${match.homeScore} - ${match.awayScore} ${match.awayTeam}
                            </div>
                            <div style="font-size: 0.75rem; color: var(--text-secondary);">
                                📅 ${new Date(match.date).toLocaleDateString('fr-FR')} • 🏟️ ${match.stadium}
                            </div>
                        </div>
                    </label>
                `).join('')}
            </div>
            
            <div style="display: flex; gap: 0.5rem; margin-top: 1.5rem;">
                <button class="btn btn-secondary" onclick="closeImportMatchesModal()" style="flex: 1;">
                    Annuler
                </button>
                <button class="btn btn-primary" onclick="confirmImportMatches()" style="flex: 1;">
                    Importer les matchs sélectionnés
                </button>
            </div>
        </div>
    `;

    content.innerHTML = html;
    modal.classList.add('show');

    // Stocker les matchs pour l'import
    window.pendingImportMatches = apiMatches;

    // Event listener pour "Tout sélectionner"
    document.getElementById('selectAllMatches').addEventListener('change', (e) => {
        document.querySelectorAll('.match-checkbox').forEach(cb => {
            cb.checked = e.target.checked;
        });
    });

    // Event listeners pour les items
    document.querySelectorAll('.import-match-item').forEach(item => {
        item.addEventListener('click', (e) => {
            if (e.target.type !== 'checkbox') {
                const checkbox = item.querySelector('.match-checkbox');
                checkbox.checked = !checkbox.checked;
            }
        });
    });
}

/**
 * Confirme l'import des matchs sélectionnés
 */
function confirmImportMatches() {
    const selectedIndexes = Array.from(document.querySelectorAll('.match-checkbox:checked'))
        .map(cb => parseInt(cb.value));

    if (selectedIndexes.length === 0) {
        showToast('Veuillez sélectionner au moins un match', 'warning');
        return;
    }

    const selectedMatches = selectedIndexes.map(i => window.pendingImportMatches[i]);

    // Ajouter les matchs
    selectedMatches.forEach(match => {
        matches.unshift(match);
    });

    saveMatches();
    updateUI();
    closeImportMatchesModal();

    showToast(`${selectedMatches.length} match(s) importé(s) avec succès !`);
}

/**
 * Ferme la modal d'import
 */
function closeImportMatchesModal() {
    document.getElementById('importMatchesModal').classList.remove('show');
    window.pendingImportMatches = null;
}

/**
 * Affiche/cache l'overlay de chargement
 */
function showLoadingOverlay(message = 'Chargement...') {
    let overlay = document.getElementById('loadingOverlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'loadingOverlay';
        overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.8);
            backdrop-filter: blur(10px);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 9999;
        `;
        overlay.innerHTML = `
            <div style="text-align: center; color: white;">
                <div style="width: 50px; height: 50px; border: 4px solid rgba(255,255,255,0.3); border-top-color: var(--primary); border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 1rem;"></div>
                <div style="font-size: 1.125rem; font-weight: 600;">${message}</div>
            </div>
        `;
        document.body.appendChild(overlay);

        // Ajouter l'animation
        if (!document.getElementById('spinAnimation')) {
            const style = document.createElement('style');
            style.id = 'spinAnimation';
            style.textContent = '@keyframes spin { to { transform: rotate(360deg); } }';
            document.head.appendChild(style);
        }
    }
    overlay.style.display = 'flex';
}

function hideLoadingOverlay() {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
}

/**
 * Ouvre la modal d'import API
 */
function openImportApiModal() {
    const modal = document.getElementById('importApiModal');
    modal.classList.add('show');

    // Pré-remplir la clé API si elle existe
    const savedKey = localStorage.getItem('football_api_key');
    if (savedKey) {
        document.getElementById('apiKey').value = savedKey;
    }
}

/**
 * Ferme la modal d'import API
 */
function closeImportApiModal() {
    document.getElementById('importApiModal').classList.remove('show');
}

/**
 * Gère le formulaire d'import API
 */
function handleImportApi(e) {
    e.preventDefault();

    const apiKey = document.getElementById('apiKey').value.trim();
    const teamName = document.getElementById('importTeamName').value.trim();
    const season = document.getElementById('importSeason').value;

    // Sauvegarder la clé API
    if (apiKey) {
        localStorage.setItem('football_api_key', apiKey);
        API_CONFIG.footballData.apiKey = apiKey;
    }

    closeImportApiModal();

    // Lancer l'import
    importTeamMatches(teamName, season);
}

/**
 * Affiche la liste des équipes disponibles
 */
function showAvailableTeams() {
    const teams = Object.keys(TEAM_IDS).sort();
    const teamsList = teams.join(', ');

    alert(`Équipes disponibles:\n\n${teamsList}\n\nVous pouvez utiliser le nom court (ex: PSG, OM, OL) ou le nom complet.`);
}

// Export des fonctions pour utilisation globale
window.importTeamMatches = importTeamMatches;
window.openImportApiModal = openImportApiModal;
window.closeImportApiModal = closeImportApiModal;
window.handleImportApi = handleImportApi;
window.confirmImportMatches = confirmImportMatches;
window.closeImportMatchesModal = closeImportMatchesModal;
window.showAvailableTeams = showAvailableTeams;
