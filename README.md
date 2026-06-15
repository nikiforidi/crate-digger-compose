# 🎧 Crate Digger Audio Ecosystem

Welcome to the central orchestration repository for the **Crate Digger Audio Ecosystem**. 

This repository (`api-gateway` / `crate-digger-compose`) acts as the unified entry point for the entire platform. It houses the **Nginx API Gateway** and the master **`docker-compose.yml`** that binds together a suite of decoupled, event-driven microservices, shared infrastructure, and background workers.

## 📦 Packages & Artifacts

| Component | Type | Install / Pull Command | Status |
| :--- | :--- | :--- | :--- |
| **Crate Digger API** | Docker | `docker pull ghcr.io/nikiforidi/crate-digger:latest` | ![Docker](https://img.shields.io/badge/GHCR-crate--digger-blue?logo=docker) |
| **Crate Digger TS** | npm | `npm i @nikiforidi/crate-digger-ts` | ![npm](https://img.shields.io/npm/v/@nikiforidi/crate-digger-ts?logo=npm) |
| **YTB Audio Relay** | Docker | `docker pull ghcr.io/nikiforidi/ytb-audio-relay:latest` | ![Docker](https://img.shields.io/badge/GHCR-ytb--audio--relay-blue?logo=docker) |
| **YTB Audio Relay TS** | npm | `npm i @nikiforidi/ytb-audio-relay-client` | ![npm](https://img.shields.io/npm/v/@nikiforidi/ytb-audio-relay-client?logo=npm) |
| **YTB Audio Preview** | Docker | `docker pull ghcr.io/nikiforidi/ytb-audio-preview:latest` | ![Docker](https://img.shields.io/badge/GHCR-ytb--audio--preview-blue?logo=docker) |
| **YTB Audio Preview TS** | npm | `npm i @nikiforidi/ytb-audio-preview-client` | ![npm](https://img.shields.io/npm/v/@nikiforidi/ytb-audio-preview-client?logo=npm) |
| **Audio Toolkit** | PyPI | `pip install audio-preview-toolkit` | ![PyPI](https://img.shields.io/pypi/v/audio-preview-toolkit?logo=pypi) |

---

## 🏗️ High-Level Architecture

The ecosystem follows a microservices architecture, utilizing **Redis Pub/Sub** for asynchronous event broadcasting and **MinIO** for distributed object storage.

```mermaid
graph TD
    Client[Frontend / External Clients] --> GW[API Gateway / Nginx]
    
    GW -->|/api/crate/*| CD[crate-digger API]
    GW -->|/api/relay/*| RELAY_API[ytb-audio-relay API]
    GW -->|/api/preview/*| PREV_API[ytb-audio-preview API]
    
    RELAY_API -.Pub/Sub.-> REDIS[(Redis)]
    PREV_API -.Pub/Sub.-> REDIS
    
    RELAY_WORKER[ytb-audio-relay Worker] -->|Listens| REDIS
    RELAY_WORKER -->|Downloads & Uploads| MINIO[(MinIO)]
    
    PREV_WORKER[ytb-audio-preview Worker] -->|Listens| REDIS
    PREV_WORKER -->|Reads Source Audio| MINIO
    PREV_WORKER -->|Uploads Preview| MINIO
    PREV_WORKER -->|Uses| TOOLKIT{{audio-preview-toolkit}}
    
    CD -->|Reads/Writes Metadata| PG[(PostgreSQL)]
    CD -->|Caches Data| REDIS
    CD -->|Stores Art/Thumbnails| MINIO
```

### 🔄 End-to-End Flow: Generating an Audio Preview

```mermaid
sequenceDiagram
    participant C as Client App
    participant GW as API Gateway
    participant PA as preview-api
    participant R as Redis
    participant PW as preview-worker
    participant M as MinIO
    participant T as audio-preview-toolkit

    C->>GW: POST /api/preview/trigger
    GW->>PA: Forward Request
    PA->>R: Publish Event (preview:trigger)
    PA-->>C: 202 Accepted (status: queued)
    
    R->>PW: Push Event to Worker
    PW->>M: Download Source Tracks
    PW->>T: Process Audio (Find loudest part, crossfade)
    T-->>PW: Return Preview Bytes
    PW->>M: Upload Preview MP3
    PW->>R: Save Result (preview_result:{id})
    
    loop Client Polling
        C->>GW: GET /api/preview/{id}/status
        GW->>PA: Forward Request
        PA->>R: Get Result
        alt Processing
            PA-->>C: 200 OK (status: processing)
        else Done
            PA-->>C: 200 OK (status: done, preview_url)
        end
    end
```

---

## 📦 Repository Map

The ecosystem is split into **11 distinct repositories**, following a strict separation of concerns. Each microservice has its own API, TypeScript client, and dedicated E2E testing suite.

| Repository | Role | Tech Stack |
| :--- | :--- | :--- |
| **`crate-digger-compose`** *(This Repo)* | Orchestration, Routing & Infra | Docker, Nginx |
| [`audio-preview-toolkit`](https://github.com/nikiforidi/audio-preview-toolkit) | Core Audio Processing Logic | Python, Pydub, FFmpeg |
| [`crate-digger`](https://github.com/nikiforidi/crate-digger) | Metadata & Discogs API | Python, FastAPI, SQLAlchemy |
| [`crate-digger-ts`](https://github.com/nikiforidi/crate-digger-ts) | TS Client for Crate Digger | TypeScript, Fetch API |
| [`crate-digger-e2e`](https://github.com/nikiforidi/crate-digger-e2e) | E2E Tests for Crate Digger | TypeScript, Vitest |
| [`ytb-audio-relay`](https://github.com/nikiforidi/ytb-audio-relay) | Telegram Audio Downloader | Python, FastAPI, Telethon, ARQ |
| [`ytb-audio-relay-client`](https://github.com/nikiforidi/ytb-audio-relay-client) | TS Client for Relay | TypeScript, Fetch API |
| [`ytb-audio-relay-e2e`](https://github.com/nikiforidi/ytb-audio-relay-e2e) | E2E Tests for Relay | TypeScript, Vitest |
| [`ytb-audio-preview`](https://github.com/nikiforidi/ytb-audio-preview) | Audio Preview Generator | Python, FastAPI, ARQ |
| [`ytb-audio-preview-client`](https://github.com/nikiforidi/ytb-audio-preview-client) | TS Client for Preview | TypeScript, Fetch API |
| [`ytb-audio-preview-e2e`](https://github.com/nikiforidi/ytb-audio-preview-e2e) | E2E Tests for Preview | TypeScript, Vitest |

---

## 🛠️ Shared Infrastructure

All services communicate over a dedicated Docker bridge network (`app-net`) and share the following stateful services:

*   **PostgreSQL 15**: The single source of truth for relational metadata (used exclusively by `crate-digger`).
*   **Redis 7**: Acts as the central nervous system. Used for caching, ARQ background job queues, and Pub/Sub event broadcasting between APIs and Workers.
*   **MinIO**: S3-compatible object storage. Stores raw audio tracks, generated previews, and Discogs artwork.

---

## 🚀 Local Development

### Prerequisites
*   Docker & Docker Compose (V2)
*   A `.env` file (copy from `.env.example` and fill in your Telegram & Discogs credentials).

### Starting the Stack
```bash
# 1. Copy and configure environment variables
cp .env.example .env

# 2. Start all services in the background
docker compose up -d

# 3. Verify all APIs are healthy via the Gateway
curl http://localhost/health
curl http://localhost/api/crate/health
curl http://localhost/api/relay/health
curl http://localhost/api/preview/health
```

---

## 🛡️ CI/CD & Testing Architecture

The ecosystem relies on a robust, multi-layered CI/CD pipeline powered by GitHub Actions.

1.  **Unit Tests (`ci.yml`)**: Each microservice repository runs `pytest`/`vitest` and `pre-commit`/`lint-staged` hooks on every push.
2.  **Docker / NPM Publishing**: When a SemVer tag (e.g., `v1.2.3`) is pushed, GitHub Actions builds the Docker image or TS package and publishes it to **GHCR** or **npm**.
3.  **E2E Integration (`*-e2e` repos)**: 
    *   The E2E repositories pull the **latest published GHCR images**.
    *   They install the **latest published npm TS clients**.
    *   They spin up the exact production stack using `docker compose`.
    *   They execute real-world scenarios (e.g., triggering a Telegram download, waiting for the Redis pub/sub event, verifying the file lands in MinIO).
4.  **Gateway Integration (`test-compose.yml`)**: This repository's CI ensures that all microservices can boot together, share the same Redis/MinIO instances, and route correctly through Nginx.

---

## 🔌 API Gateway Routing

The Nginx gateway strips the prefixes and routes traffic to the internal Docker network:

| External URL | Internal Service | Port |
| :--- | :--- | :--- |
| `http://localhost/api/crate/*` | `crate-digger` | `8000` |
| `http://localhost/api/relay/*` | `ytb-audio-relay` | `8000` |
| `http://localhost/api/preview/*` | `ytb-audio-preview` | `8000` |
```

---

### 🤖 Completing Dependabot Configuration

Now that the README is perfect, let's finish configuring **Dependabot** for the rest of your repositories. We will use the `groups` feature to bundle minor/patch updates into a single weekly PR, keeping your inbox clean.

#### 📦 Type C: TypeScript Clients
**Applies to:** `crate-digger-ts`, `ytb-audio-relay-client`, `ytb-audio-preview-client`

These repos only have npm dependencies and GitHub Actions.

```yaml
# .github/dependabot.yml
version: 2
updates:
  # 1. GitHub Actions
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule: { interval: "weekly", day: "monday", time: "09:00" }
    commit-message: { prefix: "chore", include: "scope" }

  # 2. Node.js Dependencies (npm)
  - package-ecosystem: "npm"
    directory: "/"
    schedule: { interval: "weekly", day: "monday", time: "09:00" }
    commit-message: { prefix: "chore", include: "scope" }
    groups:
      npm-minor-patch:
        update-types: ["minor", "patch"]
        patterns: ["*"]
```

#### 🧪 Type D: E2E Test Repositories
**Applies to:** `crate-digger-e2e`, `ytb-audio-relay-e2e`, `ytb-audio-preview-e2e`

These repos have npm dependencies (for Vitest and the TS clients), GitHub Actions, and Docker (for the `docker-compose.yml` files).

```yaml
# .github/dependabot.yml
version: 2
updates:
  # 1. GitHub Actions
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule: { interval: "weekly", day: "monday", time: "09:00" }
    commit-message: { prefix: "chore", include: "scope" }

  # 2. Node.js Dependencies (npm)
  - package-ecosystem: "npm"
    directory: "/"
    schedule: { interval: "weekly", day: "monday", time: "09:00" }
    commit-message: { prefix: "chore", include: "scope" }
    groups:
      npm-minor-patch:
        update-types: ["minor", "patch"]
        patterns: ["*"]

  # 3. Docker (Base images in docker-compose.yml)
  - package-ecosystem: "docker"
    directory: "/"
    schedule: { interval: "weekly", day: "monday", time: "09:00" }
    commit-message: { prefix: "chore", include: "scope" }
```

#### 🌐 Type E: API Gateway / Orchestration
**Applies to:** `crate-digger-compose` (This Repo)

This repo only has Docker (for `docker-compose.yml` and `Dockerfile` if any) and GitHub Actions.

```yaml
# .github/dependabot.yml
version: 2
updates:
  # 1. GitHub Actions
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule: { interval: "weekly", day: "monday", time: "09:00" }
    commit-message: { prefix: "chore", include: "scope" }

  # 2. Docker (Base images like nginx:alpine, redis:7-alpine)
  - package-ecosystem: "docker"
    directory: "/"
    schedule: { interval: "weekly", day: "monday", time: "09:00" }
    commit-message: { prefix: "chore", include: "scope" }
