import json
import pandas as pd
import os
from logger import logger, log_latency

@log_latency("Artifact Compilation (Build DB)")
def build_db():
    logger.info("Starting Artifact Compilation")
    
    # Load files
    try:
        with open("data/checkpoints/hotel_matches.json", "r") as f:
            matches = json.load(f)
        with open("data/checkpoints/near_misses.json", "r") as f:
            near_misses = json.load(f)
        # Removed canonical_mappings.json to enforce deterministic ID logic
    except Exception as e:
        logger.error(f"Failed to load intermediate files: {e}")
        return

    # Load rooms (optional, could be empty if GEMINI_API_KEY was missing)
    rooms_by_canonical = {}
    if os.path.exists("data/checkpoints/normalized_rooms.json"):
        with open("data/checkpoints/normalized_rooms.json", "r") as f:
            rooms = json.load(f)
        for r in rooms:
            c_id = r.get("canonical_hotel_id")
            if c_id not in rooms_by_canonical:
                rooms_by_canonical[c_id] = []
            rooms_by_canonical[c_id].append(r)
            
    df_a = pd.read_csv(os.path.join("data", "supplier_a.csv")).fillna("")
    df_b = pd.read_csv(os.path.join("data", "supplier_b.csv")).fillna("")
    
    df_a_dict = df_a.set_index("id").to_dict(orient="index")
    df_b_dict = df_b.set_index("id").to_dict(orient="index")
    
    df_rooms_a = pd.read_csv(os.path.join("data", "rooms_a.csv")).fillna("")
    df_rooms_b = pd.read_csv(os.path.join("data", "rooms_b.csv")).fillna("")
    rooms_a_dict = df_rooms_a.groupby("hotel_id").apply(lambda x: x.to_dict('records')).to_dict()
    rooms_b_dict = df_rooms_b.groupby("hotel_id").apply(lambda x: x.to_dict('records')).to_dict()
    
    def get_stars(data):
        val = data.get("stars", 0)
        try:
            return float(val) if val != "" else 0.0
        except (ValueError, TypeError):
            return 0.0
            
    canonical_hotels = []
    matched_a = set()
    matched_b = set()
    
    for match in matches:
        id_a = match["supplier_a_id"]
        id_b = match["supplier_b_id"]
        conf = match["match_confidence"]
        
        matched_a.add(id_a)
        matched_b.add(id_b)
        
        canonical_id = f"CANONICAL-{id_a}"
        
        a_data = df_a_dict.get(id_a, {})
        b_data = df_b_dict.get(id_b, {})
        
        # Merge amenities (split by pipe, lowercased, then set union)
        am_a = set([x.strip().lower() for x in str(a_data.get("amenities", "")).split("|") if x.strip()])
        am_b = set([x.strip().lower() for x in str(b_data.get("amenities", "")).split("|") if x.strip()])
        merged_amenities = sorted(list(am_a.union(am_b)))
        
        # Merge image_urls (split by pipe, set union to deduplicate)
        img_a = set([x.strip() for x in str(a_data.get("image_urls", "")).split("|") if x.strip()])
        img_b = set([x.strip() for x in str(b_data.get("image_urls", "")).split("|") if x.strip()])
        merged_images = sorted(list(img_a.union(img_b)))
        
        # Determine canonical name & address (prefer Supplier A for simplicity, or longest)
        name = a_data.get("name", "")
        if len(b_data.get("name", "")) > len(name):
            name = b_data.get("name", "")
            
        # Force match_confidence to None for exclusive rooms to comply with API contract
        hotel_rooms = rooms_by_canonical.get(canonical_id, [])
        for r in hotel_rooms:
            if not r.get("supplier_a_room_ids") or not r.get("supplier_b_room_ids"):
                r["match_confidence"] = None

        canonical_obj = {
            "id": canonical_id,
            "name": name,
            "address": a_data.get("address", ""),
            "lat": a_data.get("lat"),
            "lon": a_data.get("lon"),
            "stars": max(get_stars(a_data), get_stars(b_data)),
            "amenities": merged_amenities,
            "images": merged_images,
            "supplier_a_id": id_a,
            "supplier_b_id": id_b,
            "match_confidence": conf,
            "rooms": hotel_rooms,
            "near_miss_candidates": near_misses.get(id_a, [])
        }
        
        canonical_hotels.append(canonical_obj)
        
    # Process unmatched Supplier A hotels
    for id_a, a_data in df_a_dict.items():
        if id_a not in matched_a:
            canonical_id = f"CANONICAL-UNMAPPED-{id_a}"
            unmapped_rooms_a = []
            for r in rooms_a_dict.get(id_a, []):
                unmapped_rooms_a.append({
                    "canonical_hotel_id": canonical_id,
                    "normalized_name": r.get("name", ""),
                    "bed_type": None,
                    "occupancy": None,
                    "view": None,
                    "meal_plan": None,
                    "supplier_a_room_ids": [r.get("room_id")],
                    "supplier_b_room_ids": [],
                    "match_confidence": None
                })
            canonical_hotels.append({
                "id": canonical_id,
                "name": a_data.get("name", ""),
                "address": a_data.get("address", ""),
                "lat": a_data.get("lat"),
                "lon": a_data.get("lon"),
                "stars": get_stars(a_data),
                "amenities": sorted(list(set([x.strip().lower() for x in str(a_data.get("amenities", "")).split("|") if x.strip()]))),
                "images": sorted(list(set([x.strip() for x in str(a_data.get("image_urls", "")).split("|") if x.strip()]))),
                "supplier_a_id": id_a,
                "supplier_b_id": None,
                "match_confidence": None,
                "rooms": unmapped_rooms_a,
                "near_miss_candidates": near_misses.get(id_a, [])
            })
            
    # Process unmatched Supplier B hotels
    for id_b, b_data in df_b_dict.items():
        if id_b not in matched_b:
            canonical_id = f"CANONICAL-UNMAPPED-{id_b}"
            unmapped_rooms_b = []
            for r in rooms_b_dict.get(id_b, []):
                unmapped_rooms_b.append({
                    "canonical_hotel_id": canonical_id,
                    "normalized_name": r.get("name", ""),
                    "bed_type": None,
                    "occupancy": None,
                    "view": None,
                    "meal_plan": None,
                    "supplier_a_room_ids": [],
                    "supplier_b_room_ids": [r.get("room_id")],
                    "match_confidence": None
                })
            canonical_hotels.append({
                "id": canonical_id,
                "name": b_data.get("name", ""),
                "address": b_data.get("address", ""),
                "lat": b_data.get("lat"),
                "lon": b_data.get("lon"),
                "stars": get_stars(b_data),
                "amenities": sorted(list(set([x.strip().lower() for x in str(b_data.get("amenities", "")).split("|") if x.strip()]))),
                "images": sorted(list(set([x.strip() for x in str(b_data.get("image_urls", "")).split("|") if x.strip()]))),
                "supplier_a_id": None,
                "supplier_b_id": id_b,
                "match_confidence": None,
                "rooms": unmapped_rooms_b,
                "near_miss_candidates": []
            })
        
    with open("canonical_hotels.json", "w") as f:
        json.dump(canonical_hotels, f, indent=2)
        
    logger.info(f"Successfully compiled {len(canonical_hotels)} canonical hotels into canonical_hotels.json")

if __name__ == "__main__":
    build_db()
