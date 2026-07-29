# Hotel Entity Resolution Pipeline: Execution Guide

This document defines the strict engineering constraints for the hotel deduplication and API pipeline. The project uses a two-stage architecture: an offline candidate generation pipeline (to bypass $O(N \times M)$ compute limitations) and a lightweight FastAPI server.

## 1. Project Setup & Configuration

Instruct the agent to initialize the workspace with the following structure:

* **`.env`**: Must contain `GEMINI_API_KEY`.
* **`requirements.txt`**:
```text
pandas
scipy
google-genai
pydantic
fastapi
uvicorn
sentence-transformers
scikit-learn

```



## 2. Phase 1 & 2: Spatial Blocking, TF-IDF Fallback & ML Record Linkage
**File:** `matcher.py`

1.  **Dataset Split:** Load `supplier_a.csv` and `supplier_b.csv`. Split the data into two groups: `has_coords` and `missing_coords`.
2.  **Spatial Candidate Generation:** For `has_coords`, build a `scipy.spatial.KDTree` using Supplier B's coordinates. Query using Supplier A's (~500m radius) to extract Candidate Pool 1.
3.  **TF-IDF Candidate Generation (The Fallback):** For `missing_coords`, use `sklearn.feature_extraction.text.TfidfVectorizer` on a concatenated string of `name + address`. Compute cosine similarity to extract Candidate Pool 2 (pairs with TF-IDF score > 0.6).
4.  **Lexical Clean-up & Star Defense:** Combine both candidate pools. Strip generic prefixes ("Hotel O", "FabHotel"). Discard pairs where `abs(hotel_a.stars - hotel_b.stars) >= 2`.
5.  **Semantic Embeddings:** Use `sentence-transformers/all-MiniLM-L6-v2` to generate embeddings for the cleaned hotel names and calculate cosine similarity.
6.  **The Classifier & Near-Miss Routing:** Calculate a feature array: `[dist_score, string_similarity, embedding_cosine]` (where `dist_score` normalizes `spatial_distance`, defaulting to 0.5 if coordinates are missing). Pass into a weighted heuristic formula to get a `match_confidence` score (0.0 to 1.0).
    *   **Score >= 0.8:** Flag as a canonical match.
    *   **Score 0.4 to 0.79:** Save in a dictionary as `near_misses` linked to the Supplier A ID.

## 3. Phase 3: Batched Room Normalization & Spend Tracking

**File:** `run_normalizer.py`

Use the `google-genai` SDK and `gemini-3.5-flash-lite` to extract structured JSON data from the chaotic room strings.

1. **Updated Pydantic Schema:** Define the strict output structure, ensuring room-level confidence is captured.

```python
from pydantic import BaseModel

class CanonicalRoom(BaseModel):
    canonical_hotel_id: str
    normalized_name: str
    bed_type: str | None
    occupancy: int | None
    view: str | None
    meal_plan: str | None
    supplier_a_room_ids: list[str]
    supplier_b_room_ids: list[str]
    match_confidence: float  # LLM outputs confidence (0.0 to 1.0) for the room merge

class RoomExtraction(BaseModel):
    rooms: list[CanonicalRoom]

```

2. **API Batching & Cost Logging:** Group raw room strings into batches of 25. Enforce `time.sleep(10)` between calls to bypass the free-tier limit of 15 Requests Per Minute. Record token usage to prove sane API spend in the final write-up.
3. **Batch Poison Defense (Recursive Fallback):** Implement a recursive `try/except` block to prevent one corrupted room string from failing 24 healthy hotels.

