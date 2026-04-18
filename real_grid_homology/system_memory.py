from __future__ import annotations

import os
import re
import resource
import subprocess
import sys

try:
    import psutil
except ImportError:  # pragma: no cover - optional dependency
    psutil = None


def current_process_rss_bytes() -> int | None:
    if psutil is not None:
        return int(psutil.Process().memory_info().rss)

    if sys.platform == "darwin":
        peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        return peak

    try:
        output = subprocess.check_output(["ps", "-o", "rss=", "-p", str(os.getpid())], text=True)
    except Exception:
        output = ""

    value = output.strip()
    if value.isdigit():
        return int(value) * 1024
    return None


def available_memory_bytes() -> int | None:
    override = os.environ.get("GRID2_HAT_AVAILABLE_MEMORY_BYTES")
    if override is not None:
        return int(override)

    if psutil is not None:
        return int(psutil.virtual_memory().available)

    if sys.platform == "darwin":
        try:
            output = subprocess.check_output(["vm_stat"], text=True)
        except Exception:
            output = ""
        match = re.search(r"page size of (\d+) bytes", output)
        if match is not None:
            page_size = int(match.group(1))
            counts: dict[str, int] = {}
            for line in output.splitlines():
                if ":" not in line:
                    continue
                key, value = line.split(":", 1)
                value = value.strip().rstrip(".")
                if not value.isdigit():
                    continue
                counts[key.strip()] = int(value)
            available_pages = (
                counts.get("Pages free", 0)
                + counts.get("Pages inactive", 0)
                + counts.get("Pages speculative", 0)
                + counts.get("Pages purgeable", 0)
            )
            if available_pages > 0:
                return available_pages * page_size

    if "SC_AVPHYS_PAGES" in os.sysconf_names and "SC_PAGE_SIZE" in os.sysconf_names:
        return int(os.sysconf("SC_AVPHYS_PAGES")) * int(os.sysconf("SC_PAGE_SIZE"))

    if "SC_PHYS_PAGES" in os.sysconf_names and "SC_PAGE_SIZE" in os.sysconf_names:
        return int(os.sysconf("SC_PHYS_PAGES")) * int(os.sysconf("SC_PAGE_SIZE"))

    return None


def macos_memory_pressure_level() -> int | None:
    if sys.platform != "darwin":
        return None
    try:
        output = subprocess.check_output(
            ["sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
            text=True,
        )
        return int(output.strip())
    except Exception:
        return None


def macos_effective_available_bytes() -> int | None:
    if sys.platform != "darwin":
        return None
    if psutil is not None:
        vm = psutil.virtual_memory()
        return int(vm.total - vm.wired)
    return None
