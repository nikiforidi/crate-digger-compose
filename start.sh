#!/usr/bin/env bash
set -euo pipefail

# ─── Цвета ────────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
log_success() { echo -e "${GREEN}[OK]${NC}    $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()    { echo -e "\n${CYAN}━━━ $* ━━━${NC}"; }

# ─── Функции ──────────────────────────────────────────────────────────────────────
check_prerequisites() {
    log_step "Шаг 0: Проверка окружения"
    if ! command -v docker &>/dev/null; then
        log_error "Docker не установлен."
        exit 1
    fi
    log_success "Docker: $(docker --version)"
    
    if ! docker compose version &>/dev/null; then
        log_error "Docker Compose v2 не установлен."
        exit 1
    fi
    log_success "Docker Compose: $(docker compose version --short)"

    if [ ! -f .env ]; then
        log_warn ".env не найден. Копирую из .env.example..."
        if [ -f .env.example ]; then
            cp .env.example .env
            log_success ".env создан. Отредактируйте его при необходимости."
        else
            log_error ".env.example не найден."
            exit 1
        fi
    else
        log_success ".env найден"
    fi
}

login_ghcr() {
    log_step "Шаг 1: Авторизация в GitHub Container Registry"
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a

    if [ -n "${GHCR_USERNAME:-}" ] && [ -n "${GHCR_PASSWORD:-}" ]; then
        log_info "Автоматический login в GHCR (из .env)..."
        if echo "$GHCR_PASSWORD" | docker login ghcr.io -u "$GHCR_USERNAME" --password-stdin 2>&1 | grep -q "Login Succeeded"; then
            log_success "Авторизация в GHCR успешна"
            return 0
        else
            log_error "Не удалось авторизоваться. Проверьте GHCR_USERNAME и GHCR_PASSWORD в .env"
            exit 1
        fi
    fi

    if [ -f "$HOME/.docker/config.json" ] && grep -q "ghcr.io" "$HOME/.docker/config.json" 2>/dev/null; then
        log_success "Найдены credentials для ghcr.io"
        return 0
    fi

    log_warn "Для запуска фронтенда нужна авторизация в GHCR."
    echo -e "${YELLOW}Введите ваш GitHub Username и PAT (или нажмите Ctrl+C, чтобы прервать)${NC}"
    read -rp "GitHub Username: " gh_user
    read -rsp "GitHub PAT: " gh_pass
    echo ""
    if echo "$gh_pass" | docker login ghcr.io -u "$gh_user" --password-stdin 2>&1 | grep -q "Login Succeeded"; then
        log_success "Авторизация успешна"
        { echo ""; echo "GHCR_USERNAME=$gh_user"; echo "GHCR_PASSWORD=$gh_pass"; } >> .env
        log_success "Credentials сохранены в .env"
    else
        log_error "Не удалось авторизоваться"
        exit 1
    fi
}

start_infrastructure() {
    log_step "Шаг 2: Запуск инфраструктуры (PostgreSQL, Redis, MinIO)"
    docker compose up -d db redis minio
    log_info "Ожидание готовности PostgreSQL..."
    for i in {1..30}; do
        if docker compose exec -T db pg_isready -U postgres &>/dev/null; then
            log_success "PostgreSQL готов! (попытка $i)"
            break
        fi
        [ "$i" -eq 30 ] && { log_error "PostgreSQL не запустился"; docker compose logs db; exit 1; }
        sleep 2
    done
}

init_db_and_buckets() {
    log_step "Шаг 3: Инициализация БД и бакетов MinIO"
    docker compose up -d db-init createbuckets
    log_info "Ожидание завершения db-init..."
    for i in {1..20}; do
        STATUS=$(docker compose ps db-init --format json 2>/dev/null | grep -o '"ExitCode":[0-9]*' | head -1 | grep -o '[0-9]*' || echo "")
        [ "$STATUS" = "0" ] && { log_success "Базы данных созданы"; break; }
        sleep 1
    done
    log_success "Бакеты созданы"
}

run_migrations() {
    log_step "Шаг 4: Применение миграций Alembic"
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
    local services=("auth-service" "crate-digger" "economy-service" "marketplace-service")
    for service in "${services[@]}"; do
        log_info "→ $service"
        if docker compose run --rm --no-deps "$service" alembic upgrade head 2>&1 | tail -1; then
            log_success "$service: миграции применены"
        else
            log_warn "$service: миграции не применились (возможно, уже применены)"
        fi
    done
}

start_all_services() {
    log_step "Шаг 5: Запуск всех сервисов"
    log_info "Запуск ВСЕХ сервисов (включая фронтенд)..."
    docker compose up -d
}

health_check() {
    log_step "Шаг 6: Проверка работоспособности"
    log_info "Ожидание готовности API Gateway (до 60 секунд)..."
    for i in {1..30}; do
        if curl -sf http://localhost/health &>/dev/null; then
            log_success "API Gateway отвечает!"
            break
        fi
        [ "$i" -eq 30 ] && { log_error "API Gateway не отвечает"; docker compose logs gateway --tail=20; exit 1; }
        sleep 2
    done
    echo ""
    log_info "Статус всех сервисов:"
    docker compose ps --format "table {{.Name}}\t{{.Status}}"
}

print_summary() {
    log_step "🚀 Экосистема Crate запущена!"
    echo ""
    echo -e "${GREEN}┌─────────────────────────────────────────────────────────────┐${NC}"
    echo -e "${GREEN}│                    Доступные сервисы                        │${NC}"
    echo -e "${GREEN}├─────────────────────────────────────────────────────────────┤${NC}"
    echo -e "│  ${CYAN}Frontend + API${NC}         http://localhost              │"
    echo -e "│  ${CYAN}API Docs (Swagger)${NC}      http://localhost/docs         │"
    echo -e "│  ${CYAN}MinIO Console${NC}           http://localhost:9001         │"
    echo -e "│  ${CYAN}Prometheus${NC}              http://localhost:9090         │"
    echo -e "${GREEN}└─────────────────────────────────────────────────────────────┘${NC}"
    echo ""
    echo -e "${YELLOW}Полезные команды:${NC}"
    echo "  docker compose ps              # Статус всех сервисов"
    echo "  docker compose logs -f <svc>   # Логи сервиса"
    echo "  docker compose down -v         # Полная очистка"
}

# ─── Главная ──────────────────────────────────────────────────────────────────────
main() {
    echo ""
    echo -e "${CYAN}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║         🎵 Crate — Запуск экосистемы маркетплейса        ║${NC}"
    echo -e "${CYAN}║              (включая фронтенд)                          ║${NC}"
    echo -e "${CYAN}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""

    check_prerequisites
    login_ghcr
    start_infrastructure
    init_db_and_buckets
    run_migrations
    start_all_services
    health_check
    print_summary
}

main "$@"