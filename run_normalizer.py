import json
import time
import pandas as pd
import os
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from logger import logger, log_latency
from dotenv import load_dotenv

load_dotenv()

class CanonicalRoom(BaseModel):
    canonical_hotel_id: str
    normalized_name: str
    bed_type: str | None = None
    occupancy: int | None = None
    view: str | None = None
    meal_plan: str | None = None
    supplier_a_room_ids: list[str] = Field(default_factory=list)
    supplier_b_room_ids: list[str] = Field(default_factory=list)
    match_confidence: float

class RoomExtraction(BaseModel):
    rooms: list[CanonicalRoom]

# Initialize SDK (reads GEMINI_API_KEY from .env automatically)
try:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY is missing from environment variables.")
    client = genai.Client(api_key=api_key)
except Exception as e:
    logger.error("Failed to initialize Gemini Client. Make sure GEMINI_API_KEY is in .env")
    client = None

def log_token_usage(usage_metadata):
    """Logs token consumption for the 1-page cost defense write-up."""
    if usage_metadata:
        prompt_tokens = getattr(usage_metadata, 'prompt_token_count', 0)
        candidate_tokens = getattr(usage_metadata, 'candidates_token_count', 0)
        with open("cost_tracker.txt", "a") as f:
            f.write(f"PROMPT_TOKENS:{prompt_tokens},CANDIDATE_TOKENS:{candidate_tokens}\n")
        logger.debug(f"Tokens - Prompt: {prompt_tokens}, Candidate: {candidate_tokens}")

def process_batch(hotel_batch):
    """
    Processes a batch of up to 25 hotels.
    Uses recursive half-splitting if a corrupted string causes an exception.
    """
    if not client:
        return None

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
        
        logger.debug(f"Sending batch of {len(hotel_batch)} hotels to Gemini.")

        model_priority = [
            "gemini-3.5-flash-lite",               # New model as requested
            "gemini-1.5-flash-8b",                 # The fastest 'Lite' version
            "gemini-2.0-flash-lite-preview-02-05", # 2.0 Lite preview
            "gemini-1.5-flash",                    # Standard 1.5 flash
            "gemini-2.5-flash"                     # The restrictive 2.5 flash
        ]
        
        response = None
        for m in model_priority:
            try:
                response = client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.0  # Deterministic output
                    ),
                )
                logger.debug(f"Successfully generated content using model: {m}")
                break
            except Exception as e:
                if "404" in str(e):
                    continue  # Model not available, try the next one
                raise e  # It's a 429 or something else, pass it up to the retry logic
                
        if not response:
            raise Exception("404: No valid models found for this API key.")

        # Log token usage for cost reporting
        if hasattr(response, 'usage_metadata'):
            log_token_usage(response.usage_metadata)

        # Enforce rate limit (Gemini free tier allows 15 RPM. 10s sleep = 6 RPM)
        time.sleep(10)
        logger.info(f"Successfully processed batch of {len(hotel_batch)} hotels")
        
        # Parse manually since we used a dict schema instead of Pydantic model
        import json
        raw_dict = json.loads(response.text)
        return RoomExtraction(**raw_dict)

    except Exception as e:
        error_msg = str(e)
        logger.warning(f"Batch execution failed for size {len(hotel_batch)}: {error_msg}")
        
        # If it's a rate limit error, DO NOT split the batch. Just wait and retry.
        if "429 Too Many Requests" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
            logger.info("Rate limit hit! Waiting 30 seconds to cool down...")
            time.sleep(30)
            return process_batch(hotel_batch)
            
        # Base case: single hotel failed completely (likely malformed JSON)
        if len(hotel_batch) == 1:
            logger.error(f"Skipping unparseable hotel: {hotel_batch[0].get('canonical_hotel_id')}")
            return None

        # Recursive fallback: bisect the batch and try both halves independently
        mid = len(hotel_batch) // 2
        time.sleep(7)  # Throttle before retrying
        
        logger.info(f"Splitting batch of {len(hotel_batch)} into {mid} and {len(hotel_batch)-mid}")
        left_results = process_batch(hotel_batch[:mid])
        right_results = process_batch(hotel_batch[mid:])

        # Combine results safely from successful sub-batches
        combined_rooms = []
        if left_results and hasattr(left_results, 'rooms'):
            combined_rooms.extend(left_results.rooms)
        if right_results and hasattr(right_results, 'rooms'):
            combined_rooms.extend(right_results.rooms)

        return RoomExtraction(rooms=combined_rooms)

