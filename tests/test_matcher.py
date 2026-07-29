import pytest
import pandas as pd
import numpy as np
import sys
import os

# Add parent directory to path to import matcher
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from matcher import generate_tfidf_candidates, extract_features

def test_null_coordinates_fallback():
    """
    Feeds NaN coordinates and asserts the system routes it to TF-IDF instead of crashing.
    """
    df_a_missing = pd.DataFrame([
        {
            'id': 'A-123',
            'clean_name': 'test hotel miami',
            'address': '123 ocean drive'
        }
    ])
    
    df_b = pd.DataFrame([
        {
            'id': 'B-456',
            'clean_name': 'test hotel miami',
            'address': '123 ocean drive',
            'lat': 25.7617,
            'lon': -80.1918
        }
    ])
    
    candidates = generate_tfidf_candidates(df_a_missing, df_b)
    
    # Assert that a candidate was generated despite missing coordinates
    assert not candidates.empty
    assert candidates.iloc[0]['id_a'] == 'A-123'
    assert candidates.iloc[0]['id_b'] == 'B-456'
    assert pd.isna(candidates.iloc[0]['spatial_distance'])

def test_shared_skyscraper_defense():
    """
    Feeds two hotels with identical coordinates but a 3-star difference, 
    asserting the pipeline rejects the match.
    """
    df_a = pd.DataFrame([
        {
            'id': 'A-111',
            'clean_name': 'generic hotel',
            'address': 'shared building',
            'lat': 10.0,
            'lon': 10.0,
            'stars': 2.0
        }
    ])
    
    df_b = pd.DataFrame([
        {
            'id': 'B-222',
            'clean_name': 'generic hotel',
            'address': 'shared building',
            'lat': 10.0,
            'lon': 10.0,
            'stars': 5.0
        }
    ])
    
    candidates_df = pd.DataFrame([
        {
            'id_a': 'A-111',
            'id_b': 'B-222',
            'spatial_distance': 0.0
        }
    ])
    
    # Run feature extraction which includes the star defense logic
    merged = extract_features(candidates_df, df_a, df_b)
    
    # The merged dataframe should be empty because abs(2.0 - 5.0) >= 2
    assert merged.empty
