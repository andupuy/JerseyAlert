// ============================================================================
// GROUNDHOPPING TRACKER - APPLICATION JAVASCRIPT
// ============================================================================

// === DONNÉES ET ÉTAT ===
let matches = [];
let currentFilter = 'all';

// === INITIALISATION ===
document.addEventListener('DOMContentLoaded', () => {
    loadMatches();
    initializeEventListeners();
    updateUI();

    // Ajouter des données d'exemple si vide
    if (matches.length === 0) {
        addSampleData();
    }
});

// === CHARGEMENT DES DONNÉES ===
function loadMatches() {
    const stored = localStorage.getItem('groundhopping_matches');
    if (stored) {
        matches = JSON.parse(stored);
    }
}

function saveMatches() {
    localStorage.setItem('groundhopping_matches', JSON.stringify(matches));
}

// === EVENT LISTENERS ===
function initializeEventListeners() {
    // Bouton d'ajout de match
    document.getElementById('addMatchBtn').addEventListener('click', openAddMatchModal);

    // Fermeture des modales
    document.getElementById('closeAddModal').addEventListener('click', closeAddMatchModal);
    document.getElementById('cancelAddBtn').addEventListener('click', closeAddMatchModal);
    document.getElementById('closeDetailsModal').addEventListener('click', closeMatchDetailsModal);
    document.getElementById('closeStatsModal').addEventListener('click', closeStatsModal);

    // Fermeture au clic sur l'overlay
    document.querySelectorAll('.modal-overlay').forEach(overlay => {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                closeAllModals();
            }
        });
    });

    // Formulaire d'ajout
    document.getElementById('addMatchForm').addEventListener('submit', handleAddMatch);

    // Bouton statistiques
    document.getElementById('statsBtn').addEventListener('click', openStatsModal);

    // Recherche
    document.getElementById('searchInput').addEventListener('input', handleSearch);

    // Filtres
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', handleFilter);
    });
}

// === GESTION DES MODALES ===
function openAddMatchModal() {
    document.getElementById('addMatchModal').classList.add('show');
    document.getElementById('matchDate').valueAsDate = new Date();
}

function closeAddMatchModal() {
    document.getElementById('addMatchModal').classList.remove('show');
    document.getElementById('addMatchForm').reset();
}

function closeMatchDetailsModal() {
    document.getElementById('matchDetailsModal').classList.remove('show');
}

function closeStatsModal() {
    document.getElementById('statsModal').classList.remove('show');
}

function closeAllModals() {
    document.querySelectorAll('.modal').forEach(modal => {
        modal.classList.remove('show');
    });
}

// === AJOUT D'UN MATCH ===
function handleAddMatch(e) {
    e.preventDefault();

    const match = {
        id: Date.now(),
        homeTeam: document.getElementById('homeTeam').value,
        awayTeam: document.getElementById('awayTeam').value,
        homeScore: parseInt(document.getElementById('homeScore').value),
        awayScore: parseInt(document.getElementById('awayScore').value),
        date: document.getElementById('matchDate').value,
        competition: document.getElementById('competition').value,
        stadium: document.getElementById('stadium').value,
        city: document.getElementById('city').value,
        country: document.getElementById('country').value,
        attendance: document.getElementById('attendance').value || null,
        notes: document.getElementById('notes').value || '',
        addedAt: new Date().toISOString()
    };

    matches.unshift(match);
    saveMatches();
    closeAddMatchModal();
    updateUI();
    showToast('Match ajouté avec succès !');
}

// === SUPPRESSION D'UN MATCH ===
function deleteMatch(matchId) {
    if (confirm('Êtes-vous sûr de vouloir supprimer ce match ?')) {
        matches = matches.filter(m => m.id !== matchId);
        saveMatches();
        updateUI();
        closeMatchDetailsModal();
        showToast('Match supprimé');
    }
}

// === AFFICHAGE DES MATCHS ===
function updateUI() {
    updateStats();
    displayMatches();
}

