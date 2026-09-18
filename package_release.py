"""
Developer Tool: Package PIDataPipeline for Distribution and Patch Releases.
Builds a clean, production-ready ZIP archive ready for GitHub Releases or client deployment.

Usage:
    python package_release.py
    python package_release.py --version 1.0.1
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime

ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
VERSION_FILE = os.path.join(ROOT_DIR, "app", "version.py")


def get_current_version() -> str:
    """Read __version__ from app/version.py."""
    if not os.path.exists(VERSION_FILE):
        return "1.0.0"
    with open(VERSION_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    return match.group(1) if match else "1.0.0"


def set_version(new_version: str):
    """Update __version__ in app/version.py and app/main.py."""
    new_version = new_version.lstrip("v")
    if os.path.exists(VERSION_FILE):
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        updated = re.sub(
            r'__version__\s*=\s*["\'][^"\']+["\']',
            f'__version__ = "{new_version}"',
            content
        )
        with open(VERSION_FILE, "w", encoding="utf-8") as f:
            f.write(updated)
        print(f"[*] Updated app/version.py to {new_version}")

    main_py = os.path.join(ROOT_DIR, "app", "main.py")
    if os.path.exists(main_py):
        with open(main_py, "r", encoding="utf-8") as f:
            content = f.read()
        updated = re.sub(
            r'version\s*=\s*["\'][^"\']+["\']',
            f'version="{new_version}"',
            content,
            count=1
        )
        with open(main_py, "w", encoding="utf-8") as f:
            f.write(updated)


def compute_sha256(file_path: str) -> str:
    """Compute SHA-256 hash of a file."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()


def should_exclude(rel_path: str) -> bool:
    """Check if relative path should be excluded from release zip."""
    norm = rel_path.replace("\\", "/")
    
    # Exclude version control and development files
    if norm.startswith(".git/") or norm == ".git":
        return True
    if norm.startswith(".vscode/") or norm.startswith(".idea/"):
        return True
    if "__pycache__" in norm or norm.endswith((".pyc", ".pyo", ".pyd")):
        return True
    
    # Exclude build, cache, and backup directories
    if norm.startswith("dist/") or norm.startswith("backups/") or norm.startswith("build/") or norm.startswith("_offline_cache/"):
        return True
    
    # Exclude test files from production release package
    if norm.startswith("test_") or "/test_" in norm:
        return True

    # EXCLUDE user-specific data and live configs (MUST preserve user privacy and prevent overwrite!)
    if norm.startswith("data/") and not norm.endswith(".gitkeep"):
        return True
    if norm in ("config/settings.json", "config/mappings.json"):
        return True

    return False


def build_package(version: str, output_dir: str = "dist") -> str:
    """Build distribution zip package."""
    os.makedirs(output_dir, exist_ok=True)
    zip_name = f"pidatapipeline-v{version}.zip"
    zip_path = os.path.join(output_dir, zip_name)

    # Ensure template config examples exist
    for cfg in ("settings", "mappings"):
        real_cfg = os.path.join(ROOT_DIR, "config", f"{cfg}.json")
        ex_cfg = os.path.join(ROOT_DIR, "config", f"{cfg}.example.json")
        if not os.path.exists(ex_cfg) and os.path.exists(real_cfg):
            shutil.copy2(real_cfg, ex_cfg)

    # Ensure empty data directory marker
    os.makedirs(os.path.join(ROOT_DIR, "data"), exist_ok=True)
    gitkeep_path = os.path.join(ROOT_DIR, "data", ".gitkeep")
    if not os.path.exists(gitkeep_path):
        with open(gitkeep_path, "w") as f:
            f.write("")

    print(f"\n========================================================")
    print(f"  Packaging PIDataPipeline v{version}")
    print(f"  Output: {zip_path}")
    print(f"========================================================")

    files_added = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Traverse repository
        for root, dirs, files in os.walk(ROOT_DIR):
            # Prune excluded directories in-place
            dirs[:] = [d for d in dirs if not should_exclude(os.path.relpath(os.path.join(root, d), ROOT_DIR))]

            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, ROOT_DIR)

                if should_exclude(rel_path):
                    continue

                zf.write(full_path, rel_path)
                files_added += 1

    size_kb = round(os.path.getsize(zip_path) / 1024, 1)
    sha256 = compute_sha256(zip_path)

    # Write sha256 checksum file
    sha_file = f"{zip_path}.sha256"
    with open(sha_file, "w", encoding="utf-8") as f:
        f.write(f"{sha256}  {zip_name}\n")

    # Also produce PIDataPipeline-App-v{version}.zip so alphabetical sorting in GitHub releases
    # places the application patch ahead of Offline-Wheels and Portable packages for legacy updaters
    app_alias_name = f"PIDataPipeline-App-v{version}.zip"
    app_alias_path = os.path.join(output_dir, app_alias_name)
    shutil.copy2(zip_path, app_alias_path)
    with open(f"{app_alias_path}.sha256", "w", encoding="utf-8") as f:
        f.write(f"{sha256}  {app_alias_name}\n")

    print(f"\n[SUCCESS] Package built successfully!")
    print(f"  Archive:     {zip_path} ({size_kb} KB, {files_added} files)")
    print(f"  Legacy Alias:{app_alias_path}")
    print(f"  SHA-256:     {sha256}")
    print(f"  Checksum:    {sha_file}")
    print(f"========================================================\n")
    return zip_path


