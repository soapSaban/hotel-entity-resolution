import pytest
import sys
import os
import json
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import run_normalizer

class MockResponse:
    def __init__(self, text):
        self.text = text
        self.usage_metadata = MagicMock(prompt_token_count=10, candidates_token_count=10)

def test_llm_batch_poisoning():
    """
    Feeds a mocked batch with one corrupted string, asserting the recursive 
    bisection safely splits and processes the rest.
    """
    # Create a batch of 2 elements
    hotel_batch = [
        {"canonical_hotel_id": "GOOD-1"},
        {"canonical_hotel_id": "POISON-2"}
    ]
    
    # Ensure client is not None so the function runs
    original_client = run_normalizer.client
    run_normalizer.client = MagicMock()
    
    # We want generate_content to raise an exception when the batch contains POISON-2, 
    # but succeed when the batch only contains GOOD-1.
    def mock_generate_content(model, contents, config):
        if "POISON-2" in contents:
            raise Exception("Simulated poisoning crash")
        
        # Return a valid JSON response for the GOOD-1 batch
        fake_rooms = {
            "rooms": [
                {
                    "canonical_hotel_id": "GOOD-1",
                    "normalized_name": "Test Room",
                    "bed_type": None,
                    "occupancy": 1,
                    "view": None,
                    "meal_plan": None,
                    "supplier_a_room_ids": ["R-1"],
                    "supplier_b_room_ids": [],
                    "match_confidence": 1.0
                }
            ]
        }
        return MockResponse(json.dumps(fake_rooms))
        
    run_normalizer.client.models.generate_content.side_effect = mock_generate_content
    
    # Patch time.sleep so the test runs instantly instead of waiting for rate limits
    with patch('time.sleep', return_value=None):
        result = run_normalizer.process_batch(hotel_batch)
        
    # Restore the original client
    run_normalizer.client = original_client
    
    # Assertions
    assert result is not None, "process_batch should not return None for a partially valid batch"
    assert hasattr(result, 'rooms'), "Result must have a 'rooms' attribute"
    assert len(result.rooms) == 1, "Only the good hotel should have been processed"
    assert result.rooms[0].canonical_hotel_id == "GOOD-1"
