"""
Developer Tool: Build Complete Offline Installation Packages for PIDataPipeline.
Produces 100% self-contained Windows bundles for environments with NO internet and NO Python.

Outputs in dist/:
1. PIDataPipeline-Portable-vX.Y.Z-win64.zip
   - Standalone portable package with embedded Python 3.11 runtime.
   - All libraries (FastAPI, Uvicorn, Requests, Pydantic, etc.) pre-installed.
   - Zero Python or internet required on client machine!
2. PIDataPipeline-Offline-Wheels-vX.Y.Z.zip
   - Pre-downloaded Windows wheel archive for machines with existing Python.
"""
import argparse
import glob
import hashlib
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
CACHE_DIR = os.path.join(ROOT_DIR, "_offline_cache")
WHEELS_CACHE = os.path.join(CACHE_DIR, "wheels_win64_311")
PYTHON_EMBED_URL = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"
PYTHON_EMBED_ZIP = os.path.join(CACHE_DIR, "python-3.11.9-embed-amd64.zip")


def get_version() -> str:
    """Read version from app/version.py."""
    ver_file = os.path.join(ROOT_DIR, "app", "version.py")
    if os.path.exists(ver_file):
        with open(ver_file, "r", encoding="utf-8") as f:
            match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', f.read())
            if match:
                return match.group(1)
    return "1.0.0"


def compute_sha256(file_path: str) -> str:
    """Compute SHA-256 hash of a file."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()


def ensure_cached_assets():
    """Ensure Python embeddable zip and wheels are downloaded into cache."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(WHEELS_CACHE, exist_ok=True)

    # 1. Download Python 3.11 Embeddable Zip if not cached
    if not os.path.exists(PYTHON_EMBED_ZIP) or os.path.getsize(PYTHON_EMBED_ZIP) < 1000000:
        print("[*] Downloading official Python 3.11.9 Windows 64-bit embeddable runtime...")
        urllib.request.urlretrieve(PYTHON_EMBED_URL, PYTHON_EMBED_ZIP)
        print(f"[OK] Downloaded Python runtime ({round(os.path.getsize(PYTHON_EMBED_ZIP)/1024/1024, 2)} MB)")
    else:
        print("[OK] Using cached Python 3.11 embeddable package.")

    # 2. Download 64-bit Windows wheels if not cached
    cached_wheels = glob.glob(os.path.join(WHEELS_CACHE, "*.whl"))
    req_file = os.path.join(ROOT_DIR, "requirements.txt")
    if len(cached_wheels) < 10:
        print("[*] Downloading offline binary wheels for requirements.txt (win_amd64)...")
        cmd = [
            sys.executable, "-m", "pip", "download",
            "--platform", "win_amd64",
            "--python-version", "3.11",
            "--only-binary=:all:",
            "-r", req_file,
            "-d", WHEELS_CACHE
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"Failed to download wheels: {res.stderr}")
        print(f"[OK] Downloaded {len(glob.glob(os.path.join(WHEELS_CACHE, '*.whl')))} wheels.")
    else:
        print(f"[OK] Using {len(cached_wheels)} cached offline wheels.")


