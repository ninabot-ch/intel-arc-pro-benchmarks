#!/bin/bash
# Samples host memory once per second while the vLLM container runs, and kills the container if the
# host is about to run out. This is the sampling loop that produced the mem.log figures quoted in
# tensor-parallel-27b.md (MemAvailable, SwapFree, Shmem, Cached, container cgroup memory.current, in MiB).
# Public copy: only the output directory and the container start were changed (start the container
# yourself with docker compose, then run this).
# usage: sample-host-mem.sh [container-name] [output-dir]
C=${1:-vllm-27b}
D=${2:-./run-$(date +%Y%m%d-%H%M%S)}; mkdir -p "$D"
( docker logs -f "$C" >"$D/vllm.log" 2>&1 & )
while docker inspect "$C" >/dev/null 2>&1; do
  read a s sh c < <(awk '/MemAvailable/{a=$2}/SwapFree/{s=$2}/^Shmem:/{sh=$2}/^Cached:/{c=$2}END{print int(a/1024),int(s/1024),int(sh/1024),int(c/1024)}' /proc/meminfo)
  m=$(cat /sys/fs/cgroup/system.slice/docker-$(docker inspect "$C" --format '{{.Id}}').scope/memory.current 2>/dev/null); m=$((${m:-0}/1048576))
  st=$(docker inspect "$C" --format '{{.State.Status}}/{{.State.OOMKilled}}/{{.State.ExitCode}}')
  echo "$(date +%T) avail=$a swapfree=$s shmem=$sh cached=$c cg=$m load=$(cut -d' ' -f1 /proc/loadavg) $st" >>"$D/mem.log"
  case "$st" in exited*) echo "END container exited $st" >>"$D/mem.log"; break;; esac
  if [ "$a" -lt 4000 ]; then echo "$(date +%T) GUARD avail=$a swapfree=$s -> stop" >>"$D/mem.log"; docker kill "$C" >/dev/null; break; fi
  sleep 1
done
