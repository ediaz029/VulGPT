"""Test script for Semantic Kernel scorer service."""
import asyncio
import json
import os
from pathlib import Path

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from semantic_kernel_scorer.main import create_kernel, invoke_kernel


async def test_scorer():
    """Test the Semantic Kernel scorer with sample data."""
    
    # Check for API key
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("AZURE_OPENAI_ENDPOINT"):
        print("Error: No API key found. Set OPENAI_API_KEY or AZURE_OPENAI_* variables.")
        print("   Add to .env file or export in terminal.")
        return False
    
    print("✓ API key found")
    
    # Test case 1: Matching vulnerability
    print("\n=== Test 1: Matching vulnerability ===")
    lead1 = {
        "headline": "SQL Injection in database module",
        "analysis": "User input concatenated directly into SQL query without sanitization",
        "cwe": "CWE-89",
        "function_names": ["execute_query"],
        "filenames": ["src/database.py"]
    }
    
    ground_truth1 = [
        {
            "id": "GHSA-test-1234-5678",
            "summary": "SQL injection vulnerability in database module",
            "details": "The execute_query function concatenates user input into SQL queries",
            "aliases": ["CVE-2024-12345"]
        }
    ]
    
    try:
        kernel = create_kernel()
        print("✓ Kernel created successfully")
        
        result1 = await invoke_kernel(kernel, lead1, ground_truth1)
        print(f"\nResult: {json.dumps(result1, indent=2)}")
        
        assert result1.get("score") in [0, 1], "Score must be 0 or 1"
        assert "reasoning" in result1, "Must include reasoning"
        print("✓ Test 1 passed: Valid response structure")
        
        if result1.get("score") == 1:
            print("  → Correctly identified as matching vulnerability")
            assert result1.get("corresponds_to") == "GHSA-test-1234-5678"
            print("  → Correctly identified vulnerability ID")
        
    except Exception as e:
        print(f"❌ Test 1 failed: {e}")
        return False

    # Test case 2: No ground truth
    print("\n=== Test 2: No ground truth ===")
    lead2 = {
        "headline": "Potential XSS vulnerability",
        "analysis": "Unescaped user input in HTML output",
        "cwe": "CWE-79",
        "function_names": ["render_page"],
        "filenames": ["src/views.py"]
    }
    
    ground_truth2 = []
    
    try:
        result2 = await invoke_kernel(kernel, lead2, ground_truth2)
        print(f"\nResult: {json.dumps(result2, indent=2)}")
        
        assert result2.get("score") == 0, "Should return 0 when no ground truth"
        assert result2.get("corresponds_to") is None, "corresponds_to should be null"
        print("✓ Test 2 passed: Correctly handles no ground truth")
        
    except Exception as e:
        print(f"❌ Test 2 failed: {e}")
        return False
    
    # Test case 3: Non-matching vulnerability
    print("\n=== Test 3: Non-matching vulnerability ===")
    lead3 = {
        "headline": "Buffer overflow in C function",
        "analysis": "Unsafe strcpy usage without bounds checking",
        "cwe": "CWE-120",
        "function_names": ["copy_buffer"],
        "filenames": ["src/utils.c"]
    }
    
    ground_truth3 = [
        {
            "id": "GHSA-diff-9999-0000",
            "summary": "SQL injection in API endpoint",
            "details": "API parameter concatenated into SQL query",
            "aliases": ["CVE-2024-99999"]
        }
    ]
    
    try:
        result3 = await invoke_kernel(kernel, lead3, ground_truth3)
        print(f"\nResult: {json.dumps(result3, indent=2)}")
        
        # Should be 0 since they're different vulnerability types
        assert result3.get("score") in [0, 1], "Score must be 0 or 1"
        print("✓ Test 3 passed: Valid response for non-matching case")
        
    except Exception as e:
        print(f"❌ Test 3 failed: {e}")
        return False
    
    print("\n" + "="*50)
    print("✅ All tests passed!")
    print("="*50)
    return True


if __name__ == "__main__":
    success = asyncio.run(test_scorer())
    sys.exit(0 if success else 1)
