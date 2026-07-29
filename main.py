import json
import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Away Canonical Hotels API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# In-memory database
db = {}
hotels_list = []

@app.on_event("startup")
async def load_data():
    global db, hotels_list
    file_path = "canonical_hotels.json"
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            data = json.load(f)
            hotels_list = data
            for hotel in data:
                db[hotel["id"]] = hotel
        print(f"Loaded {len(db)} canonical hotels into memory.")
    else:
        print(f"Warning: {file_path} not found. API will return empty results.")

# API Routes
@app.get("/hotels")
def search_hotels(search: str = Query(None, description="Search term for hotel name or address")):
    """
    Returns a list of basic hotel details matching the search query.
    If no query provided, returns the first 50 hotels.
    """
    if not search:
        return {"results": hotels_list[:50]}
        
    search_lower = search.lower()
    results = []
    
    for hotel in hotels_list:
        if search_lower in hotel.get("name", "").lower() or search_lower in hotel.get("address", "").lower():
            # Return basic details for list view to save bandwidth
            results.append({
                "id": hotel["id"],
                "name": hotel["name"],
                "address": hotel["address"],
                "stars": hotel.get("stars", 0),
                "match_confidence": hotel.get("match_confidence")
            })
            
    return {"results": results[:100]} # Limit to 100 for performance

@app.get("/hotels/{hotel_id}")
def get_hotel(hotel_id: str):
    """
    Returns the deep payload for a specific canonical hotel, including normalized rooms
    and near-miss candidates.
    """
    original_hotel = db.get(hotel_id)
    if not original_hotel:
        raise HTTPException(status_code=404, detail="Hotel not found")
        
    # Create a shallow copy so we don't permanently mutate the in-memory cache
    hotel = dict(original_hotel)
    
    # For single-supplier rooms, strip the match_confidence since no match occurred
    if "rooms" in hotel:
        # Create a new list of rooms to avoid mutating the cached dictionaries
        processed_rooms = []
        for r in hotel["rooms"]:
            room_copy = dict(r)
            if not (room_copy.get("supplier_a_room_ids") and room_copy.get("supplier_b_room_ids")):
                room_copy["match_confidence"] = None
            processed_rooms.append(room_copy)
        hotel["rooms"] = processed_rooms
        
    return hotel

# Mount static files last so API routes take precedence
app.mount("/", StaticFiles(directory="static", html=True), name="static")
