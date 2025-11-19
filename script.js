// Mock Data for Ligue 2
const matches = [
    {
        id: 1,
        homeTeam: { name: "Bordeaux", short: "BOR", color: "#001B50" },
        awayTeam: { name: "St-Étienne", short: "ASSE", color: "#009538" },
        score: { home: 2, away: 1 },
        status: "LIVE",
        time: "78'",
        events: [
            { time: "12'", type: "goal", player: "Vipotnik (BOR)" },
            { time: "45'", type: "card", player: "Briançon (ASSE)" },
            { time: "56'", type: "goal", player: "Sissoko (ASSE)" },
            { time: "75'", type: "goal", player: "Elis (BOR)" }
        ],
        stats: { possession: "55% - 45%", shots: "12 - 8" }
    },
    {
        id: 2,
        homeTeam: { name: "Metz", short: "FCM", color: "#862633" },
        awayTeam: { name: "Guingamp", short: "EAG", color: "#B50B1F" },
        score: { home: 0, away: 0 },
        status: "UPCOMING",
        time: "20:45",
        events: [],
        stats: { possession: "0% - 0%", shots: "0 - 0" }
    },
    {
        id: 3,
        homeTeam: { name: "Bastia", short: "SCB", color: "#004EA2" },
        awayTeam: { name: "Ajaccio", short: "ACA", color: "#EF3E42" },
        score: { home: 1, away: 0 },
        status: "FINISHED",
        time: "FT",
        events: [
            { time: "34'", type: "goal", player: "Alfarela (SCB)" },
            { time: "88'", type: "card", player: "Red Card (ACA)" }
        ],
        stats: { possession: "48% - 52%", shots: "9 - 11" }
    },
    {
        id: 4,
        homeTeam: { name: "Caen", short: "SMC", color: "#EF3E42" },
        awayTeam: { name: "Angers", short: "SCO", color: "#000000" },
        score: { home: 0, away: 2 },
        status: "FINISHED",
        time: "FT",
        events: [
            { time: "22'", type: "goal", player: "Diony (SCO)" },
            { time: "67'", type: "goal", player: "Abdelli (SCO)" }
        ],
        stats: { possession: "60% - 40%", shots: "14 - 6" }
    }
];

// DOM Elements
const matchListEl = document.getElementById('match-list');
const matchDetailEl = document.getElementById('match-detail');
const mainContent = document.getElementById('main-content');
const refreshBtn = document.getElementById('refresh-btn');

// Initialize
function init() {
    renderMatchList();
    
    refreshBtn.addEventListener('click', () => {
        refreshBtn.style.transform = 'rotate(360deg)';
        setTimeout(() => refreshBtn.style.transform = 'none', 500);
        renderMatchList(); // Re-render to simulate refresh
    });
}

// Render Match List
function renderMatchList() {
    matchListEl.innerHTML = '';
    
    matches.forEach(match => {
        const card = document.createElement('div');
        card.className = 'match-card';
        card.onclick = () => showMatchDetail(match);

        const isLive = match.status === 'LIVE';
        const statusClass = isLive ? 'status-live' : (match.status === 'FINISHED' ? 'status-finished' : '');
        const liveDot = isLive ? '<span class="live-dot"></span>' : '';

        card.innerHTML = `
            <div class="match-status ${statusClass}">
                ${liveDot} ${match.status === 'UPCOMING' ? match.time : match.status}
                ${isLive ? `<span style="margin-left:auto; color:var(--accent)">${match.time}</span>` : ''}
            </div>
            <div class="match-teams">
                <div class="team">
                    <div class="team-logo" style="background:${match.homeTeam.color}">${match.homeTeam.short}</div>
                    <span class="team-name">${match.homeTeam.name}</span>
                </div>
                <div class="score-board">
                    ${match.status === 'UPCOMING' ? 'vs' : `${match.score.home} - ${match.score.away}`}
                </div>
                <div class="team">
                    <div class="team-logo" style="background:${match.awayTeam.color}">${match.awayTeam.short}</div>
                    <span class="team-name">${match.awayTeam.name}</span>
                </div>
            </div>
        `;
        matchListEl.appendChild(card);
    });
}

// Show Match Detail
function showMatchDetail(match) {
    matchListEl.classList.remove('active');
    matchListEl.classList.add('hidden');
    
    matchDetailEl.classList.remove('hidden');
    matchDetailEl.classList.add('active');

    const isLive = match.status === 'LIVE';

    matchDetailEl.innerHTML = `
        <div class="detail-header">
            <button class="back-btn" onclick="goBack()">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M19 12H5M12 19l-7-7 7-7"/>
                </svg>
                Retour
            </button>
        </div>

        <div class="match-card" style="cursor:default; transform:none;">
            <div class="match-teams">
                <div class="team">
                    <div class="team-logo" style="background:${match.homeTeam.color}; width:64px; height:64px; font-size:24px;">${match.homeTeam.short}</div>
                    <span class="team-name" style="font-size:16px; margin-top:8px;">${match.homeTeam.name}</span>
                </div>
                <div class="score-board" style="font-size:32px;">
                    ${match.status === 'UPCOMING' ? 'vs' : `${match.score.home} - ${match.score.away}`}
                </div>
                <div class="team">
                    <div class="team-logo" style="background:${match.awayTeam.color}; width:64px; height:64px; font-size:24px;">${match.awayTeam.short}</div>
                    <span class="team-name" style="font-size:16px; margin-top:8px;">${match.awayTeam.name}</span>
                </div>
            </div>
            <div class="match-time">${match.status === 'UPCOMING' ? match.time : (isLive ? match.time : 'Terminé')}</div>
        </div>

        <h3 style="margin: 24px 0 12px 0;">Statistiques</h3>
        <div class="stat-row">
            <span class="stat-label">Possession</span>
            <span class="stat-value">${match.stats.possession}</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">Tirs</span>
            <span class="stat-value">${match.stats.shots}</span>
        </div>

        <h3 style="margin: 24px 0 12px 0;">Temps forts</h3>
        <div class="events-list">
            ${match.events.length > 0 ? match.events.map(e => `
                <div class="event-item">
                    <span class="event-time">${e.time}</span>
                    <span class="event-desc">
                        <strong>${e.type === 'goal' ? '⚽ BUT' : '🟨 CARTON'}</strong> - ${e.player}
                    </span>
                </div>
            `).join('') : '<div style="color:var(--text-secondary); font-style:italic;">Aucun événement majeur</div>'}
        </div>
    `;
}

// Navigation
window.goBack = function() {
    matchDetailEl.classList.remove('active');
    matchDetailEl.classList.add('hidden');
    
    matchListEl.classList.remove('hidden');
    matchListEl.classList.add('active');
};

// Start
init();
