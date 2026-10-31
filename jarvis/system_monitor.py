from __future__ import annotations

import platform
from dataclasses import dataclass

try:
    import psutil
except ImportError:  # Optional dependency; model and assistant still run without it.
    psutil = None


@dataclass(frozen=True)
class SystemSnapshot:
    operating_system: str
    processor: str
    cpu_percent: float | None
    memory_percent: float | None
    memory_used_gb: float | None
    memory_total_gb: float | None
    disk_percent: float | None
    disk_used_gb: float | None
    disk_total_gb: float | None
    battery_percent: float | None
    battery_plugged: bool | None


def collect_system_snapshot() -> SystemSnapshot:
    if psutil is None:
        return SystemSnapshot(
            operating_system=f"{platform.system()} {platform.release()} ({platform.version()})",
            processor=platform.processor() or "Not reported by Windows",
            cpu_percent=None, memory_percent=None, memory_used_gb=None,
            memory_total_gb=None, disk_percent=None, disk_used_gb=None,
            disk_total_gb=None, battery_percent=None, battery_plugged=None,
        )
    try:
        memory = psutil.virtual_memory()
        memory_percent = float(memory.percent)
        memory_used = memory.used / (1024 ** 3)
        memory_total = memory.total / (1024 ** 3)
    except (OSError, AttributeError):
        memory_percent = memory_used = memory_total = None

    try:
        disk = psutil.disk_usage(psutil.disk_partitions(all=False)[0].mountpoint)
        disk_percent = float(disk.percent)
        disk_used = disk.used / (1024 ** 3)
        disk_total = disk.total / (1024 ** 3)
    except (OSError, IndexError, AttributeError):
        disk_percent = disk_used = disk_total = None

    try:
        battery = psutil.sensors_battery()
        battery_percent = float(battery.percent) if battery is not None else None
        battery_plugged = bool(battery.power_plugged) if battery is not None else None
    except (OSError, AttributeError):
        battery_percent = battery_plugged = None

    try:
        cpu_percent = float(psutil.cpu_percent(interval=None))
    except (OSError, AttributeError):
        cpu_percent = None

    return SystemSnapshot(
        operating_system=f"{platform.system()} {platform.release()} ({platform.version()})",
        processor=platform.processor() or "Not reported by Windows",
        cpu_percent=cpu_percent,
        memory_percent=memory_percent,
        memory_used_gb=memory_used,
        memory_total_gb=memory_total,
        disk_percent=disk_percent,
        disk_used_gb=disk_used,
        disk_total_gb=disk_total,
        battery_percent=battery_percent,
        battery_plugged=battery_plugged,
    )
