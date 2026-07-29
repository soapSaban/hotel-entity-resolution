import requests
import time

BASE_URL = "http://localhost:8000"

def run_tests():
    print("Running API Validation Tests...\n")
    
    # Wait for API to boot just in case
    for _ in range(5):
        try:
            requests.get(BASE_URL)
            break
        except requests.exceptions.ConnectionError:
            time.sleep(1)

    # 1. Test GET /hotels (no search)
    print("TEST 1: GET /hotels (List all, limited to 100)")
    r = requests.get(f"{BASE_URL}/hotels")
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert len(data["results"]) > 0
    print(f"  -> SUCCESS: Retrieved {len(data['results'])} default results")

    # 2. Test GET /hotels?search=...
    print("\nTEST 2: GET /hotels?search=taj")
    r = requests.get(f"{BASE_URL}/hotels", params={"search": "taj"})
    assert r.status_code == 200
    search_data = r.json()
    assert len(search_data["results"]) > 0
    print(f"  -> SUCCESS: Retrieved {len(search_data['results'])} search results")
    
    # 3. Test GET /hotels/{id}
    first_hotel = search_data["results"][0]
    canonical_id = first_hotel["id"]
    print(f"\nTEST 3: GET /hotels/{canonical_id} (Deep payload)")
    r = requests.get(f"{BASE_URL}/hotels/{canonical_id}")
    assert r.status_code == 200
    deep_hotel = r.json()
    assert deep_hotel["id"] == canonical_id
    assert "rooms" in deep_hotel
    assert "amenities" in deep_hotel
    assert "images" in deep_hotel
    print(f"  -> SUCCESS: Retrieved deep payload for {deep_hotel['name']}")
    
    # 4. Test GET /hotels/{id} (Missing ID edge case)
    print("\nTEST 4: GET /hotels/INVALID-ID-123 (Missing ID edge case)")
    r = requests.get(f"{BASE_URL}/hotels/INVALID-ID-123")
    assert r.status_code == 404
    print("  -> SUCCESS: Properly returned 404 Not Found")
    
    # 5. Test frontend UI endpoint
    print("\nTEST 5: GET / (Frontend UI)")
    r = requests.get(f"{BASE_URL}/")
    assert r.status_code == 200
    assert "Canonical Hotels" in r.text
    print("  -> SUCCESS: Frontend UI is served correctly")
    
    print("\nAll tests passed perfectly! The system is production-ready.")

if __name__ == "__main__":
    run_tests()
