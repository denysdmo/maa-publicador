"""Aprovação pelo app (12/11/2026). Roda no GitHub Actions quando o DONO do repositório abre um issue de aprovação
(botão "Aprovar" / "Vetar" da agenda). O corpo do issue traz uma linha por post:
    aprovar: midia/2026-11-13/1-sexta-manha-1-quiz.jpg
    vetar: midia/2026-11-13/2-sabado-manha-2-quiz.jpg
    cancelar: midia/2026-11-16/3-quarta-manha-1-quiz.jpg
O post é achado pelo primeiro arquivo da linha em fila.csv.
  aprovar  → só "rascunho" vira "pendente" (agendado; o publicador posta no horário)
  vetar    → só "rascunho" vira "cancelado"
  cancelar → só "pendente" volta a "rascunho" (botão "Cancelar agendamento", 14/11/2026); a outra versão que tinha
             sido cancelada por causa dessa aprovação também volta a "rascunho"
Versões: se dois rascunhos têm o mesmo horário e o mesmo tipo (ex.: v1 e v2 de um story), aprovar um cancela o outro.
Imprime o resumo (vai para o comentário do issue)."""
import csv, os, re, sys

AQUI = os.path.dirname(os.path.abspath(__file__))
FILA = os.path.join(AQUI, "fila.csv")
CAMPOS = ["quando", "tipo", "arquivos", "legenda", "status", "resultado"]

corpo = sys.stdin.read()
pedidos = [(m.group(1).lower(), m.group(2).strip()) for m in re.finditer(r"^\s*(aprovar|vetar|cancelar)\s*:\s*(\S+)\s*$", corpo, re.M | re.I)]
with open(FILA, encoding="utf-8-sig", newline="") as f:
    linhas = list(csv.DictReader(f))
primeiro = lambda l: l["arquivos"].split("|")[0].strip()
nome = lambda l: f"{l['tipo']} {l['quando'][8:10]}/{l['quando'][5:7]} {l['quando'][11:16]} ({os.path.basename(primeiro(l))})"
saida = []
for acao, arq in pedidos:
    l = next((x for x in linhas if primeiro(x) == arq), None)
    if not l:
        saida.append(f"- ⚠️ não achei `{arq}` na fila")
        continue
    if acao == "cancelar":
        if l["status"] != "pendente":
            saida.append(f"- {nome(l)}: estava **{l['status']}** (não agendado), não mudei")
            continue
        l["status"], l["resultado"] = "rascunho", ""
        saida.append(f"- ↩️ {nome(l)}: agendamento cancelado, voltou para aprovação")
        for o in linhas:
            if o is not l and o["status"] == "cancelado" and o["resultado"] == "outra versão foi aprovada" and o["quando"] == l["quando"] and o["tipo"] == l["tipo"]:
                o["status"], o["resultado"] = "rascunho", ""
                saida.append(f"  - a outra versão ({os.path.basename(primeiro(o))}) também voltou para aprovação")
        continue
    if l["status"] != "rascunho":
        saida.append(f"- {nome(l)}: já estava **{l['status']}**, não mudei")
        continue
    if acao == "vetar":
        l["status"], l["resultado"] = "cancelado", "vetado no app"
        saida.append(f"- ❌ {nome(l)}: vetado")
        continue
    l["status"] = "pendente"
    saida.append(f"- ✅ {nome(l)}: aprovado e agendado")
    for o in linhas:
        if o is not l and o["status"] == "rascunho" and o["quando"] == l["quando"] and o["tipo"] == l["tipo"]:
            o["status"], o["resultado"] = "cancelado", "outra versão foi aprovada"
            saida.append(f"  - a outra versão ({os.path.basename(primeiro(o))}) foi cancelada")
with open(FILA, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=CAMPOS)
    w.writeheader()
    w.writerows({k: l.get(k, "") for k in CAMPOS} for l in linhas)
print("\n".join(saida) if saida else "Nenhum pedido de aprovação encontrado no texto.")
