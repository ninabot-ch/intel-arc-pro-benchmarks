import json,time,urllib.request,re
U="http://127.0.0.1:8004/v1/chat/completions"
doc="".join("Section %d : le module %d couvre les tableaux croisés dynamiques, les filtres, la mise en forme conditionnelle et les fonctions RECHERCHEV et INDEX. "%(i,i%17) for i in range(2600))
doc+="\nLe code secret du dossier est ORCHIDEE-4471.\n"+"".join("Annexe %d : rappel des consignes de sécurité et du calendrier des sessions. "%i for i in range(300))
def ask(q):
    b=json.dumps({"model":"qwen3.8-27b","messages":[{"role":"user","content":doc+"\n\n"+q}],"max_tokens":40,"temperature":0,"chat_template_kwargs":{"enable_thinking":False}}).encode()
    t0=time.time(); r=json.load(urllib.request.urlopen(urllib.request.Request(U,b,{"content-type":"application/json"}),timeout=400))
    return (r["choices"][0]["message"].get("content") or "").strip(), time.time()-t0
ok=0; out=[]
for s in (7,333,1234,1999,2588):
    a,t=ask("Quel numéro de module est couvert par la section %d ? Réponds par le nombre seul."%s)
    m=re.search(r"\d+",a); good=bool(m) and int(m.group(0))==s%17; ok+=good; out.append("s%d→%s%s(%.0fs)"%(s,a[:6],"✓" if good else "✗ attendu %d"%(s%17),t))
print("recherche précise dans 110k jetons : %d/5 | %s"%(ok," ".join(out)))
