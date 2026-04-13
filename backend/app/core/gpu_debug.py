import logging
import shutil
import subprocess

import torch


logger = logging.getLogger(__name__)


def _format_mib(num_bytes: int) -> str:
    return f"{num_bytes / (1024 * 1024):.1f} MiB"


def capture_tegrastats_snapshot() -> str:
    tegrastats_path = shutil.which("tegrastats")
    if not tegrastats_path:
        return "tegrastats unavailable"

    try:
        proc = subprocess.run(
            [tegrastats_path, "--interval", "1000", "--count", "1"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        output = (proc.stdout or proc.stderr or "").strip()
        return output or f"tegrastats exit code={proc.returncode}"
    except Exception as e:
        return f"tegrastats error: {type(e).__name__}: {e}"


def capture_gpu_snapshot() -> str:
    parts: list[str] = []

    try:
        cuda_available = torch.cuda.is_available()
        # parts.append(f"torch.cuda.is_available={cuda_available}")
    except Exception as e:
        # parts.append(f"torch.cuda.is_available error={type(e).__name__}: {e}")
        cuda_available = False

    if cuda_available:
        try:
            device_count = torch.cuda.device_count()
            parts.append(f"device_count={device_count}")
            if device_count > 0:
                parts.append(f"device_name={torch.cuda.get_device_name(0)}")
        except Exception as e:
            parts.append(f"device_info error={type(e).__name__}: {e}")

        try:
            free_bytes, total_bytes = torch.cuda.mem_get_info(0)
            used_bytes = total_bytes - free_bytes
            parts.append(
                "mem="
                f"free {_format_mib(free_bytes)} / "
                f"used {_format_mib(used_bytes)} / "
                f"total {_format_mib(total_bytes)}"
            )
        except Exception as e:
            parts.append(f"mem_get_info error={type(e).__name__}: {e}")

        try:
            allocated = torch.cuda.memory_allocated(0)
            reserved = torch.cuda.memory_reserved(0)
            # parts.append(
            #     "torch_mem="
            #     f"allocated {_format_mib(allocated)} / "
            #     f"reserved {_format_mib(reserved)}"
            # )
        except Exception as e:
            parts.append(f"torch_mem error={type(e).__name__}: {e}")

    parts.append(f"tegrastats={capture_tegrastats_snapshot()}")
    return " | ".join(parts)


def log_gpu_snapshot(label: str, *, level: int = logging.INFO) -> None:
    logger.log(level, "[GPU] %s | %s", label, capture_gpu_snapshot())
