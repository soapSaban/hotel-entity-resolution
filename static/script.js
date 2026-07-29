const searchInput = document.getElementById('searchInput');
const searchBtn = document.getElementById('searchBtn');
const resultsContainer = document.getElementById('resultsContainer');
const detailView = document.getElementById('detailView');
const detailContent = document.getElementById('detailContent');
const backBtn = document.getElementById('backBtn');
const loader = document.getElementById('loader');

// Base URL for API
const API_BASE = '';

// Event Listeners
searchBtn.addEventListener('click', () => performSearch(searchInput.value));
searchInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') performSearch(searchInput.value);
});
backBtn.addEventListener('click', showListView);

// Initial load
performSearch('');

async function performSearch(query) {
    showLoader();
    try {
        const res = await fetch(`${API_BASE}/hotels?search=${encodeURIComponent(query)}`);
        const data = await res.json();
        renderResults(data.results);
    } catch (err) {
        console.error("Failed to search hotels", err);
        resultsContainer.innerHTML = '<p>Error loading hotels. Make sure the backend is running.</p>';
    }
    hideLoader();
}

function renderResults(hotels) {
    resultsContainer.innerHTML = '';
    if (!hotels || hotels.length === 0) {
        resultsContainer.innerHTML = '<p>No hotels found.</p>';
        return;
    }
    
    hotels.forEach(hotel => {
        const card = document.createElement('div');
        card.className = 'hotel-card';
        card.onclick = () => fetchHotelDetails(hotel.id);
        
        card.innerHTML = `
            <div class="hotel-name">${hotel.name}</div>
            <div class="hotel-address">${hotel.address}</div>
            <div class="hotel-meta">
                <span class="stars">★ ${hotel.stars}</span>
                ${hotel.match_confidence !== null 
                    ? `<span class="confidence">${(hotel.match_confidence * 100).toFixed(1)}% Match</span>` 
                    : `<span class="confidence" style="background: #e0e0e0; color: #424242;">Standalone</span>`}
            </div>
        `;
        resultsContainer.appendChild(card);
    });
}

async function fetchHotelDetails(id) {
    showLoader();
    resultsContainer.classList.add('hidden');
    
    try {
        const res = await fetch(`${API_BASE}/hotels/${id}`);
        const data = await res.json();
        renderDetailView(data);
    } catch (err) {
        console.error("Failed to fetch hotel details", err);
        showListView();
    }
    hideLoader();
}