@log_latency("LLM Room Normalization")
def normalize_rooms():
    logger.info("Starting Room Normalization Pipeline")
    
    with open("data/checkpoints/hotel_matches.json", "r") as f:
        matches = json.load(f)
        
    df_rooms_a = pd.read_csv(os.path.join("data", "rooms_a.csv")).fillna("")
    df_rooms_b = pd.read_csv(os.path.join("data", "rooms_b.csv")).fillna("")
    
    rooms_a_dict = df_rooms_a.groupby("hotel_id").apply(lambda x: x.to_dict('records')).to_dict()
    rooms_b_dict = df_rooms_b.groupby("hotel_id").apply(lambda x: x.to_dict('records')).to_dict()
    
    # Load existing checkpoint to avoid re-processing
    processed_ids = set()
    all_normalized_rooms = []
    canonical_mappings = {}
    
    if os.path.exists("data/checkpoints/normalized_rooms.json"):
        try:
            with open("data/checkpoints/normalized_rooms.json", "r") as f:
                all_normalized_rooms = json.load(f)
                processed_ids = {r['canonical_hotel_id'] for r in all_normalized_rooms}
            logger.info(f"Loaded checkpoint with {len(processed_ids)} processed hotels.")
        except Exception:
            pass
            
    if os.path.exists("data/checkpoints/canonical_mappings.json"):
        try:
            with open("data/checkpoints/canonical_mappings.json", "r") as f:
                canonical_mappings = json.load(f)
        except Exception:
            pass
            
    payloads = []
    for idx, match in enumerate(matches):
        id_a = match['supplier_a_id']
        id_b = match['supplier_b_id']
        canonical_id = f"CANONICAL-{id_a}"
        
        if canonical_id in processed_ids:
            continue
            
        r_a = rooms_a_dict.get(id_a, [])
        r_b = rooms_b_dict.get(id_b, [])
        
        payloads.append({
            "canonical_hotel_id": canonical_id,
            "supplier_a_id": id_a,
            "supplier_b_id": id_b,
            "rooms_supplier_a": [{"room_id": r['room_id'], "name": r['name'], "amenities": r['amenities']} for r in r_a],
            "rooms_supplier_b": [{"room_id": r['room_id'], "name": r['name'], "amenities": r['amenities']} for r in r_b]
        })
    
    # Process in batches of 25
    batch_size = 25
    
    for i in range(0, len(payloads), batch_size):
        batch = payloads[i:i+batch_size]
        logger.info(f"Processing batch {i//batch_size + 1}/{(len(payloads)+batch_size-1)//batch_size}")
        result = process_batch(batch)
        if result and hasattr(result, 'rooms'):
            all_normalized_rooms.extend([r.model_dump() for r in result.rooms])
            
            # Save checkpoint after EVERY successful batch
            with open("data/checkpoints/normalized_rooms.json", "w") as f:
                json.dump(all_normalized_rooms, f, indent=2)
                
            for p in batch:
                canonical_mappings[p['supplier_a_id']] = p['canonical_hotel_id']
            with open("data/checkpoints/canonical_mappings.json", "w") as f:
                json.dump(canonical_mappings, f, indent=2)
                
    logger.info("Room Normalization Pipeline Completed successfully.")

if __name__ == "__main__":
    if not client:
        logger.error("Skipping normalization because GEMINI_API_KEY is not set.")
    else:
        normalize_rooms()
