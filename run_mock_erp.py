"""
Standalone launcher for the Oracle ERP Cloud Mock Simulation Server.
Run with: python run_mock_erp.py
"""
import sys
import uvicorn
from app.mock_erp_server import mock_erp_app, MOCK_PORT

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else MOCK_PORT
    print("=" * 60)
    print(f"  Oracle ERP Cloud Mock Simulation Server")
    print(f"  Host: http://127.0.0.1:{port}")
    print(f"  OAuth Token URL: http://127.0.0.1:{port}/oauth2/v1/token")
    print(f"  FSCM REST API: http://127.0.0.1:{port}/fscmRestApi/resources/11.13.18.05/standardReceipts")
    print("=" * 60)
    uvicorn.run(mock_erp_app, host="127.0.0.1", port=port, log_level="info")
