"""
Client-Side Patch & Update Engine.
Enables end users to check, download, and apply application updates without Git.

Key Safety Guarantees:
1. NEVER overwrites user configurations (config/settings.json, config/mappings.json).
2. NEVER touches operational data or logs (data/*.json).
3. Automatically creates a rollback backup before applying any patch.
4. Supports both Online (GitHub Releases) and Offline/Air-Gapped (local ZIP) patching.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

import requests

from app.version import __version__, GITHUB_REPO

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BACKUPS_DIR = os.path.join(ROOT_DIR, "backups")


def parse_semver(ver_str: str) -> Tuple[int, ...]:
    """Extract integer tuple from version string (e.g. 'v1.2.3' -> (1, 2, 3))."""
    cleaned = re.sub(r"[^0-9.]", "", ver_str)
    parts = cleaned.split(".")
    try:
        return tuple(int(p) for p in parts if p)
    except ValueError:
        return (0, 0, 0)


def check_for_updates(github_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Queries GitHub Releases API to check if a newer version is published.
    """
    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": f"PIDataPipeline-Updater/{__version__}"
    }
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        
        if resp.status_code == 404:
            return {
                "update_available": False,
                "current_version": __version__,
                "latest_version": __version__,
                "message": f"No official release published yet on repository '{GITHUB_REPO}'. You are on v{__version__}."
            }

        if resp.status_code == 403:
            return {
                "update_available": False,
                "current_version": __version__,
                "latest_version": None,
                "error": "GitHub API rate limit exceeded. Please wait a few minutes or provide a GitHub token."
            }

        if resp.status_code != 200:
            return {
                "update_available": False,
                "current_version": __version__,
                "latest_version": None,
                "error": f"GitHub API responded with HTTP {resp.status_code}"
            }

        data = resp.json()
        latest_tag = data.get("tag_name", "").lstrip("v")
        release_name = data.get("name", f"Release v{latest_tag}")
        release_body = data.get("body", "No changelog provided.")
        published_at = data.get("published_at", "")
        html_url = data.get("html_url", "")

        # Find download URL: prefer .zip assets, fallback to zipball_url
        download_url = None
        asset_size_kb = 0
        for asset in data.get("assets", []):
            name = asset.get("name", "").lower()
            if name.endswith(".zip"):
                download_url = asset.get("browser_download_url")
                asset_size_kb = round(asset.get("size", 0) / 1024, 1)
                break

        if not download_url:
            download_url = data.get("zipball_url")

        is_newer = parse_semver(latest_tag) > parse_semver(__version__)

        return {
            "update_available": is_newer,
            "current_version": __version__,
            "latest_version": latest_tag,
            "release_name": release_name,
            "release_notes": release_body,
            "published_at": published_at,
            "download_url": download_url,
            "asset_size_kb": asset_size_kb,
            "html_url": html_url,
            "message": f"New version v{latest_tag} is available!" if is_newer else f"You are running the latest version (v{__version__})."
        }

    except requests.exceptions.ConnectionError:
        return {
            "update_available": False,
            "current_version": __version__,
            "latest_version": None,
            "error": "Unable to connect to GitHub. Check your network or use an offline patch ZIP."
        }
    except Exception as e:
        return {
            "update_available": False,
            "current_version": __version__,
            "latest_version": None,
            "error": str(e)
        }


