#!/bin/bash
# setup-vps.sh — Configura a VPS do zero para rodar o Cortiq Decision Copilot
# Execute uma vez na VPS: bash setup-vps.sh

set -e

echo "==> Atualizando pacotes..."
sudo apt-get update -y && sudo apt-get upgrade -y

echo "==> Instalando dependências do sistema..."
sudo apt-get install -y python3 python3-pip python3-venv git

echo "==> Clonando o repositório..."
cd ~
if [ ! -d "cortiq-decisioncopilot" ]; then
  git clone https://github.com/ygorbueno1555-prog/cortiq-decisioncopilot.git
fi
cd cortiq-decisioncopilot

echo "==> Criando ambiente virtual e instalando dependências Python..."
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Configurando variáveis de ambiente..."
if [ ! -f ".env" ]; then
  cp env.example .env
  echo ""
  echo "ATENÇÃO: edite o arquivo .env com suas chaves de API:"
  echo "  nano ~/cortiq-decisioncopilot/.env"
fi

echo "==> Criando serviço systemd..."
sudo bash -c "cat > /etc/systemd/system/cortiq.service" <<EOF
[Unit]
Description=Cortiq Decision Copilot
After=network.target

[Service]
User=$USER
WorkingDirectory=/home/$USER/cortiq-decisioncopilot
EnvironmentFile=/home/$USER/cortiq-decisioncopilot/.env
ExecStart=/home/$USER/cortiq-decisioncopilot/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable cortiq
sudo systemctl start cortiq

echo ""
echo "==> Setup concluído!"
echo "    Serviço rodando em: http://$(hostname -I | awk '{print $1}'):8000"
echo "    Verificar status: sudo systemctl status cortiq"
echo "    Ver logs:         sudo journalctl -u cortiq -f"
