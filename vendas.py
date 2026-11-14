"""Coletor do funil de vendas (14/11/2026): Instagram -> VTurb (vídeo da página da bio) -> Kiwify (checkout).
Roda na nuvem (publicar.yml) no máximo a cada 3 h, como o metricas.py, e grava metricas/funil.json (lido pela aba Métricas).

O repositório é PÚBLICO: aqui só entram TOTAIS por dia e por origem. Nada de nome, e-mail, CPF ou telefone de cliente,
nem a venda uma a uma.

Segredos (GitHub > Settings > Secrets and variables > Actions), colados pelo próprio Denys:
  VTURB_TOKEN           VTurb > Configurações > API (token de Analytics)
  VTURB_PLAYER_ID       opcional: id do player do vídeo da bio (vários: separe por vírgula). Sem ele, pega os 5 mais vistos.
  KIWIFY_CLIENT_ID      Kiwify > Apps > API > Criar API Key
  KIWIFY_CLIENT_SECRET  idem (aparece uma vez só, na janela da chave)
  KIWIFY_ACCOUNT_ID     idem (mesma tela)
Uso: python vendas.py"""
import datetime, json, os, time, urllib.error, urllib.parse, urllib.request

PASTA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "metricas")
FUSO = datetime.timezone(datetime.timedelta(hours=-3))
TZ = "America/Sao_Paulo"
DIAS = 90
JANELAS = [1, 3, 7, 14, 30, 90]
PAGAS = {"paid", "approved", "authorized"}
DEVOLVIDAS = {"refunded", "chargedback", "pending_refund", "refund_requested"}


