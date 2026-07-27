const LISTS = [
    { name: "Deportes", url: "https://iptv-org.github.io/iptv/categories/sports.m3u" },
    { name: "Argentina", url: "https://iptv-org.github.io/iptv/countries/ar.m3u" },
    { name: "Brasil", url: "https://iptv-org.github.io/iptv/countries/br.m3u" },
    { name: "Paraguay", url: "https://iptv-org.github.io/iptv/countries/py.m3u" },
    { name: "Uruguay", url: "https://iptv-org.github.io/iptv/countries/uy.m3u" },
    { name: "Chile", url: "https://iptv-org.github.io/iptv/countries/cl.m3u" },
    { name: "Colombia", url: "https://iptv-org.github.io/iptv/countries/co.m3u" },
    { name: "Adultos", url: "https://iptv-org.github.io/iptv/categories/xxx.m3u" },
    { name: "General", url: "https://iptv-org.github.io/iptv/index.category.m3u" }
];

let groupedChannels = {};
let flatList = [];
let currentIndex = 0;
let hlsInstance = null;

const player = document.getElementById("player");
const playerWrapper = document.getElementById("player-wrapper");
const heroSection = document.getElementById("hero-section");
const contentContainer = document.getElementById("content");
const searchInput = document.getElementById("search");
const statusText = document.getElementById("status");

async function init() {
    statusText.innerText = "Cargando listas...";
    groupedChannels = {};
    flatList = [];

    for (const list of LISTS) {
        try {
            const res = await fetch(list.url);
            if (!res.ok) continue;
            const text = await res.text();
            parseM3U(text, list.name);
        } catch (error) {
            console.error(`Error loading ${list.name}:`, error);
        }
    }

    render(groupedChannels);
    statusText.innerText = `Conectado (${flatList.length} canales)`;
    
    // Setup Search
    searchInput.addEventListener("input", (e) => {
        const term = e.target.value.toLowerCase();
        const filtered = filterChannels(term);
        render(filtered);
    });
}

function parseM3U(data, listName) {
    const lines = data.split("\n");

    for (let i = 0; i < lines.length; i++) {
        if (lines[i].startsWith("#EXTINF")) {
            const name = lines[i].split(",")[1]?.trim() || "Canal Desconocido";
            const logo = (lines[i].match(/tvg-logo="(.*?)"/)||[])[1] || "";
            let group = (lines[i].match(/group-title="(.*?)"/)||[])[1] || listName;
            const url = lines[i+1]?.trim();

            if (url && url.startsWith("http")) {
                const channel = { name, logo, group, url };
                if (!groupedChannels[group]) groupedChannels[group] = [];
                
                // Avoid duplicates by URL
                if (!flatList.some(c => c.url === url)) {
                    groupedChannels[group].push(channel);
                    flatList.push(channel);
                }
            }
        }
    }
}

function filterChannels(term) {
    if (!term) return groupedChannels;
    
    let filtered = {};
    for (let group in groupedChannels) {
        const matches = groupedChannels[group].filter(c => 
            c.name.toLowerCase().includes(term) || 
            group.toLowerCase().includes(term)
        );
        if (matches.length > 0) filtered[group] = matches;
    }
    return filtered;
}

function render(data) {
    contentContainer.innerHTML = "";
    
    const groups = Object.keys(data).sort();
    
    if (groups.length === 0) {
        contentContainer.innerHTML = `<div style="text-align:center; padding:50px; opacity:0.5;">No se encontraron canales.</div>`;
        return;
    }

    groups.forEach(groupName => {
        const row = document.createElement("div");
        row.className = "row";
        
        row.innerHTML = `
            <h2>${groupName} <span>(${data[groupName].length})</span></h2>
            <div class="channels"></div>
        `;
        
        const channelsDiv = row.querySelector(".channels");
        
        data[groupName].forEach(channel => {
            const card = document.createElement("div");
            card.className = "channel";
            
            card.innerHTML = `
                <div class="channel-img-container">
                    <img src="${channel.logo}" loading="lazy" onerror="this.src='https://via.placeholder.com/100?text=TV'">
                </div>
                <div class="channel-info">
                    <div class="channel-name">${channel.name}</div>
                </div>
            `;
            
            card.onclick = () => playChannel(channel);
            channelsDiv.appendChild(card);
        });
        
        contentContainer.appendChild(row);
    });
}

function playChannel(channel) {
    currentIndex = flatList.findIndex(c => c.url === channel.url);
    
    // Show player, hide hero if it's the first play
    playerWrapper.style.display = "block";
    heroSection.style.display = "none";
    
    // Smooth scroll to top
    window.scrollTo({ top: 0, behavior: 'smooth' });

    play(channel.url);
    
    // Trigger Fullscreen IMMEDIATELY to satisfy browser security
    goFullScreen();
}

function play(url) {
    if (hlsInstance) {
        hlsInstance.destroy();
    }

    if (Hls.isSupported()) {
        hlsInstance = new Hls();
        hlsInstance.loadSource(url);
        hlsInstance.attachMedia(player);
        hlsInstance.on(Hls.Events.MANIFEST_PARSED, function() {
            player.play();
        });
    } else if (player.canPlayType('application/vnd.apple.mpegurl')) {
        // For Safari/iOS native support
        player.src = url;
        player.addEventListener('loadedmetadata', function() {
            player.play();
        });
    }

    // Add controls for easier mobile use
    player.controls = true;
}

function goFullScreen() {
    const video = document.getElementById("player");
    
    // 1. Try official API (Always best if supported)
    try {
        if (video.requestFullscreen) {
            video.requestFullscreen();
        } else if (video.webkitRequestFullscreen) {
            video.webkitRequestFullscreen();
        } else if (video.msRequestFullscreen) {
            video.msRequestFullscreen();
        } else if (video.webkitEnterFullscreen) {
            video.webkitEnterFullscreen();
        }
    } catch (e) {
        console.warn("Fullscreen API failed, falling back to Theater Mode", e);
    }

    // 2. Fallback: Theater Mode (Simulated fullscreen via CSS)
    toggleTheater(true);
}

function toggleTheater(force) {
    const body = document.body;
    if (force === true) {
        body.classList.add("theater-mode");
    } else if (force === false) {
        body.classList.remove("theater-mode");
    } else {
        body.classList.toggle("theater-mode");
    }
}

// Remote / Keyboard controls
document.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight") {
        currentIndex = (currentIndex + 1) % flatList.length;
        playChannel(flatList[currentIndex]);
    } else if (e.key === "ArrowLeft") {
        currentIndex = (currentIndex - 1 + flatList.length) % flatList.length;
        playChannel(flatList[currentIndex]);
    }
});

init();
