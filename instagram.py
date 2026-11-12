"""Publica no Instagram (@meuarraisamador) pela API oficial (Graph API, token de usuário do sistema).

Uso:
  python -I instagram.py story  <imagem>                      [--teste]
  python -I instagram.py post   <imagem> --legenda arquivo.txt [--teste]
  python -I instagram.py carrossel <img1> <img2> ... --legenda arquivo.txt [--teste]
  python -I instagram.py reel   <video.mp4> --legenda arquivo.txt [--capa capa.jpg] [--teste]

--teste: sobe o arquivo e cria o container, mas NÃO publica.
Token em C:\\Users\\nekig\\.config\\maa\\instagram.env (IG_TOKEN, IG_USER_ID). Nunca imprime o token.
Hospedagem: link temporário do Litterbox (24 h). A API exige URL pública e imagem em JPEG.
Log: automacao/instagram-log.csv
"""
import argparse, csv, datetime, json, mimetypes, os, sys, tempfile, time, urllib.error, urllib.parse, urllib.request, uuid

API = "https://graph.facebook.com/v21.0"
ENV = r"C:\Users\nekig\.config\maa\instagram.env"
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "instagram-log.csv")


def env():
    if os.environ.get("IG_TOKEN"):  # nuvem (GitHub Actions): token vem dos Secrets
        return os.environ["IG_TOKEN"], os.environ["IG_USER_ID"]
    d = {}
    for l in open(ENV, encoding="utf-8-sig"):
        l = l.strip()
        if "=" in l and not l.startswith("#"):
            k, v = l.split("=", 1)
            d[k.strip()] = v.strip()
    if not d.get("IG_TOKEN"):
        sys.exit("IG_TOKEN vazio em " + ENV)
    return d["IG_TOKEN"], d["IG_USER_ID"]


TOKEN, UID = env()


def api(metodo, caminho, **params):
    params["access_token"] = TOKEN
    dados = urllib.parse.urlencode(params).encode()
    url = f"{API}/{caminho}"
    req = urllib.request.Request(url + ("?" + dados.decode() if metodo == "GET" else ""), data=None if metodo == "GET" else dados, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        corpo = json.load(e)
        raise RuntimeError(f"API {caminho}: {corpo.get('error', corpo).get('message', corpo)}") from None


def jpeg(caminho):
    """PNG -> JPEG (a API só aceita JPEG em imagem)."""
    if caminho.lower().endswith((".jpg", ".jpeg", ".mp4", ".mov")):
        return caminho
    saida = os.path.join(tempfile.gettempdir(), uuid.uuid4().hex + ".jpg")
    os.system(f'ffmpeg -loglevel error -y -i "{caminho}" -q:v 2 "{saida}"')
    if not os.path.exists(saida):
        raise RuntimeError("falha ao converter para JPEG: " + caminho)
    return saida


REPO_RAW = "https://raw.githubusercontent.com/denysdmo/maa-publicador/main/"


def sobe(caminho, tentativas=3):
    """Devolve uma URL pública do arquivo.
    Na nuvem (GitHub Actions): o arquivo já está no repositório PÚBLICO, em JPEG/MP4 -> link raw do GitHub.
    No PC: envia para o Litterbox (expira em 24 h)."""
    if os.environ.get("GITHUB_ACTIONS"):
        rel = os.path.relpath(os.path.abspath(caminho), os.getcwd()).replace(os.sep, "/")
        if not rel.lower().endswith((".jpg", ".jpeg", ".mp4", ".mov")):
            raise RuntimeError("na nuvem a mídia precisa estar em JPEG ou MP4: " + rel)
        return REPO_RAW + urllib.parse.quote(rel)
    caminho = jpeg(caminho)
    nome = os.path.basename(caminho)
    tipo = mimetypes.guess_type(nome)[0] or "application/octet-stream"
    for t in range(tentativas):
        try:
            b = uuid.uuid4().hex
            corpo = (
                f'--{b}\r\nContent-Disposition: form-data; name="reqtype"\r\n\r\nfileupload\r\n'
                f'--{b}\r\nContent-Disposition: form-data; name="time"\r\n\r\n24h\r\n'
                f'--{b}\r\nContent-Disposition: form-data; name="fileToUpload"; filename="{nome}"\r\nContent-Type: {tipo}\r\n\r\n'
            ).encode() + open(caminho, "rb").read() + f"\r\n--{b}--\r\n".encode()
            req = urllib.request.Request(
                "https://litterbox.catbox.moe/resources/internals/api.php",
                data=corpo,
                headers={"Content-Type": f"multipart/form-data; boundary={b}", "User-Agent": "maa-postagem/1.0"},
            )
            with urllib.request.urlopen(req, timeout=180) as r:
                url = r.read().decode().strip()
            if url.startswith("https://"):
                return url
            raise RuntimeError("resposta inesperada do Litterbox: " + url[:200])
        except Exception as e:  # noqa: BLE001
            if t == tentativas - 1:
                raise
            print(f"  upload falhou ({e}); tentando de novo em 20 s")
            time.sleep(20)


def espera(cid, limite=300):
    """Espera o container ficar FINISHED (vídeo demora)."""
    ini = time.time()
    while True:
        st = api("GET", cid, fields="status_code,status")
        if st.get("status_code") == "FINISHED":
            return
        if st.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"container {st}")
        if time.time() - ini > limite:
            raise RuntimeError("container não ficou pronto a tempo")
        time.sleep(5)