def create_backup() -> str:
    """
    Creates a timestamped rollback copy of code and scripts before applying a patch.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(BACKUPS_DIR, f"backup_v{__version__}_{timestamp}")
    os.makedirs(backup_dir, exist_ok=True)

    items_to_backup = ["app", "run.py", "run_mock_erp.py", "package_release.py", "requirements.txt", "scripts", "update.bat"]
    for item in items_to_backup:
        src = os.path.join(ROOT_DIR, item)
        dst = os.path.join(backup_dir, item)
        if os.path.isdir(src):
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        elif os.path.isfile(src):
            shutil.copy2(src, dst)

    return backup_dir


def apply_patch_from_zip(zip_path: str, backup: bool = True) -> Dict[str, Any]:
    """
    Extracts and applies a patch ZIP archive over the installation.
    Preserves all configurations and operational data.
    """
    if not os.path.exists(zip_path):
        return {"success": False, "error": f"Patch archive not found: {zip_path}"}

    backup_path = None
    if backup:
        backup_path = create_backup()

    extracted_files = 0
    requirements_changed = False

    with zipfile.ZipFile(zip_path, "r") as zf:
        namelist = zf.namelist()

        # Check if archive has a single top-level directory wrapper (common in GitHub tarballs/zipballs)
        top_dirs = {name.split("/")[0] for name in namelist if "/" in name}
        prefix = ""
        if len(top_dirs) == 1:
            first_dir = list(top_dirs)[0]
            # Check if all files are inside this directory
            if all(n.startswith(first_dir + "/") or n == first_dir for n in namelist):
                prefix = first_dir + "/"

        for member in zf.infolist():
            rel_name = member.filename
            if prefix and rel_name.startswith(prefix):
                rel_name = rel_name[len(prefix):]

            if not rel_name or rel_name.endswith("/"):
                continue

            # Security: Path traversal prevention
            norm_rel = os.path.normpath(rel_name).replace("\\", "/")
            if norm_rel.startswith("..") or os.path.isabs(norm_rel):
                continue

            # ----------------------------------------------------
            # STRICT PROTECTION RULES FOR USER DATA AND CONFIGS
            # ----------------------------------------------------
            # Rule 1: NEVER overwrite live user data / history / logs
            if norm_rel.startswith("data/") and not norm_rel.endswith(".gitkeep"):
                continue

            # Rule 2: NEVER overwrite existing settings.json or mappings.json
            dest_file = os.path.join(ROOT_DIR, norm_rel)
            if norm_rel in ("config/settings.json", "config/mappings.json") and os.path.exists(dest_file):
                continue

            # Check if requirements.txt changed
            if norm_rel == "requirements.txt":
                requirements_changed = True

            # Extract file
            os.makedirs(os.path.dirname(dest_file), exist_ok=True)
            with zf.open(member) as source, open(dest_file, "wb") as target:
                shutil.copyfileobj(source, target)
            extracted_files += 1

    # Check for new python dependencies
    pip_output = ""
    if requirements_changed:
        req_file = os.path.join(ROOT_DIR, "requirements.txt")
        if os.path.exists(req_file):
            try:
                proc = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", req_file, "--quiet"],
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                pip_output = proc.stdout or proc.stderr or "Dependencies verified."
            except Exception as e:
                pip_output = f"Warning: could not auto-install requirements: {e}"

    # Import updated version
    try:
        from app.version import __version__ as new_ver
    except Exception:
        new_ver = "Updated"

    # Log update to audit log if storage available
    try:
        from app.storage import add_log
        add_log("INFO", "SYSTEM", f"Patch successfully applied. Version updated to {new_ver} ({extracted_files} files updated).")
    except Exception:
        pass

    return {
        "success": True,
        "new_version": new_ver,
        "files_updated": extracted_files,
        "backup_path": backup_path,
        "pip_status": pip_output.strip() if pip_output else None,
        "message": f"Successfully updated to version {new_ver}! ({extracted_files} files updated)."
    }


def restart_server_process():
    """
    Restarts the server process cleanly after a 1.0s delay to allow HTTP response to send.
    Works seamlessly in both portable environments and standard Python installations.
    """
    import threading

    def _worker():
        time.sleep(1.0)
        # Check for portable Python executable vs system Python
        portable_py = os.path.join(ROOT_DIR, "python", "python.exe")
        py_bin = portable_py if os.path.exists(portable_py) else sys.executable
        run_py = os.path.join(ROOT_DIR, "run.py")

        if sys.platform == "win32":
            # Wait 1.5s via ping for port 8000 to be completely released, then launch fresh server
            cmd = f'ping 127.0.0.1 -n 2 >nul & start "AVEVA PI to Oracle ERP Data Pipeline" "{py_bin}" "{run_py}"'
            subprocess.Popen(
                cmd,
                shell=True,
                cwd=ROOT_DIR,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            cmd = f'sleep 1 && "{py_bin}" "{run_py}" &'
            subprocess.Popen(cmd, shell=True, cwd=ROOT_DIR)

        os._exit(0)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def download_and_apply_update(download_url: Optional[str] = None, github_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Downloads patch ZIP from download_url (or latest release) and applies it.
    """
    if not download_url:
        check = check_for_updates(github_token)
        if not check.get("update_available"):
            return {
                "success": False,
                "error": check.get("error") or check.get("message") or "No update available to apply."
            }
        download_url = check.get("download_url")

    if not download_url:
        return {"success": False, "error": "No valid download asset found for release."}

    headers = {
        "Accept": "application/octet-stream",
        "User-Agent": f"PIDataPipeline-Updater/{__version__}"
    }
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    tmp_file = None
    try:
        resp = requests.get(download_url, headers=headers, stream=True, timeout=60)
        if resp.status_code != 200:
            return {"success": False, "error": f"Failed to download patch (HTTP {resp.status_code})"}

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tf:
            tmp_file = tf.name
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    tf.write(chunk)

        result = apply_patch_from_zip(tmp_file, backup=True)
        return result

    except Exception as e:
        return {"success": False, "error": f"Error during download or patch application: {str(e)}"}
    finally:
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except Exception:
                pass