function displayMatches() {
    const matchesList = document.getElementById('matchesList');
    const emptyState = document.getElementById('emptyState');
    const matchCount = document.getElementById('matchCount');

    // Filtrer les matchs
    let filteredMatches = matches;

    // Filtre par compétition
    if (currentFilter !== 'all') {
        filteredMatches = matches.filter(m => {
            if (currentFilter === 'ligue1') return m.competition === 'ligue1';
            if (currentFilter === 'coupe') return m.competition.includes('coupe');
            if (currentFilter === 'europe') return m.competition.includes('league');
            return true;
        });
    }

    // Filtre par recherche
    const searchTerm = document.getElementById('searchInput').value.toLowerCase();
    if (searchTerm) {
        filteredMatches = filteredMatches.filter(m =>
            m.homeTeam.toLowerCase().includes(searchTerm) ||
            m.awayTeam.toLowerCase().includes(searchTerm) ||
            m.stadium.toLowerCase().includes(searchTerm) ||
            m.city.toLowerCase().includes(searchTerm)
        );
    }

    // Mise à jour du compteur
    matchCount.textContent = `${filteredMatches.length} match${filteredMatches.length > 1 ? 's' : ''}`;

    // Affichage
    if (filteredMatches.length === 0) {
        matchesList.innerHTML = '';
        emptyState.classList.add('show');
    } else {
        emptyState.classList.remove('show');
        matchesList.innerHTML = filteredMatches.map(match => createMatchCard(match)).join('');

        // Ajouter les event listeners
        document.querySelectorAll('.match-card').forEach(card => {
            card.addEventListener('click', () => {
                const matchId = parseInt(card.dataset.matchId);
                showMatchDetails(matchId);
            });
        });
    }
}

function createMatchCard(match) {
    const date = new Date(match.date);
    const formattedDate = date.toLocaleDateString('fr-FR', {
        day: 'numeric',
        month: 'long',
        year: 'numeric'
    });

    const competitionLabels = {
        'ligue1': 'Ligue 1',
        'ligue2': 'Ligue 2',
        'coupe-france': 'Coupe de France',
        'coupe-ligue': 'Coupe de la Ligue',
        'champions-league': 'Champions League',
        'europa-league': 'Europa League',
        'autre': 'Autre'
    };

    const totalGoals = match.homeScore + match.awayScore;

    return `
        <div class="match-card" data-match-id="${match.id}">
            <div class="match-header">
                <span class="match-date">📅 ${formattedDate}</span>
                <span class="match-competition">${competitionLabels[match.competition] || match.competition}</span>
            </div>
            <div class="match-teams">
                <div class="team">
                    <div class="team-name">${match.homeTeam}</div>
                    <div class="team-score">${match.homeScore}</div>
                </div>
                <div class="match-separator">-</div>
                <div class="team">
                    <div class="team-name">${match.awayTeam}</div>
                    <div class="team-score">${match.awayScore}</div>
                </div>
            </div>
            <div class="match-info">
                <div class="match-info-item">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
                        <circle cx="12" cy="10" r="3"/>
                    </svg>
                    ${match.stadium}
                </div>
                <div class="match-info-item">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <circle cx="12" cy="12" r="10"/>
                        <polyline points="12 6 12 12 16 14"/>
                    </svg>
                    ${totalGoals} but${totalGoals > 1 ? 's' : ''}
                </div>
            </div>
        </div>
    `;
}

