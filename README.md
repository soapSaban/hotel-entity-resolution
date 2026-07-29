# Hotel Entity Resolution API
[![CI Pipeline](https://github.com/soapSaban/hotel-app/actions/workflows/ci.yml/badge.svg)](https://github.com/soapSaban/hotel-app/actions/workflows/ci.yml)

This repository contains a full pipeline and API for resolving and merging chaotic hotel supplier feeds into a clean, canonical data layer.

It utilizes an offline processing pipeline that leverages Spatial KD-Trees, TF-IDF string matching, and a Machine Learning classifier for entity resolution, followed by an LLM-driven schema normalizer for room deduplication.

## Quick Start (Running the Application)

The architecture is split cleanly into two Docker services to ensure lightning-fast boot times for the API, while preserving the heavy offline Machine Learning pipeline for reproducibility.

### 1. Boot the API & UI (Instant)
To launch the FastAPI server and the interactive frontend UI using the pre-computed canonical database:

```bash
docker compose up --build api
```
The server will boot instantly on port `8000`. Once the container is running, open `http://localhost:8000/` in your browser to test the endpoints via the interactive UI.

### 2. Re-run the Data Pipeline (Optional)
If you wish to re-run the Entity Resolution and LLM normalizer pipeline from scratch against the raw CSVs, run:

```bash
docker compose run --build pipeline
```
This builds a secondary container with heavy ML dependencies (PyTorch, MiniLM) and sequentially executes `matcher.py`, `run_normalizer.py`, and `build_db.py`. It will safely output new checkpoints into `data/checkpoints/` and regenerate `canonical_hotels.json`.

**Note:** To run the pipeline, you must create a `.env` file in the root directory containing `GEMINI_API_KEY="your_key"`. The API server does not require this key, as it reads from the static artifact.

---

## API Contract & Endpoints

### 1. Search Hotels
**Endpoint:** `GET /hotels?search={query}`

Returns a list of shallow canonical hotel records matching the search query across names and addresses. If no query is provided, it returns a default list of up to 50 hotels.

**Example Request:**
```bash
curl "http://localhost:8000/hotels?search=taj"
```

**Example Response:**
```json
{
  "results": [
    {
      "id": "CANONICAL-A-97677",
      "name": "Taj MG Road, Bengaluru",
      "address": "41/3 MG Road, Bengaluru, Karnataka, 560001, India",
      "stars": 5.0,
      "match_confidence": 0.81103
    }
  ]
}
```

### 2. Get Deep Canonical Payload
**Endpoint:** `GET /hotels/{id}`

Returns the authoritative, fully-merged canonical record for a specific hotel. This payload contains the deduplicated amenities, source supplier provenance, perfectly structured and normalized room options, and any near-miss candidates identified by the ML classifier.

**Example Request:**
```bash
curl "http://localhost:8000/hotels/CANONICAL-A-31392"
```

**Example Response:**
```json
{
  "id": "CANONICAL-A-31392",
  "name": "Treebo Edha Suites Koramangala",
  "address": "# 24, Intermediate Ring Road, Koramangala, 560047 Bangalore, India",
  "lat": 12.93817,
  "lon": 77.63055,
  "stars": 3.0,
  "amenities": [
    "accessible facilities",
    "air conditioning",
    "fitness center",
    "laundry facilities",
    "laundry service",
    "luggage storage",
    "multilingual staff",
    "newspaper",
    "parking",
    "restaurant",
    "room service",
    "smoking area",
    "wifi"
  ],
  "images": [
    "https://images.oyoroomscdn.com/uploads/hotel_image/105749/large/5e05df84b80a6538.jpg",
    "https://images.oyoroomscdn.com/uploads/hotel_image/105749/large/c5332fc3ce5cdba0.jpg"
  ],
  "supplier_a_id": "A-31392",
  "supplier_b_id": "B-25528",
  "match_confidence": 0.98717,
  "rooms": [
    {
      "canonical_hotel_id": "CANONICAL-A-31392",
      "normalized_name": "Deluxe Single Use",
      "bed_type": null,
      "occupancy": 1,
      "view": null,
      "meal_plan": null,
      "supplier_a_room_ids": [],
      "supplier_b_room_ids": ["RB-37789"],
      "match_confidence": null
    }
  ],
  "near_miss_candidates": [
    {
      "supplier_b_id": "B-65243",
      "name": "Tulip Inn Koramangala",
      "score": 0.46000
    }
  ]
}
```
