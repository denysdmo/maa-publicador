"""Relatório semanal de métricas (13/11/2026): resumo da semana passada (segunda a domingo) para o aviso de segunda.
Uso: python relatorio.py  → imprime Markdown (o workflow abre um issue com ele)."""
import csv, datetime, json, os

P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metricas")
FUSO = datetime.timezone(datetime.timedelta(hours=-3))
hoje = datetime.datetime.now(FUSO).date()
fim = hoje - datetime.timedelta(days=hoje.weekday() + 1)  # domingo passado
ini = fim - datetime.timedelta(days=6)
n = lambda x: float(x) if str(x).replace(".", "", 1).isdigit() else 0.0
m = [l for l in csv.DictReader(open(os.path.join(P, "midias.csv"), encoding="utf-8")) if ini.isoformat() <= l["data"] <= fim.isoformat()]
s = [l for l in csv.DictReader(open(os.path.join(P, "stories.csv"), encoding="utf-8")) if ini.isoformat() <= l["data"] <= fim.isoformat()]
c = [l for l in csv.DictReader(open(os.path.join(P, "conta.csv"), encoding="utf-8")) if ini.isoformat() <= l["data"] <= fim.isoformat()]
r = json.load(open(os.path.join(P, "resumo.json"), encoding="utf-8"))
soma = lambda ls, k: int(sum(n(l.get(k)) for l in ls))
out = [f"## Semana de {ini:%d/%m} a {fim:%d/%m}", "",
       f"- **Seguidores:** {r.get('seguidores')} ({soma(c, 'follower_count'):+d} na semana)",
       f"- **Alcance da conta:** {soma(c, 'reach')} · **visitas ao perfil:** {soma(c, 'profile_views')} · **cliques no link:** {soma(c, 'website_clicks')}",
       f"- **Publicações:** {len(m)} no feed · {len(s)} stories", ""]
if m:
    out += ["### Top 3 do feed", ""]
    for l in sorted(m, key=lambda l: n(l["reach"]), reverse=True)[:3]:
        out.append(f"- [{l['formato']} {l['data'][8:]}/{l['data'][5:7]}]({l['link']}): **{int(n(l['reach']))}** de alcance, {int(n(l['saved']))} salvos, {int(n(l['shares']))} compartilhamentos · {l['legenda'][:80]}")
    out.append("")
if s:
    out += [f"### Stories: alcance médio {int(sum(n(l['reach']) for l in s) / len(s))}, respostas {soma(s, 'replies')}", ""]
out += ["Veja tudo na aba **📊 Métricas** da agenda. Na sexta eu uso esses números para montar a próxima semana."]
print("\n".join(out))