// === DÉTAILS D'UN MATCH ===
function showMatchDetails(matchId) {
    const match = matches.find(m => m.id === matchId);
    if (!match) return;

    const date = new Date(match.date);
    const formattedDate = date.toLocaleDateString('fr-FR', {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
        year: 'numeric'
    });

    const competitionLabels = {
        'ligue1': 'Ligue 1',
        'ligue2': 'Ligue 2',
        'coupe-france': 'Coupe de France',
        'coupe-ligue': 'Coupe de la Ligue',
        'champions-league': 'Champions League',
        'europa-league': 'Europa League',
        'autre': 'Autre'
    };

    const totalGoals = match.homeScore + match.awayScore;

    const content = `
        <div style="padding: 1rem 0;">
            <div style="text-align: center; margin-bottom: 2rem;">
                <div style="font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 0.5rem;">
                    ${formattedDate}
                </div>
                <div style="display: inline-block; padding: 6px 16px; background: rgba(0, 212, 170, 0.1); border: 1px solid rgba(0, 212, 170, 0.3); border-radius: 20px; font-size: 0.875rem; color: var(--primary); font-weight: 600; margin-bottom: 1.5rem;">
                    ${competitionLabels[match.competition] || match.competition}
                </div>
                
                <div style="display: flex; align-items: center; justify-content: space-around; margin: 2rem 0;">
                    <div style="flex: 1; text-align: center;">
                        <div style="font-size: 1.25rem; font-weight: 600; margin-bottom: 0.5rem;">${match.homeTeam}</div>
                        <div style="font-size: 3rem; font-weight: 800; background: linear-gradient(135deg, var(--primary) 0%, var(--accent-blue) 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">${match.homeScore}</div>
                    </div>
                    <div style="font-size: 2rem; color: var(--text-muted); font-weight: 300;">-</div>
                    <div style="flex: 1; text-align: center;">
                        <div style="font-size: 1.25rem; font-weight: 600; margin-bottom: 0.5rem;">${match.awayTeam}</div>
                        <div style="font-size: 3rem; font-weight: 800; background: linear-gradient(135deg, var(--primary) 0%, var(--accent-blue) 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">${match.awayScore}</div>
                    </div>
                </div>
            </div>
            
            <div style="background: var(--bg-card); border-radius: 12px; padding: 1.5rem; margin-bottom: 1rem;">
                <h3 style="font-size: 1rem; font-weight: 700; margin-bottom: 1rem; color: var(--text-secondary);">📍 INFORMATIONS</h3>
                
                <div style="display: grid; gap: 1rem;">
                    <div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.25rem;">Stade</div>
                        <div style="font-weight: 600;">🏟️ ${match.stadium}</div>
                    </div>
                    
                    <div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.25rem;">Ville</div>
                        <div style="font-weight: 600;">📍 ${match.city}, ${match.country}</div>
                    </div>
                    
                    ${match.attendance ? `
                    <div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.25rem;">Affluence</div>
                        <div style="font-weight: 600;">👥 ${parseInt(match.attendance).toLocaleString('fr-FR')} spectateurs</div>
                    </div>
                    ` : ''}
                    
                    <div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.25rem;">Buts marqués</div>
                        <div style="font-weight: 600;">⚽ ${totalGoals} but${totalGoals > 1 ? 's' : ''}</div>
                    </div>
                </div>
            </div>
            
            ${match.notes ? `
            <div style="background: var(--bg-card); border-radius: 12px; padding: 1.5rem; margin-bottom: 1rem;">
                <h3 style="font-size: 1rem; font-weight: 700; margin-bottom: 1rem; color: var(--text-secondary);">📝 NOTES</h3>
                <div style="color: var(--text-primary); line-height: 1.6;">${match.notes}</div>
            </div>
            ` : ''}
            
            <div style="display: flex; gap: 0.5rem; margin-top: 1.5rem;">
                <button class="btn btn-danger" onclick="deleteMatch(${match.id})" style="flex: 1;">
                    🗑️ Supprimer
                </button>
            </div>
        </div>
    `;

    document.getElementById('matchDetailsContent').innerHTML = content;
    document.getElementById('matchDetailsModal').classList.add('show');
}

// === STATISTIQUES ===
function updateStats() {
    const totalMatches = matches.length;
    const totalGoals = matches.reduce((sum, m) => sum + m.homeScore + m.awayScore, 0);

    // Stades uniques
    const stadiums = new Set(matches.map(m => m.stadium));
    const totalStadiums = stadiums.size;

    // Pays uniques
    const countries = new Set(matches.map(m => m.country));
    const totalCountries = countries.size;

    document.getElementById('totalMatches').textContent = totalMatches;
    document.getElementById('totalStadiums').textContent = totalStadiums;
    document.getElementById('totalCountries').textContent = totalCountries;
    document.getElementById('totalGoals').textContent = totalGoals;
}

function openStatsModal() {
    const stats = calculateDetailedStats();
    const content = generateStatsHTML(stats);

    document.getElementById('statsContent').innerHTML = content;
    document.getElementById('statsModal').classList.add('show');
}

