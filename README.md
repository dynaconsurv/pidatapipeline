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

## 🔄 How to Forever Run the Application (Auto-Start / Background Service)

To run the data pipeline continuously in production so that you **never need to manually open a command prompt or keep a terminal window open**, choose any of the options below:

### Option 1: Automatic Windows Scheduled Task (Recommended — No Extra Software)
Runs silently in the background every time Windows boots up, before or without user login, with zero console windows visible.

1. Right-click [`scripts/install_windows_task.bat`](file:///C:/Users/Fuad/Documents/dev/pidatapipeline/scripts/install_windows_task.bat) and select **"Run as Administrator"**.
2. That's it! Windows Task Scheduler will now automatically launch the pipeline on system startup.
3. **Control Commands** (via Command Prompt / PowerShell):
   - Start immediately: `schtasks /run /tn "PIDataPipeline"`
   - Stop: Double-click [`scripts/stop_background.bat`](file:///C:/Users/Fuad/Documents/dev/pidatapipeline/scripts/stop_background.bat)
   - Remove auto-start: `schtasks /delete /tn "PIDataPipeline" /f`

---

### Option 2: Run as a Native Windows Service (Using NSSM)
If your organization requires management via the standard Windows Services manager (`services.msc`) with automatic crash recovery:

1. Download **[NSSM (Non-Sucking Service Manager)](https://nssm.cc/download)** and place `nssm.exe` in your system PATH (or in the project folder).
2. Open Command Prompt as Administrator and run:
   ```cmd
   nssm install PIDataPipeline "C:\Users\Fuad\AppData\Local\Python\pythoncore-3.14-64\python.exe" "C:\Users\Fuad\Documents\dev\pidatapipeline\run.py"
   nssm set PIDataPipeline AppDirectory "C:\Users\Fuad\Documents\dev\pidatapipeline"
   nssm set PIDataPipeline Description "AVEVA PI Web API to Oracle ERP Cloud Data Pipeline"
   nssm set PIDataPipeline Start SERVICE_AUTO_START
   nssm start PIDataPipeline
   ```
3. The pipeline will now run 24/7 as an official Windows Service, restart automatically on system reboot or failures, and can be paused/started from `services.msc`.

---

### Option 3: Silent Launcher & Windows Startup Folder (Quick & Simple)
If you want the pipeline to run silently whenever you log in to Windows without requiring Administrator privileges:

1. Press `Win + R`, type `shell:startup`, and hit Enter to open the Windows Startup folder.
2. Right-click [`scripts/start_background.vbs`](file:///C:/Users/Fuad/Documents/dev/pidatapipeline/scripts/start_background.vbs) and select **"Create shortcut"**.
3. Move that shortcut into the `shell:startup` folder.
4. It will now execute invisibly in the background every time you log in to Windows.
5. To stop it at any time, double-click [`scripts/stop_background.bat`](file:///C:/Users/Fuad/Documents/dev/pidatapipeline/scripts/stop_background.bat).

---

### Option 4: Linux / Server Deployment (systemd)
If deploying onto a Linux server or VM:

1. Copy [`scripts/pidatapipeline.service`](file:///C:/Users/Fuad/Documents/dev/pidatapipeline/scripts/pidatapipeline.service) to `/etc/systemd/system/`:
   ```bash
   sudo cp scripts/pidatapipeline.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now pidatapipeline
   ```
2. Check live status:
   ```bash
   sudo systemctl status pidatapipeline
   ```

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

### 4. 🧪 Local Oracle ERP Cloud Simulation Sub-Application (Port 8080)
For offline development, testing, and client demos without live Oracle Cloud tenant access, a dedicated sub-application runs on **port 8080**:
- **Simulates Oracle Identity Cloud Service (IDCS/IAM)**: Provides the standard `/oauth2/v1/token` endpoint accepting Client Credentials grant with Basic Auth or form body.
- **Simulates Oracle Fusion REST Resources**: Endpoints like `/fscmRestApi/resources/11.13.18.05/standardReceipts` handle OPTIONS handshake probes and HTTP 201 Created ingestion responses with unique `TransactionId` tokens.
- **One-Click Controls in Settings Page**:
  - **"Start Simulator (Port 8080)"**: Spawns the simulation sub-app asynchronously in the background.
  - **"Auto-Fill Mock Credentials & Activate"**: Automatically populates Settings with the simulator endpoints and credentials (`DEMO_ORCL_CLIENT_ID`, `DEMO_ORCL_SECRET_KEY_9982`), starts the simulator, and executes an immediate connection handshake test.
  - **"Inspect Ingested Data"**: Live view of telemetry payloads received and processed by the simulator.
  - **"Stop Simulator"**: Shuts down the sub-application cleanly.
- **Standalone CLI Runner**: Can also be executed independently in a separate console:
  ```bash
  python run_mock_erp.py
  # or custom port:
  python run_mock_erp.py 8080
  ```

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

## 📦 Software Packaging & Patch Releases (Zero-Git Update System)

This data pipeline includes a built-in release packaging and patch deployment system so that **end users never need Git installed or know any Git commands** to update to the latest release.

### 🛡️ Safety & Data Protection Guarantees
- **Config Protection**: Your plant's PI Web API credentials, Oracle ERP Cloud OAuth keys, and custom attribute mappings in `config/settings.json` and `config/mappings.json` are **NEVER overwritten** during a patch.
- **Data Protection**: Telemetry pull records and publish audit trails in `data/*.json` are completely untouched.
- **Rollback Backups**: Before applying any patch, the updater automatically archives the current working code to `backups/backup_v<version>_<timestamp>/`.
- **Dependency Sync**: If a new release adds Python packages to `requirements.txt`, the updater installs them automatically.

---

### 1. How Users Apply Patches (Without Git)

#### Method A: 1-Click Web UI Updater (Easiest)
1. Open the web interface at `http://127.0.0.1:8000` and navigate to **Settings**.
2. Scroll to **"Software Updates & Patch Management"**.
3. Click **"Check for Updates"**.
4. If a newer release is published on GitHub, the release notes and an **"Install Patch (vX.X.X)"** button will appear.
5. Click **"Install Patch"**. The backend will download the patch archive, create a rollback snapshot, update code files, and notify you when complete.
6. Restart the service or run `scripts/stop_background.bat` & `scripts/start_background.vbs`.

#### Method B: 1-Click Windows Batch File (`update.bat`)
1. In the application folder, double-click **`update.bat`**.
2. Select `[1]` to check for updates or `[2]` to download and apply the latest release directly.
3. The script automatically updates all code and dependencies without requiring Git.

#### Method C: Offline / Air-Gapped Plant Systems (Local ZIP Patch)
Industrial plant servers are often in isolated operational networks (OT) with no internet access:
1. Download the release package (`pidatapipeline-vX.X.X.zip`) from an internet-connected machine.
2. Transfer the `.zip` file via approved plant media to the pipeline server.
3. Apply it via either:
   - **Web UI**: In Settings, click **"Upload Offline Patch (.zip)"** and choose the file.
   - **Command Line**: Run `python -m app.updater --file path\to\pidatapipeline-vX.X.X.zip`.
   - **Batch**: Double-click `update.bat` and select Option `[3]`.

---

### 2. How the Developer Packages & Publishes a Release

#### Method A: Automatic via GitHub Actions
Whenever you create and push a Git tag:
```bash
git tag v1.0.1
git push origin v1.0.1
```
The GitHub Actions workflow (`.github/workflows/release.yml`) automatically builds the clean distribution `.zip` and creates a published GitHub Release with the downloadable asset attached.

#### Method B: Local Packaging Script (`package_release.py`)
Run the packaging utility to create a clean release archive:
```bash
# Package current version
python package_release.py

# Or bump version and package in one step
python package_release.py --version 1.0.1
```
Output:
- Creates `dist/pidatapipeline-v1.0.1.zip`
- Generates SHA-256 checksum: `dist/pidatapipeline-v1.0.1.zip.sha256`
- Automatically excludes `.git`, `__pycache__`, local dev data (`data/*.json`), developer credentials (`config/*.json`), tests, and build artifacts.
- You can now attach this `.zip` to your GitHub Release or deliver it directly to clients.

---

## 🗂️ File Storage Structure

```
pidatapipeline/
├── config/
│   ├── settings.json         # PI Web API & Oracle ERP Cloud connection settings (preserved on updates)
│   ├── mappings.json         # Configured PI AF attribute to ERP field mappings (preserved on updates)
│   ├── settings.example.json # Initial configuration template for fresh installs
│   └── mappings.example.json # Initial mapping template for fresh installs
├── data/
│   ├── pull_history.json     # Telemetry readings history pulled from PI Web API
│   ├── publish_history.json  # Dispatch records & ERP response payloads
│   └── logs.json             # Structured application and error audit log
├── scripts/
│   ├── install_windows_task.bat # 1-click Windows Scheduled Task auto-start installer
│   ├── start_background.vbs     # Invisible silent background runner (no CMD window)
│   ├── stop_background.bat      # 1-click pipeline stop script
│   └── pidatapipeline.service   # Linux systemd service unit
├── app/
│   ├── config.py             # Reentrant thread-safe JSON settings & mappings manager
│   ├── pi_client.py          # AVEVA PI Web API client with simulation engine
│   ├── oracle_erp_client.py  # Oracle ERP Cloud OAuth 2.0 & REST client
│   ├── mock_erp_server.py    # Oracle ERP Cloud REST API mock simulation server
│   ├── pipeline.py           # Background pipeline scheduler & extraction engine
│   ├── storage.py            # File-backed operational logging & history manager
│   ├── updater.py            # Zero-Git client-side patch download & safe extraction engine
│   ├── version.py            # Central semantic version & release repository metadata
│   ├── main.py               # FastAPI application & REST endpoints
│   └── static/
│       ├── index.html        # Interactive Single Page Application
│       ├── css/style.css     # Clean editorial minimalist theme
│       └── js/app.js         # Real-time dashboard polling, modals & update controls
├── run.py                    # Main pipeline application startup launcher (Port 8000)
├── run_mock_erp.py           # Standalone Oracle ERP Cloud mock server launcher (Port 8080)
├── update.bat                # 1-click Windows patch & update manager (No Git required)
├── package_release.py        # Developer release packaging & checksum generator
├── requirements.txt          # Python dependencies
└── README.md                 # Complete documentation
```
