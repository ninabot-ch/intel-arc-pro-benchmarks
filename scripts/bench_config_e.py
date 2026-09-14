#!/usr/bin/env python3
"""Benchmark for multiple resident LLMs served over OpenAI-compatible endpoints.

Reports per-model decode rate, prefill, aggregate throughput under concurrency, and
host RAM pressure. Token counts come from each response's `usage` object rather than
being counted client-side.

Adjust EP below for your own ports and model names. Writes a Markdown report to stdout.
"""
import json, time, urllib.request, subprocess, concurrent.futures as cf

EP = [
    ("gpt-oss-20b",     "card 0",   "http://localhost:8003/v1/chat/completions", "gpt-oss-20b"),
    ("qwen3-coder-30b", "card 1",   "http://localhost:8006/v1/chat/completions", "qwen3-coder-30b"),
    ("qwen3-next-80b",  "cards 2+3","http://localhost:8007/v1/chat/completions", "qwen3-next-80b"),
]

def sysinfo():
    f = open("/proc/meminfo").read()
    g = lambda k: int([l for l in f.split("\n") if l.startswith(k)][0].split()[1]) // 1024
    swap = g("SwapTotal") - g("SwapFree")
    load = open("/proc/loadavg").read().split()[0]
    # Wall-power reading came from a site-specific UPS over the LAN; removed here.
    ups = "n/a"
    return {"avail_mb": g("MemAvailable"), "swap_mb": swap, "load": load, "ups_load": ups or "?"}

def vram():
    out = {}
    try:
        txt = open("/var/lib/node-exporter/textfile_collector/b60.prom").read()
        for line in txt.split("\n"):
            if line.startswith("b60_vram_resident_bytes"):
                pci = line.split('pci="')[1].split('"')[0]
                out[pci[-7:]] = round(float(line.split()[-1]) / 1e9, 1)
    except Exception:
        pass
    return out

def ask(url, model, prompt, max_tokens, timeout=900):
    body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}],
                       "max_tokens": max_tokens, "temperature": 0.7}).encode()
    t0 = time.time()
    r = urllib.request.urlopen(urllib.request.Request(
        url, body, {"Content-Type": "application/json"}), timeout=timeout)
    d = json.load(r)
    dt = time.time() - t0
    u = d.get("usage", {}) or {}
    return u.get("prompt_tokens", 0), u.get("completion_tokens", 0), dt

ESSAY = "Ecris un texte de 300 mots sur l'automatisation administrative des PME suisses."
BIG = "Contexte:\n" + ("Le reglement suisse sur la TVA prevoit des taux differencies selon les prestations fournies. " * 170)

lines = ["# Bench SOKKAN Anchor — configuration E (4x Arc Pro B60 24 Go)",
         f"_{time.strftime('%Y-%m-%d %H:%M')} — ROG1, 3 modeles residents simultanement_", ""]

# 0) etat au repos, tout charge
s0 = sysinfo()
lines += ["## Etat au repos (les 3 modeles charges en VRAM)", "",
          f"- RAM hote disponible : **{s0['avail_mb']} Mo** sur 62 Go · swap {s0['swap_mb']} Mo · load {s0['load']}",
          f"- Charge onduleur : **{s0['ups_load']} %**",
          f"- VRAM residente par carte : {vram()}", ""]

# 1) warmup + debit isole
lines += ["## Debit par modele (isole, rien d'autre en charge)", "",
          "| Modele | Cartes | Decode | Prefill (~4k tok) |", "|---|---|---|---|"]
solo = {}
for name, cards, url, model in EP:
    try:
        ask(url, model, "Bonjour", 20, timeout=300)
        _, o, dt = ask(url, model, ESSAY, 400)
        tps = o / dt if dt else 0
        pin, po, pdt = ask(url, model, BIG + "\n\nResume en 2 phrases.", 80)
        solo[name] = tps
        lines.append(f"| {name} | {cards} | **{tps:.1f} tok/s** | {pin} tok en {pdt:.1f}s |")
    except Exception as e:
        lines.append(f"| {name} | {cards} | ECHEC: {type(e).__name__} | — |")

# 2) charge concurrente : les 3 modeles en meme temps, 4 requetes chacun
lines += ["", "## Charge concurrente — les 3 modeles servent en meme temps", "",
          "_4 requetes simultanees par modele (12 au total) : le scenario d'un chassis client_", ""]
def job(args):
    name, _, url, model = args
    try:
        _, o, dt = ask(url, model, ESSAY, 300)
        return name, o, dt
    except Exception as e:
        return name, 0, 0

t0 = time.time()
peak = {"avail_mb": 10**9, "swap_mb": 0, "ups_load": "?"}
with cf.ThreadPoolExecutor(12) as ex:
    futs = [ex.submit(job, e) for e in EP for _ in range(4)]
    while not all(f.done() for f in futs):
        s = sysinfo()
        peak["avail_mb"] = min(peak["avail_mb"], s["avail_mb"])
        peak["swap_mb"] = max(peak["swap_mb"], s["swap_mb"])
        peak["ups_load"] = s["ups_load"]
        time.sleep(3)
    res = [f.result() for f in futs]
wall = time.time() - t0

agg = {}
for name, o, dt in res:
    agg.setdefault(name, [0, 0])
    agg[name][0] += o
    agg[name][1] = max(agg[name][1], dt)
lines += ["| Modele | tokens produits | tok/s agrege |", "|---|---|---|"]
total = 0
for name, (tok, dt) in agg.items():
    total += tok
    lines.append(f"| {name} | {tok} | **{tok/wall:.1f}** |")
lines += [f"| **Total plateforme** | **{total}** | **{total/wall:.1f} tok/s** |", "",
          f"- Duree du run : {wall:.1f}s",
          f"- **Creux de RAM hote pendant la charge : {peak['avail_mb']} Mo disponibles** (swap {peak['swap_mb']} Mo)",
          f"- Charge onduleur au pic : **{peak['ups_load']} %**",
          f"- VRAM par carte en charge : {vram()}", ""]

s1 = sysinfo()
lines += ["## Retour au repos", "",
          f"- RAM disponible : {s1['avail_mb']} Mo · swap {s1['swap_mb']} Mo · load {s1['load']} · UPS {s1['ups_load']} %", ""]

print("\n".join(lines))
