# 🎧 Crate Digger Audio Ecosystem

Welcome to the central orchestration repository for the Crate Digger Audio Ecosystem.

This repository (`api-gateway` / `crate-digger-compose`) acts as the unified entry point for the entire platform. It houses the Nginx API Gateway and the master `docker-compose.yml` that binds together a suite of decoupled, event-driven microservices, shared infrastructure, and background workers.

## 📦 Packages & Artifacts

| Component | Type | Install / Pull Command | Status |
| --- | --- | --- | --- |
| Crate Digger API | Docker | `docker pull ghcr.io/nikiforidi/crate-digger:latest` | ![Docker](https://img.shields.io/badge/GHCR-crate--digger-blue?logo=docker) |
| Crate Digger TS | npm | `npm i @nikiforidi/crate-digger-ts` | ![npm](https://img.shields.io/badge/npm-@nikiforidi/crate--digger--ts-blue?logo=npm) |
| Auth Service | Docker | `docker pull ghcr.io/nikiforidi/auth-service:latest` | ![Docker](https://img.shields.io/badge/GHCR-auth--service-blue?logo=docker) |
| Economy Service | Docker | `docker pull ghcr.io/nikiforidi/economy-service:latest` | ![Docker](https://img.shields.io/badge/GHCR-economy--service-blue?logo=docker) |
| YTB Audio Relay | Docker | `docker pull ghcr.io/nikiforidi/ytb-audio-relay:latest` | ![Docker](https://img.shields.io/badge/GHCR-ytb--audio--relay-blue?logo=docker) |
| YTB Audio Relay TS | npm | `npm i @nikiforidi/ytb-audio-relay-client` | ![npm](https://img.shields.io/badge/npm-@nikiforidi/ytb--audio--relay--client-blue?logo=npm) |
| YTB Audio Preview | Docker | `docker pull ghcr.io/nikiforidi/ytb-audio-preview:latest` | ![Docker](https://img.shields.io/badge/GHCR-ytb--audio--preview-blue?logo=docker) |
| YTB Audio Preview TS | npm | `npm i @nikiforidi/ytb-audio-preview-client` | ![npm](https://img.shields.io/badge/npm-@nikiforidi/ytb--audio--preview--client-blue?logo=npm) |
| Audio Toolkit | PyPI | `pip install audio-preview-toolkit` | ![PyPI](https://img.shields.io/badge/PyPI-audio--preview--toolkit-blue?logo=pypi) |

## 🏗️ High-Level Architecture

The ecosystem follows a microservices architecture, utilizing Redis Pub/Sub for asynchronous event broadcasting and MinIO for distributed object storage.

```mermaid
graph TD
    Client[Frontend / External Clients] --> GW[API Gateway / Nginx]
    
    GW -->|/api/auth/*| AUTH[auth-service]
    GW -->|/api/crate/*| CD[crate-digger API]
    GW -->|/api/economy/*| ECO[economy-service]
    GW -->|/api/relay/*| RELAY_API[ytb-audio-relay API]
    GW -->|/api/preview/*| PREV_API[ytb-audio-preview API]
    
    AUTH -->|Reads/Writes Users| PG[(PostgreSQL)]
    AUTH -->|Stores verify tokens| REDIS[(Redis)]
    AUTH -.->|Send emails| UNI[Unisender API]
    
    ECO -->|Orders, Wallets, Tx| PG
    ECO -->|Idempotency cache| REDIS
    ECO -.->|Validate JWT| AUTH
    ECO -.->|Get listing data| CD
    ECO -.->|Payments & Payouts| YK[ЮKassa API]
    
    RELAY_API -.Pub/Sub.-> REDIS
    PREV_API -.Pub/Sub.-> REDIS
    
    RELAY_WORKER[ytb-audio-relay Worker] -->|Listens| REDIS
    RELAY_WORKER -->|Downloads & Uploads| MINIO[(MinIO)]
    
    PREV_WORKER[ytb-audio-preview Worker] -->|Listens| REDIS
    PREV_WORKER -->|Reads Source Audio| MINIO
    PREV_WORKER -->|Uploads Preview| MINIO
    PREV_WORKER -->|Uses| TOOLKIT{{audio-preview-toolkit}}
    
    CD -->|Reads/Writes Metadata| PG
    CD -->|Caches Data| REDIS
    CD -->|Stores Art/Thumbnails| MINIO
```

## 🛒 End-to-End Flow: Purchasing a Vinyl Record

```mermaid
sequenceDiagram
    participant C as Buyer
    participant GW as API Gateway
    participant AUTH as auth-service
    participant ECO as economy-service
    participant CD as crate-digger
    participant YK as ЮKassa
    participant S as Seller

    C->>AUTH: POST /api/auth/register (email, password)
    AUTH-->>C: 201 + verification email
    C->>AUTH: POST /api/auth/verify (token)
    AUTH-->>C: 200 + JWT access_token
    
    C->>CD: GET /api/crate/listings
    CD-->>C: List of vinyl records
    
    C->>ECO: POST /api/economy/orders/checkout (JWT + items)
    ECO->>CD: Validate listings (internal)
    ECO->>YK: Create split payment
    YK-->>ECO: payment_url
    ECO-->>C: 201 + payment_url
    
    C->>YK: Pay with card
    YK->>ECO: Webhook (payment.succeeded)
    ECO-->>ECO: Freeze seller funds (escrow)
    
    C->>ECO: POST /api/economy/orders/{id}/confirm-delivery
    ECO-->>ECO: Release funds to seller balance
    
    S->>ECO: POST /api/economy/seller/payout
    ECO->>YK: Create payout to seller
```

## 📦 Repository Map

The ecosystem is split into 15 distinct repositories, following a strict separation of concerns. Each microservice has its own API, TypeScript client, and dedicated E2E testing suite.

| Repository | Role | Tech Stack |
| --- | --- | --- |
| crate-digger-compose (This Repo) | Orchestration, Routing & Infra | Docker, Nginx |
| [auth-service](https://github.com/nikiforidi/auth-service) | JWT auth, registration, Unisender emails | Python, FastAPI, Redis, JWT |
| [economy-service](https://github.com/nikiforidi/economy-service) | Orders, ЮKassa payments, escrow, payouts | Python, FastAPI, SQLAlchemy, ЮKassa |
| [audio-preview-toolkit](https://github.com/nikiforidi/audio-preview-toolkit) | Core Audio Processing Logic | Python, Pydub, FFmpeg |
| [crate-digger](https://github.com/nikiforidi/crate-digger) | Metadata & Discogs API | Python, FastAPI, SQLAlchemy |
| [crate-digger-ts](https://github.com/nikiforidi/crate-digger-ts) | TS Client for Crate Digger | TypeScript, Fetch API |
| [crate-digger-e2e](https://github.com/nikiforidi/crate-digger-e2e) | E2E Tests for Crate Digger | TypeScript, Vitest |
| [ytb-audio-relay](https://github.com/nikiforidi/ytb-audio-relay) | Telegram Audio Downloader | Python, FastAPI, Telethon, ARQ |
| [ytb-audio-relay-client](https://github.com/nikiforidi/ytb-audio-relay-client) | TS Client for Relay | TypeScript, Fetch API |
| [ytb-audio-relay-e2e](https://github.com/nikiforidi/ytb-audio-relay-e2e) | E2E Tests for Relay | TypeScript, Vitest |
| [ytb-audio-preview](https://github.com/nikiforidi/ytb-audio-preview) | Audio Preview Generator | Python, FastAPI, ARQ |
| [ytb-audio-preview-client](https://github.com/nikiforidi/ytb-audio-preview-client) | TS Client for Preview | TypeScript, Fetch API |
| [ytb-audio-preview-e2e](https://github.com/nikiforidi/ytb-audio-preview-e2e) | E2E Tests for Preview | TypeScript, Vitest |

## 🛠️ Shared Infrastructure

All services communicate over a dedicated Docker bridge network (`app-net`) and share the following stateful services:

- **PostgreSQL 15**: Relational data split across three databases:
  - `crate_digger` — metadata & Discogs integration (crate-digger)
  - `auth_db` — users, roles, verification tokens (auth-service)
  - `economy_db` — orders, seller wallets, transactions (economy-service)
- **Redis 7**: Central nervous system. Caching, ARQ background job queues, Pub/Sub event broadcasting, and auth verify tokens.
- **MinIO**: S3-compatible object storage. Stores raw audio tracks, generated previews, and Discogs artwork.

## 🚀 Local Development

### Prerequisites
- Docker & Docker Compose (V2)
- A `.env` file (copy from `.env.example` and fill in your Telegram, Discogs, Unisender & YooKassa credentials).

### Starting the Stack

```bash
# 1. Copy and configure environment variables
cp .env.example .env

# 2. Start all services in the background
docker compose up -d

# 3. Verify all APIs are healthy via the Gateway
curl http://localhost/health
curl http://localhost/api/crate/health
curl http://localhost/api/auth/health
curl http://localhost/api/economy/health
curl http://localhost/api/relay/health
curl http://localhost/api/preview/health
```

## 🛡️ CI/CD & Testing Architecture

The ecosystem relies on a robust, multi-layered CI/CD pipeline powered by GitHub Actions.

- **Unit Tests (`ci.yml`)**: Each microservice repository runs `pytest`/`vitest` and `pre-commit`/`lint-staged` hooks on every push.
- **Docker / NPM Publishing**: When a SemVer tag (e.g., `v1.2.3`) is pushed, GitHub Actions builds the Docker image or TS package and publishes it to GHCR or npm.
- **OpenAPI Publishing**: Each service publishes its OpenAPI spec as a GitHub Release artifact, enabling contract-first development and TypeScript client generation.
- **E2E Integration (`*-e2e` repos)**:
  - The E2E repositories pull the latest published GHCR images.
  - They install the latest published npm TS clients.
  - They spin up the exact production stack using `docker compose`.
  - They execute real-world scenarios (e.g., registering a user, purchasing a vinyl, triggering a Telegram download).
- **Gateway Integration (`test-compose.yml`)**: This repository's CI ensures that all microservices can boot together, share the same Redis/PostgreSQL/MinIO instances, and route correctly through Nginx.

## 🔌 API Gateway Routing

The Nginx gateway strips the prefixes and routes traffic to the internal Docker network:

| External URL | Internal Service | Port |
| --- | --- | --- |
| `http://localhost/api/auth/*` | auth-service | 8000 |
| `http://localhost/api/crate/*` | crate-digger | 8000 |
| `http://localhost/api/economy/*` | economy-service | 8000 |
| `http://localhost/api/relay/*` | ytb-audio-relay | 8000 |
| `http://localhost/api/preview/*` | ytb-audio-preview | 8000 |

## 🛡️ Production Features

### Structured Logging
Все запросы логируются в JSON формате с `correlation_id` для трассировки:
```json
{
  "event": "request_completed",
  "correlation_id": "abc-123",
  "user_id": "user-uuid",
  "method": "GET",
  "path": "/api/v1/releases/12345",
  "status_code": 200,
  "duration_ms": 45.2
}