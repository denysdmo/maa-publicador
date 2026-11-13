"""Coletor de métricas do Instagram (13/11/2026). Roda na nuvem (metricas.yml) a cada poucas horas e grava:
  metricas/midias.csv   uma linha por post/carrossel/reel (atualiza os números a cada coleta)
  metricas/stories.csv  uma linha por story (stories só têm métricas por 24 h: por isso a coleta frequente)
  metricas/conta.csv    um dia por linha: alcance, seguidores ganhos, visitas ao perfil, cliques no link
  metricas/resumo.json  ranking e médias por formato/dia/hora (lido pela aba Métricas da agenda e pela rodada de sexta)
Uso: python metricas.py [--tudo]   (--tudo: refaz o histórico inteiro; padrão: últimos 60 dias)
Token: o mesmo do publicador (IG_TOKEN com instagram_manage_insights)."""
import csv, datetime, json, os, sys, time, urllib.error, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import instagram as ig  # noqa: E402

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metricas")
TOK, UID = ig.env()
FUSO = datetime.timezone(datetime.timedelta(hours=-3))


def get(path, **q):
    q["access_token"] = TOK
    url = f"{ig.API}/{path}?{urllib.parse.urlencode(q)}"
    for t in range(3):
        try:
            return json.load(urllib.request.urlopen(url, timeout=40))
        except urllib.error.HTTPError as e:
            err = json.load(e).get("error", {})
            return {"erro": err.get("message", "")[:200], "code": err.get("code")}
        except Exception:
            time.sleep(3 * (t + 1))
    return {"erro": "sem resposta"}


def insights(mid, metricas):
    """Pede as métricas; se a API recusar alguma (varia por tipo de mídia), tira a culpada e tenta de novo."""
    pedir = list(metricas)
    out = {}
    while pedir:
        r = get(f"{mid}/insights", metric=",".join(pedir))
        if "erro" not in r:
            for d in r.get("data", []):
                v = d.get("values", [{}])
                out[d["name"]] = (v[0].get("value") if v else None) if "total_value" not in d else d["total_value"].get("value")
            return out
        culpada = next((m for m in pedir if m in r["erro"]), None)
        if not culpada:
            return out
        pedir.remove(culpada)
    return out


def ler(nome, chave):
    p = os.path.join(PASTA, nome)
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8", newline="") as f:
        return {l[chave]: l for l in csv.DictReader(f)}