def reel_direto(arquivo, legenda, extra):
    """Plano B para vídeo: upload direto para a Meta (protocolo resumable), sem precisar de link público."""
    r = api("POST", f"{UID}/media", media_type="REELS", upload_type="resumable", caption=legenda, share_to_feed="true", **extra)
    cid = r["id"]
    uri = r.get("uri") or f"https://rupload.facebook.com/ig-api-upload/v21.0/{cid}"
    dados = open(arquivo, "rb").read()
    req = urllib.request.Request(uri, data=dados, method="POST", headers={"Authorization": f"OAuth {TOKEN}", "offset": "0", "file_size": str(len(dados))})
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            print("  upload direto:", resp.read().decode()[:200])
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"upload direto: HTTP {e.code} {e.read().decode()[:300]}") from None
    espera(cid, 900)
    return cid


def publica(cid, teste):
    espera(cid, 900)
    if teste:
        print("  TESTE: container pronto, NÃO publicado:", cid)
        return None
    for t in range(3):
        try:
            r = api("POST", f"{UID}/media_publish", creation_id=cid)
            mid = r["id"]
            link = api("GET", mid, fields="permalink").get("permalink", "")
            print("  publicado:", link or mid)
            return link or mid
        except RuntimeError as e:
            if t == 2:
                raise
            print(f"  publicação falhou ({e}); tentando de novo em 30 s")
            time.sleep(30)


def registra(tipo, arquivos, resultado, teste):
    novo = not os.path.exists(LOG)
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if novo:
            w.writerow(["quando", "tipo", "arquivos", "resultado", "teste"])
        w.writerow([datetime.datetime.now().isoformat(timespec="seconds"), tipo, " | ".join(arquivos), resultado, teste])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("tipo", choices=["story", "post", "carrossel", "reel"])
    p.add_argument("arquivos", nargs="+")
    p.add_argument("--legenda")
    p.add_argument("--capa")
    p.add_argument("--teste", action="store_true")
    a = p.parse_args()
    legenda = open(a.legenda, encoding="utf-8").read().strip() if a.legenda else ""
    try:
        if a.tipo == "story":
            url = sobe(a.arquivos[0])
            video = url.lower().endswith((".mp4", ".mov"))
            cid = api("POST", f"{UID}/media", media_type="STORIES", **({"video_url": url} if video else {"image_url": url}))["id"]
        elif a.tipo == "post":
            cid = api("POST", f"{UID}/media", image_url=sobe(a.arquivos[0]), caption=legenda)["id"]
        elif a.tipo == "carrossel":
            if not 2 <= len(a.arquivos) <= 10:
                sys.exit("carrossel: de 2 a 10 imagens")
            filhos = []
            for arq in a.arquivos:
                c = api("POST", f"{UID}/media", image_url=sobe(arq), is_carousel_item="true")["id"]
                espera(c)
                filhos.append(c)
            cid = api("POST", f"{UID}/media", media_type="CAROUSEL", children=",".join(filhos), caption=legenda)["id"]
        else:
            extra = {"cover_url": sobe(a.capa)} if a.capa else {}
            cid = None
            if os.environ.get("IG_VIDEO", "url") == "url":
                try:
                    cid = api("POST", f"{UID}/media", media_type="REELS", video_url=sobe(a.arquivos[0]), caption=legenda, share_to_feed="true", **extra)["id"]
                    espera(cid, 900)
                except RuntimeError as e:
                    print(f"  vídeo por link falhou ({e}); tentando o upload direto")
                    cid = None
            if cid is None:
                cid = reel_direto(a.arquivos[0], legenda, extra)
        res = publica(cid, a.teste)
        registra(a.tipo, a.arquivos, res or f"container {cid}", a.teste)
    except Exception as e:  # noqa: BLE001
        registra(a.tipo, a.arquivos, f"ERRO: {e}", a.teste)
        print("ERRO:", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
