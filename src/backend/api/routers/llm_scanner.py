"""
FastAPI router for LLM-based vulnerability scanning
"""

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import os
import tempfile
import asyncio
from src.backend.api.llm.vulnerability_scanner import scanner, LeadList, ScoreResponse

router = APIRouter()

class CodeAnalysisRequest(BaseModel):
    code: str
    file_path: Optional[str] = ""
    language: Optional[str] = "python"

class CodeAnalysisResponse(BaseModel):
    vulnerabilities: LeadList
    analysis_time: float
    file_path: str

class VulnerabilityScore(BaseModel):
    submission: Dict[str, Any]
    real_vulnerabilities: List[Dict[str, Any]]

class ScanStatusResponse(BaseModel):
    status: str
    message: str
    model_available: bool

@router.get("/scan/status", response_model=ScanStatusResponse)
async def get_scan_status():
    """Check if the vulnerability scanning service is available"""
    try:
        # Test Ollama connection
        test_response = await scanner._call_ollama("Hello")
        model_available = test_response is not None
        
        return ScanStatusResponse(
            status="ready" if model_available else "model_unavailable",
            message="Vulnerability scanning is ready" if model_available else "LLM model not available",
            model_available=model_available
        )
    except Exception as e:
        return ScanStatusResponse(
            status="error",
            message=f"Scanning service error: {str(e)}",
            model_available=False
        )

@router.post("/scan/code", response_model=CodeAnalysisResponse)
async def scan_code_for_vulnerabilities(request: CodeAnalysisRequest):
    """
    Analyze code for security vulnerabilities using LLM
    
    Args:
        request: Code analysis request with code content and metadata
        
    Returns:
        Analysis results with identified vulnerabilities
    """
    try:
        import time
        start_time = time.time()
        
        # Analyze the code
        result = await scanner.analyze_code_chunk(request.code, request.file_path)
        
        if result is None:
            raise HTTPException(
                status_code=500, 
                detail="Failed to analyze code. LLM may be unavailable or returned invalid response."
            )
        
        analysis_time = time.time() - start_time
        
        return CodeAnalysisResponse(
            vulnerabilities=result,
            analysis_time=analysis_time,
            file_path=request.file_path
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Code analysis failed: {str(e)}")

@router.post("/scan/file")
async def scan_file_for_vulnerabilities(file: UploadFile = File(...)):
    """
    Upload and analyze a file for security vulnerabilities
    
    Args:
        file: Uploaded file to analyze
        
    Returns:
        Analysis results with identified vulnerabilities
    """
    try:
        # Check file size (limit to 1MB)
        if file.size and file.size > 1024 * 1024:
            raise HTTPException(status_code=413, detail="File too large. Maximum size is 1MB.")
        
        # Read file content
        content = await file.read()
        try:
            code_content = content.decode('utf-8')
        except UnicodeDecodeError:
            raise HTTPException(status_code=400, detail="File must be a valid text file (UTF-8 encoded)")
        
        # Analyze the code
        import time
        start_time = time.time()
        
        result = await scanner.analyze_code_chunk(code_content, file.filename or "uploaded_file")
        
        if result is None:
            raise HTTPException(
                status_code=500, 
                detail="Failed to analyze file. LLM may be unavailable or returned invalid response."
            )
        
        analysis_time = time.time() - start_time
        
        return CodeAnalysisResponse(
            vulnerabilities=result,
            analysis_time=analysis_time,
            file_path=file.filename or "uploaded_file"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File analysis failed: {str(e)}")

@router.post("/scan/score", response_model=ScoreResponse)
async def score_vulnerability_submission(request: VulnerabilityScore):
    """
    Score a vulnerability submission against real vulnerabilities
    
    Args:
        request: Vulnerability scoring request
        
    Returns:
        Score and reasoning for the submission
    """
    try:
        result = await scanner.score_vulnerability(
            request.submission, 
            request.real_vulnerabilities
        )
        
        if result is None:
            raise HTTPException(
                status_code=500, 
                detail="Failed to score vulnerability. LLM may be unavailable or returned invalid response."
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vulnerability scoring failed: {str(e)}")

@router.get("/scan/models")
async def list_available_models():
    """List available LLM models for vulnerability scanning"""
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{scanner.ollama_url}/api/tags")
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(status_code=500, detail="Failed to fetch available models")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching models: {str(e)}")

@router.post("/scan/repository")
async def scan_repository_directory(directory_path: str):
    """
    Scan a directory/repository for vulnerabilities
    
    Args:
        directory_path: Path to the directory to scan
        
    Returns:
        Aggregated vulnerability analysis results
    """
    if not os.path.exists(directory_path):
        raise HTTPException(status_code=404, detail="Directory not found")
    
    if not os.path.isdir(directory_path):
        raise HTTPException(status_code=400, detail="Path must be a directory")
    
    # Security check - prevent scanning outside allowed directories
    allowed_paths = ["/tmp", "/workspace", "/app"]
    if not any(directory_path.startswith(path) for path in allowed_paths):
        raise HTTPException(status_code=403, detail="Directory scanning not allowed for this path")
    
    try:
        results = []
        supported_extensions = {'.py', '.js', '.ts', '.java', '.cpp', '.c', '.php', '.rb', '.go'}
        
        # Walk through directory and analyze code files
        for root, dirs, files in os.walk(directory_path):
            # Skip hidden directories and common non-source directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', 'venv', 'env']]
            
            for file in files:
                if any(file.endswith(ext) for ext in supported_extensions):
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, directory_path)
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            
                        # Skip very large files (>50KB)
                        if len(content) > 50 * 1024:
                            continue
                            
                        # Analyze the file
                        result = await scanner.analyze_code_chunk(content, relative_path)
                        if result and result.leads:
                            results.append({
                                "file_path": relative_path,
                                "vulnerabilities": result.dict()
                            })
                            
                    except Exception as e:
                        # Log error but continue with other files
                        print(f"Error analyzing {file_path}: {e}")
                        continue
        
        return {
            "directory": directory_path,
            "total_files_analyzed": len(results),
            "results": results
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Repository scan failed: {str(e)}")