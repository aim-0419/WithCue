#!/usr/bin/env bash
set -euo pipefail

echo "== date =="
date
echo

echo "== tegrastats (1 sample) =="
if command -v tegrastats >/dev/null 2>&1; then
  tegrastats --interval 1000 --count 1 || true
else
  echo "tegrastats not found"
fi
echo

echo "== jtop status =="
if command -v jtop >/dev/null 2>&1; then
  jtop --health || true
else
  echo "jtop not found"
fi
echo

echo "== GPU related processes =="
ps -eo pid,ppid,cmd,%mem,%cpu --sort=-%mem | grep -E "python|uvicorn|pt_main_thread|cuda|triton|torch" | grep -v grep || true
echo

echo "== Python torch CUDA snapshot =="
python - <<'PY'
import torch
print("cuda_available=", torch.cuda.is_available())
if torch.cuda.is_available():
    print("device_count=", torch.cuda.device_count())
    print("device_name=", torch.cuda.get_device_name(0))
    try:
        free_bytes, total_bytes = torch.cuda.mem_get_info(0)
        used_bytes = total_bytes - free_bytes
        print("mem_free_mib=", round(free_bytes / 1024 / 1024, 1))
        print("mem_used_mib=", round(used_bytes / 1024 / 1024, 1))
        print("mem_total_mib=", round(total_bytes / 1024 / 1024, 1))
    except Exception as e:
        print("mem_get_info_error=", type(e).__name__, e)
    try:
        print("memory_allocated_mib=", round(torch.cuda.memory_allocated(0) / 1024 / 1024, 1))
        print("memory_reserved_mib=", round(torch.cuda.memory_reserved(0) / 1024 / 1024, 1))
    except Exception as e:
        print("torch_mem_error=", type(e).__name__, e)
PY
