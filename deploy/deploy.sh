#!/usr/bin/env bash
# MongoDB Anomaly Detection Assistant — Zero-downtime deploy script
# Kullanım: sudo bash deploy/deploy.sh [git-branch]
#
# Varsayılan branch: main
# Örnek:  sudo bash deploy/deploy.sh claude/ml-anomaly-detection-platform-kHalA

set -euo pipefail

# ─── Konfigürasyon ───────────────────────────────────────────────
APP_NAME="mongodb-assistant"
BASE_DIR="/opt/mongodb-assistant"
SHARED_DIR="$BASE_DIR/shared"
RELEASES_DIR="$BASE_DIR/releases"
CURRENT_LINK="$BASE_DIR/current"
SERVICE_USER="mongodb-assistant"
SERVICE_GROUP="mongodb-assistant"
REPO_URL="https://github.com/YOUR_USERNAME/MongoDB-LLM-assistant.git"
BRANCH="${1:-main}"
RELEASE_TAG="$(date +%Y%m%d_%H%M%S)"
RELEASE_DIR="$RELEASES_DIR/$RELEASE_TAG"
VENV_DIR="$RELEASE_DIR/venv"

echo "══════════════════════════════════════════════════"
echo "  Deploy: $APP_NAME"
echo "  Branch: $BRANCH"
echo "  Release: $RELEASE_TAG"
echo "══════════════════════════════════════════════════"

# ─── 1. İlk kurulum kontrolü ─────────────────────────────────────
setup_first_time() {
    echo "[1/7] İlk kurulum kontrolleri..."

    # Service user oluştur (yoksa)
    if ! id "$SERVICE_USER" &>/dev/null; then
        useradd -r -s /bin/false -d "$BASE_DIR" "$SERVICE_USER"
        echo "  → User '$SERVICE_USER' oluşturuldu"
    fi

    # Dizin yapısı
    mkdir -p "$RELEASES_DIR"
    mkdir -p "$SHARED_DIR/storage"/{models,exports,temp,backups,uploads}
    mkdir -p /var/log/mongodb-assistant

    # .env kontrolü
    if [ ! -f "$SHARED_DIR/.env" ]; then
        echo "  ⚠ $SHARED_DIR/.env bulunamadı!"
        echo "  → Lütfen .env dosyasını oluşturun ve tekrar çalıştırın."
        echo "  → Örnek: cp .env.example $SHARED_DIR/.env && nano $SHARED_DIR/.env"
        exit 1
    fi

    echo "  → Dizin yapısı hazır"
}

# ─── 2. Kodu çek ─────────────────────────────────────────────────
fetch_code() {
    echo "[2/7] Kod çekiliyor → $RELEASE_DIR"
    git clone --depth 1 --branch "$BRANCH" "$REPO_URL" "$RELEASE_DIR"
    echo "  → Commit: $(git -C "$RELEASE_DIR" rev-parse --short HEAD)"
}

# ─── 3. Virtual environment ──────────────────────────────────────
setup_venv() {
    echo "[3/7] Virtual environment kuruluyor..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet --upgrade pip
    "$VENV_DIR/bin/pip" install --quiet -r "$RELEASE_DIR/requirements.txt"
    echo "  → $(${VENV_DIR}/bin/pip list 2>/dev/null | wc -l) paket yüklendi"
}

# ─── 4. Shared dizinleri bağla ────────────────────────────────────
link_shared() {
    echo "[4/7] Shared dizinler bağlanıyor..."

    # .env → release'a symlink (load_dotenv CWD'den okuyabilsin)
    ln -sf "$SHARED_DIR/.env" "$RELEASE_DIR/.env"

    # Storage — release içindeki storage dizinini shared'a bağla
    # (STORAGE_PATH .env'de absolute olmalı, ama yine de bağlayalım)
    rm -rf "$RELEASE_DIR/storage" 2>/dev/null || true
    ln -sf "$SHARED_DIR/storage" "$RELEASE_DIR/storage"

    echo "  → .env ve storage symlink'leri hazır"
}

# ─── 5. Ownership ────────────────────────────────────────────────
fix_permissions() {
    echo "[5/7] Dosya izinleri ayarlanıyor..."
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$RELEASE_DIR"
    chown -R "$SERVICE_USER:$SERVICE_GROUP" "$SHARED_DIR"
    chown -R "$SERVICE_USER:$SERVICE_GROUP" /var/log/mongodb-assistant
    echo "  → Owner: $SERVICE_USER:$SERVICE_GROUP"
}

# ─── 6. Symlink switch + restart ─────────────────────────────────
switch_and_restart() {
    echo "[6/7] Release aktif ediliyor..."

    # Eski release'ı kaydet (rollback için)
    PREVIOUS=""
    if [ -L "$CURRENT_LINK" ]; then
        PREVIOUS="$(readlink -f "$CURRENT_LINK")"
        echo "  → Önceki: $PREVIOUS"
    fi

    # Atomic symlink switch
    ln -sfn "$RELEASE_DIR" "$CURRENT_LINK"
    echo "  → Aktif: $RELEASE_DIR"

    # systemd unit'i kopyala (değişmiş olabilir)
    cp "$RELEASE_DIR/deploy/mongodb-assistant.service" /etc/systemd/system/
    systemctl daemon-reload

    # Restart
    systemctl restart "$APP_NAME"
    sleep 2

    if systemctl is-active --quiet "$APP_NAME"; then
        echo "  → Servis çalışıyor ✓"
    else
        echo "  ✗ Servis başlatılamadı! Rollback yapılıyor..."
        if [ -n "$PREVIOUS" ]; then
            ln -sfn "$PREVIOUS" "$CURRENT_LINK"
            systemctl restart "$APP_NAME"
            echo "  → Rollback tamamlandı: $PREVIOUS"
        fi
        journalctl -u "$APP_NAME" --no-pager -n 20
        exit 1
    fi
}

# ─── 7. Smoke test ───────────────────────────────────────────────
smoke_test() {
    echo "[7/7] Smoke test..."

    # Test 1: API ayakta mı?
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/status || echo "000")
    if [ "$HTTP_CODE" = "200" ]; then
        echo "  → API status: $HTTP_CODE ✓"
    else
        echo "  ✗ API yanıt vermiyor (HTTP $HTTP_CODE)"
        exit 1
    fi

    # Test 2: Storage path doğru mu?
    STORAGE_CHECK=$(curl -s http://localhost:8000/api/status | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('storage_path', d.get('status', 'unknown')))
except:
    print('parse_error')
" 2>/dev/null || echo "parse_error")
    echo "  → Storage: $STORAGE_CHECK"

    echo "══════════════════════════════════════════════════"
    echo "  Deploy tamamlandı! ✓"
    echo "  Release: $RELEASE_TAG"
    echo "  Rollback: ln -sfn $PREVIOUS $CURRENT_LINK && systemctl restart $APP_NAME"
    echo "══════════════════════════════════════════════════"
}

# ─── Eski release'ları temizle (son 3 hariç) ─────────────────────
cleanup_old() {
    local count
    count=$(ls -1d "$RELEASES_DIR"/*/ 2>/dev/null | wc -l)
    if [ "$count" -gt 3 ]; then
        echo "  → Eski release'lar temizleniyor (son 3 korunuyor)..."
        ls -1dt "$RELEASES_DIR"/*/ | tail -n +4 | xargs rm -rf
    fi
}

# ─── Ana akış ────────────────────────────────────────────────────
setup_first_time
fetch_code
setup_venv
link_shared
fix_permissions
switch_and_restart
smoke_test
cleanup_old