function calculateDetailedStats() {
    const totalMatches = matches.length;
    const totalGoals = matches.reduce((sum, m) => sum + m.homeScore + m.awayScore, 0);

    // Stades
    const stadiumsMap = {};
    matches.forEach(m => {
        if (!stadiumsMap[m.stadium]) {
            stadiumsMap[m.stadium] = {
                name: m.stadium,
                city: m.city,
                country: m.country,
                visits: 0,
                goals: 0
            };
        }
        stadiumsMap[m.stadium].visits++;
        stadiumsMap[m.stadium].goals += m.homeScore + m.awayScore;
    });

    const stadiums = Object.values(stadiumsMap).sort((a, b) => b.visits - a.visits);

    // Compétitions
    const competitionsMap = {};
    matches.forEach(m => {
        if (!competitionsMap[m.competition]) {
            competitionsMap[m.competition] = 0;
        }
        competitionsMap[m.competition]++;
    });

    // Pays
    const countriesMap = {};
    matches.forEach(m => {
        if (!countriesMap[m.country]) {
            countriesMap[m.country] = 0;
        }
        countriesMap[m.country]++;
    });

    const countries = Object.entries(countriesMap)
        .map(([name, count]) => ({ name, count }))
        .sort((a, b) => b.count - a.count);

    // Match avec le plus de buts
    const highestScoringMatch = matches.reduce((max, m) => {
        const goals = m.homeScore + m.awayScore;
        const maxGoals = max.homeScore + max.awayScore;
        return goals > maxGoals ? m : max;
    }, matches[0] || { homeScore: 0, awayScore: 0 });

    return {
        totalMatches,
        totalGoals,
        avgGoals: (totalGoals / totalMatches).toFixed(2),
        stadiums,
        countries,
        highestScoringMatch,
        competitionsMap
    };
}

function generateStatsHTML(stats) {
    const competitionLabels = {
        'ligue1': 'Ligue 1',
        'ligue2': 'Ligue 2',
        'coupe-france': 'Coupe de France',
        'coupe-ligue': 'Coupe de la Ligue',
        'champions-league': 'Champions League',
        'europa-league': 'Europa League',
        'autre': 'Autre'
    };

    return `
        <div style="padding: 1rem 0;">
            <!-- Stats générales -->
            <div style="background: var(--bg-card); border-radius: 12px; padding: 1.5rem; margin-bottom: 1rem;">
                <h3 style="font-size: 1rem; font-weight: 700; margin-bottom: 1rem; color: var(--text-secondary);">📊 STATISTIQUES GÉNÉRALES</h3>
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 1rem;">
                    <div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.25rem;">Total matchs</div>
                        <div style="font-size: 1.5rem; font-weight: 800; background: linear-gradient(135deg, var(--primary) 0%, var(--accent-blue) 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">${stats.totalMatches}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.25rem;">Total buts</div>
                        <div style="font-size: 1.5rem; font-weight: 800; background: linear-gradient(135deg, var(--primary) 0%, var(--accent-blue) 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">${stats.totalGoals}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.25rem;">Moyenne buts/match</div>
                        <div style="font-size: 1.5rem; font-weight: 800; background: linear-gradient(135deg, var(--primary) 0%, var(--accent-blue) 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">${stats.avgGoals}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.25rem;">Stades visités</div>
                        <div style="font-size: 1.5rem; font-weight: 800; background: linear-gradient(135deg, var(--primary) 0%, var(--accent-blue) 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">${stats.stadiums.length}</div>
                    </div>
                </div>
            </div>
            
            <!-- Top stades -->
            <div style="background: var(--bg-card); border-radius: 12px; padding: 1.5rem; margin-bottom: 1rem;">
                <h3 style="font-size: 1rem; font-weight: 700; margin-bottom: 1rem; color: var(--text-secondary);">🏟️ TOP STADES</h3>
                ${stats.stadiums.slice(0, 5).map((stadium, index) => `
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.75rem; background: var(--bg-tertiary); border-radius: 8px; margin-bottom: 0.5rem;">
                        <div>
                            <div style="font-weight: 600;">${index + 1}. ${stadium.name}</div>
                            <div style="font-size: 0.75rem; color: var(--text-secondary);">${stadium.city}, ${stadium.country}</div>
                        </div>
                        <div style="text-align: right;">
                            <div style="font-weight: 700; color: var(--primary);">${stadium.visits} visite${stadium.visits > 1 ? 's' : ''}</div>
                            <div style="font-size: 0.75rem; color: var(--text-secondary);">${stadium.goals} buts</div>
                        </div>
                    </div>
                `).join('')}
            </div>
            
            <!-- Pays visités -->
            <div style="background: var(--bg-card); border-radius: 12px; padding: 1.5rem; margin-bottom: 1rem;">
                <h3 style="font-size: 1rem; font-weight: 700; margin-bottom: 1rem; color: var(--text-secondary);">🌍 PAYS VISITÉS</h3>
                ${stats.countries.map(country => `
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.75rem; background: var(--bg-tertiary); border-radius: 8px; margin-bottom: 0.5rem;">
                        <div style="font-weight: 600;">${country.name}</div>
                        <div style="font-weight: 700; color: var(--primary);">${country.count} match${country.count > 1 ? 's' : ''}</div>
                    </div>
                `).join('')}
            </div>
            
            ${stats.highestScoringMatch.homeTeam ? `
            <!-- Match record -->
            <div style="background: var(--bg-card); border-radius: 12px; padding: 1.5rem;">
                <h3 style="font-size: 1rem; font-weight: 700; margin-bottom: 1rem; color: var(--text-secondary);">🔥 MATCH LE PLUS PROLIFIQUE</h3>
                <div style="text-align: center;">
                    <div style="font-size: 1.25rem; font-weight: 600; margin-bottom: 0.5rem;">
                        ${stats.highestScoringMatch.homeTeam} ${stats.highestScoringMatch.homeScore} - ${stats.highestScoringMatch.awayScore} ${stats.highestScoringMatch.awayTeam}
                    </div>
                    <div style="font-size: 2rem; font-weight: 800; background: linear-gradient(135deg, var(--primary) 0%, var(--accent-blue) 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
                        ${stats.highestScoringMatch.homeScore + stats.highestScoringMatch.awayScore} buts
                    </div>
                    <div style="font-size: 0.875rem; color: var(--text-secondary); margin-top: 0.5rem;">
                        ${new Date(stats.highestScoringMatch.date).toLocaleDateString('fr-FR')} - ${stats.highestScoringMatch.stadium}
                    </div>
                </div>
            </div>
            ` : ''}
        </div>
    `;
}

