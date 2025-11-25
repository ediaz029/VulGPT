"""Mock benchmark dataset for comparing ADK and Semantic Kernel scorers."""
from __future__ import annotations

# Diverse set of vulnerability test cases with known ground truth
MOCK_BENCHMARK = [
    # Test 1: True Positive - SQL Injection (should match)
    {
        "id": "test_001",
        "lead": {
            "headline": "SQL Injection in user authentication",
            "analysis": "User-supplied credentials are directly concatenated into SQL query without parameterization",
            "cwe": "CWE-89",
            "function_names": ["authenticate_user", "build_query"],
            "filenames": ["auth/login.py"]
        },
        "ground_truth": [
            {
                "id": "GHSA-2024-1234",
                "summary": "SQL injection vulnerability in authentication module",
                "details": "The authenticate_user function concatenates user input into SQL queries",
                "aliases": ["CVE-2024-1234"]
            }
        ],
        "expected_score": 1,
        "category": "sql_injection"
    },
    
    # Test 2: True Positive - XSS (should match)
    {
        "id": "test_002",
        "lead": {
            "headline": "Cross-Site Scripting in comment rendering",
            "analysis": "User comments are rendered without HTML escaping, allowing script injection",
            "cwe": "CWE-79",
            "function_names": ["render_comment", "display_user_content"],
            "filenames": ["views/comments.js"]
        },
        "ground_truth": [
            {
                "id": "GHSA-2024-5678",
                "summary": "Stored XSS vulnerability in comment system",
                "details": "User-generated comments are not sanitized before display",
                "aliases": ["CVE-2024-5678"]
            }
        ],
        "expected_score": 1,
        "category": "xss"
    },
    
    # Test 3: True Positive - Path Traversal (should match)
    {
        "id": "test_003",
        "lead": {
            "headline": "Path Traversal in file download endpoint",
            "analysis": "User-provided filename is used without validation, allowing access to arbitrary files",
            "cwe": "CWE-22",
            "function_names": ["download_file"],
            "filenames": ["api/files.py"]
        },
        "ground_truth": [
            {
                "id": "GHSA-2024-9012",
                "summary": "Directory traversal in file download API",
                "details": "Insufficient path validation allows reading arbitrary files",
                "aliases": ["CVE-2024-9012"]
            }
        ],
        "expected_score": 1,
        "category": "path_traversal"
    },
    
    # Test 4: False Positive - Overly broad lead (should NOT match)
    {
        "id": "test_004",
        "lead": {
            "headline": "Potential security issue in data processing",
            "analysis": "The system processes user data which could potentially be exploited",
            "cwe": "CWE-20",
            "function_names": ["process_data"],
            "filenames": ["utils/processor.py"]
        },
        "ground_truth": [
            {
                "id": "GHSA-2024-3456",
                "summary": "Command injection in image processing",
                "details": "Image metadata is passed to shell command without sanitization",
                "aliases": ["CVE-2024-3456"]
            }
        ],
        "expected_score": 0,
        "category": "false_positive_vague"
    },
    
    # Test 5: False Positive - Wrong CWE (should NOT match)
    {
        "id": "test_005",
        "lead": {
            "headline": "Buffer overflow in string parsing",
            "analysis": "Fixed-size buffer can overflow when processing long input strings",
            "cwe": "CWE-120",
            "function_names": ["parse_string"],
            "filenames": ["parser.c"]
        },
        "ground_truth": [
            {
                "id": "GHSA-2024-7890",
                "summary": "SQL injection in search functionality",
                "details": "Search queries are concatenated without parameterization",
                "aliases": ["CVE-2024-7890"]
            }
        ],
        "expected_score": 0,
        "category": "false_positive_wrong_type"
    },
    
    # Test 6: True Negative - No ground truth (should NOT match)
    {
        "id": "test_006",
        "lead": {
            "headline": "Insecure deserialization in session handler",
            "analysis": "Session data is deserialized without integrity checks",
            "cwe": "CWE-502",
            "function_names": ["load_session"],
            "filenames": ["session.py"]
        },
        "ground_truth": [],
        "expected_score": 0,
        "category": "true_negative_no_vuln"
    },
    
    # Test 7: True Positive - Memory leak (should match)
    {
        "id": "test_007",
        "lead": {
            "headline": "Memory leak in build process",
            "analysis": "Heap memory is leaked into the final executable during packaging",
            "cwe": "CWE-401",
            "function_names": ["build_package"],
            "filenames": ["builder.js"]
        },
        "ground_truth": [
            {
                "id": "GHSA-2024-mem1",
                "summary": "Memory leak during build exposes sensitive data",
                "details": "Build process leaks Node.js heap memory into output",
                "aliases": ["CVE-2024-mem1"]
            }
        ],
        "expected_score": 1,
        "category": "memory_leak"
    },
    
    # Test 8: True Positive - Authentication bypass (should match)
    {
        "id": "test_008",
        "lead": {
            "headline": "Authentication bypass via timing attack",
            "analysis": "Token comparison uses non-constant-time equality check",
            "cwe": "CWE-208",
            "function_names": ["verify_token"],
            "filenames": ["auth/verify.py"]
        },
        "ground_truth": [
            {
                "id": "GHSA-2024-time1",
                "summary": "Timing attack in bearer authentication",
                "details": "Token verification allows timing-based token length estimation",
                "aliases": ["CVE-2024-time1"]
            }
        ],
        "expected_score": 1,
        "category": "timing_attack"
    },
    
    # Test 9: False Positive - Wrong function (should NOT match)
    {
        "id": "test_009",
        "lead": {
            "headline": "SQL injection in export function",
            "analysis": "Export query concatenates user filters without sanitization",
            "cwe": "CWE-89",
            "function_names": ["export_data"],
            "filenames": ["export.py"]
        },
        "ground_truth": [
            {
                "id": "GHSA-2024-import1",
                "summary": "SQL injection in import function",
                "details": "Import functionality has SQL injection in column mapping",
                "aliases": ["CVE-2024-import1"]
            }
        ],
        "expected_score": 0,
        "category": "false_positive_wrong_function"
    },
    
    # Test 10: True Positive - CSRF (should match)
    {
        "id": "test_010",
        "lead": {
            "headline": "Cross-Site Request Forgery in settings update",
            "analysis": "Settings endpoint lacks CSRF token validation",
            "cwe": "CWE-352",
            "function_names": ["update_settings"],
            "filenames": ["api/settings.py"]
        },
        "ground_truth": [
            {
                "id": "GHSA-2024-csrf1",
                "summary": "CSRF vulnerability in account settings",
                "details": "Settings modification endpoint missing CSRF protection",
                "aliases": ["CVE-2024-csrf1"]
            }
        ],
        "expected_score": 1,
        "category": "csrf"
    },
    
    # Test 11: Edge case - Multiple ground truths, only one matches
    {
        "id": "test_011",
        "lead": {
            "headline": "Remote Code Execution via template injection",
            "analysis": "User input is evaluated in template context without sandboxing",
            "cwe": "CWE-94",
            "function_names": ["render_template"],
            "filenames": ["templates/engine.py"]
        },
        "ground_truth": [
            {
                "id": "GHSA-2024-sqli2",
                "summary": "SQL injection in reporting module",
                "details": "Report queries lack parameterization",
                "aliases": ["CVE-2024-sqli2"]
            },
            {
                "id": "GHSA-2024-rce1",
                "summary": "Template injection leads to RCE",
                "details": "Template engine evaluates user input as code",
                "aliases": ["CVE-2024-rce1"]
            }
        ],
        "expected_score": 1,
        "category": "rce_template_injection"
    },
    
    # Test 12: Edge case - Similar but distinct vulnerabilities
    {
        "id": "test_012",
        "lead": {
            "headline": "XML External Entity injection",
            "analysis": "XML parser allows external entity expansion without restrictions",
            "cwe": "CWE-611",
            "function_names": ["parse_xml"],
            "filenames": ["parser/xml.py"]
        },
        "ground_truth": [
            {
                "id": "GHSA-2024-xxe2",
                "summary": "XXE in SVG file upload",
                "details": "SVG upload processing vulnerable to XXE",
                "aliases": ["CVE-2024-xxe2"]
            }
        ],
        "expected_score": 0,
        "category": "false_positive_similar"
    },
]

def get_benchmark_stats():
    """Calculate expected statistics for the benchmark."""
    expected_tp = sum(1 for case in MOCK_BENCHMARK if case["expected_score"] == 1)
    expected_fp = sum(1 for case in MOCK_BENCHMARK if case["expected_score"] == 0 and case["ground_truth"])
    expected_tn = sum(1 for case in MOCK_BENCHMARK if case["expected_score"] == 0 and not case["ground_truth"])
    
    return {
        "total_cases": len(MOCK_BENCHMARK),
        "expected_true_positives": expected_tp,
        "expected_false_positives": expected_fp,
        "expected_true_negatives": expected_tn,
        "categories": list(set(case["category"] for case in MOCK_BENCHMARK))
    }
