"""Stage the Pages site and a checksum-verified, self-hosted Python runtime.

Only the build downloads from upstream. Visitors load every simulation asset
from the Pages origin. This script needs Python's standard library only.
The packaging helper lives beside the site source and is excluded from output.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
VERSION = "314.0.7"
CORE_SHA256 = "2abdcc2e35208af406e07724cffa85bc582ced97e9028383ecf5462541393f95"
CORE_URL = f"https://github.com/pyodide/pyodide/releases/download/{VERSION}/pyodide-core-{VERSION}.tar.bz2"
PACKAGE_URL = f"https://cdn.jsdelivr.net/pyodide/v{VERSION}/full/"
CORE_FILES = {"pyodide.mjs", "pyodide.asm.mjs", "pyodide.asm.wasm",
              "python_stdlib.zip", "pyodide-lock.json"}


def download(url, target, sha256):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == sha256:
        return
    print(f"Downloading {target.name}", flush=True)
    temporary = target.with_suffix(target.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as response, temporary.open("wb") as output:
        shutil.copyfileobj(response, output)
    if hashlib.sha256(temporary.read_bytes()).hexdigest() != sha256:
        temporary.unlink()
        raise ValueError(f"Checksum mismatch for {target.name}")
    temporary.replace(target)


def stage_runtime(destination, cache):
    archive = cache / f"pyodide-core-{VERSION}.tar.bz2"
    download(CORE_URL, archive, CORE_SHA256)
    destination.mkdir(parents=True, exist_ok=True)
    copied = set()
    with tarfile.open(archive, "r:bz2") as source:
        for member in source.getmembers():
            name = Path(member.name).name
            if member.isfile() and (name in CORE_FILES or name.lower().startswith(("license", "copying"))):
                with source.extractfile(member) as content, (destination / name).open("wb") as output:
                    shutil.copyfileobj(content, output)
                copied.add(name)
    if not CORE_FILES <= copied:
        raise ValueError(f"Runtime archive missing {CORE_FILES - copied}")
    lock_path = destination / "pyodide-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    required = set()

    def include(name):
        if name in required:
            return
        required.add(name)
        for dependency in lock["packages"][name]["depends"]:
            include(dependency)

    include("numpy")
    for name in sorted(required):
        package = lock["packages"][name]
        filename = package["file_name"]
        if Path(filename).name != filename or ":" in filename:
            raise ValueError("Expected a relative package filename in the pinned lockfile.")
        wheel = cache / filename
        download(PACKAGE_URL + filename, wheel, package["sha256"])
        shutil.copy2(wheel, destination / filename)
    # Advertise only packages actually hosted here; never resolve unshipped wheels.
    lock["packages"] = {name: lock["packages"][name] for name in sorted(required)}
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    (destination / "NOTICE.txt").write_text(
        f"Pyodide {VERSION}: https://github.com/pyodide/pyodide/tree/{VERSION}\n"
        "NumPy and its bundled library licenses are included in its wheel.\n"
        "See LICENSE.pyodide and LICENSE.python for the runtime and Python licenses.\n", encoding="utf-8")
    # Pyodide's core archive does not necessarily include its project license.
    python_version = lock["info"]["python"]
    licenses = {
        "LICENSE.pyodide": (VERSION, f"https://raw.githubusercontent.com/pyodide/pyodide/{VERSION}/LICENSE"),
        "LICENSE.python": (python_version, f"https://raw.githubusercontent.com/python/cpython/v{python_version}/LICENSE"),
    }
    for name, (version, url) in licenses.items():
        license_cache = cache / f"{name}-{version}"
        if not license_cache.exists():
            with urllib.request.urlopen(url, timeout=60) as response:
                license_cache.write_bytes(response.read())
        shutil.copy2(license_cache, destination / name)


def build(output, cache):
    output, cache = output.resolve(), cache.resolve()
    # All recursive operations stay in these dedicated workspace build folders.
    if output != ROOT / "_site" or cache != ROOT / ".site-cache":
        raise ValueError("Build output and cache must be the workspace's _site and .site-cache directories.")
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(ROOT / "docs", output,
                    ignore=shutil.ignore_patterns(Path(__file__).name, "__pycache__"))
    shutil.copytree(ROOT / "luminous-life" / "dist", output / "luminous-life")
    (output / "luminous-life" / "runtime-config.js").write_text(
        "export const runtimeConfig = { transport: 'worker', "
        "clientURL: '../life/client.js', demosURL: '../index.html' };\n", encoding="utf-8")
    python = output / "life" / "python"
    python.mkdir(parents=True, exist_ok=True)
    for name in ("Game_of_Life.py", "life_engines.py", "life_protocol.py"):
        shutil.copy2(ROOT / name, python / name)
    stage_runtime(output / "life" / "runtime" / VERSION, cache)
    (output / ".nojekyll").touch()
    files = [path for path in output.rglob("*") if path.is_file()]
    print(f"Built {output}: {sum(path.stat().st_size for path in files) / 1024 ** 2:.1f} MiB", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    build(ROOT / "_site", ROOT / ".site-cache")