// === FILTRES ET RECHERCHE ===
function handleFilter(e) {
    document.querySelectorAll('.filter-btn').forEach(btn => btn.classList.remove('active'));
    e.target.classList.add('active');
    currentFilter = e.target.dataset.filter;
    displayMatches();
}

function handleSearch() {
    displayMatches();
}

// === NOTIFICATIONS ===
function showToast(message) {
    const toast = document.getElementById('toast');
    const toastMessage = document.getElementById('toastMessage');

    toastMessage.textContent = message;
    toast.classList.add('show');

    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

// === DONNÉES D'EXEMPLE ===
function addSampleData() {
    const sampleMatches = [
        {
            id: Date.now() + 1,
            homeTeam: 'AS Saint-Étienne',
            awayTeam: 'Olympique de Marseille',
            homeScore: 1,
            awayScore: 0,
            date: '2023-10-18',
            competition: 'ligue1',
            stadium: 'Stade Geoffroy-Guichard',
            city: 'Saint-Étienne',
            country: 'France',
            attendance: '28000',
            notes: 'Ambiance incroyable ! Victoire importante contre l\'OM.',
            addedAt: new Date().toISOString()
        },
        {
            id: Date.now() + 2,
            homeTeam: 'Paris Saint-Germain',
            awayTeam: 'AS Saint-Étienne',
            homeScore: 3,
            awayScore: 1,
            date: '2023-09-15',
            competition: 'ligue1',
            stadium: 'Parc des Princes',
            city: 'Paris',
            country: 'France',
            attendance: '47000',
            notes: 'Premier match au Parc des Princes. Stade magnifique !',
            addedAt: new Date().toISOString()
        },
        {
            id: Date.now() + 3,
            homeTeam: 'Olympique Lyonnais',
            awayTeam: 'AS Saint-Étienne',
            homeScore: 2,
            awayScore: 2,
            date: '2023-11-05',
            competition: 'ligue1',
            stadium: 'Groupama Stadium',
            city: 'Lyon',
            country: 'France',
            attendance: '58000',
            notes: 'Derby ! Ambiance de folie, match nul spectaculaire.',
            addedAt: new Date().toISOString()
        }
    ];

    matches = sampleMatches;
    saveMatches();
    updateUI();
}