# -------------------------------------------------------------
# Interactive CLI Runner (Called directly or via update.bat)
# -------------------------------------------------------------
def run_cli():
    parser = argparse.ArgumentParser(description="PIDataPipeline Patch & Update Tool")
    parser.add_argument("--check", action="store_true", help="Check for available updates on GitHub.")
    parser.add_argument("--apply", action="store_true", help="Download and apply latest update.")
    parser.add_argument("--file", type=str, help="Apply patch from a local ZIP file.")
    parser.add_argument("--token", type=str, help="GitHub Personal Access Token for private repos.")
    args = parser.parse_args()

    print("=" * 65)
    print(f"  PIDataPipeline Patch & Update Manager")
    print(f"  Current Version: v{__version__}")
    print("=" * 65)

    if args.file:
        print(f"\nApplying offline patch from: {args.file}")
        res = apply_patch_from_zip(args.file, backup=True)
        if res.get("success"):
            print(f"\n[SUCCESS] {res.get('message')}")
            print(f"Backup created at: {res.get('backup_path')}")
        else:
            print(f"\n[ERROR] {res.get('error')}")
        return

    if args.check:
        print("\nChecking for updates...")
        info = check_for_updates(args.token)
        print(f"Result: {info.get('message') or info.get('error')}")
        if info.get("update_available"):
            print(f"Release: {info.get('release_name')}")
            print(f"Notes:\n{info.get('release_notes')}")
        return

    if args.apply:
        print("\nChecking and applying latest update...")
        res = download_and_apply_update(github_token=args.token)
        if res.get("success"):
            print(f"\n[SUCCESS] {res.get('message')}")
            print(f"Backup created at: {res.get('backup_path')}")
        else:
            print(f"\n[ERROR] {res.get('error')}")
        return

    # Interactive menu if no arguments passed
    print("\nPlease choose an action:")
    print("  [1] Check for updates on GitHub")
    print("  [2] Download and apply latest update from GitHub")
    print("  [3] Apply an offline patch from a local ZIP file")
    print("  [4] Exit")
    print("-" * 65)

    choice = input("Enter choice [1-4]: ").strip()
    if choice == "1":
        print("\nChecking GitHub Releases...")
        info = check_for_updates()
        if info.get("error"):
            print(f"[!] {info.get('error')}")
        else:
            print(f"[i] {info.get('message')}")
            if info.get("update_available"):
                print(f"Release: {info.get('release_name')}")
                print(f"Notes:\n{info.get('release_notes')}")
    elif choice == "2":
        print("\nDownloading and installing latest update...")
        res = download_and_apply_update()
        if res.get("success"):
            print(f"\n[SUCCESS] {res.get('message')}")
            print(f"Backup created at: {res.get('backup_path')}")
        else:
            print(f"\n[!] {res.get('error')}")
    elif choice == "3":
        zip_path = input("Enter full path to patch ZIP file: ").strip().strip('"')
        if os.path.exists(zip_path):
            res = apply_patch_from_zip(zip_path, backup=True)
            if res.get("success"):
                print(f"\n[SUCCESS] {res.get('message')}")
                print(f"Backup created at: {res.get('backup_path')}")
            else:
                print(f"\n[ERROR] {res.get('error')}")
        else:
            print(f"[!] File not found: {zip_path}")
    else:
        print("Cancelled.")


if __name__ == "__main__":
    run_cli()
