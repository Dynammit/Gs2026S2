# DroneVision — Global Solution (Cloud Computing & MaaS)

Aplicação Web hospedada no **Azure App Service**, integrada ao **Azure AI Vision**, para analisar fotografias capturadas por um drone: o operador envia a imagem e recebe **descrição**, **etiquetas (tags)** e **objetos identificados**.

- Aluno: Kayky Ferreira — RM94630
- Disciplina: Cloud Computing & Machine as a Service (MaaS) — Prof. João Menk

## Estrutura do repositório

```
implantar-rm94630.sh   # cria a infraestrutura e faz o deploy (Azure CLI)
app/
  app.py               # aplicação Web (Flask)
  requirements.txt
README.md
```

## Recursos criados (padrão de nomenclatura do enunciado)

| Recurso            | Nome                     |
|--------------------|--------------------------|
| Resource Group     | `rg-dronevision-rm94630`   |
| Azure AI Vision    | `aiv-dronevision-rm94630`  |
| App Service Plan   | `plan-dronevision-rm94630` |
| Web App            | `app-dronevision-rm94630`  |

URL final: `https://app-dronevision-rm94630.azurewebsites.net`

## Como executar (Azure Cloud Shell — modo **Bash**)

1. Abra o Cloud Shell em https://shell.azure.com e confirme que está em **Bash** (canto superior esquerdo).
2. Clone o repositório e entre na pasta:
   ```bash
   git clone <URL_DO_SEU_REPOSITORIO>
   cd <PASTA_DO_REPOSITORIO>
   ```
3. Execute o script:
   ```bash
   chmod +x implantar-rm94630.sh
   ./implantar-rm94630.sh
   ```
4. Ao final, o script imprime a URL da aplicação. Abra no navegador, envie uma imagem de drone e veja o resultado.

Se a região padrão (`brazilsouth`) estiver bloqueada na sua assinatura, rode com outra: `LOCATION=eastus2 ./implantar-rm94630.sh`.

> A chave do Azure AI Vision **não está no código**: o script a lê via `az cognitiveservices account keys list` e a grava como *App Setting* do Web App. Nunca coloque chaves no GitHub.

## O que o script faz

1. Registra os provedores `Microsoft.CognitiveServices` e `Microsoft.Web`.
2. `az group create` — Resource Group.
3. `az cognitiveservices account create --kind ComputerVision` — Azure AI Vision (tenta o SKU gratuito F0; se já existir um F0 na assinatura, usa S1).
4. `az appservice plan create` — plano Linux (B1).
5. `az webapp create` — Web App com runtime Python 3.11.
6. `az webapp config appsettings set` — grava `VISION_ENDPOINT` e `VISION_KEY`; `az webapp config set` define o comando de inicialização (gunicorn).
7. `az webapp deploy --type zip` — publica o código da pasta `app/`.
8. Testa `/health` e lista os recursos criados.

## Como a aplicação se integra com a Visão Computacional

O operador acessa a página **DroneVision** pelo navegador (HTTPS) e seleciona uma fotografia. O Web App, hospedado no Azure App Service, valida o arquivo (formato JPG/PNG/GIF/BMP e limite de 4 MB) e envia os bytes da imagem por uma requisição HTTPS `POST` à API **Analyze Image (v3.2)** do Azure AI Vision, no endpoint do recurso `aiv-dronevision-rm94630`, pedindo as características `Description`, `Tags` e `Objects`. A autenticação é feita pelo cabeçalho `Ocp-Apim-Subscription-Key`, com a chave obtida pelo script de implantação e guardada em variáveis de ambiente do App Service (`VISION_ENDPOINT` e `VISION_KEY`), nunca no código. O serviço devolve um JSON com a legenda da imagem, as etiquetas e os objetos com suas posições e níveis de confiança; a aplicação transforma esse JSON em uma página com a descrição textual, as tags e os objetos identificados destacados sobre a foto. Se a imagem for inválida, a chave estiver incorreta, o limite de requisições for atingido ou o serviço estiver indisponível, a aplicação interpreta o código HTTP retornado e mostra uma mensagem apropriada ao operador.

## Evidências para a entrega (prints)

- [ ] **Cloud Shell:** execução do `./implantar-rm94630.sh` (início, etapas e a mensagem final com a URL).
- [ ] **Portal da Azure:** o Resource Group `rg-dronevision-rm94630` listando os 4 recursos, mais um print de cada recurso (AI Vision, App Service Plan e Web App).
- [ ] **Aplicação publicada:** a URL `azurewebsites.net` visível na barra do navegador, com uma imagem analisada e o resultado (descrição, tags e objetos).
- [ ] **Segunda imagem** com o tema da GS (o enunciado exige no mínimo duas).
- [ ] (Opcional) print de uma mensagem de erro, por exemplo enviando um `.txt`.

Sugestões de imagens (tema monitoramento aéreo): foto aérea de uma cidade, de uma plantação, de uma floresta ou de um rio, vista de drone. Use fotos de bancos gratuitos como Pexels ou Unsplash, em JPG ou PNG de até 4 MB.

## Limpeza (depois de entregar)

```bash
az group delete --name rg-dronevision-rm94630 --yes --no-wait
```
Isso apaga todos os recursos e interrompe qualquer custo.