def gravar(nome, linhas, campos):
    os.makedirs(PASTA, exist_ok=True)
    with open(os.path.join(PASTA, nome), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        w.writerows(linhas)


def quando_local(ts):
    d = datetime.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z").astimezone(FUSO)
    return d


FEED = ["reach", "views", "likes", "comments", "saved", "shares", "total_interactions", "follows", "profile_visits"]
REEL = ["reach", "views", "likes", "comments", "saved", "shares", "total_interactions", "ig_reels_avg_watch_time", "ig_reels_video_view_total_time"]
STORY = ["reach", "views", "replies", "shares", "total_interactions", "follows", "profile_visits", "navigation"]
CAMPOS_M = ["id", "data", "dia_semana", "hora", "formato", "legenda", "link", "reach", "views", "likes", "comments", "saved", "shares",
            "total_interactions", "follows", "profile_visits", "ig_reels_avg_watch_time", "taxa_engaj", "coletado"]
CAMPOS_S = ["id", "data", "dia_semana", "hora", "link", "reach", "views", "replies", "shares", "total_interactions", "follows",
            "profile_visits", "navigation", "saidas", "avancos", "voltas", "coletado"]
DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def formato(m):
    if m.get("media_product_type") == "REELS":
        return "reel"
    return {"CAROUSEL_ALBUM": "carrossel", "IMAGE": "post", "VIDEO": "video"}.get(m.get("media_type"), m.get("media_type", "?").lower())


def coleta_midias(tudo):
    antigas = ler("midias.csv", "id")
    limite = datetime.datetime.now(FUSO) - datetime.timedelta(days=99999 if tudo else 60)
    agora = datetime.datetime.now(FUSO).isoformat(timespec="minutes")
    r = get(f"{UID}/media", fields="id,media_type,media_product_type,timestamp,caption,permalink", limit=50)
    while r and "data" in r:
        parar = False
        for m in r["data"]:
            d = quando_local(m["timestamp"])
            if d < limite:
                parar = True
                break
            f = formato(m)
            ins = insights(m["id"], REEL if f == "reel" else FEED)
            reach = ins.get("reach") or 0
            inter = (ins.get("saved") or 0) * 2 + (ins.get("shares") or 0) * 3 + (ins.get("comments") or 0) + (ins.get("likes") or 0) * 0.5
            antigas[m["id"]] = {
                "id": m["id"], "data": d.strftime("%Y-%m-%d"), "dia_semana": DIAS[d.weekday()], "hora": d.strftime("%H:%M"), "formato": f,
                "legenda": (m.get("caption") or "").replace("\n", " ")[:160], "link": m.get("permalink", ""),
                **{k: ins.get(k, "") for k in CAMPOS_M if k in ins},
                "taxa_engaj": round(inter / reach * 100, 2) if reach else "", "coletado": agora,
            }
        nxt = r.get("paging", {}).get("next")
        if parar or not nxt:
            break
        r = json.load(urllib.request.urlopen(nxt, timeout=40))
    linhas = sorted(antigas.values(), key=lambda x: x["data"] + x["hora"], reverse=True)
    gravar("midias.csv", linhas, CAMPOS_M)
    return linhas


def coleta_stories():
    antigas = ler("stories.csv", "id")
    agora = datetime.datetime.now(FUSO).isoformat(timespec="minutes")
    r = get(f"{UID}/stories", fields="id,timestamp,permalink")
    for s in r.get("data", []):
        d = quando_local(s["timestamp"])
        ins = insights(s["id"], STORY)
        nav = get(f"{s['id']}/insights", metric="navigation", breakdown="story_navigation_action_type")
        acoes = {}
        for item in nav.get("data", []):
            for b in item.get("total_value", {}).get("breakdowns", []):
                for res in b.get("results", []):
                    acoes[res["dimension_values"][0]] = res["value"]
        antigas[s["id"]] = {
            "id": s["id"], "data": d.strftime("%Y-%m-%d"), "dia_semana": DIAS[d.weekday()], "hora": d.strftime("%H:%M"), "link": s.get("permalink", ""),
            **{k: ins.get(k, "") for k in CAMPOS_S if k in ins},
            "saidas": acoes.get("tap_exit", ""), "avancos": acoes.get("tap_forward", ""),
            "voltas": acoes.get("tap_back", ""), "coletado": agora,
        }
    linhas = sorted(antigas.values(), key=lambda x: x["data"] + x["hora"], reverse=True)
    gravar("stories.csv", linhas, CAMPOS_S)
    return linhas


DIARIAS = ["views", "reach", "profile_views", "website_clicks", "accounts_engaged", "total_interactions", "likes", "comments", "shares", "saves", "replies", "follows_and_unfollows"]
CAMPOS_C = ["data", "follower_count"] + DIARIAS


def coleta_conta(tudo=False):
    """Um dia por linha (horário de Brasília). Histórico acumula: na 1ª vez (ou --tudo) busca 90 dias; depois, os 4 últimos."""
    antigas = ler("conta.csv", "data")
    fim = int(time.time())
    completos = len([l for l in antigas.values() if str(l.get("views", "")) != ""])
    dias = 90 if (tudo or completos < 20) else 4
    # novos seguidores por dia (série; a API dá até 30 dias)
    serie = get(f"{UID}/insights", metric="follower_count", period="day", since=fim - 29 * 86400, until=fim)
    for d in serie.get("data", []):
        for v in d.get("values", []):
            dia = (datetime.datetime.fromisoformat(v["end_time"].replace("+0000", "+00:00")) - datetime.timedelta(days=1)).astimezone(FUSO).strftime("%Y-%m-%d")
            antigas.setdefault(dia, {"data": dia})["follower_count"] = v["value"]
    hoje = datetime.datetime.now(FUSO).replace(hour=0, minute=0, second=0, microsecond=0)
    for k in range(dias):
        ini = hoje - datetime.timedelta(days=k)
        a = int(ini.timestamp())
        t = get(f"{UID}/insights", metric=",".join(DIARIAS), period="day", metric_type="total_value", since=a, until=min(a + 86400, fim))
        dia = ini.strftime("%Y-%m-%d")
        for d in t.get("data", []):
            antigas.setdefault(dia, {"data": dia})[d["name"]] = d.get("total_value", {}).get("value", "")
    perfil = get(UID, fields="followers_count,media_count")
    linhas = sorted(antigas.values(), key=lambda x: x["data"], reverse=True)
    gravar("conta.csv", linhas, CAMPOS_C)
    return linhas, perfil


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def resumo(midias, stories, conta, perfil):
    def media(ls, k):
        v = [num(l.get(k)) for l in ls if str(l.get(k, "")) != ""]
        return round(sum(v) / len(v), 1) if v else 0

    por_formato = {}
    for f in sorted({m["formato"] for m in midias}):
        ls = [m for m in midias if m["formato"] == f]
        por_formato[f] = {"posts": len(ls), "alcance": media(ls, "reach"), "salvos": media(ls, "saved"), "compart": media(ls, "shares"), "engaj": media(ls, "taxa_engaj")}
    por_dia = {d: {"posts": len([m for m in midias if m["dia_semana"] == d]), "alcance": media([m for m in midias if m["dia_semana"] == d], "reach")} for d in DIAS}
    por_hora = {}
    for m in midias:
        h = m["hora"][:2]
        por_hora.setdefault(h, []).append(num(m.get("reach")))
    por_hora = {h: {"posts": len(v), "alcance": round(sum(v) / len(v), 1)} for h, v in sorted(por_hora.items())}
    top = sorted(midias, key=lambda m: num(m.get("reach")), reverse=True)[:10]
    top_engaj = sorted([m for m in midias if num(m.get("reach")) >= 100], key=lambda m: num(m.get("taxa_engaj")), reverse=True)[:10]
    out = {
        "atualizado": datetime.datetime.now(FUSO).isoformat(timespec="minutes"),
        "seguidores": perfil.get("followers_count"), "publicacoes": perfil.get("media_count"),
        "por_formato": por_formato, "por_dia": por_dia, "por_hora": por_hora,
        "top_alcance": [{k: m.get(k) for k in ("data", "formato", "legenda", "link", "reach", "saved", "shares", "taxa_engaj")} for m in top],
        "top_engajamento": [{k: m.get(k) for k in ("data", "formato", "legenda", "link", "reach", "saved", "shares", "taxa_engaj")} for m in top_engaj],
        "stories_medias": {"alcance": media(stories, "reach"), "respostas": media(stories, "replies"), "saidas": media(stories, "saidas")},
        "conta": conta[:400],
        "publicacoes_por_dia": {d: len([m for m in midias if m["data"] == d]) for d in sorted({m["data"] for m in midias})[-400:]},
    }
    with open(os.path.join(PASTA, "resumo.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    return out


if __name__ == "__main__":
    tudo = "--tudo" in sys.argv
    m = coleta_midias(tudo)
    s = coleta_stories()
    c, p = coleta_conta(tudo)
    r = resumo(m, s, c, p)
    print(f"ok: {len(m)} publicações, {len(s)} stories, {len(c)} dias; seguidores {r['seguidores']}")
