"""
DroneVision - Aplicação Web (Azure App Service) integrada ao Azure AI Vision.

O operador envia uma fotografia capturada pelo drone; a aplicação chama a API
Analyze Image (v3.2) do Azure AI Vision e exibe descrição, etiquetas (tags) e
objetos identificados.

Configuração (App Settings do Azure, definidas pelo script de implantação):
    VISION_ENDPOINT  -> https://<nome>.cognitiveservices.azure.com
    VISION_KEY       -> chave do recurso Azure AI Vision
"""
import base64
import os

import requests
from flask import Flask, render_template_string, request

app = Flask(__name__)

LIMITE_BYTES = 4 * 1024 * 1024  # limite da API Analyze Image v3.2
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # corta uploads absurdos
TIPOS_ACEITOS = {"image/jpeg", "image/png", "image/gif", "image/bmp"}
IDIOMAS = {"pt": "Português", "en": "English", "es": "Español"}


class ErroDeAnalise(Exception):
    """Erro com mensagem já pronta para ser exibida ao operador."""


def analisar_imagem(dados: bytes, idioma: str) -> dict:
    endpoint = os.getenv("VISION_ENDPOINT", "").rstrip("/")
    chave = os.getenv("VISION_KEY", "")
    if not endpoint or not chave:
        raise ErroDeAnalise(
            "O serviço de Visão Computacional não está configurado "
            "(VISION_ENDPOINT / VISION_KEY ausentes)."
        )

    url = f"{endpoint}/vision/v3.2/analyze"
    params = {"visualFeatures": "Description,Tags,Objects", "language": idioma}
    headers = {
        "Ocp-Apim-Subscription-Key": chave,
        "Content-Type": "application/octet-stream",
    }

    try:
        resp = requests.post(url, params=params, headers=headers, data=dados, timeout=30)
    except requests.Timeout:
        raise ErroDeAnalise(
            "O serviço de Visão Computacional demorou demais para responder. "
            "Tente novamente em instantes."
        )
    except requests.RequestException:
        raise ErroDeAnalise(
            "Serviço de Visão Computacional indisponível no momento. "
            "Tente novamente mais tarde."
        )

    if resp.status_code == 200:
        return resp.json()

    try:
        codigo = resp.json().get("error", {}).get("code", "")
    except ValueError:
        codigo = ""

    if resp.status_code == 400:
        if codigo == "InvalidImageSize":
            raise ErroDeAnalise(
                "Imagem inválida: dimensões fora do permitido "
                "(mínimo 50x50 e máximo 16000x16000 pixels)."
            )
        if codigo in ("InvalidImageFormat", "InvalidImageUrl"):
            raise ErroDeAnalise(
                "Imagem inválida: o arquivo não pôde ser lido como imagem. "
                "Envie JPG, PNG, GIF ou BMP."
            )
        raise ErroDeAnalise("Imagem inválida: o serviço não conseguiu processar o arquivo enviado.")
    if resp.status_code in (401, 403):
        raise ErroDeAnalise(
            "Falha de autenticação no serviço de Visão Computacional "
            "(chave ou endpoint inválidos)."
        )
    if resp.status_code == 429:
        raise ErroDeAnalise(
            "Limite de requisições do serviço atingido. Aguarde alguns segundos e tente novamente."
        )
    if resp.status_code >= 500:
        raise ErroDeAnalise(
            "Serviço de Visão Computacional indisponível no momento. "
            "Tente novamente mais tarde."
        )
    raise ErroDeAnalise(f"Falha na análise da imagem (HTTP {resp.status_code}).")


