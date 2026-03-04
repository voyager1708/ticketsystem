#!/usr/bin/env bash
# WSL2 Ubuntu 24.04 用 Docker CE（公式）インストールスクリプト
set -e

echo "=== Docker インストール (WSL Ubuntu) ==="
echo "アーキテクチャ: $(dpkg --print-architecture)"
echo ""

# 前提パッケージ
echo "[1/4] 前提パッケージをインストール中..."
sudo apt-get update -qq
sudo apt-get install -y ca-certificates curl gnupg

# Docker 公式リポジトリの GPG キーとリポジトリ追加 (Ubuntu 24.04)
echo "[2/4] Docker 公式リポジトリを追加中..."
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
CODENAME=$(. /etc/os-release && echo "${VERSION_CODENAME:-$UBUNTU_CODENAME}")
echo "   Ubuntu コードネーム: $CODENAME"
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $CODENAME stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Docker CE（公式）をインストール
echo "[3/4] Docker CE をインストール中..."
sudo apt-get update -qq
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 現在のユーザーを docker グループに追加（sudo なしで docker を実行するため）
echo "[4/4] ユーザーを docker グループに追加中..."
sudo groupadd docker 2>/dev/null || true
sudo usermod -aG docker "$USER"

echo ""
echo "=== インストール完了 ==="
echo "Docker を sudo なしで使うには、一度 WSL を終了してから再度 Ubuntu を開いてください。"
echo "  (PowerShell で: wsl --shutdown  その後、Ubuntu を起動)"
echo ""
echo "確認コマンド:"
echo "  docker --version"
echo "  docker compose version"
echo ""
