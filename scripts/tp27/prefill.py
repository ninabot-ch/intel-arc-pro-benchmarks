import json,time,sys,random,urllib.request
U="http://127.0.0.1:%s/v1/chat/completions"%(sys.argv[2] if len(sys.argv)>2 else "8004")
n=int(sys.argv[1]); seed=random.randint(0,10**9)
doc="Dossier %d. "%seed+"".join("Fiche %d-%d : le module %d traite des tableaux croisés, des filtres et de la fonction INDEX. "%(seed%997,i,i%17) for i in range(n))
b=json.dumps({"model":"qwen3.8-27b","messages":[{"role":"user","content":doc+"\nRéponds par le seul mot : lu."}],"max_tokens":8,"temperature":0,"chat_template_kwargs":{"enable_thinking":False}}).encode()
t0=time.time(); r=json.load(urllib.request.urlopen(urllib.request.Request(U,b,{"content-type":"application/json"}),timeout=600)); t=time.time()-t0
p=r["usage"]["prompt_tokens"]; print("lecture à froid : %d jetons en %.1f s = %.0f tok/s"%(p,t,p/t))
