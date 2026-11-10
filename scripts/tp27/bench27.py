import json,time,sys,urllib.request,threading
U="http://127.0.0.1:8004/v1/chat/completions"
def run(prompt,max_tokens,res,i):
    b=json.dumps({"model":"qwen3.8-27b","messages":[{"role":"user","content":prompt}],"max_tokens":max_tokens,"stream":True,"stream_options":{"include_usage":True},"temperature":0.2,"chat_template_kwargs":{"enable_thinking":False}}).encode()
    t0=time.time(); t1=None; usage=None; txt=""
    try:
        with urllib.request.urlopen(urllib.request.Request(U,b,{"content-type":"application/json"}),timeout=600) as r:
            for l in r:
                l=l.decode().strip()
                if not l.startswith("data: ") or l=="data: [DONE]": continue
                d=json.loads(l[6:])
                if d.get("usage"): usage=d["usage"]
                for c in d.get("choices",[]):
                    x=(c.get("delta") or {}).get("content") or ""
                    if x and t1 is None: t1=time.time()
                    txt+=x
        t2=time.time(); out=usage["completion_tokens"]
        res[i]=dict(ttft=round((t1 or t2)-t0,2),out=out,inp=usage["prompt_tokens"],tps=round(out/max(t2-(t1 or t0),1e-6),1),total=round(t2-t0,1),txt=txt[:100].replace("\n"," "))
    except Exception as e: res[i]=dict(err=str(e)[:200])
def med(v): v=sorted(v); return v[len(v)//2] if v else None
def conc(n,prompt,mt):
    res=[None]*n; th=[threading.Thread(target=run,args=(prompt,mt,res,i)) for i in range(n)]; t0=time.time()
    [t.start() for t in th]; [t.join() for t in th]; w=time.time()-t0
    ok=[r for r in res if r and "err" not in r]
    print("c=%d ok=%d/%d ttft_med=%s tps_flux_med=%s agrege=%s tok/s mur=%.1fs"%(n,len(ok),n,med([r["ttft"] for r in ok]),med([r["tps"] for r in ok]),round(sum(r["out"] for r in ok)/w,1) if ok else None,w),flush=True)
    for r in res:
        if r and "err" in r: print("  err",r["err"],flush=True); break
    return res
short="Explique en dix phrases comment préparer un plan de formation Excel pour des débutants."
r=conc(1,short,300); print(r[0],flush=True)
k=int(sys.argv[1]) if len(sys.argv)>1 else 0
long="Voici un document interne.\n"+("Le module 3 couvre les tableaux croisés dynamiques, les filtres, la mise en forme conditionnelle et les fonctions RECHERCHEV et INDEX. "*k)+"\nRésume ce document en cinq points."
r=conc(1,long,200); print("long froid",{x:r[0].get(x) for x in ("ttft","inp","out","tps","err")},flush=True)
r=conc(1,long,200); print("long chaud",{x:r[0].get(x) for x in ("ttft","inp","out","tps","err")},flush=True)
for n in (4,8): conc(n,short,250)
