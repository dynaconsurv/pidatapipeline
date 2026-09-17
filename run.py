"""
Startup launcher for the AVEVA PI to Oracle ERP Cloud Data Pipeline Web Application.
Run with: python run.py
"""
import os
import sys
import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "127.0.0.1")
    print(f"============================================================")
    print(f"  AVEVA PI Web API -> Oracle ERP Cloud Data Pipeline")
    print(f"  Web Dashboard: http://{host}:{port}")
    print(f"  Storage: Pure JSON files in ./config/ and ./data/")
    print(f"============================================================")
    uvicorn.run("app.main:app", host=host, port=port, log_level="info")
