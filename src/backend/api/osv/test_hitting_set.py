#!/usr/bin/env python3
"""Test the minimum hitting set implementation"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vulnerability_repo_mapper import find_minimum_hitting_set

def test_paper_example():
    """Test case from the research paper"""
    print("=== Test 1: Paper Example ===")
    # CVE-1 affects [v1.0, v1.1, v1.2], CVE-2 affects [v1.1, v1.2]
    # Expected: [v1.2] (1 version covers both, and v1.2 is most recent)
    
    test_data = [
        ["v1.0", "v1.1", "v1.2"],  # CVE-1 - fixed to include v1.2
        ["v1.1", "v1.2"]           # CVE-2 - v1.2 covers both
    ]
    
    # With recency scores favoring newer versions
    recency = {
        "v1.0": 1000,
        "v1.1": 2000,
        "v1.2": 3000
    }
    
    result = find_minimum_hitting_set(test_data, recency)
    print(f"Result: {result}")
    print(f"Expected: ['v1.2'] (most recent version that covers all CVEs)")
    
    # Verify coverage
    for i, cve in enumerate(test_data):
        covered = any(v in result for v in cve)
        print(f"CVE {i+1} covered: {covered}")
    
    assert len(result) == 1, f"Expected 1 version, got {len(result)}"
    assert result == ["v1.2"], f"Expected v1.2 (most recent version covering both CVEs), got {result}"
    print("✅ Test passed!\n")

def test_multiple_hits_needed():
    """Test where multiple versions are required"""
    print("=== Test 2: Multiple Versions Required ===")
    # CVE-1: [v1.0], CVE-2: [v2.0], CVE-3: [v3.0]
    # Expected: [v1.0, v2.0, v3.0] (need all 3)
    
    test_data = [
        ["v1.0"],
        ["v2.0"],
        ["v3.0"]
    ]
    
    result = find_minimum_hitting_set(test_data)
    print(f"Result: {result}")
    print(f"Expected: 3 versions")
    
    assert len(result) == 3, f"Expected 3 versions, got {len(result)}"
    print("✅ Test passed!\n")

def test_edge_cases():
    """Test edge cases"""
    print("=== Test 3: Edge Cases ===")
    
    # Empty input
    result1 = find_minimum_hitting_set([])
    assert result1 == [], f"Expected empty list for empty input, got {result1}"
    print("✅ Empty input: passed")
    
    # Single CVE, single version
    result2 = find_minimum_hitting_set([["v1.0"]])
    assert result2 == ["v1.0"], f"Expected ['v1.0'], got {result2}"
    print("✅ Single CVE: passed")
    
    # Empty CVE list (should be filtered out)
    result3 = find_minimum_hitting_set([["v1.0"], [], ["v2.0"]])
    assert len(result3) == 2, f"Expected 2 versions, got {len(result3)}"
    print("✅ Empty CVE filtering: passed\n")

if __name__ == "__main__":
    test_paper_example()
    test_multiple_hits_needed()
    test_edge_cases()
    print("🎉 All tests passed!")