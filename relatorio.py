"""Relatório semanal (13/11/2026; refeito em 14/11 a pedido do Denys: "mostre o que deu certo, o que deu errado, os
próximos passos; atue como especialista em social media e auditoria").

Analisa a semana de segunda a domingo e cruza 3 fontes:
  metricas/midias.csv  (feed: alcance, salvos, compartilhamentos, seguidores)    metricas/stories.csv (stories)
  metricas/conta.csv   (conta por dia)                                            fila.csv (o que foi planejado/saiu)
Grava metricas/relatorios/<segunda>.json (lido pela aba Métricas do app) e atualiza metricas/relatorios/indice.json.
A análise escrita do especialista (rodada de sexta, feita pelo Claude) fica em metricas/relatorios/<segunda>-especialista.md
e o app mostra junto. Imprime o Markdown (o workflow de segunda abre um issue com ele).

Uso: python relatorio.py [AAAA-MM-DD (segunda da semana)] [--salvar]   (padrão: a semana passada)"""
import csv, datetime, json, os, statistics, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(AQUI, "metricas")
R = os.path.join(P, "relatorios")
FUSO = datetime.timezone(datetime.timedelta(hours=-3))
agora = datetime.datetime.now(FUSO)

args = [a for a in sys.argv[1:] if not a.startswith("--")]
if args:
    ini = datetime.date.fromisoformat(args[0])
else:
    hoje = agora.date()
    ini = hoje - datetime.timedelta(days=hoje.weekday() + 7)  # segunda passada
fim = ini + datetime.timedelta(days=6)
ini_ant, fim_ant = ini - datetime.timedelta(days=7), ini - datetime.timedelta(days=1)


