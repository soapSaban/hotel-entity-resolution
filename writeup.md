# Engineering Write-Up: Architectural Decisions & Trade-Offs

Rather than just summarizing the code, I wanted to walk you through the core engineering decisions, the trade-offs I weighed, and the "why" behind the pipeline design.

### Q: What was your approach and what did you discard?
**What I discarded:** I immediately discarded the idea of an LLM-driven $O(N \times M)$ brute force comparison. Comparing 4,000 Supplier A hotels against 4,000 Supplier B hotels equates to over 13 million pairings. Pushing 13 million pairs through an LLM API would cost thousands of dollars, take weeks to process, and fail constantly due to rate limits. I also discarded binary exact-string matching, as real-world names ("Treebo Edha Suites" vs "Treebo Trend Edha") rarely match perfectly.

**My Approach:** Instead, I built a fast, dual-phase pipeline. Phase 1 bypasses the $O(N \times M)$ problem entirely using spatial indexing (`scipy.spatial.KDTree`) to instantly fetch candidates within a 500-meter radius with near-zero compute. Phase 2 extracts features (spatial distance, TF-IDF string similarity, and MiniLM semantic embeddings) and feeds them into a weighted heuristic classifier to calculate a precise `match_confidence` score. We only invoke the LLM for schema mapping *after* this heavy filtering is complete.

### Q: How does the system handle ambiguous matches or "near-misses"?

A binary true/false match discards valuable intelligence. By utilizing a weighted heuristic scoring system on our feature array (50% semantic cosine, 30% Jaccard string similarity, 20% spatial distance), the system outputs a calibrated probability from 0.0 to 1.0.
* **Score > 0.8:** Automatically merged into a canonical entity.
* **Score 0.4 to 0.79:** Flagged as a "near-miss."
Instead of discarding these, I dynamically inject them into the `near_miss_candidates` array of the final JSON object. When you query the `GET /hotels/{id}` endpoint, the API serves both the canonical hotel and its borderline candidates, enabling seamless human-in-the-loop review for edge cases.

### Q: What was the total API spend in dollars?
By aggressively filtering candidates with offline ML (MiniLM) before hitting the LLM, I compressed the final LLM schema normalization step into just 87 batched API calls via the Gemini free tier. 
**Total API spend: $0.00**. 
The pipeline executes locally in minutes, making it highly scalable, affordable, and fully reproducible for future data drifts without incurring cloud costs.

### Q: How did you handle the fragility of LLM JSON extraction for the room mapping?
Room mapping requires heavy semantic interpretation ("Deluxe, Twin" vs "Twin Deluxe Room w/ Breakfast"). I batched 25 hotels at a time and passed them through Gemini using explicit JSON instructions in the prompt, and enforced the schema post-generation using Pydantic. 

**Defensive Engineering:** To protect against broken JSON schemas or unexpected API drops, I implemented a recursive bisection algorithm. If a batch of 25 fails, the system splits it in half (12 and 13) and retries them independently. This ensures that one corrupted edge-case row never crashes the entire batch or pipeline.

### Q: How did you ensure 1-to-1 matching without duplicate collisions?
Because KD-Trees inherently act as a K-Nearest Neighbor algorithm, multiple Supplier A hotels could theoretically cluster around the same Supplier B hotel, causing many-to-one duplication. 
To mathematically guarantee a 1-to-1 bipartite mapping, the system maintains a globally tracked `seen_a` and `seen_b` hash set. Matches are sorted by absolute global confidence score (descending), ensuring that the highest confidence match is strictly prioritized and claimed first, resolving edge-case overlaps instantly.

### Q: Is there proof of the pipeline's efficiency and defensive error handling?
Yes. I built a custom logger to monitor and track every step of the pipeline execution in real-time. You can inspect the `pipeline_execution.log` file in the root directory to see the step-by-step latency of the ML models and watch the LLM recursive bisection algorithm in action. You can also review `cost_tracker.txt` to see the exact token usage and prove the $0.00 cost efficiency of the LLM phase.
### Q: How did you handle the reality of messy, incomplete data feeds?

Real-world supplier feeds frequently drop critical data. If a hotel had `NaN` or `0.0, 0.0` coordinates, it would immediately crash the `KDTree` spatial index and be lost forever.
Instead of dropping these rows, I built a routing mechanism. Rows missing coordinates bypass the spatial index entirely and are routed to a TF-IDF text vectorizer. This fallback computes cosine similarity across concatenated `name + address` strings, generating a secondary candidate pool. This ensures we achieve maximum recall even when the spatial data is completely corrupted.

### Q: How did you convince yourself the matching works?
I utilized a few layers of defense:
1. **Star-Diff Hard Rejection:** I implemented a hard rejection rule. Even if the ML model thought the names and locations were identical, if both suppliers provided a valid star rating (>0) and `abs(star_diff) >= 2`, the match was instantly rejected.
2. **Endpoint Spot-Checking:** I actively pulled deep payloads from the final `GET /hotels/{id}` API to manually verify that multi-supplier rooms were correctly linked and amenities were perfectly deduplicated. **You can verify this yourself using the auto-generated Swagger UI available at `http://localhost:8000/docs` once the Docker container is running (or by using the custom glassmorphism frontend served at the root `http://localhost:8000/`!).**

### Q: If we scale this to 200,000 hotels across 3 suppliers, what breaks first?
The current architecture will break in two specific places:
1. **The In-Memory API:** `main.py` currently loads the entire `canonical_hotels.json` into a global Python dictionary `db = {}` for lightning-fast responses. At 200k hotels, this will exceed RAM limits. **Fix:** We must migrate the canonical layer to a PostgreSQL database utilizing PostGIS for spatial queries.
2. **The TF-IDF Matrix:** A dense cosine similarity matrix for 200k × 200k strings will OOM (Out of Memory) during Phase 1 fallback generation. **Fix:** We must migrate the string embedding fallback from Scikit-Learn to a dedicated Vector Database (e.g., Elasticsearch, Pinecone, or pgvector).
