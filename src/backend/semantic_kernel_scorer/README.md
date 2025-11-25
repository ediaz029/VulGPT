# Semantic Kernel Scorer Service

This service provides vulnerability lead scoring using Microsoft's Semantic Kernel framework with OpenAI or Azure OpenAI models.

## Configuration

### Option 1: OpenAI (Default)

Create or update `.env` file in the project root:

```env
OPENAI_API_KEY=sk-your-openai-api-key
OPENAI_MODEL_ID=gpt-4-turbo  # Optional, defaults to gpt-4-turbo
```

### Option 2: Azure OpenAI

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com
AZURE_OPENAI_API_KEY=your-azure-api-key
AZURE_OPENAI_DEPLOYMENT_NAME=your-deployment-name
```

## Installation

Install dependencies (from project root):

```bash
cd src/backend/api
uv sync
```

## Running the Service

Start the Semantic Kernel scorer on port 8901:

```bash
# From project root
PYTHONPATH=src/backend uv run --project src/backend/api \
  python -m uvicorn semantic_kernel_scorer.main:app \
  --host 0.0.0.0 \
  --port 8901
```

## Testing the Service

### Health Check

```bash
curl http://localhost:8901/health
```

Expected response:
```json
{"status": "ok", "service": "semantic_kernel"}
```

### Score a Lead

```bash
curl -X POST http://localhost:8901/score \
  -H "Content-Type: application/json" \
  -d '{
    "lead": {
      "headline": "SQL Injection vulnerability",
      "analysis": "User input is directly concatenated into SQL query without sanitization",
      "cwe": "CWE-89",
      "function_names": ["execute_query"],
      "filenames": ["src/database.py"]
    },
    "ground_truth": [
      {
        "id": "GHSA-xxxx-yyyy-zzzz",
        "summary": "SQL injection in database module",
        "details": "The execute_query function concatenates user input...",
        "aliases": ["CVE-2024-12345"]
      }
    ]
  }'
```

Expected response:
```json
{
  "score": 1,
  "reasoning": "The lead describes SQL injection (CWE-89) in execute_query function, which matches the ground truth vulnerability GHSA-xxxx-yyyy-zzzz.",
  "corresponds_to": "GHSA-xxxx-yyyy-zzzz",
  "source": "semantic_kernel"
}
```

## API Endpoints

### `GET /health`
Returns service health status.

### `POST /score`
Scores a vulnerability lead against ground truth.

**Request Body:**
```json
{
  "lead": {
    "headline": "string",
    "analysis": "string",
    "cwe": "string",
    "function_names": ["string"],
    "filenames": ["string"]
  },
  "ground_truth": [
    {
      "id": "string",
      "summary": "string",
      "details": "string",
      "aliases": ["string"]
    }
  ]
}
```

**Response:**
```json
{
  "score": 0 | 1,
  "reasoning": "string",
  "corresponds_to": "string | null",
  "source": "semantic_kernel"
}
```

## Architecture

- **agent.py**: Defines the system prompt for vulnerability scoring
- **main.py**: FastAPI service that wraps Semantic Kernel
- Uses deterministic temperature (0.0) for consistent scoring
- Supports both OpenAI and Azure OpenAI backends
- Returns responses in identical schema to ADK scorer for comparison

## Comparison with ADK Scorer

Both scorers expose the same API contract:
- ADK scorer runs on port 8900 (uses Google Gemini)
- SK scorer runs on port 8901 (uses OpenAI/Azure)
- Both return: `score`, `reasoning`, `corresponds_to`, `source`

This allows A/B testing by pointing `RemoteScoringClient` to different endpoints.
