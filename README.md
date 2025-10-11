# VulGPT
Senior Project TAMUSA

# Dockerized Vulnerability Detection Tool

This repository contains a Python backend (with Neo4j integration) and a Vue/Vite frontend. The following instructions describe how to build and run both services using Docker Compose.

---

## Prerequisites

- **Docker**: Install [Docker](https://docs.docker.com/get-docker/).
- **Docker Compose**: Comes bundled with Docker Desktop on Windows/Mac. On Linux, install separately if needed.

---


**Key Files:**

- **docker-compose.yml**: Defines the `backend` and `frontend` services.
- **.env**: Contains environment variables like `NEO4J_IP`, `NEO4J_USER`, `NEO4J_PASS`.
- **src/backend/Dockerfile**: Builds the Python backend image.
- **src/frontend/Dockerfile**: Builds the Vue (Vite) frontend image.

---

## Environment Variables

Create a `.env` file in the project root with your Neo4j credentials:

```env
NEO4J_IP=your.neo4j.external.ip
NEO4J_USER=neo4j
NEO4J_PASS=your_password
```
---

# Running the Containers

## 1. Clone this Repository
If you haven’t already, clone this repository.  

## 2. Navigate to the Project Root
Ensure you are in the directory where `docker-compose.yml` is located.  

## 3. Build and Start the Containers
Run the following command:  

```bash
docker-compose up --build
```
## This Will
- Build the **FASTAPI backend** image.  
- Build the **Vue (Vite) frontend** image.  
- Start both containers on a Docker network (`app-network`).  

---

## 4. Check Logs
- The backend runs `main.py`, which prints **"Hello from FASTAPI!"** upon successfully connecting to FastAPI on 8080 port.  
- The frontend starts a **Vite dev server** at [http://localhost:5173](http://localhost:5173).

---

## 5. Access the Frontend
Open your browser and go to:  
🔗 [http://localhost:5173](http://localhost:5173)

---

## Notes on the Backend

### ✅ Current Behavior
- The backend runs a FastAPI server  
- The backend includes an **LLM-powered vulnerability scanner** that chunks repository code and queries a local Ollama model (e.g., `mistral:7b-instruct-q4_0`) for structured vulnerability leads.

### 🤖 LLM Scanner Overview
- `src/backend/tasks/run_vulnerability_scanner.py` orchestrates the scan. It reads the checkout manifest, slices files into context-friendly chunks, and calls `VulnerabilityScanner`.
- `src/backend/api/llm/vulnerability_scanner.py` prepares prompts that enforce a Pydantic-defined YAML schema, invokes Ollama via `httpx`, and parses the model output into actionable findings.
- Generated leads are written to JSON artifacts such as `data/scanner_findings.json`, which include chunk metadata and CWE-classified leads for downstream triage.

To run the scanner manually once repositories are checked out:

```bash
PYTHONPATH=src uv run --project src/backend/api \
	src/backend/tasks/run_vulnerability_scanner.py \
	--manifest data/checkout_manifest.json \
	--output data/scanner_findings.json \
	--ollama-url http://localhost:11434 \
	--model mistral:7b-instruct-q4_0 \
	--chunk-size 1200 \
	--concurrency 1
```

> ℹ️  Ensure the Ollama container is running (`docker compose up ollama`) and that the target model is pulled before executing the scanner.

---

### 🔄 Future Implementation
1. **Adding** try points for FASTAPI url.

## FastAPI Configuration
- TBD

## Neo4j Configuration
- Ensure your **firewall rules** allow inbound traffic on **port 7687**.
- The `.env` file should have the correct **`NEO4J_URI`**.  

---

## Additional Tips

### ⚡ Live Reloading (Frontend)
- The frontend is mapped to **port 5173**.  
- If you want live reloading, make sure you haven’t overridden `/app` with a volume that omits `node_modules`.  

### 📁 Docker Volumes (For Local Development)
- If you want **immediate code changes**, you can **uncomment** the volume mappings in `docker-compose.yml` under the frontend service.  
- However, be mindful of handling `node_modules`.  

---

# Git Hook Setup
To enforce commit message conventions, run the following command after cloning the repository:

```bash
./setup-hooks.sh
