"""Publicador da fila (12/11/2026). Roda a cada 10 min pelo Agendador de Tarefas do Windows (tarefa "MAA Publicador").
Lê automacao/fila.csv e publica pela API (instagram.py) tudo o que já passou do horário e está "pendente".

Colunas de fila.csv:
  quando            2026-11-16T08:00   (horário de Brasília)
  tipo              story | post | carrossel | reel
  arquivos          caminhos separados por " | " (relativos à pasta Edições - Claude ou absolutos)
  legenda           caminho de um .txt (post, carrossel, reel), ou vazio
  status            pendente | publicado | erro | atrasado | cancelado   (o publicador atualiza)
  resultado         link ou mensagem de erro
Para VETAR um post: troque o status para "cancelado" (ou apague a linha).
Post mais de 3 h atrasado (PC desligado) vira "atrasado" e NÃO sai, para não postar fora de hora.
"""
import csv, datetime, os, subprocess, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
NUVEM = bool(os.environ.get("GITHUB_ACTIONS"))
RAIZ = AQUI if NUVEM else os.path.dirname(AQUI)  # na nuvem os caminhos são relativos ao repositório (midia/...)
FILA = os.path.join(AQUI, "fila.csv")
TRAVA = os.path.join(AQUI, ".publicador.lock")
CAMPOS = ["quando", "tipo", "arquivos", "legenda", "status", "resultado"]
ATRASO_MAX = datetime.timedelta(hours=3)


def caminho(p):
    p = p.strip()
    return p if os.path.isabs(p) else os.path.join(RAIZ, p)


def avisa(falhas):
    if NUVEM:  # na nuvem o aviso é o e-mail de falha do GitHub + o status na fila
        print("FALHAS:", [(l["quando"], l["status"], l["resultado"]) for l in falhas])
        return
    """Balão de notificação do Windows quando um post falha ou atrasa (funciona com o Claude fechado)."""
    texto = "; ".join(f"{l['tipo']} {l['quando'][5:16].replace('T', ' ')}: {l['status']}" for l in falhas)[:220].replace("'", "")
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms; $n = New-Object System.Windows.Forms.NotifyIcon; "
        "$n.Icon = [System.Drawing.SystemIcons]::Warning; $n.Visible = $true; "
        f"$n.ShowBalloonTip(15000, 'Instagram: post nao saiu', '{texto} (veja automacao/fila.csv)', 'Warning'); Start-Sleep 16; $n.Dispose()"
    )
    subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps], creationflags=0x08000000)


def main():
    if not os.path.exists(FILA):
        return
    # trava simples contra execução dupla (expira em 30 min)
    if os.path.exists(TRAVA) and (datetime.datetime.now().timestamp() - os.path.getmtime(TRAVA)) < 1800:
        return
    open(TRAVA, "w").close()
    try:
        with open(FILA, encoding="utf-8-sig", newline="") as f:
            linhas = list(csv.DictReader(f))
        agora = datetime.datetime.now()
        mudou = False
        for l in sorted(linhas, key=lambda x: x["quando"]):
            if l.get("status", "pendente").strip() not in ("", "pendente"):
                continue
            quando = datetime.datetime.fromisoformat(l["quando"].strip())
            if quando > agora:
                continue
            mudou = True
            l["_avisar"] = True
            if agora - quando > ATRASO_MAX:
                l["status"], l["resultado"] = "atrasado", f"não publicado: PC desligado no horário ({agora:%d/%m %H:%M})"
                continue
            cmd = [sys.executable, "-I", os.path.join(AQUI, "instagram.py"), l["tipo"].strip()]
            cmd += [caminho(a) for a in l["arquivos"].split("|") if a.strip()]
            if l.get("legenda", "").strip():
                cmd += ["--legenda", caminho(l["legenda"])]
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1500)
            saida = (r.stdout + r.stderr).strip().splitlines()
            ultima = saida[-1] if saida else ""
            if r.returncode == 0:
                l["status"], l["resultado"] = "publicado", ultima.replace("publicado:", "").strip()
            else:
                l["status"], l["resultado"] = "erro", ultima[:300]
        falhas = [l for l in linhas if l.get("status") in ("erro", "atrasado") and l.get("_avisar")]
        if falhas:
            avisa(falhas)
        if mudou:
            with open(FILA, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.DictWriter(f, fieldnames=CAMPOS, extrasaction="ignore")
                w.writeheader()
                for l in linhas:
                    w.writerow({k: l.get(k, "") for k in CAMPOS})
    finally:
        os.remove(TRAVA)


if __name__ == "__main__":
    main()