```python
import time
from google import genai
from google.genai import types

# Initialize SDK (reads GEMINI_API_KEY from .env automatically)
client = genai.Client()

def log_token_usage(usage_metadata):
    """Logs token consumption for the 1-page cost defense write-up."""
    if usage_metadata:
        prompt_tokens = getattr(usage_metadata, 'prompt_token_count', 0)
        candidate_tokens = getattr(usage_metadata, 'candidates_token_count', 0)
        with open("cost_tracker.txt", "a") as f:
            f.write(f"PROMPT_TOKENS:{prompt_tokens},CANDIDATE_TOKENS:{candidate_tokens}\n")

def process_batch(hotel_batch):
    """
    Processes a batch of up to 25 hotels.
    Uses recursive half-splitting if a corrupted string causes an exception.
    """
    try:
        prompt = (
            f"Extract, deduplicate, and normalize the rooms for these hotels. "
            f"Assign a match_confidence score (0.0 to 1.0) for each merged room profile. "
            f"If a room exists in only one supplier, keep it and leave the other ID list empty. "
            f"You MUST return a JSON object with a single root key 'rooms' which contains an array of room objects. "
            f"Each room object MUST have these keys: 'canonical_hotel_id' (string), 'normalized_name' (string), "
            f"'bed_type' (string or null), 'occupancy' (integer or null), 'view' (string or null), "
            f"'meal_plan' (string or null), 'supplier_a_room_ids' (array of strings), "
            f"'supplier_b_room_ids' (array of strings), 'match_confidence' (number 0.0 to 1.0). "
            f"Data: {hotel_batch}"
        )

        response = client.models.generate_content(
            model='gemini-3.5-flash-lite',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0  # Deterministic output
            ),
        )

        # Log token usage for cost reporting
        if hasattr(response, 'usage_metadata'):
            log_token_usage(response.usage_metadata)

        # Enforce rate limit (15 RPM limit)
        time.sleep(10)
        import json
        raw_dict = json.loads(response.text)
        return RoomExtraction(**raw_dict)

    except Exception as e:
        print(f"[Warning] Batch execution failed for size {len(hotel_batch)}: {e}")
        
        # If it's a rate limit error, DO NOT split the batch. Just wait and retry.
        if "429 Too Many Requests" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            print("Rate limit hit! Waiting 30 seconds to cool down...")
            time.sleep(30)
            return process_batch(hotel_batch)
            
        # Base case: single hotel failed completely
        if len(hotel_batch) == 1:
            print(f"[Error] Skipping unparseable hotel: {hotel_batch[0].get('canonical_hotel_id')}")
            return None

        # Recursive fallback: bisect the batch and try both halves independently
        mid = len(hotel_batch) // 2
        time.sleep(7)  # Throttle before retrying
        
        left_results = process_batch(hotel_batch[:mid])
        right_results = process_batch(hotel_batch[mid:])

        # Combine results safely from successful sub-batches
        combined_rooms = []
        if left_results and hasattr(left_results, 'rooms'):
            combined_rooms.extend(left_results.rooms)
        if right_results and hasattr(right_results, 'rooms'):
            combined_rooms.extend(right_results.rooms)

        return RoomExtraction(rooms=combined_rooms)

```



## 4. Phase 4: Artifact Compilation
**File:** `build_db.py`

Merge the deduplicated amenities, the parsed JSON room data, and the supplier provenance links into `canonical_hotels.json`. 

**Data Contract Enforcement:**
1. **Deterministic IDs:** Assign globally consistent canonical IDs natively (`CANONICAL-{id_a}`) to prevent index-shift cache corruption.
2. **Confidence Stripping:** For exclusive, single-supplier rooms, forcibly set `match_confidence: null` to reflect that no merge occurred.
3. **Near Miss Injection:** For every canonical hotel, check the `near_misses` dictionary from Phase 2. If this hotel had any pairs that scored between 0.4 and 0.79, inject a `"near_miss_candidates": [{supplier_b_id, score, name}, ...]` array into its final JSON object. This guarantees the `/hotels/{id}` endpoint natively serves the near-misses requirement.

## 5. Phase 5: API & Deployment

**File:** `main.py`
**File:** `Dockerfile` & `docker-compose.yml`

Instruct the Antigravity agent to generate the serving layer as an Artifact.

1. **FastAPI App:** On startup, read `canonical_hotels.json` into memory.
2. **Endpoints:**
* `GET /hotels?search=query` (Return list of basic hotel details matching the query).
* `GET /hotels/{id}` (Return deep payload including normalized rooms and confidence scores).


3. **Dockerization:** Use a slim Python 3.11 base image. Expose port `8000`. The `docker-compose.yml` must execute `uvicorn main:app --host 0.0.0.0` so the reviewer can launch the entire project with `docker compose up --build`.