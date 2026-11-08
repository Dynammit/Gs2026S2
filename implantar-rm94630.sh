#!/usr/bin/env bash
# =============================================================================
# implantar-rm94630.sh
# Global Solution - Cloud Computing & MaaS (FIAP) - Projeto DroneVision
#
# Cria TODA a infraestrutura via Azure CLI e publica a aplicação Web:
#   Resource Group  ->  Azure AI Vision  ->  App Service Plan  ->  Web App
#
# Executar no Azure Cloud Shell, modo BASH, dentro da pasta do repositório:
#   chmod +x implantar-rm94630.sh
#   ./implantar-rm94630.sh
#
# Opcional: trocar a região   ->  LOCATION=eastus2 ./implantar-rm94630.sh
# =============================================================================
set -euo pipefail

# ------------------------------- Parâmetros ----------------------------------
RM="94630"
PROJETO="dronevision"
LOCATION="${LOCATION:-centralus}"
SKU_PLANO="${SKU_PLANO:-B1}"
RUNTIME="${RUNTIME:-PYTHON:3.11}"

# Padrão de nomenclatura do enunciado
RG="rg-${PROJETO}-rm${RM}"
AIV="aiv-${PROJETO}-rm${RM}"
PLANO="plan-${PROJETO}-rm${RM}"
APP="app-${PROJETO}-rm${RM}"

PASTA_APP="app"
ZIP="app.zip"

passo() { echo; echo "==> $1"; }

# ------------------------------- Pré-checagens -------------------------------
if [ ! -d "$PASTA_APP" ] || [ ! -f "$PASTA_APP/app.py" ]; then
  echo "ERRO: pasta '$PASTA_APP/' com app.py não encontrada. Rode o script na raiz do repositório."
  exit 1
fi

passo "Assinatura em uso"
az account show --query "{assinatura:name, id:id}" -o table

# ---------------------------- Provedores de recursos -------------------------
passo "Registrando provedores de recursos (necessário em algumas assinaturas)"
az provider register --namespace Microsoft.CognitiveServices --wait
az provider register --namespace Microsoft.Web --wait

# ------------------------------- Resource Group ------------------------------
passo "Criando Resource Group: $RG ($LOCATION)"
az group create --name "$RG" --location "$LOCATION" --output table

# ------------------------------- Azure AI Vision -----------------------------
passo "Criando Azure AI Vision: $AIV"
criar_visao() {
  az cognitiveservices account create \
    --name "$AIV" \
    --resource-group "$RG" \
    --location "$LOCATION" \
    --kind ComputerVision \
    --sku "$1" \
    --custom-domain "$AIV" \
    --yes \
    --output none
}

# Tenta o plano gratuito (F0); se a assinatura já tiver um F0, usa o S1.
if SAIDA=$(criar_visao F0 2>&1); then
  echo "Recurso criado com o SKU gratuito (F0)."
else
  echo "SKU F0 indisponível nesta assinatura. Tentando S1..."
  echo "Motivo: $(echo "$SAIDA" | tail -n 1)"
  criar_visao S1
  echo "Recurso criado com o SKU S1."
fi

ENDPOINT=$(az cognitiveservices account show \
  --name "$AIV" --resource-group "$RG" --query "properties.endpoint" -o tsv)
CHAVE=$(az cognitiveservices account keys list \
  --name "$AIV" --resource-group "$RG" --query "key1" -o tsv)
echo "Endpoint do serviço de visão: $ENDPOINT"

# ------------------------------- App Service Plan ----------------------------
passo "Criando App Service Plan: $PLANO ($SKU_PLANO, Linux)"
az appservice plan create \
  --name "$PLANO" \
  --resource-group "$RG" \
  --location "$LOCATION" \
  --sku "$SKU_PLANO" \
  --is-linux \
  --output table

# ------------------------------- Web App -------------------------------------
passo "Criando Web App: $APP ($RUNTIME)"
az webapp create \
  --name "$APP" \
  --resource-group "$RG" \
  --plan "$PLANO" \
  --runtime "$RUNTIME" \
  --output table

passo "Configurando variáveis de ambiente e comando de inicialização"
az webapp config appsettings set \
  --name "$APP" \
  --resource-group "$RG" \
  --settings \
    VISION_ENDPOINT="$ENDPOINT" \
    VISION_KEY="$CHAVE" \
    SCM_DO_BUILD_DURING_DEPLOYMENT=true \
  --output none

az webapp config set \
  --name "$APP" \
  --resource-group "$RG" \
  --startup-file "gunicorn --bind=0.0.0.0 --timeout 120 app:app" \
  --output none

az webapp update --name "$APP" --resource-group "$RG" --https-only true --output none

# ------------------------------- Deploy --------------------------------------
passo "Publicando a aplicação via Azure CLI (zip deploy)"
rm -f "$ZIP"
(cd "$PASTA_APP" && zip -qr "../$ZIP" . -x "__pycache__/*" "*.pyc")
az webapp deploy \
  --name "$APP" \
  --resource-group "$RG" \
  --src-path "$ZIP" \
  --type zip \
  --output none
rm -f "$ZIP"

# ------------------------------- Verificação ---------------------------------
URL="https://${APP}.azurewebsites.net"
passo "Aguardando a aplicação responder em $URL/health"
for i in $(seq 1 24); do
  CODIGO=$(curl -s -o /dev/null -w "%{http_code}" "$URL/health" || true)
  if [ "$CODIGO" = "200" ]; then
    echo "Aplicação no ar (HTTP 200)."
    break
  fi
  echo "  tentativa $i/24: HTTP $CODIGO (aguardando 10s)..."
  sleep 10
done

passo "Recursos criados em $RG"
az resource list --resource-group "$RG" \
  --query "[].{Nome:name, Tipo:type, Local:location}" -o table

echo
echo "============================================================"
echo " DroneVision publicada em: $URL"
echo "============================================================"