def push_git_release(version: str) -> bool:
    """Commit version files, tag git commit, and push to GitHub to trigger Actions."""
    tag = f"v{version}"
    print(f"\n[*] Preparing to push git tag '{tag}' to GitHub to trigger release workflow...")
    try:
        # Check if git is available
        subprocess.run(["git", "--version"], cwd=ROOT_DIR, check=True, capture_output=True)

        # Stage updated version files
        subprocess.run(["git", "add", "app/version.py", "app/main.py"], cwd=ROOT_DIR, check=True)

        # Commit if modified
        status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT_DIR, capture_output=True, text=True)
        if "app/version.py" in status.stdout or "app/main.py" in status.stdout:
            subprocess.run(["git", "commit", "-m", f"chore(release): bump version to {version}"], cwd=ROOT_DIR, check=True)
            print(f"[OK] Committed version bump to {version}")

        # Create tag
        print(f"[*] Creating local git tag '{tag}'...")
        tag_proc = subprocess.run(["git", "tag", "-a", tag, "-m", f"Release {tag}"], cwd=ROOT_DIR, capture_output=True, text=True)
        if tag_proc.returncode != 0:
            if "already exists" in tag_proc.stderr:
                print(f"[!] Git tag '{tag}' already exists locally. Updating tag...")
                subprocess.run(["git", "tag", "-f", "-a", tag, "-m", f"Release {tag}"], cwd=ROOT_DIR, check=True)
            else:
                print(f"[ERROR] Could not create tag: {tag_proc.stderr}")
                return False

        # Push to remote
        print(f"[*] Pushing 'main' branch and tag '{tag}' to GitHub...")
        subprocess.run(["git", "push", "origin", "main"], cwd=ROOT_DIR, check=True)
        subprocess.run(["git", "push", "origin", tag, "--force"], cwd=ROOT_DIR, check=True)

        print("\n" + "=" * 65)
        print(f"  [SUCCESS] Git tag '{tag}' pushed to GitHub!")
        print(f"  GitHub Actions workflow 'Package & Publish Release' is now triggered!")
        print(f"  Track live build & release at:")
        print(f"    https://github.com/dynaconsurv/pidatapipeline/actions")
        print(f"    https://github.com/dynaconsurv/pidatapipeline/releases")
        print("=" * 65 + "\n")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Git push failed: {e}")
        return False
    except Exception as ex:
        print(f"\n[ERROR] Failed to push git tag: {ex}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Package PIDataPipeline into a release zip.")
    parser.add_argument("--version", type=str, help="Version tag to package (e.g. 1.0.5).")
    parser.add_argument("--output-dir", type=str, default="dist", help="Target output folder (default: dist).")
    parser.add_argument("--push", action="store_true", help="Automatically commit, tag, and push to GitHub to trigger GitHub Actions release.")
    parser.add_argument("--no-push", action="store_true", help="Do not push git tag or prompt.")
    args = parser.parse_args()

    target_ver = args.version.lstrip("v") if args.version else get_current_version()
    if args.version:
        set_version(target_ver)

    build_package(target_ver, args.output_dir)

    if args.push:
        push_git_release(target_ver)
    elif not args.no_push:
        try:
            prompt = input(f"Do you want to push git tag 'v{target_ver}' to GitHub to trigger GitHub Actions release now? [Y/n]: ").strip().lower()
            if prompt in ("", "y", "yes"):
                push_git_release(target_ver)
            else:
                print("Skipped GitHub push. Git tag was not pushed.")
        except (EOFError, KeyboardInterrupt):
            pass
