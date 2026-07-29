import pandas as pd
import numpy as np
import os
import json
import re
from scipy.spatial import KDTree
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from logger import logger, log_latency
import warnings
warnings.filterwarnings('ignore')

DATA_DIR = "data"
SUPPLIER_A = os.path.join(DATA_DIR, "supplier_a.csv")
SUPPLIER_B = os.path.join(DATA_DIR, "supplier_b.csv")
MATCHES_OUTPUT = "data/checkpoints/hotel_matches.json"
NEAR_MISSES_OUTPUT = "data/checkpoints/near_misses.json"

def clean_name(name):
    if not isinstance(name, str):
        return ""
    name = name.lower()
    name = re.sub(r'^(hotel o|fabhotel|collection o|oyo|super oyo)\s+', '', name)
    name = re.sub(r'[^a-z0-9 ]', '', name)
    return name.strip()

@log_latency("Load Data & Split by Coordinates")
def load_and_split():
    df_a = pd.read_csv(SUPPLIER_A)
    df_b = pd.read_csv(SUPPLIER_B)

    # Clean stars
    df_a['stars'] = pd.to_numeric(df_a['stars'], errors='coerce').fillna(0)
    df_b['stars'] = pd.to_numeric(df_b['stars'], errors='coerce').fillna(0)
    
    # Fill NA addresses/names
    df_a['name'] = df_a['name'].fillna("")
    df_a['address'] = df_a['address'].fillna("")
    df_b['name'] = df_b['name'].fillna("")
    df_b['address'] = df_b['address'].fillna("")

    # Clean names
    df_a['clean_name'] = df_a['name'].apply(clean_name)
    df_b['clean_name'] = df_b['name'].apply(clean_name)

    # Split Supplier A
    valid_coords_a = df_a['lat'].notna() & df_a['lon'].notna() & (df_a['lat'] != 0.0) & (df_a['lon'] != 0.0)
    df_a_coords = df_a[valid_coords_a].copy()
    df_a_missing = df_a[~valid_coords_a].copy()

    # Split Supplier B
    valid_coords_b = df_b['lat'].notna() & df_b['lon'].notna() & (df_b['lat'] != 0.0) & (df_b['lon'] != 0.0)
    df_b_coords = df_b[valid_coords_b].copy()
    
    logger.info(f"Loaded {len(df_a)} from A, {len(df_b)} from B")
    logger.info(f"Supplier A: {len(df_a_coords)} with coords, {len(df_a_missing)} missing coords")
    
    return df_a, df_b, df_a_coords, df_a_missing, df_b_coords

@log_latency("Spatial Candidate Generation (KDTree)")
def generate_spatial_candidates(df_a_coords, df_b_coords):
    # Rough degree to km conversion (~111 km per degree)
    # 500m radius is approx 0.0045 degrees
    RADIUS_DEG = 0.0045 
    
    tree = KDTree(df_b_coords[['lat', 'lon']].values)
    candidates = []
    
    for _, row_a in df_a_coords.iterrows():
        idx = tree.query_ball_point([row_a['lat'], row_a['lon']], RADIUS_DEG)
        for i in idx:
            row_b = df_b_coords.iloc[i]
            dist = np.linalg.norm(
                np.array([row_a['lat'], row_a['lon']]) - np.array([row_b['lat'], row_b['lon']])
            ) * 111.0 # rough km
            candidates.append({
                'id_a': row_a['id'],
                'id_b': row_b['id'],
                'spatial_distance': dist
            })
            
    logger.info(f"Generated {len(candidates)} spatial candidates")
    return pd.DataFrame(candidates)

@log_latency("TF-IDF Fallback Candidate Generation")
def generate_tfidf_candidates(df_a_missing, df_b):
    if len(df_a_missing) == 0:
        return pd.DataFrame()
        
    df_a_missing['text'] = df_a_missing['clean_name'] + " " + df_a_missing['address']
    df_b['text'] = df_b['clean_name'] + " " + df_b['address']
    
    vectorizer = TfidfVectorizer(ngram_range=(1,2), max_features=10000)
    tfidf_b = vectorizer.fit_transform(df_b['text'])
    tfidf_a = vectorizer.transform(df_a_missing['text'])
    
    sim_matrix = cosine_similarity(tfidf_a, tfidf_b)
    
    candidates = []
    for i, row_a in enumerate(df_a_missing.itertuples()):
        b_indices = np.where(sim_matrix[i] > 0.6)[0]
        for j in b_indices:
            candidates.append({
                'id_a': row_a.id,
                'id_b': df_b.iloc[j]['id'],
                'spatial_distance': np.nan # Missing coords
            })
            
    logger.info(f"Generated {len(candidates)} TF-IDF candidates")
    return pd.DataFrame(candidates)

