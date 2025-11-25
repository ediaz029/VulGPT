"""Benchmark script to compare ADK and Semantic Kernel scorers."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Dict, List, Any

import httpx

from benchmark_data import MOCK_BENCHMARK, get_benchmark_stats

# Scorer endpoints
ADK_ENDPOINT = "http://localhost:8900/score"
SK_ENDPOINT = "http://localhost:8901/score"


async def score_with_service(
    endpoint: str,
    lead: Dict[str, Any],
    ground_truth: List[Dict[str, Any]],
    timeout: float = 30.0
) -> Dict[str, Any]:
    """Score a lead using the specified service endpoint."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        start_time = time.time()
        try:
            response = await client.post(
                endpoint,
                json={"lead": lead, "ground_truth": ground_truth}
            )
            elapsed = time.time() - start_time
            response.raise_for_status()
            result = response.json()
            result["latency_ms"] = round(elapsed * 1000, 2)
            result["error"] = None
            return result
        except Exception as e:
            elapsed = time.time() - start_time
            return {
                "score": None,
                "reasoning": "",
                "corresponds_to": None,
                "source": endpoint,
                "latency_ms": round(elapsed * 1000, 2),
                "error": str(e)
            }


async def run_benchmark():
    """Run both scorers on the benchmark dataset."""
    print("="*70)
    print("ADK vs Semantic Kernel Scorer Comparison")
    print("="*70)
    
    benchmark_stats = get_benchmark_stats()
    print(f"\nBenchmark Dataset:")
    print(f"  Total test cases: {benchmark_stats['total_cases']}")
    print(f"  Expected TPs: {benchmark_stats['expected_true_positives']}")
    print(f"  Expected FPs: {benchmark_stats['expected_false_positives']}")
    print(f"  Expected TNs: {benchmark_stats['expected_true_negatives']}")
    print(f"  Categories: {', '.join(benchmark_stats['categories'])}")
    
    print(f"\n{'='*70}")
    print("Running benchmark...")
    print(f"{'='*70}\n")
    
    results = []
    
    for i, test_case in enumerate(MOCK_BENCHMARK, 1):
        test_id = test_case["id"]
        lead = test_case["lead"]
        ground_truth = test_case["ground_truth"]
        expected = test_case["expected_score"]
        category = test_case["category"]
        
        print(f"[{i}/{len(MOCK_BENCHMARK)}] {test_id} ({category})")
        print(f"  Lead: {lead['headline']}")
        
        # Score with both services
        adk_result = await score_with_service(ADK_ENDPOINT, lead, ground_truth)
        sk_result = await score_with_service(SK_ENDPOINT, lead, ground_truth)
        
        result = {
            "test_id": test_id,
            "category": category,
            "expected_score": expected,
            "lead": lead,
            "ground_truth": ground_truth,
            "adk": adk_result,
            "sk": sk_result,
        }
        results.append(result)
        
        # Print quick summary
        adk_status = "✓" if adk_result["score"] == expected else "✗"
        sk_status = "✓" if sk_result["score"] == expected else "✗"
        
        print(f"  ADK:  score={adk_result['score']} {adk_status} ({adk_result['latency_ms']}ms)")
        print(f"  SK:   score={sk_result['score']} {sk_status} ({sk_result['latency_ms']}ms)")
        print()
    
    return results


