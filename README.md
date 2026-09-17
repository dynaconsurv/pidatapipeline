# AVEVA PI Web API to Oracle ERP Cloud Data Pipeline

An enterprise-grade, lightweight Industrial IoT (IIoT) data pipeline that extracts process telemetry from **AVEVA PI Web API (Asset Framework - AF)**, maps and transforms the attributes, and dispatches them into **Oracle ERP Cloud REST APIs** (e.g., Asset Maintenance, Meter Readings, Inventory, or Standard Receipts).

> **Zero-Database Architecture**: All configurations, attribute mappings, telemetry pull histories, ERP publish histories, and audit logs are persisted exclusively in human-readable JSON files (`config/` and `data/`).

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.10+
- Installed packages: `fastapi`, `uvicorn`, `requests`, `pydantic`

```bash
pip install -r requirements.txt
```

### 2. Launch the Application
Run the startup script:
```bash
python run.py
```
Open your browser at:
**[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

## 🧭 Application Features & Pages

### 1. 📊 Dashboard Page (`/`)
- **AVEVA PI Web API Status Card**:
  - Live connectivity indicator (**Connected**, **Simulation Mode**, or **Failed**).
  - Round-trip latency in milliseconds and last successful pull timestamp.
  - Interactive **"Pull Now"** and **"Test PI"** buttons.
  - Diagnostic error console displaying detailed error logs and SSL troubleshooting hints if connection fails.
- **Oracle ERP Cloud API Status Card**:
  - Displays **Pending connection setup** by default until your Oracle ERP Cloud credentials and endpoint are confirmed.
  - Shows current authentication method, target resource path, and status reason.
  - Interactive **"Test ERP / Token"** button.
  - Diagnostic error console if connection or OAuth token exchange fails.
- **Scheduler & Next Pull Countdown Card**:
  - Live real-time countdown clock (e.g. `00:24`) showing seconds remaining until the next scheduled data pull.
  - Quick **Pause / Resume** and **Trigger Run** controls.
  - Configurable interval (default: 30 seconds).
- **Last ERP Publish Card**:
  - Displays **Pending Setup** status, record count staged, timestamp, and HTTP response code.
  - One-click inspection of the staged ERP JSON payload.
- **Last 5 Data Pulls from AVEVA PI Web API Table**:
  - Prominently displays the last 5 telemetry items pulled:
    - Attribute Name & Unit of Measure (UOM)
    - Full AF Path (`\\Server\Database\Element|Attribute`)
    - Current Process Value
    - Source PI Timestamp
    - Quality / Status badge (`Good`, `Questionable`, `Bad`)
    - Target ERP Meter Code
    - Ingestion Time
- **Pipeline Activity & Error Logs**:
  - Real-time audit log stream filterable by category (All, AVEVA PI Web API, Oracle ERP Cloud, Pipeline Engine, System).

---

### 2. 🔀 Attribute Mapping Page
Configure which attributes to extract from PI AF and where to map them in Oracle ERP Cloud:
- **AF Hierarchy Explorer**:
  - Interactive drill-down browser for PI AF Servers, AF Databases, Elements, and Attributes.
  - Direct "+ Map" shortcut to add an AF attribute into the pipeline.
  - **"Load Preset Templates"** button to load industrial asset presets (Boiler 101, Steam Turbine, Generator, Water Pumps).
- **Mappings Table**:
  - Active/Inactive toggle per attribute.
  - Source AF Server, AF Database, Element Path, and Attribute Name.
  - Target Oracle ERP Meter Code / Tag (e.g. `BLR101_STM_TEMP`).
  - Target ERP Value Field (e.g. `readingValue`).
  - Scaling multiplier and decimal rounding.
- **Target Oracle ERP Cloud Payload Preview**:
  - Live dynamic preview of the exact JSON payload structured for Oracle ERP Cloud REST ingestion.
- Persisted to: `config/mappings.json`.

---

### 3. ⚙️ Settings Page
- **AVEVA PI Web API Configuration**:
  - Base URL (e.g. `https://pi-server.local/piwebapi`).
  - Authentication: **Basic Authentication**, **Bearer Token**, **Kerberos (Windows Integrated)**, or **Anonymous**.
  - Default AF Server and AF Database.
  - **Verify SSL toggle**: Turn off if your industrial plant uses internal/self-signed SSL certificates.
  - **Simulation Mode toggle**: Enables built-in telemetry simulation with realistic industrial data so you can test the pipeline completely offline.
  - **"Test PI Connection"** button with diagnostic reporting.
- **Oracle ERP Cloud Configuration**:
  - **Enable Oracle ERP Cloud Transmission toggle**: Leave unchecked to maintain the safe **"Pending connection setup"** state.
  - Authentication method selector:
    - **OAuth 2.0 (Client Credentials - Recommended by Oracle)**:
      - Token URL (Oracle IDCS / IAM endpoint, e.g. `https://<idcs-instance>.identity.oraclecloud.com/oauth2/v1/token`)
      - Client ID & Client Secret
      - Scope (default: `urn:opc:resource:consumer::all`)
    - **Basic Authentication**: Username & Password for dev/test pods.
    - **Static Bearer Token**: Custom API gateway token.
  - Oracle ERP Cloud Pod Base URL (e.g. `https://<pod>.fa.oraclecloud.com`).
  - Resource Endpoint (e.g. `/fscmRestApi/resources/11.13.18.05/standardReceipts` or `/fscmRestApi/resources/latest/inventoryTransactions`).
  - HTTP Method: `POST`, `PATCH`, or `PUT`.
  - Dry-run validation toggle.
  - **"Test ERP Handshake / Token"** button.
- **Pipeline Scheduling**:
  - Interval in seconds (e.g. 10, 30, 60, 300).
- Persisted to: `config/settings.json`.

---

## 🔍 Oracle ERP Cloud API Integration Research

Here is the exact architectural specification for integrating with Oracle ERP Cloud:

### 1. Authentication
* **OAuth 2.0 Client Credentials Grant (Production Standard)**:
  1. Your Oracle Cloud Administrator registers a *Confidential Application* in Oracle Identity Cloud Service (IDCS) or Oracle Cloud Infrastructure (OCI) IAM Identity Domain.
  2. The application is assigned the appropriate ERP Cloud roles (e.g. *Asset Maintenance Integration*, *Inventory Manager*).
  3. The pipeline requests an OAuth access token:
     - **Method**: `POST`
     - **URL**: `https://<idcs-instance>.identity.oraclecloud.com/oauth2/v1/token`
     - **Headers**: `Authorization: Basic base64(client_id:client_secret)`
     - **Body**: `grant_type=client_credentials&scope=urn:opc:resource:consumer::all`
  4. Response:
     ```json
     {
       "access_token": "eyJhbGciOi...",
       "token_type": "Bearer",
       "expires_in": 3600
     }
     ```
  5. The pipeline automatically caches the token in memory and uses it until 60 seconds before expiration, avoiding unnecessary token requests.
  6. Subsequent REST API calls include:
     `Authorization: Bearer <access_token>`

* **Basic Authentication (Testing & Internal)**:
  - Sent directly as `Authorization: Basic base64(username:password)` with each request.
  - Note: Not supported if your Oracle ERP user is enforced with Single Sign-On (SSO) or MFA.

### 2. Standard Headers
Oracle Fusion Applications REST APIs expect:
```http
Content-Type: application/vnd.oracle.adf.resourceitem+json
Accept: application/json
REST-Framework-Version: 4
```

### 3. What Details to Request from your Oracle ERP Team
When your Oracle ERP Cloud administrator or integration partner is ready, request:
1. **Pod Base URL**: `https://<pod-name>.fa.<datacenter>.oraclecloud.com`
2. **Auth Details**:
   - If OAuth 2.0: IDCS Token URL, Client ID, Client Secret, Scope.
   - If Basic Auth: Integration Service Account Username & Password.
3. **Target Resource REST Path**:
   - For Meter Readings / Maintenance: `/fscmRestApi/resources/11.13.18.05/meterReadings`
   - For Receipts: `/fscmRestApi/resources/11.13.18.05/standardReceipts`
   - For Custom Objects: `/fscmRestApi/resources/latest/<customObjectName>_c`

---

## 🗂️ File Storage Structure

```
pidatapipeline/
├── config/
│   ├── settings.json         # PI Web API & Oracle ERP Cloud connection settings
│   └── mappings.json         # Configured PI AF attribute to ERP field mappings
├── data/
│   ├── pull_history.json     # Telemetry readings history pulled from PI Web API
│   ├── publish_history.json  # Dispatch records & ERP response payloads
│   └── logs.json             # Structured application and error audit log
├── app/
│   ├── config.py             # Reentrant thread-safe JSON settings & mappings manager
│   ├── pi_client.py          # AVEVA PI Web API client with simulation engine
│   ├── oracle_erp_client.py  # Oracle ERP Cloud OAuth 2.0 & REST client
│   ├── pipeline.py           # Background pipeline scheduler & extraction engine
│   ├── storage.py            # File-backed operational logging & history manager
│   ├── main.py               # FastAPI application & REST endpoints
│   └── static/
│       ├── index.html        # Interactive Single Page Application
│       ├── css/style.css     # Clean enterprise industrial telemetry theme
│       └── js/app.js         # Real-time dashboard polling & modal logic
├── run.py                    # Startup launcher
├── requirements.txt          # Python dependencies
└── README.md                 # Complete documentation
```