def build_portable_package(version: str, output_dir: str) -> str:
    """Builds the 100% self-contained portable Windows package."""
    stage_name = f"PIDataPipeline-Portable-v{version}-win64"
    stage_dir = os.path.join(ROOT_DIR, "build", stage_name)
    shutil.rmtree(stage_dir, ignore_errors=True)
    os.makedirs(stage_dir, exist_ok=True)

    print(f"\n[*] Assembling portable package: {stage_name}...")

    # 1. Setup python runtime folder
    py_dir = os.path.join(stage_dir, "python")
    os.makedirs(py_dir, exist_ok=True)
    with zipfile.ZipFile(PYTHON_EMBED_ZIP, "r") as zf:
        zf.extractall(py_dir)

    # Configure python311._pth to support root app imports and site-packages
    pth_file = os.path.join(py_dir, "python311._pth")
    with open(pth_file, "w", encoding="utf-8") as f:
        f.write("python311.zip\n.\n..\nLib/site-packages\n")

    # Extract all pre-downloaded wheels into python/Lib/site-packages
    sp_dir = os.path.join(py_dir, "Lib", "site-packages")
    os.makedirs(sp_dir, exist_ok=True)
    for whl in glob.glob(os.path.join(WHEELS_CACHE, "*.whl")):
        with zipfile.ZipFile(whl, "r") as zf:
            zf.extractall(sp_dir)

    # 2. Copy Application Folders
    shutil.copytree(os.path.join(ROOT_DIR, "app"), os.path.join(stage_dir, "app"), ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(os.path.join(ROOT_DIR, "scripts"), os.path.join(stage_dir, "scripts"))

    # Config folder with clean templates
    os.makedirs(os.path.join(stage_dir, "config"), exist_ok=True)
    for cfg in ("settings", "mappings"):
        ex_file = os.path.join(ROOT_DIR, "config", f"{cfg}.example.json")
        real_file = os.path.join(ROOT_DIR, "config", f"{cfg}.json")
        src = ex_file if os.path.exists(ex_file) else real_file
        shutil.copy2(src, os.path.join(stage_dir, "config", f"{cfg}.json"))
        shutil.copy2(src, os.path.join(stage_dir, "config", f"{cfg}.example.json"))

    # Data directory
    os.makedirs(os.path.join(stage_dir, "data"), exist_ok=True)
    with open(os.path.join(stage_dir, "data", ".gitkeep"), "w") as f:
        f.write("")

    # Root application files
    shutil.copy2(os.path.join(ROOT_DIR, "run.py"), os.path.join(stage_dir, "run.py"))
    shutil.copy2(os.path.join(ROOT_DIR, "run_mock_erp.py"), os.path.join(stage_dir, "run_mock_erp.py"))
    shutil.copy2(os.path.join(ROOT_DIR, "requirements.txt"), os.path.join(stage_dir, "requirements.txt"))
    shutil.copy2(os.path.join(ROOT_DIR, "README.md"), os.path.join(stage_dir, "README.md"))

    # 3. Create 1-Click Portable Batch Launchers
    # start.bat
    start_bat_content = """@echo off
setlocal
title AVEVA PI to Oracle ERP Data Pipeline
echo ================================================================
echo   AVEVA PI to Oracle ERP Cloud Data Pipeline (Portable)
echo ================================================================
echo.
echo Launching web dashboard at http://127.0.0.1:8000 ...
start "" "http://127.0.0.1:8000"
cd /d "%~dp0"
"%~dp0python\\python.exe" "%~dp0run.py"
pause
"""
    with open(os.path.join(stage_dir, "start.bat"), "w", encoding="utf-8") as f:
        f.write(start_bat_content)

    # start_silent.vbs
    start_vbs_content = '''Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
appDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonExe = appDir & "\\python\\pythonw.exe"
runPy = appDir & "\\run.py"
WshShell.CurrentDirectory = appDir
WshShell.Run """" & pythonExe & """ """ & runPy & """", 0, False
'''
    with open(os.path.join(stage_dir, "start_silent.vbs"), "w", encoding="utf-8") as f:
        f.write(start_vbs_content)

    # stop.bat
    stop_bat_content = """@echo off
title Stop PIDataPipeline
echo Stopping PIDataPipeline background process...
taskkill /f /im python.exe /fi "WINDOWTITLE eq AVEVA PI*" >nul 2>&1
wmic process where "commandline like '%%run.py%%'" call terminate >nul 2>&1
echo [OK] Pipeline process stopped.
timeout /t 2 >nul
"""
    with open(os.path.join(stage_dir, "stop.bat"), "w", encoding="utf-8") as f:
        f.write(stop_bat_content)

    # install_service.bat
    install_service_content = '''@echo off
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ================================================================
    echo Error: Please right-click this file and select "Run as Administrator".
    echo ================================================================
    pause
    exit /b 1
)
set SCRIPT_DIR=%~dp0
set VBS_PATH=%SCRIPT_DIR%start_silent.vbs
echo Registering PIDataPipeline portable Windows startup task...
schtasks /create /tn "PIDataPipeline" /tr "wscript.exe \\"%VBS_PATH%\\"" /sc onstart /ru "SYSTEM" /rl HIGHEST /f
if %errorLevel% neq 0 (
    schtasks /create /tn "PIDataPipeline" /tr "wscript.exe \\"%VBS_PATH%\\"" /sc onlogon /rl HIGHEST /f
)
echo [SUCCESS] Windows startup task created! It will run 24/7 on boot.
pause
'''
    with open(os.path.join(stage_dir, "install_service.bat"), "w", encoding="utf-8") as f:
        f.write(install_service_content)

    # update.bat
    update_bat_content = """@echo off
title PIDataPipeline - Offline Patch Manager
cd /d "%~dp0"
"%~dp0python\\python.exe" -m app.updater
pause
"""
    with open(os.path.join(stage_dir, "update.bat"), "w", encoding="utf-8") as f:
        f.write(update_bat_content)

    # README_OFFLINE.txt
    readme_content = f"""========================================================================
  AVEVA PI to Oracle ERP Cloud Data Pipeline
  Standalone Offline Portable Package v{version} (Windows 64-bit)
========================================================================

NO INTERNET CONNECTION OR PYTHON INSTALLATION REQUIRED!
This package includes a standalone, portable Python runtime and all
required dependencies pre-installed.

QUICK START INSTRUCTIONS:
1. Extract this entire folder anywhere on your computer (e.g. C:\\PIDataPipeline).
2. Double-click "start.bat".
3. Your web browser will open automatically at:
   http://127.0.0.1:8000

BACKGROUND AUTO-START (OPTIONAL):
- To run invisibly in the background without a CMD window:
  Double-click "start_silent.vbs".
- To start automatically whenever Windows boots up:
  Right-click "install_service.bat" and select "Run as Administrator".
- To stop the background pipeline:
  Double-click "stop.bat".

OFFLINE PATCHING:
- Whenever a patch is provided (e.g. patch.zip):
  Double-click "update.bat" and select Option [3] to apply the patch.
  Your settings (config/) and telemetry history (data/) will remain safe!
========================================================================
"""
    with open(os.path.join(stage_dir, "README_OFFLINE.txt"), "w", encoding="utf-8") as f:
        f.write(readme_content)

    # 4. Compress to ZIP
    os.makedirs(output_dir, exist_ok=True)
    zip_path = os.path.join(output_dir, f"{stage_name}.zip")
    print(f"[*] Compressing {stage_name}.zip (this may take a few seconds)...")
    
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(stage_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, stage_dir)
                zf.write(full_path, rel_path)

    sha = compute_sha256(zip_path)
    with open(f"{zip_path}.sha256", "w") as f:
        f.write(f"{sha}  {os.path.basename(zip_path)}\n")

    size_mb = round(os.path.getsize(zip_path) / 1024 / 1024, 2)
    print(f"[OK] Created Portable Package: {zip_path} ({size_mb} MB)")
    print(f"    SHA-256: {sha}")
    return zip_path


def build_wheels_package(version: str, output_dir: str) -> str:
    """Builds the standalone offline wheels bundle for machines with existing Python."""
    stage_name = f"PIDataPipeline-Offline-Wheels-v{version}"
    stage_dir = os.path.join(ROOT_DIR, "build", stage_name)
    shutil.rmtree(stage_dir, ignore_errors=True)
    os.makedirs(stage_dir, exist_ok=True)

    print(f"\n[*] Assembling offline wheels package: {stage_name}...")
    wheels_dest = os.path.join(stage_dir, "wheels")
    os.makedirs(wheels_dest, exist_ok=True)
    for whl in glob.glob(os.path.join(WHEELS_CACHE, "*.whl")):
        shutil.copy2(whl, wheels_dest)

    shutil.copy2(os.path.join(ROOT_DIR, "requirements.txt"), os.path.join(stage_dir, "requirements.txt"))

    install_bat = """@echo off
title Install Offline Dependencies
echo ================================================================
echo   Installing PIDataPipeline Dependencies from Local Wheels
echo   (No Internet Connection Required)
echo ================================================================
echo.
pip install --no-index --find-links=wheels -r requirements.txt
if %ERRORLEVEL% equ 0 (
    echo.
    echo [SUCCESS] All dependencies installed successfully!
) else (
    echo.
    echo [ERROR] Installation failed. Check that Python and Pip are in PATH.
)
pause
"""
    with open(os.path.join(stage_dir, "install_offline_dependencies.bat"), "w", encoding="utf-8") as f:
        f.write(install_bat)

    zip_path = os.path.join(output_dir, f"{stage_name}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(stage_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, stage_dir)
                zf.write(full_path, rel_path)

    sha = compute_sha256(zip_path)
    with open(f"{zip_path}.sha256", "w") as f:
        f.write(f"{sha}  {os.path.basename(zip_path)}\n")

    size_mb = round(os.path.getsize(zip_path) / 1024 / 1024, 2)
    print(f"[OK] Created Wheels Package: {zip_path} ({size_mb} MB)")
    print(f"    SHA-256: {sha}")
    return zip_path


def main():
    parser = argparse.ArgumentParser(description="Build offline installation packages for PIDataPipeline.")
    parser.add_argument("--version", type=str, help="Version string (default: from app/version.py).")
    parser.add_argument("--output-dir", type=str, default="dist", help="Output directory (default: dist).")
    parser.add_argument("--clean-cache", action="store_true", help="Clear download cache and re-download assets.")
    args = parser.parse_args()

    ver = args.version.lstrip("v") if args.version else get_version()

    if args.clean_cache:
        shutil.rmtree(CACHE_DIR, ignore_errors=True)

    print("=" * 65)
    print(f"  PIDataPipeline Offline Package Builder v{ver}")
    print("=" * 65)

    ensure_cached_assets()
    pkg_portable = build_portable_package(ver, args.output_dir)
    pkg_wheels = build_wheels_package(ver, args.output_dir)

    # Clean build staging
    shutil.rmtree(os.path.join(ROOT_DIR, "build"), ignore_errors=True)

    print("\n" + "=" * 65)
    print("  [ALL OFFLINE PACKAGES GENERATED SUCCESSFULLY]")
    print("=" * 65)
    print("Deliver to clients with NO internet:")
    print(f"  1. Standalone Portable Package (No Python needed on client):")
    print(f"     -> {pkg_portable}")
    print(f"  2. Offline Wheels Package (For clients with existing Python):")
    print(f"     -> {pkg_wheels}")
    print("=" * 65)


if __name__ == "__main__":
    main()