@log_latency("Feature Extraction & Star Defense")
def extract_features(candidates_df, df_a, df_b):
    if candidates_df.empty:
        return pd.DataFrame()
        
    df_a_sub = df_a.set_index('id')
    df_b_sub = df_b.set_index('id')
    
    # Merge data
    merged = candidates_df.join(df_a_sub, on='id_a', rsuffix='_a').join(df_b_sub, on='id_b', rsuffix='_b')
    
    # Star Defense: Only penalize if BOTH suppliers provided a valid star rating (> 0)
    def valid_star_diff(row):
        if row['stars'] > 0 and row['stars_b'] > 0:
            return abs(row['stars'] - row['stars_b']) < 2
        return True # If either is missing (0), don't penalize
        
    merged['star_defense_pass'] = merged.apply(valid_star_diff, axis=1)
    merged = merged[merged['star_defense_pass']].copy()
    logger.info(f"Candidates remaining after Star Defense: {len(merged)}")
    
    # Jaccard String Similarity
    def jaccard_sim(str1, str2):
        s1 = set(str1.split())
        s2 = set(str2.split())
        if not s1 and not s2:
            return 0.0
        return len(s1.intersection(s2)) / len(s1.union(s2))
        
    merged['string_similarity'] = merged.apply(lambda row: jaccard_sim(row['clean_name'], row['clean_name_b']), axis=1)
    
    # Embeddings
    model = SentenceTransformer('all-MiniLM-L6-v2')
    names_a = merged['clean_name'].tolist()
    names_b = merged['clean_name_b'].tolist()
    
    emb_a = model.encode(names_a, show_progress_bar=False)
    emb_b = model.encode(names_b, show_progress_bar=False)
    
    merged['embedding_cosine'] = [cosine_similarity([a], [b])[0][0] for a, b in zip(emb_a, emb_b)]
    
    return merged

@log_latency("Classification & Routing")
def classify_and_route(features_df, df_a, df_b):
    if features_df.empty:
        return [], {}
        
    # Heuristic matching confidence instead of training a model without labels
    # weight embeddings highly, penalize distance slightly
    # Normalize distance: 0km -> 1.0, 0.5km -> 0.0
    features_df['dist_score'] = np.clip(1.0 - (features_df['spatial_distance'] / 0.5), 0, 1)
    
    # Neutralize score for missing coordinates
    features_df['dist_score'] = features_df['dist_score'].fillna(0.5)
    
    # Confidence formula
    # 50% embedding, 30% string sim, 20% spatial distance
    features_df['match_confidence'] = (
        0.5 * features_df['embedding_cosine'] + 
        0.3 * features_df['string_similarity'] + 
        0.2 * features_df['dist_score']
    )
    
    # Clip and ensure it's within [0.0, 1.0]
    features_df['match_confidence'] = features_df['match_confidence'].clip(0, 1.0)
    
    # Deduplicate: Only keep the best match for each Supplier A ID
    features_df = features_df.sort_values('match_confidence', ascending=False)
    
    matches = []
    near_misses = {}
    
    df_b_dict = df_b.set_index('id').to_dict(orient='index')
    
    seen_a = set()
    seen_b = set()
    for _, row in features_df.iterrows():
        id_a = row['id_a']
        id_b = row['id_b']
        conf = row['match_confidence']
        
        if id_a in seen_a or id_b in seen_b:
            if id_a not in seen_a and id_b in seen_b:
                if conf >= 0.4:
                    if id_a not in near_misses:
                        near_misses[id_a] = []
                    if len(near_misses[id_a]) < 5:
                        near_misses[id_a].append({
                            'supplier_b_id': id_b,
                            'name': df_b_dict[id_b]['name'],
                            'score': float(conf)
                        })
            elif id_a in seen_a:
                if 0.4 <= conf < 0.8:
                    if id_a not in near_misses:
                        near_misses[id_a] = []
                    if len(near_misses[id_a]) < 5:
                        near_misses[id_a].append({
                            'supplier_b_id': id_b,
                            'name': df_b_dict[id_b]['name'],
                            'score': float(conf)
                        })
            continue
            
        if conf >= 0.8:
            matches.append({
                'supplier_a_id': id_a,
                'supplier_b_id': id_b,
                'match_confidence': float(conf)
            })
            seen_a.add(id_a)
            seen_b.add(id_b)
        elif 0.4 <= conf < 0.8:
            if id_a not in near_misses:
                near_misses[id_a] = []
            near_misses[id_a].append({
                'supplier_b_id': id_b,
                'name': df_b_dict[id_b]['name'],
                'score': float(conf)
            })
            
    logger.info(f"Found {len(matches)} matches (>= 0.8)")
    logger.info(f"Found {len(near_misses)} near misses (0.4 - 0.79)")
    
    return matches, near_misses

def main():
    logger.info("Starting Matcher Pipeline")
    df_a, df_b, df_a_coords, df_a_missing, df_b_coords = load_and_split()
    
    pool1 = generate_spatial_candidates(df_a_coords, df_b_coords)
    pool2 = generate_tfidf_candidates(df_a_missing, df_b)
    
    candidates = pd.concat([pool1, pool2], ignore_index=True)
    logger.info(f"Total Combined Candidates: {len(candidates)}")
    
    features = extract_features(candidates, df_a, df_b)
    matches, near_misses = classify_and_route(features, df_a, df_b)
    
    with open(MATCHES_OUTPUT, 'w') as f:
        json.dump(matches, f, indent=2)
        
    with open(NEAR_MISSES_OUTPUT, 'w') as f:
        json.dump(near_misses, f, indent=2)
        
    logger.info("Matcher Pipeline Completed successfully.")

if __name__ == "__main__":
    main()
