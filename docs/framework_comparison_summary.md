# ADK vs Semantic Kernel - Quick Summary
**Real Benchmark Results | November 24, 2025**

---

## 🎯 The Question
Which AI framework should VulGPT use for vulnerability scoring: Google ADK or Microsoft Semantic Kernel?

---

## 📊 Test Setup
- **12 test cases**: SQL Injection, XSS, Path Traversal, Memory Leaks, Timing Attacks, CSRF, RCE, XXE
- **Both models tested**: Google Gemini 2.5 Flash vs OpenAI GPT-4o-mini
- **Live services**: Both running simultaneously, real API calls

---

## ✅ Results Summary

| Metric | ADK (Google) | SK (OpenAI) | Winner |
|--------|--------------|-------------|---------|
| **Accuracy** | ✅ **100%** | ✅ **100%** | **TIE** |
| **Precision** | ✅ **100%** | ✅ **100%** | **TIE** |
| **Recall** | ✅ **100%** | ✅ **100%** | **TIE** |
| **Speed** | 3.50s | **2.66s** | **SK (24% faster)** |
| **Cost/1K** | $0.50 | **$0.15** | **SK (70% cheaper)** |
| **Errors** | 0% | 0% | TIE |

---

## 🏆 Winner: Semantic Kernel

**Why?**
- ✅ **Same perfect accuracy** as ADK
- ✅ **24% faster** (834ms saved per lead)
- ✅ **70% cheaper** ($35/month savings per 100K leads)
- ✅ **More flexible** (can swap models easily)

---

## 💡 Key Insight
Both frameworks are **production-ready** with perfect accuracy. Choose Semantic Kernel for better **speed + cost**, or ADK if you need **Google ecosystem integration**.

**Recommendation:** Deploy with Semantic Kernel.

---

## 📈 Real-World Impact

**Scanning 1,000 vulnerability leads:**
- ADK: 58 minutes, $0.50
- SK: **43 minutes**, **$0.15** ✅

**Savings:** 15 minutes + $0.35 per 1K leads

At scale (100K leads/month): **$35/month savings, 25 hours faster**

---

## 🔬 Technical Details
- Both services expose identical `/score` API
- Both achieved 7/7 true positives, 0/0 false positives
- Both correctly rejected all 5 edge cases
- Zero errors across all 12 tests
- Full results: `data/framework_comparison_results.json`
- Analysis: `docs/framework_comparison_analysis.md`

---

## ✨ Demo Commands

**Start services:**
```bash
# Terminal 1: ADK
PYTHONPATH=src/backend uv run --project src/backend/api \
  python -m uvicorn adk_scorer.main:app --port 8900

# Terminal 2: SK  
PYTHONPATH=src/backend uv run --project src/backend/api \
  python -m uvicorn semantic_kernel_scorer.main:app --port 8901
```

**Test them:**
```bash
curl http://localhost:8900/health
curl http://localhost:8901/health
```

**Run benchmark:**
```bash
PYTHONPATH=src/backend uv run --project src/backend/api \
  python src/backend/semantic_kernel_scorer/run_benchmark.py
```