function renderDetailView(hotel) {
    let html = `
        <div class="detail-header">
            <h1 class="detail-title">${hotel.name}</h1>
            <p class="hotel-address">${hotel.address} • ★ ${hotel.stars}</p>
            <div style="margin-top: 1rem;">
                ${hotel.supplier_a_id ? `<span class="supplier-badge prov-a">Supplier A: ${hotel.supplier_a_id}</span>` : ''}
                ${hotel.supplier_b_id ? `<span class="supplier-badge prov-b">Supplier B: ${hotel.supplier_b_id}</span>` : ''}
            </div>
        </div>
    `;

    // Images Carousel
    if (hotel.images && hotel.images.length > 0) {
        html += `<div class="image-gallery">`;
        hotel.images.forEach(img => {
            html += `<img src="${img}" class="gallery-img" alt="Hotel Image" onerror="this.style.display='none'">`;
        });
        html += `</div>`;
    }

    // Amenities
    if (hotel.amenities && hotel.amenities.length > 0) {
        html += `<h2 class="section-title">Amenities</h2><div class="amenities-container">`;
        hotel.amenities.forEach(am => {
            html += `<span class="amenity-chip">${am}</span>`;
        });
        html += `</div>`;
    }

    // Rooms Table
    // Filter to only show rooms that are actually being compared (exist in both suppliers)
    const comparedRooms = hotel.rooms ? hotel.rooms.filter(r => r.supplier_a_room_ids?.length > 0 && r.supplier_b_room_ids?.length > 0) : [];
    const exclusiveRooms = hotel.rooms ? hotel.rooms.filter(r => !(r.supplier_a_room_ids?.length > 0 && r.supplier_b_room_ids?.length > 0)) : [];
    
    if (comparedRooms && comparedRooms.length > 0) {
        html += `<h2 class="section-title">Rooms (Merged & Compared by LLM)</h2>
        <div class="table-wrapper">
            <table>
                <thead>
                    <tr>
                        <th>Normalized Name</th>
                        <th>Bed Type</th>
                        <th>Occupancy</th>
                        <th>Provenance (Compared IDs)</th>
                        <th>Confidence (LLM)</th>
                    </tr>
                </thead>
                <tbody>
        `;
        comparedRooms.forEach(room => {
            let provHtml = '';
            (room.supplier_a_room_ids || []).forEach(id => provHtml += `<span class="supplier-badge prov-a">${id}</span>`);
            (room.supplier_b_room_ids || []).forEach(id => provHtml += `<span class="supplier-badge prov-b">${id}</span>`);
            
            let confHtml = '';
            if (room.match_confidence >= 0.95) {
                confHtml = `<span style="color: #2e7d32; font-weight: bold;">${(room.match_confidence * 100).toFixed(1)}%</span>`;
            } else {
                confHtml = `<span style="color: #d84315; font-weight: bold;">${(room.match_confidence * 100).toFixed(1)}%</span>`;
            }
            
            html += `
                <tr>
                    <td><strong>${room.normalized_name}</strong></td>
                    <td>${room.bed_type || '-'}</td>
                    <td>${room.occupancy || '-'}</td>
                    <td>${provHtml || '-'}</td>
                    <td>${confHtml}</td>
                </tr>
            `;
        });
        html += `</tbody></table></div>`;
    }

    if (exclusiveRooms && exclusiveRooms.length > 0) {
        html += `<h2 class="section-title">Rooms (Exclusive to One Supplier)</h2>
        <div class="table-wrapper">
            <table>
                <thead>
                    <tr>
                        <th>Normalized Name</th>
                        <th>Bed Type</th>
                        <th>Occupancy</th>
                        <th>Provenance (Single ID)</th>
                        <th>Confidence (LLM)</th>
                    </tr>
                </thead>
                <tbody>
        `;
        exclusiveRooms.forEach(room => {
            let provHtml = '';
            (room.supplier_a_room_ids || []).forEach(id => provHtml += `<span class="supplier-badge prov-a">${id}</span>`);
            (room.supplier_b_room_ids || []).forEach(id => provHtml += `<span class="supplier-badge prov-b">${id}</span>`);
            
            // For single-supplier rooms, "match confidence" doesn't logically apply
            let confHtml = `<span style="color: #757575; font-style: italic;">N/A</span>`;
            
            html += `
                <tr>
                    <td><strong>${room.normalized_name}</strong></td>
                    <td>${room.bed_type || '-'}</td>
                    <td>${room.occupancy || '-'}</td>
                    <td>${provHtml || '-'}</td>
                    <td>${confHtml}</td>
                </tr>
            `;
        });
        html += `</tbody></table></div>`;
    }

    // Near Misses
    if (hotel.near_miss_candidates && hotel.near_miss_candidates.length > 0) {
        html += `<h2 class="section-title">Near Miss Candidates</h2>
        <div class="table-wrapper">
            <table>
                <thead>
                    <tr>
                        <th>Supplier B Name</th>
                        <th>Score</th>
                    </tr>
                </thead>
                <tbody>
        `;
        hotel.near_miss_candidates.forEach(miss => {
            html += `
                <tr>
                    <td>${miss.name} <br><span class="supplier-badge prov-b">${miss.supplier_b_id}</span></td>
                    <td><span class="confidence">${(miss.score * 100).toFixed(1)}%</span></td>
                </tr>
            `;
        });
        html += `</tbody></table></div>`;
    }

    detailContent.innerHTML = html;
    detailView.classList.remove('hidden');
}

function showListView() {
    detailView.classList.add('hidden');
    resultsContainer.classList.remove('hidden');
}

function showLoader() {
    loader.classList.remove('hidden');
}

function hideLoader() {
    loader.classList.add('hidden');
}