def http(url, metodo="GET", corpo=None, cab=None, form=False):
    cab = dict(cab or {})
    dados = None
    if corpo is not None:
        if form:
            dados = urllib.parse.urlencode(corpo).encode()
            cab["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            dados = json.dumps(corpo).encode()
            cab["Content-Type"] = "application/json"
    cab.setdefault("User-Agent", "maa-publicador")
    for t in range(4):
        try:
            req = urllib.request.Request(url, data=dados, headers=cab, method=metodo)
            return json.load(urllib.request.urlopen(req, timeout=60))
        except urllib.error.HTTPError as e:
            if e.code == 429 and t < 3:
                time.sleep(20 * (t + 1))
                continue
            try:
                corpo_err = json.load(e)
            except Exception:
                corpo_err = {}
            msg = corpo_err.get("message") or corpo_err.get("error") or ""
            raise RuntimeError(f"HTTP {e.code} {str(msg)[:160]}")
        except (urllib.error.URLError, TimeoutError):
            time.sleep(5 * (t + 1))
    raise RuntimeError("sem resposta")


def hoje():
    return datetime.datetime.now(FUSO).date()


def n(x):
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def origem(src):
    s = (src or "").strip().lower()
    if not s:
        return "sem UTM"
    if s in ("ig", "insta") or "instagram" in s:
        return "instagram"
    return s


# ---------------------------------------------------------------- Kiwify
def kiwify():
    cid, sec, conta = (os.environ.get(k, "").strip() for k in ("KIWIFY_CLIENT_ID", "KIWIFY_CLIENT_SECRET", "KIWIFY_ACCOUNT_ID"))
    if not (cid and sec and conta):
        return {"status": "falta_chave"}
    base = "https://public-api.kiwify.com/v1"
    tok = http(base + "/oauth/token", "POST", {"client_id": cid, "client_secret": sec}, form=True)["access_token"]
    cab = {"Authorization": "Bearer " + tok, "x-kiwify-account-id": conta}
    fim, ini = hoje(), hoje() - datetime.timedelta(days=DIAS - 1)
    vendas, pag = [], 1
    while True:
        q = {"start_date": ini.isoformat(), "end_date": (fim + datetime.timedelta(days=1)).isoformat(),
             "page_size": 100, "page_number": pag, "view_full_sale_details": "true"}
        r = http(base + "/sales?" + urllib.parse.urlencode(q), cab=cab)
        lote = r.get("data") or []
        vendas += lote
        total = (r.get("pagination") or {}).get("count") or 0
        if not lote or len(vendas) >= total or pag > 50:
            break
        pag += 1
    dias, por_origem, por_campanha, por_meio, produtos = {}, {}, {}, {}, {}
    for v in vendas:
        st = v.get("status", "")
        try:
            d = datetime.datetime.fromisoformat(v["created_at"].replace("Z", "+00:00")).astimezone(FUSO).date().isoformat()
        except Exception:
            continue
        pg = v.get("payment") or {}
        bruto = n(pg.get("charge_amount")) / 100
        liq = n(pg.get("net_amount") or v.get("net_amount")) / 100
        tr = v.get("tracking") or {}
        o = origem(tr.get("utm_source") or tr.get("src"))
        dia = dias.setdefault(d, {"data": d, "vendas": 0, "bruto": 0.0, "liquido": 0.0, "ig_vendas": 0, "ig_liquido": 0.0,
                                  "pendentes": 0, "devolvidas": 0, "recusadas": 0})
        if st in PAGAS:
            dia["vendas"] += 1
            dia["bruto"] += bruto
            dia["liquido"] += liq
            if o == "instagram":
                dia["ig_vendas"] += 1
                dia["ig_liquido"] += liq
            for chave, valor, alvo in (("o", o, por_origem), ("c", tr.get("utm_campaign") or "-", por_campanha),
                                       ("m", tr.get("utm_medium") or "-", por_meio), ("p", (v.get("product") or {}).get("name") or "-", produtos)):
                a = alvo.setdefault(d, {}).setdefault(valor, [0, 0.0])
                a[0] += 1
                a[1] += liq
        elif st in DEVOLVIDAS:
            dia["devolvidas"] += 1
        elif st in ("refused",):
            dia["recusadas"] += 1
        else:
            dia["pendentes"] += 1
    for d in dias.values():
        for k in ("bruto", "liquido", "ig_liquido"):
            d[k] = round(d[k], 2)
    arred = lambda m: {d: {k: [a[0], round(a[1], 2)] for k, a in x.items()} for d, x in m.items()}
    return {"status": "ok", "vendas_lidas": len(vendas), "dias": sorted(dias.values(), key=lambda x: x["data"], reverse=True),
            "por_origem": arred(por_origem), "por_campanha": arred(por_campanha), "por_meio": arred(por_meio), "produtos": arred(produtos)}


# ---------------------------------------------------------------- VTurb
def vturb():
    tok = os.environ.get("VTURB_TOKEN", "").strip()
    if not tok:
        return {"status": "falta_chave"}
    base = "https://analytics.vturb.net"
    cab = {"X-Api-Token": tok, "X-Api-Version": "v1"}
    post = lambda p, corpo: http(base + p, "POST", corpo, cab)
    fim, ini = hoje(), hoje() - datetime.timedelta(days=DIAS - 1)
    fim_s = fim.isoformat() + " 23:59:59"
    players = {p["id"]: p for p in http(base + "/players/list", cab=cab)}
    ids = [x.strip() for x in os.environ.get("VTURB_PLAYER_ID", "").split(",") if x.strip()]
    if not ids:
        # sem player escolhido: os 5 com mais plays nos últimos 30 dias
        r = post("/events/total_by_company_players", {"events": ["started"], "start_date": (fim - datetime.timedelta(days=29)).isoformat(), "end_date": fim_s})
        ids = [x["player_id"] for x in sorted(r, key=lambda x: -n(x.get("total"))) if n(x.get("total")) > 0][:5]
    dias, origens, janelas, curva = {}, {}, {}, None
    for pid in ids:
        dur = int(n((players.get(pid) or {}).get("duration"))) or 600
        base_q = {"player_id": pid, "start_date": ini.isoformat(), "end_date": fim_s, "timezone": TZ, "video_duration": dur}
        pdias = {}
        for s in post("/sessions/stats_by_day", base_q):
            d = str(s.get("date_key"))[:10]
            pdias[d] = int(n(s.get("total_started_session_uniq")))
            a = dias.setdefault(d, {"data": d, "plays": 0, "views": 0, "finalizados": 0, "cliques": 0, "acima_pitch": 0, "conversoes": 0})
            a["plays"] += int(n(s.get("total_started_session_uniq")))
            a["views"] += int(n(s.get("total_viewed_session_uniq")))
            a["finalizados"] += int(n(s.get("total_finished_session_uniq")))
            a["cliques"] += int(n(s.get("total_clicked_session_uniq")))
            a["acima_pitch"] += int(n(s.get("total_over_pitch")))
            a["conversoes"] += int(n(s.get("total_conversions")))
        try:
            for s in post("/traffic_origin/stats_by_day", {**base_q, "query_keys": ["utm_source"]}):
                d, o = str(s.get("date_key"))[:10], origem(s.get("grouped_field"))
                a = origens.setdefault(d, {}).setdefault(o, [0, 0, 0])
                a[0] += int(n(s.get("total_started_session_uniq")))
                a[1] += int(n(s.get("total_clicked_session_uniq")))
                a[2] += int(n(s.get("total_conversions")))
        except RuntimeError as e:
            print("vturb origem:", e)
        for j in JANELAS:
            q = {"player_id": pid, "video_duration": dur, "timezone": TZ, "start_date": (fim - datetime.timedelta(days=j - 1)).isoformat(), "end_date": fim_s}
            e = post("/times/user_engagement", q)
            w = janelas.setdefault(str(j), {"seg_x_plays": 0.0, "plays": 0, "ret_x_plays": 0.0})
            pl = sum(v for d, v in pdias.items() if d >= q["start_date"][:10])
            w["seg_x_plays"] += n(e.get("average_watched_time")) * pl
            w["ret_x_plays"] += n(e.get("engagement_rate")) * pl
            w["plays"] += pl
            if j == 30 and curva is None and e.get("grouped_timed"):
                g = sorted(e["grouped_timed"], key=lambda x: n(x.get("timed")))
                topo = max(n(x.get("total_users")) for x in g) or 1
                passo = max(1, len(g) // 40)
                curva = {"player": (players.get(pid) or {}).get("name", pid), "duracao": dur,
                         "pontos": [[int(n(x["timed"])), round(n(x["total_users"]) / topo * 100, 1)] for x in g[::passo]]}
    jan = {}
    for j, w in janelas.items():
        pl = w["plays"] or 0
        jan[j] = {"tempo_medio_s": round(w["seg_x_plays"] / pl) if pl else 0, "retencao": round(w["ret_x_plays"] / pl, 1) if pl else 0,
                  "minutos": round(w["seg_x_plays"] / 60)}
    return {"status": "ok", "players": [{"id": p, "nome": (players.get(p) or {}).get("name", "")} for p in ids],
            "dias": sorted(dias.values(), key=lambda x: x["data"], reverse=True), "por_origem": origens, "janelas": jan, "curva": curva}


if __name__ == "__main__":
    out = {"atualizado": datetime.datetime.now(FUSO).isoformat(timespec="minutes")}
    for nome, f in (("vturb", vturb), ("kiwify", kiwify)):
        try:
            out[nome] = f()
        except Exception as e:  # um lado falhar não apaga o outro
            out[nome] = {"status": "erro", "erro": str(e)[:200]}
        print(nome, out[nome].get("status"), out[nome].get("erro", ""))
    os.makedirs(PASTA, exist_ok=True)
    with open(os.path.join(PASTA, "funil.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
