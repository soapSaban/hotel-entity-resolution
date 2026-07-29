import json
import pandas as pd
import os
from collections import defaultdict
from logger import logger

def recover_cache():
    logger.info("Starting cache recovery process...")
    
    # Load rooms to establish mapping from room_id -> supplier_x_id
    logger.info("Loading room data...")
    df_rooms_a = pd.read_csv('data/rooms_a.csv').set_index('room_id')
    df_rooms_b = pd.read_csv('data/rooms_b.csv').set_index('room_id')
    
    # Load matches to map supplier_b_id -> supplier_a_id (for fallback)
    logger.info("Loading matches...")
    with open('data/checkpoints/hotel_matches.json', 'r') as f:
        matches = json.load(f)
    
    # Create lookup dictionaries
    b_to_a = {m['supplier_b_id']: m['supplier_a_id'] for m in matches}
    
    # Load the corrupt cache
    if not os.path.exists('data/checkpoints/normalized_rooms.json'):
        logger.error("No cache to recover.")
        return
        
    logger.info("Loading normalized_rooms.json...")
    with open('data/checkpoints/normalized_rooms.json', 'r') as f:
        rooms = json.load(f)
        
    # Group rooms by old canonical_hotel_id
    groups = defaultdict(list)
    for r in rooms:
        groups[r['canonical_hotel_id']].append(r)
        
    new_normalized_rooms = []
    new_canonical_mappings = {}
    
    migrated_count = 0
    failed_groups = []
    
    for old_id, room_list in groups.items():
        id_a = None
        
        # 1. Try to recover from Supplier A room IDs
        for r in room_list:
            if r.get('supplier_a_room_ids'):
                room_id = r['supplier_a_room_ids'][0]
                if room_id in df_rooms_a.index:
                    val = df_rooms_a.loc[room_id]['hotel_id']
                    id_a = val.iloc[0] if isinstance(val, pd.Series) else val
                    break
                    
        # 2. Try to recover from Supplier B room IDs and matches lookup
        if not id_a:
            for r in room_list:
                if r.get('supplier_b_room_ids'):
                    room_id = r['supplier_b_room_ids'][0]
                    if room_id in df_rooms_b.index:
                        val = df_rooms_b.loc[room_id]['hotel_id']
                        id_b = val.iloc[0] if isinstance(val, pd.Series) else val
                        id_a = b_to_a.get(id_b)
                        if id_a:
                            break
                            
        if id_a:
            migrated_count += 1
            deterministic_id = f"CANONICAL-{id_a}"
            
            # Update all rooms with the new canonical ID
            for r in room_list:
                r['canonical_hotel_id'] = deterministic_id
                new_normalized_rooms.append(r)
                
            # Regenerate canonical mapping
            new_canonical_mappings[id_a] = deterministic_id
        else:
            failed_groups.append(old_id)
            
    logger.info(f"Successfully recovered {migrated_count}/{len(groups)} cache groups.")
    if failed_groups:
        logger.warning(f"Failed to recover {len(failed_groups)} groups: {failed_groups[:5]}...")
        
    # Save the recovered data
    with open('data/checkpoints/normalized_rooms.json', 'w') as f:
        json.dump(new_normalized_rooms, f, indent=2)
        
    with open('data/checkpoints/canonical_mappings.json', 'w') as f:
        json.dump(new_canonical_mappings, f, indent=2)
        
    logger.info("Cache successfully rewritten with deterministic IDs.")

if __name__ == "__main__":
    recover_cache()