def calculate_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Calculate comparison metrics from results."""
    metrics = {
        "adk": {
            "true_positives": 0,
            "false_positives": 0,
            "true_negatives": 0,
            "false_negatives": 0,
            "correct_predictions": 0,
            "latencies_ms": [],
            "errors": 0,
        },
        "sk": {
            "true_positives": 0,
            "false_positives": 0,
            "true_negatives": 0,
            "false_negatives": 0,
            "correct_predictions": 0,
            "latencies_ms": [],
            "errors": 0,
        }
    }
    
    for result in results:
        expected = result["expected_score"]
        has_ground_truth = len(result["ground_truth"]) > 0
        
        for framework in ["adk", "sk"]:
            fw_result = result[framework]
            score = fw_result["score"]
            
            if fw_result["error"]:
                metrics[framework]["errors"] += 1
                continue
            
            metrics[framework]["latencies_ms"].append(fw_result["latency_ms"])
            
            if score == expected:
                metrics[framework]["correct_predictions"] += 1
            
            if score == 1 and expected == 1:
                metrics[framework]["true_positives"] += 1
            elif score == 1 and expected == 0:
                metrics[framework]["false_positives"] += 1
            elif score == 0 and expected == 0:
                metrics[framework]["true_negatives"] += 1
            elif score == 0 and expected == 1:
                metrics[framework]["false_negatives"] += 1
    
    # Calculate derived metrics
    for framework in ["adk", "sk"]:
        m = metrics[framework]
        tp = m["true_positives"]
        fp = m["false_positives"]
        fn = m["false_negatives"]
        
        m["precision"] = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        m["recall"] = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        m["f1_score"] = (
            2 * m["precision"] * m["recall"] / (m["precision"] + m["recall"])
            if (m["precision"] + m["recall"]) > 0 else 0.0
        )
        m["accuracy"] = m["correct_predictions"] / len(results) if results else 0.0
        
        latencies = m["latencies_ms"]
        m["avg_latency_ms"] = sum(latencies) / len(latencies) if latencies else 0.0
        m["min_latency_ms"] = min(latencies) if latencies else 0.0
        m["max_latency_ms"] = max(latencies) if latencies else 0.0
    
    return metrics


def print_comparison_report(metrics: Dict[str, Any]):
    """Print formatted comparison report."""
    print("\n" + "="*70)
    print("COMPARISON MATRIX")
    print("="*70)
    
    print(f"\n{'Metric':<30} {'ADK (Google)':<20} {'SK (OpenAI)':<20}")
    print("-"*70)
    
    # Correctness metrics
    print(f"{'Precision':<30} {metrics['adk']['precision']:>19.2%} {metrics['sk']['precision']:>19.2%}")
    print(f"{'Recall':<30} {metrics['adk']['recall']:>19.2%} {metrics['sk']['recall']:>19.2%}")
    print(f"{'F1 Score':<30} {metrics['adk']['f1_score']:>19.2%} {metrics['sk']['f1_score']:>19.2%}")
    print(f"{'Accuracy':<30} {metrics['adk']['accuracy']:>19.2%} {metrics['sk']['accuracy']:>19.2%}")
    
    print("\n" + "-"*70)
    
    # Confusion matrix elements
    print(f"{'True Positives':<30} {metrics['adk']['true_positives']:>19} {metrics['sk']['true_positives']:>19}")
    print(f"{'False Positives':<30} {metrics['adk']['false_positives']:>19} {metrics['sk']['false_positives']:>19}")
    print(f"{'True Negatives':<30} {metrics['adk']['true_negatives']:>19} {metrics['sk']['true_negatives']:>19}")
    print(f"{'False Negatives':<30} {metrics['adk']['false_negatives']:>19} {metrics['sk']['false_negatives']:>19}")
    
    print("\n" + "-"*70)
    
    # Performance metrics
    print(f"{'Avg Latency (ms)':<30} {metrics['adk']['avg_latency_ms']:>19.1f} {metrics['sk']['avg_latency_ms']:>19.1f}")
    print(f"{'Min Latency (ms)':<30} {metrics['adk']['min_latency_ms']:>19.1f} {metrics['sk']['min_latency_ms']:>19.1f}")
    print(f"{'Max Latency (ms)':<30} {metrics['adk']['max_latency_ms']:>19.1f} {metrics['sk']['max_latency_ms']:>19.1f}")
    print(f"{'Errors':<30} {metrics['adk']['errors']:>19} {metrics['sk']['errors']:>19}")
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    # Determine winner
    adk_score = (metrics['adk']['f1_score'] * 0.5 + 
                 metrics['adk']['accuracy'] * 0.3 +
                 (1 - metrics['adk']['avg_latency_ms']/1000) * 0.2)
    sk_score = (metrics['sk']['f1_score'] * 0.5 + 
                metrics['sk']['accuracy'] * 0.3 +
                (1 - metrics['sk']['avg_latency_ms']/1000) * 0.2)
    
    if abs(adk_score - sk_score) < 0.05:
        winner = "TIE - Both frameworks perform similarly"
    elif adk_score > sk_score:
        winner = "ADK (Google Gemini) - Better overall performance"
    else:
        winner = "Semantic Kernel (OpenAI) - Better overall performance"
    
    print(f"\nWinner: {winner}\n")
    
    print("Key Observations:")
    
    if metrics['adk']['precision'] > metrics['sk']['precision']:
        print("  • ADK has higher precision (fewer false positives)")
    elif metrics['sk']['precision'] > metrics['adk']['precision']:
        print("  • Semantic Kernel has higher precision (fewer false positives)")
    
    if metrics['adk']['recall'] > metrics['sk']['recall']:
        print("  • ADK has higher recall (catches more real vulnerabilities)")
    elif metrics['sk']['recall'] > metrics['adk']['recall']:
        print("  • Semantic Kernel has higher recall (catches more real vulnerabilities)")
    
    if metrics['adk']['avg_latency_ms'] < metrics['sk']['avg_latency_ms']:
        faster_pct = ((metrics['sk']['avg_latency_ms'] - metrics['adk']['avg_latency_ms']) / 
                      metrics['sk']['avg_latency_ms'] * 100)
        print(f"  • ADK is {faster_pct:.1f}% faster")
    else:
        faster_pct = ((metrics['adk']['avg_latency_ms'] - metrics['sk']['avg_latency_ms']) / 
                      metrics['adk']['avg_latency_ms'] * 100)
        print(f"  • Semantic Kernel is {faster_pct:.1f}% faster")
    
    print("\n" + "="*70)


async def main():
    """Main benchmark execution."""
    try:
        # Run benchmark
        results = await run_benchmark()
        
        # Calculate metrics
        metrics = calculate_metrics(results)
        
        # Print report
        print_comparison_report(metrics)
        
        # Save results
        output_file = Path(__file__).parent.parent.parent.parent / "data" / "framework_comparison_results.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, "w") as f:
            json.dump({
                "results": results,
                "metrics": metrics
            }, f, indent=2)
        
        print(f"\nDetailed results saved to: {output_file}")
        
    except Exception as e:
        print(f"\n❌ Benchmark failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