def montar_resultado(bruto: dict) -> dict:
    desc = bruto.get("description", {})
    legendas = desc.get("captions", [])
    meta = bruto.get("metadata", {})
    largura = meta.get("width") or 1
    altura = meta.get("height") or 1

    objetos = []
    for o in bruto.get("objects", []):
        r = o.get("rectangle", {})
        objetos.append(
            {
                "nome": o.get("object", "?"),
                "conf": round(o.get("confidence", 0) * 100),
                "esq": r.get("x", 0) / largura * 100,
                "topo": r.get("y", 0) / altura * 100,
                "larg": r.get("w", 0) / largura * 100,
                "alt": r.get("h", 0) / altura * 100,
            }
        )

    tags = [
        {"nome": t.get("name", "?"), "conf": round(t.get("confidence", 0) * 100)}
        for t in bruto.get("tags", [])
    ]
    return {
        "descricao": legendas[0]["text"] if legendas else None,
        "conf_descricao": round(legendas[0]["confidence"] * 100) if legendas else None,
        "tags": tags,
        "objetos": objetos,
    }


PAGINA = """
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DroneVision</title>
<style>
  :root { --bg:#0e1621; --card:#17212f; --borda:#2a3a50; --txt:#e8eef6; --mut:#8fa3bd; --azul:#2f8cff; --verde:#35d07f; --erro:#ff6b6b; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:"Segoe UI",Arial,sans-serif; background:var(--bg); color:var(--txt); }
  header { padding:26px 20px; text-align:center; border-bottom:1px solid var(--borda); background:linear-gradient(135deg,#0b2a52,#0e1621); }
  header h1 { margin:0; font-size:2rem; letter-spacing:.5px; }
  header p { margin:6px 0 0; color:var(--mut); }
  main { max-width:960px; margin:24px auto; padding:0 16px; display:grid; gap:18px; }
  .card { background:var(--card); border:1px solid var(--borda); border-radius:12px; padding:20px; }
  label { display:block; font-weight:600; margin:0 0 6px; }
  input[type=file], select { width:100%; padding:10px; border:1px solid var(--borda); border-radius:8px; background:#0e1621; color:var(--txt); font-size:1rem; }
  .linha { display:grid; grid-template-columns:2fr 1fr; gap:14px; }
  @media (max-width:640px) { .linha { grid-template-columns:1fr; } }
  button { margin-top:16px; width:100%; padding:13px; border:0; border-radius:10px; background:var(--azul); color:#fff; font-size:1.05rem; font-weight:600; cursor:pointer; }
  button:disabled { opacity:.6; cursor:wait; }
  .erro { border-color:var(--erro); color:var(--erro); }
  .resultado { display:grid; grid-template-columns:1.2fr 1fr; gap:20px; align-items:start; }
  @media (max-width:760px) { .resultado { grid-template-columns:1fr; } }
  .foto { position:relative; display:inline-block; width:100%; }
  .foto img { width:100%; display:block; border-radius:8px; }
  .caixa { position:absolute; border:2px solid var(--verde); border-radius:3px; }
  .caixa span { position:absolute; top:-1px; left:-1px; background:var(--verde); color:#04210f; font-size:.72rem; font-weight:700; padding:1px 5px; }
  h2 { margin:18px 0 6px; font-size:1.05rem; color:var(--mut); text-transform:uppercase; letter-spacing:.8px; }
  h2:first-child { margin-top:0; }
  .descricao { font-size:1.4rem; font-weight:600; margin:0 0 4px; }
  .conf { color:var(--mut); margin:0 0 16px; }
  .chips span { display:inline-block; background:#1d2c42; border:1px solid var(--borda); padding:4px 10px; border-radius:20px; margin:0 6px 6px 0; font-size:.9rem; }
  .chips em { color:var(--mut); font-style:normal; font-size:.8rem; }
  footer { text-align:center; color:var(--mut); font-size:.85rem; padding:6px 0 28px; }
</style>
</head>
<body>
<header>
  <h1>DroneVision</h1>
  <p>Análise de imagens de drone com Azure AI Vision</p>
</header>
<main>
  <form class="card" method="post" enctype="multipart/form-data" id="form">
    <div class="linha">
      <div>
        <label for="arquivo">Fotografia capturada pelo drone</label>
        <input type="file" id="arquivo" name="arquivo" accept="image/jpeg,image/png,image/gif,image/bmp">
      </div>
      <div>
        <label for="idioma">Idioma do resultado</label>
        <select id="idioma" name="idioma">
          {% for cod, nome in idiomas.items() %}
          <option value="{{ cod }}" {{ 'selected' if cod == idioma else '' }}>{{ nome }}</option>
          {% endfor %}
        </select>
      </div>
    </div>
    <button type="submit" id="botao">Analisar imagem</button>
  </form>

  {% if erro %}
  <div class="card erro"><strong>Não foi possível analisar a imagem.</strong><br>{{ erro }}</div>
  {% endif %}

  {% if resultado %}
  <section class="card resultado">
    <div class="foto">
      <img src="{{ preview }}" alt="Imagem analisada">
      {% for o in resultado.objetos %}
      <div class="caixa" style="left:{{ o.esq }}%;top:{{ o.topo }}%;width:{{ o.larg }}%;height:{{ o.alt }}%;"><span>{{ o.nome }}</span></div>
      {% endfor %}
    </div>
    <div>
      <h2>Descrição</h2>
      {% if resultado.descricao %}
        <p class="descricao">{{ resultado.descricao }}</p>
        <p class="conf">Confiança: {{ resultado.conf_descricao }}%</p>
      {% else %}
        <p class="conf">Nenhuma descrição foi retornada para esta imagem.</p>
      {% endif %}

      <h2>Etiquetas (tags)</h2>
      <div class="chips">
        {% for t in resultado.tags[:15] %}<span>{{ t.nome }} <em>{{ t.conf }}%</em></span>{% else %}<p class="conf">Nenhuma etiqueta identificada.</p>{% endfor %}
      </div>

      <h2>Objetos identificados</h2>
      <div class="chips">
        {% for o in resultado.objetos %}<span>{{ o.nome }} <em>{{ o.conf }}%</em></span>{% else %}<p class="conf">Nenhum objeto identificado.</p>{% endfor %}
      </div>
    </div>
  </section>
  {% endif %}
</main>
<footer>DroneVision &middot; Global Solution &middot; Cloud Computing &amp; MaaS</footer>
<script>
  document.getElementById("form").addEventListener("submit", function () {
    var b = document.getElementById("botao");
    b.disabled = true; b.textContent = "Analisando...";
  });
</script>
</body>
</html>
"""