def n(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def ler(nome):
    p = os.path.join(P, nome)
    return list(csv.DictReader(open(p, encoding="utf-8"))) if os.path.exists(p) else []


def entre(ls, a, b, k="data"):
    return [l for l in ls if a.isoformat() <= l[k][:10] <= b.isoformat()]


midias, stories, conta = ler("midias.csv"), ler("stories.csv"), ler("conta.csv")
fila = list(csv.DictReader(open(os.path.join(AQUI, "fila.csv"), encoding="utf-8-sig")))
resumo = json.load(open(os.path.join(P, "resumo.json"), encoding="utf-8")) if os.path.exists(os.path.join(P, "resumo.json")) else {}

m, m_ant = entre(midias, ini, fim), entre(midias, ini_ant, fim_ant)
s = entre(stories, ini, fim)
c, c_ant = entre(conta, ini, fim), entre(conta, ini_ant, fim_ant)
f_sem = [l for l in fila if ini.isoformat() <= l["quando"][:10] <= fim.isoformat()]
base = entre(midias, ini - datetime.timedelta(days=30), fim)  # 30 dias até o fim da semana
med = statistics.median([n(l["reach"]) for l in base if n(l["reach"])] or [0]) or 1

FORMATO = {"reel": "Reel", "carrossel": "Carrossel", "post": "Post", "video": "Vídeo"}
DIA = {"seg": "segunda", "ter": "terça", "qua": "quarta", "qui": "quinta", "sex": "sexta", "sáb": "sábado", "dom": "domingo"}
nome = lambda l: f"{FORMATO.get(l['formato'], l['formato'])} de {DIA.get(l['dia_semana'], l['dia_semana'])} {l['data'][8:]}/{l['data'][5:7]} ({l['hora']})"
tema = lambda l: (l.get("legenda") or "").split(".")[0].split("?")[0][:80].strip()
soma = lambda ls, k: sum(n(l.get(k)) for l in ls)
pct = lambda a, b: None if not b else round((a - b) / b * 100)

# ------------------------------------------------------------------ números
NUM = [("Novos seguidores", "follower_count"), ("Alcance da conta", "reach"), ("Visualizações", "views"), ("Visitas ao perfil", "profile_views"),
       ("Cliques no link da bio", "website_clicks"), ("Compartilhamentos", "shares"), ("Salvamentos", "saves")]
numeros = [{"rotulo": r, "valor": int(soma(c, k)), "antes": int(soma(c_ant, k)), "delta": pct(soma(c, k), soma(c_ant, k))} for r, k in NUM]
numeros += [{"rotulo": "Publicações no feed", "valor": len(m), "antes": len(m_ant), "delta": pct(len(m), len(m_ant))},
            {"rotulo": "Stories publicados", "valor": len(s), "antes": None, "delta": None}]
num = {x["rotulo"]: x for x in numeros}

# ------------------------------------------------------------------ o que deu certo / errado
certo, errado = [], []
ordem = sorted(m, key=lambda l: n(l["reach"]), reverse=True)
for l in ordem:
    x = n(l["reach"]) / med
    if x >= 1.3 and len(certo) < 3:
        certo.append(f"**{nome(l)}** chegou a **{int(n(l['reach']))} contas**, {x:.1f}× a mediana dos últimos 30 dias ({int(med)}). Tema: “{tema(l)}”.")
comp = [l for l in m if n(l["shares"]) > 0 and n(l["reach"]) > 0]
if comp:
    b = max(comp, key=lambda l: n(l["shares"]) / n(l["reach"]))
    certo.append(f"Mais **enviado** da semana: {nome(b)}, {int(n(b['shares']))} compartilhamentos ({n(b['shares']) / n(b['reach']) * 100:.1f}% do alcance). É o sinal que mais leva o perfil a quem ainda não segue.")
salv = [l for l in m if n(l["saved"]) > 0 and n(l["reach"]) > 0]
if salv:
    b = max(salv, key=lambda l: n(l["saved"]) / n(l["reach"]))
    certo.append(f"Mais **salvo**: {nome(b)}, {int(n(b['saved']))} salvamentos ({n(b['saved']) / n(b['reach']) * 100:.1f}% do alcance): conteúdo que a pessoa guarda para estudar.")
for x in numeros[:7]:
    if x["delta"] is not None and x["delta"] >= 15 and x["valor"] >= 5:
        certo.append(f"**{x['rotulo']}** subiu {x['delta']}% em relação à semana anterior ({x['antes']} → {x['valor']}).")
resp = [l for l in s if n(l.get("replies")) > 0]
if resp:
    b = max(resp, key=lambda l: n(l["replies"]))
    certo.append(f"Story com mais respostas: {b['dia_semana']} {b['data'][8:]}/{b['data'][5:7]} {b['hora']} ({int(n(b['replies']))} respostas).")

for l in reversed(ordem):
    x = n(l["reach"]) / med
    if x <= 0.6 and len([e for e in errado if "abaixo" in e]) < 3:
        errado.append(f"**{nome(l)}** ficou abaixo: {int(n(l['reach']))} contas ({x:.1f}× a mediana). Tema: “{tema(l)}”.")
for x in numeros[:7]:
    if x["delta"] is not None and x["delta"] <= -20 and x["antes"] >= 5:
        errado.append(f"**{x['rotulo']}** caiu {abs(x['delta'])}% ({x['antes']} → {x['valor']}).")
st_saida = [l for l in s if n(l.get("reach")) >= 5 and n(l.get("saidas")) / n(l["reach"]) > 0.2]
if st_saida:
    errado.append(f"{len(st_saida)} story(s) com muita saída (mais de 20% de quem viu saiu da sequência): rever o que vem antes deles.")
falhas = [l for l in f_sem if l["status"] in ("erro", "atrasado")]
for l in falhas:
    errado.append(f"Não saiu: {l['tipo']} de {l['quando'][8:10]}/{l['quando'][5:7]} {l['quando'][11:16]} ({l['status']}: {l['resultado'][:80]}).")
perdidos = [l for l in f_sem if l["status"] == "rascunho" and l["quando"] < agora.strftime("%Y-%m-%dT%H:%M")]
if perdidos:
    errado.append(f"{len(perdidos)} peça(s) ficaram **sem aprovação** e não foram postadas no horário.")
if num["Cliques no link da bio"]["valor"] == 0 and num["Visitas ao perfil"]["valor"] > 20:
    errado.append("Ninguém clicou no link da bio mesmo com visitas ao perfil: o caminho até a venda está travado.")

# ------------------------------------------------------------------ próximos passos (regras de especialista)
passos = []
if ordem and n(ordem[0]["reach"]) / med >= 1.3:
    passos.append(f"Repetir o **molde** do campeão ({FORMATO.get(ordem[0]['formato'], ordem[0]['formato'])}, “{tema(ordem[0])}”) com **outro ângulo** ou outro tema da prova. Repostar igual não funciona.")
ph = {h: v for h, v in (resumo.get("por_hora") or {}).items() if v.get("posts", 0) >= 3}
pf = resumo.get("por_formato") or {}
if ph:
    h = max(ph, key=lambda k: ph[k]["alcance"])
    passos.append(f"Manter o carro-chefe no horário de melhor média: **{h}h** ({int(ph[h]['alcance'])} de alcance médio em {ph[h]['posts']} posts).")
if pf:
    f = max(pf, key=lambda k: pf[k]["alcance"])
    passos.append(f"Formato com melhor alcance médio: **{FORMATO.get(f, f)}** ({int(pf[f]['alcance'])}). Garanta pelo menos 2 por semana.")
tx_comp = soma(m, "shares") / max(1, soma(m, "reach")) * 100
if m and tx_comp < 1:
    passos.append(f"Compartilhamento baixo ({tx_comp:.1f}% do alcance): colocar no **meio** dos reels o “manda pra quem vai fazer a prova” e pegadinhas para testar o amigo.")
if num["Visitas ao perfil"]["valor"] and num["Cliques no link da bio"]["valor"] / max(1, num["Visitas ao perfil"]["valor"]) < 0.1:
    passos.append("Menos de 10% das visitas ao perfil clicam no link: reforçar o CTA da bio e o 2º CTA na legenda (“questões assim, com explicação, no link da bio”).")
if num["Novos seguidores"]["valor"] <= max(5, num["Novos seguidores"]["antes"] * 0.8):
    passos.append("Seguidores andando devagar: abrir uma **série** (“Pegadinha da semana nº X”) para quem gostou de uma peça ir atrás da próxima.")
if perdidos:
    passos.append("Aprovar a semana até domingo à noite no app (botão **Aprovar todos**) para nada ficar parado.")
if falhas:
    passos.append("Conferir as falhas de publicação (aviso no GitHub) e reagendar o que não saiu.")
if not passos:
    passos.append("Semana estável: manter o plano e testar 1 variável (gancho ou horário) no reel de maior alcance.")

# ------------------------------------------------------------------ auditoria
cont = lambda st: len([l for l in f_sem if l["status"] == st])
tipos = {}
for l in f_sem:
    tipos[l["tipo"]] = tipos.get(l["tipo"], 0) + 1
auditoria = [
    f"Planejado na fila: **{len(f_sem)}** peças ({', '.join(f'{v} {k}' for k, v in sorted(tipos.items()))}).",
    f"Publicadas: **{cont('publicado')}** · agendadas: {cont('pendente')} · sem aprovação: {cont('rascunho')} · canceladas/vetadas: {cont('cancelado')} · falhas: {cont('erro') + cont('atrasado')}.",
    f"Publicações medidas no feed: {len(m)} · stories medidos: {len(s)} (stories só têm números por 24 h).",
    f"Mediana de alcance do feed nos últimos 30 dias: **{int(med)}** contas (régua usada acima).",
    f"Métricas atualizadas em {resumo.get('atualizado', '—')[:16].replace('T', ' ')}.",
]
if not c:
    auditoria.append("⚠️ Sem dados de conta para esta semana (a coleta ainda não rodou).")

rel = {
    "semana": {"ini": ini.isoformat(), "fim": fim.isoformat()},
    "gerado": agora.isoformat(timespec="minutes"),
    "seguidores": resumo.get("seguidores"),
    "numeros": numeros,
    "certo": certo or ["Nenhuma peça passou de 1,3× a mediana nesta semana."],
    "errado": errado or ["Nada abaixo do esperado e nenhuma falha de publicação."],
    "passos": passos,
    "auditoria": auditoria,
    "top": [{k: l.get(k) for k in ("data", "hora", "formato", "legenda", "link", "reach", "saved", "shares")} for l in ordem[:5]],
}

if "--salvar" in sys.argv:
    os.makedirs(R, exist_ok=True)
    json.dump(rel, open(os.path.join(R, f"{ini.isoformat()}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    semanas = sorted({f[:10] for f in os.listdir(R) if f[:4].isdigit() and f.endswith(".json")}, reverse=True)
    indice = [{"ini": w, "especialista": os.path.exists(os.path.join(R, f"{w}-especialista.md"))} for w in semanas]
    json.dump(indice, open(os.path.join(R, "indice.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def seta(x):
    return "" if x["delta"] is None else f" ({'+' if x['delta'] >= 0 else ''}{x['delta']}%)"


md = [f"## Semana de {ini:%d/%m} a {fim:%d/%m}", "", f"Seguidores hoje: **{rel['seguidores']}**", ""]
md += [f"- {x['rotulo']}: **{x['valor']}**{seta(x)}" for x in numeros] + [""]
for titulo, k in (("✅ O que deu certo", "certo"), ("⚠️ O que deu errado", "errado"), ("➡️ Próximos passos", "passos"), ("🔎 Auditoria", "auditoria")):
    md += [f"### {titulo}", ""] + [f"- {t}" for t in rel[k]] + [""]
md.append("O relatório completo, com a análise do especialista, está na aba **Métricas** do app: https://denysdmo.github.io/maa-publicador/")
print("\n".join(md))
