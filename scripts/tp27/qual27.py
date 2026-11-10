import json,sys,re,time,urllib.request
U="http://127.0.0.1:8004/v1/chat/completions"; M=sys.argv[1] if len(sys.argv)>1 else "qwen3.8-27b"
def call(msgs,tools=None,mt=220):
    b={"model":M,"messages":msgs,"max_tokens":mt,"temperature":0,"chat_template_kwargs":{"enable_thinking":False}}
    if tools: b["tools"]=tools
    r=json.load(urllib.request.urlopen(urllib.request.Request(U,json.dumps(b).encode(),{"content-type":"application/json"}),timeout=180))
    return r["choices"][0]["message"]
def q(p): return (call([{"role":"user","content":p}]).get("content") or "").strip()
def js(t):
    m=re.search(r"\{.*\}",t,re.S)
    try: return json.loads(m.group(0)) if m else None
    except Exception: return None
T=[]
def add(name,fn): T.append((name,fn))
add("arith1",lambda: "1554" in q("Calcule 37 × 42. Donne seulement le nombre."))
add("arith2",lambda: "391" in q("Une formation coûte 1 150 CHF HT. TVA 8,1 %. Montant de la TVA arrondi au franc ? Donne seulement le nombre.").replace("93","391") if False else "93" in q("Une formation coûte 1 150 CHF HT. TVA 8,1 %. Montant de la TVA arrondi au franc ? Donne seulement le nombre."))
add("arith3",lambda: "17" in q("J'ai 3 groupes de 12 apprenants, 19 abandonnent. Combien en reste-t-il ? Seulement le nombre."))
add("arith4",lambda: "2,5" in q("4 formateurs préparent un module en 10 jours. Avec 16 formateurs au même rythme, combien de jours ? Réponds avec un nombre décimal français.").replace(".",","))
add("logique1",lambda: "jeudi" in q("Si le 3 mars est un mardi, quel jour de la semaine est le 12 mars ? Un seul mot.").lower())
add("logique2",lambda: q("Alice est plus âgée que Bob. Bob est plus âgé que Chloé. Qui est la plus jeune ? Un seul prénom.").lower().startswith("chlo"))
add("logique3",lambda: "non" in q("Tous les modules validés ont un quiz. Le module 7 n'a pas de quiz. Le module 7 est-il validé ? Réponds par oui ou non.").lower()[:12])
add("logique4",lambda: "b" == q("Quelle option est un nombre premier ? A) 21 B) 23 C) 27 D) 33. Réponds par la lettre seule.").strip().lower()[:1])
def ex1():
    d=js(q("Extrais en JSON strict {\"nom\":…,\"date\":\"AAAA-MM-JJ\",\"participants\":nombre} depuis : « La session Excel avancé aura lieu le 14 janvier 2027 avec douze participants. » Réponds uniquement par le JSON."))
    return bool(d) and d.get("date")=="2027-01-14" and d.get("participants")==12 and "excel" in str(d.get("nom","")).lower()
add("extract1",ex1)
def ex2():
    d=js(q("Mail : « Bonjour, je souhaite décaler la formation du 9 au 16 février, merci. Camille Roux, Formatis ». Donne en JSON strict {\"intention\":\"report|annulation|inscription\",\"expediteur\":…,\"nouvelle_date\":\"JJ.MM\"}. JSON seul."))
    return bool(d) and d.get("intention")=="report" and "camille" in str(d.get("expediteur","")).lower() and str(d.get("nouvelle_date","")).startswith("16.02")
add("extract2",ex2)
def ex3():
    d=js(q("Classe ce ticket en JSON strict {\"priorite\":\"haute|moyenne|basse\",\"equipe\":\"facturation|technique|pedagogie\"} : « La plateforme est inaccessible pour tous nos apprenants depuis ce matin. » JSON seul."))
    return bool(d) and d.get("priorite")=="haute" and d.get("equipe")=="technique"
add("extract3",ex3)
def ex4():
    d=js(q("Liste en JSON strict {\"montants\":[nombres]} tous les montants en CHF de ce texte : « Acompte de 450 CHF, solde de 1 350 CHF, frais de dossier 80 CHF, remise de 10 %. » JSON seul."))
    return bool(d) and sorted(d.get("montants",[]))==[80,450,1350]
add("extract4",ex4)
add("fr1",lambda: "auraient" in q("Conjugue « avoir » au conditionnel présent, 3e personne du pluriel. Un seul mot.").lower())
add("fr2",lambda: any(w in q("Traduis en anglais, une phrase : « Le plan de formation doit être validé avant vendredi. »").lower() for w in ["training plan must be","training plan has to be","training plan needs to be"]))
add("fr3",lambda: len(q("Résume en exactement 5 mots : « Les agents IA assistent les formateurs dans la préparation des supports. »").replace("."," ").split())==5)
add("consigne1",lambda: q("Réponds exactement par le mot OK en majuscules et rien d'autre.")=="OK")
add("consigne2",lambda: re.fullmatch(r"\s*-\s*\S.*\n\s*-\s*\S.*\n\s*-\s*\S.*\s*",q("Donne exactement trois puces, une par ligne, commençant par « - », sur les avantages d'un quiz. Rien d'autre.")) is not None)
add("refus_invention",lambda: any(w in q("Quel est le chiffre d'affaires 2025 exact de la société Formatis SA ? Si tu ne le sais pas, dis-le.").lower() for w in ["ne sais pas","pas accès","ne dispose pas","je n'ai pas","ne connais pas","pas d'information","pas en mesure"]))
TOOLS=[{"type":"function","function":{"name":n,"description":d,"parameters":{"type":"object","properties":p,"required":list(p)}}} for n,d,p in [
 ("chercher_document","Cherche un document interne par mots-clés",{"requete":{"type":"string"}}),
 ("envoyer_mail","Envoie un mail",{"destinataire":{"type":"string"},"objet":{"type":"string"},"corps":{"type":"string"}}),
 ("creer_evenement","Crée un événement d'agenda",{"titre":{"type":"string"},"date":{"type":"string","description":"AAAA-MM-JJ"},"heure":{"type":"string","description":"HH:MM"}})]]
def tool(p,name,chk):
    m=call([{"role":"user","content":p}],TOOLS); tc=m.get("tool_calls") or []
    if not tc or tc[0]["function"]["name"]!=name: return False
    try: a=json.loads(tc[0]["function"]["arguments"])
    except Exception: return False
    return chk(a)
add("outil1",lambda: tool("Trouve le référentiel de compétences Excel 2025.","chercher_document",lambda a:"excel" in a.get("requete","").lower()))
add("outil2",lambda: tool("Planifie la séance de restitution le 22 avril 2027 à 14h.","creer_evenement",lambda a:a.get("date")=="2027-04-22" and a.get("heure","").startswith("14")))
add("outil3",lambda: tool("Écris à alex@example.org pour confirmer la réunion de lundi.","envoyer_mail",lambda a:a.get("destinataire")=="alex@example.org" and len(a.get("corps",""))>10))
def notool():
    m=call([{"role":"user","content":"Combien font 2 + 2 ?"}],TOOLS); return not m.get("tool_calls") and "4" in (m.get("content") or "")
add("outil_aucun",notool)
ok=0; t0=time.time(); fails=[]
for n,f in T:
    try: r=bool(f())
    except Exception as e: r=False; n+="(err:%s)"%str(e)[:40]
    ok+=r
    if not r: fails.append(n)
print("%s : %d/%d en %.0f s | échecs : %s"%(M,ok,len(T),time.time()-t0,", ".join(fails) or "aucun"))
