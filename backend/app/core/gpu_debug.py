# Jetson Orin Nano의 GPU 메모리 사용량과 하드웨어 상태를 로그로 기록하는 디버그 유틸리티.
# PyTorch CUDA API와 tegrastats 명령을 조합해 GPU 여유 메모리, 사용량, 전체 용량을 수집한다.
# 모델 로드·언로드 등 메모리 변화가 생기는 시점에 호출해 GPU 상태를 추적한다.

import logging
import shutil
import subprocess

import torch


logger = logging.getLogger(__name__)


# 바이트 단위 숫자를 읽기 쉬운 MiB(메비바이트) 문자열로 변환하는 내부 헬퍼 함수.
# 매개변수: num_bytes - 변환할 바이트 수(int).
# 반환값: "123.4 MiB" 형식의 문자열.
def _format_mib(num_bytes: int) -> str:
    return f"{num_bytes / (1024 * 1024):.1f} MiB"


# tegrastats 명령을 1회 실행해 Jetson 보드의 전체 하드웨어 상태 문자열을 반환하는 함수.
# tegrastats가 시스템에 설치되어 있지 않으면 "tegrastats unavailable"을 반환한다.
# 반환값: tegrastats 출력 문자열 또는 오류 설명 문자열.
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


# 현재 GPU 메모리 여유/사용/전체 용량과 tegrastats 정보를 수집해 한 줄 문자열로 반환하는 함수.
# CUDA를 사용할 수 없는 환경에서도 tegrastats 정보만 포함해 안전하게 동작한다.
# 반환값: "device_count=1 | mem=free 1234.5 MiB / used 234.5 MiB / total ... | tegrastats=..." 형식의 문자열.
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


# 지정한 레이블과 함께 현재 GPU 상태를 로그에 기록하는 함수.
# 매개변수: label - 로그에 표시할 상황 설명 문자열(예: "after_cuda_empty_cache"). level - 로그 레벨(기본 INFO).
def log_gpu_snapshot(label: str, *, level: int = logging.INFO) -> None:
    logger.log(level, "[GPU] %s | %s", label, capture_gpu_snapshot())