def renderizar(**extra):
    contexto = dict(erro=None, resultado=None, preview=None, idioma="pt", idiomas=IDIOMAS)
    contexto.update(extra)
    return render_template_string(PAGINA, **contexto)


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        return renderizar()

    idioma = request.form.get("idioma", "pt")
    if idioma not in IDIOMAS:
        idioma = "pt"

    arquivo = request.files.get("arquivo")
    if not arquivo or not arquivo.filename:
        return renderizar(idioma=idioma, erro="Nenhuma imagem foi selecionada. Escolha uma fotografia para analisar.")

    if (arquivo.mimetype or "").lower() not in TIPOS_ACEITOS:
        return renderizar(
            idioma=idioma,
            erro="Formato de arquivo não suportado. Envie uma imagem JPG, PNG, GIF ou BMP.",
        )

    dados = arquivo.read()
    if not dados:
        return renderizar(idioma=idioma, erro="O arquivo enviado está vazio.")
    if len(dados) > LIMITE_BYTES:
        return renderizar(
            idioma=idioma,
            erro="Imagem inválida: o arquivo excede 4 MB, limite do serviço de Visão Computacional.",
        )

    try:
        resultado = montar_resultado(analisar_imagem(dados, idioma))
    except ErroDeAnalise as e:
        return renderizar(idioma=idioma, erro=str(e))

    preview = f"data:{arquivo.mimetype};base64," + base64.b64encode(dados).decode()
    return renderizar(idioma=idioma, resultado=resultado, preview=preview)


@app.errorhandler(413)
def arquivo_grande(_):
    return renderizar(erro="Imagem inválida: o arquivo é grande demais (máximo de 4 MB)."), 413


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
