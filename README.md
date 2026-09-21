# Dead Man's Switch 

## Stack

| Component | Choice |
|---|---|
| Frontend | React 19 + Vite + Lucide Icons |
| Backend API | FastAPI (async) + Uvicorn |
| DB | SQLite |
| Auth | Google OAuth2 (Authlib) + JWT access/refresh tokens |
| OTP | Email (SMTP) + Redis NX storage + GETDEL atomicity |
| Cache / Rate-limit / Lock | Redis (Memurai on Windows / Redis on Linux/macOS) |
| Background jobs | Celery + Celery Beat + Celery Flower (`--pool=solo` on Windows) |
| Encryption | Fernet (`cryptography`) — at rest encryption |
| Package manager | uv (Python) + npm (Frontend) |

---

## 🚀 1-Command Docker Quickstart (Recommended)

Run the entire application stack (**React Frontend + FastAPI Backend + Celery Worker + Celery Beat + Redis + PostgreSQL + Flower Dashboard**) with a single command from one terminal:

```bash
docker compose up --build
```
*(Or in detached mode: `docker compose up -d --build`)*

### Service URLs:
- **React Frontend**: [http://localhost:5173](http://localhost:5173)
- **FastAPI Backend (Swagger Docs)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Celery Flower Dashboard**: [http://localhost:5555](http://localhost:5555)

### Stop All Services:
```bash
docker compose down
```

---

## Manual Local Setup Guide (Step-by-Step)

### Step 1: Clone the Repository

```bash
git clone <YOUR_GIT_REPO_URL>
cd "dead switch"
```

---

### Step 2: Backend Installation & Setup (FastAPI)

1. **Install all Python dependencies**:
   ```bash
   uv sync
   ```
   *(This automatically creates the `.venv` virtual environment and installs all packages defined in `pyproject.toml`)*

2. **Configure environment variables (`.env`)**:
   ```bash
   # Windows:
   copy .env.example .env

   # Linux / macOS:
   cp .env.example .env
   ```

3. **Generate a Fernet Encryption Key** and paste it into `FERNET_KEY` in your `.env`:
   ```bash
   uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

4. **Fill in required `.env` values**:
   - `GOOGLE_CLIENT_ID` & `GOOGLE_CLIENT_SECRET`: From Google Cloud Console (OAuth 2.0 Client Credentials with Authorized redirect URI: `http://localhost:8000/auth/callback`).
   - `SMTP_USER` & `SMTP_PASSWORD`: Your email and Gmail App Password for sending OTPs and reveal emails.
   - `SMTP_FROM`: Sender email address (e.g. your Gmail).
   - `JWT_SECRET`: Any long random secret string.
   - `DATABASE_URL`: Defaults to `sqlite+aiosqlite:///./deadswitch.db` (zero database server configuration needed).

5. **Run Database Migrations**:
   ```bash
   uv run alembic upgrade head
   ```
   *(This creates all tables including `users`, `switches`, and `otp_attempts` in SQLite/Postgres)*

---

### Step 3: Frontend Installation & Setup (React + Vite)

Open a terminal or navigate into the `frontend` folder to install UI dependencies:

```bash
cd frontend
npm install
cd ..
```

---

### Step 4: Running the Application

1. **Start Backend API (Terminal 1)**:
   ```bash
   .venv\Scripts\Activate.ps1
   uv run uvicorn app.main:app --reload
   ```
   - Swagger Docs: http://localhost:8000/docs
   - Login Direct: http://localhost:8000/auth/login

2. **Start Frontend Dev Server (Terminal 2)**:
   ```bash
   cd frontend
   npm run dev
   ```
   - UI Dashboard: http://localhost:5173

3. **Start Celery Worker (Terminal 3)**:
   ```bash
   uv run celery -A app.tasks.celery_app worker --pool=solo --loglevel=info
   ```

4. **Start Celery Beat Scheduler (Terminal 4)**:
   ```bash
   uv run celery -A app.tasks.celery_app beat --loglevel=info
   ```

5. **Start Celery Flower Web Dashboard (Terminal 5 - Optional)**:
   ```bash
   uv run celery -A app.tasks.celery_app flower --port=5555
   ```
   - Flower UI: http://localhost:5555

---

## ☸️ Kubernetes & Helm Local Deployment (Minikube)

The project includes a production-ready Helm chart (`deadHand/`) to orchestrate the entire Dead Man's Switch infrastructure on a local Kubernetes cluster (Minikube or MicroK8s).

### 🏛️ Cluster Topology & Components

When deployed, the chart provisions 7 coordinated workloads:

| Component | Workload Type | Port / Internal DNS | Role |
|---|---|---|---|
| **PostgreSQL 16** | Deployment + PVC (`1Gi`) | `db:5432` | Primary ACID relational database with persistent storage |
| **Redis 7** | Deployment + PVC (`500Mi`) | `redis:6379` | Deadline sorted sets, distributed lock manager & OTP cache |
| **FastAPI Backend** | Deployment + ClusterIP | `backend:8000` | REST API, auto Alembic migrations via init container, Fernet encryption |
| **React Frontend** | Deployment + NodePort | `deadhand-frontend:5173` (NodePort: `30173`) | React 19 UI with embedded Nginx reverse proxy routing API calls |
| **Celery Worker** | Deployment | Background Worker | Asynchronous tasks, deadline reveal execution, and email delivery |
| **Celery Beat** | Deployment | Scheduler | Periodic deadline scanner (runs every 30s) |
| **Celery Flower** | Deployment + NodePort | `deadhand-flower:5555` (NodePort: `30555`) | Real-time monitoring and task inspection dashboard |

---

### 📋 Prerequisites

Ensure the following CLI tools are installed on your machine:
- **Docker Desktop** (or Docker Engine)
- **Minikube** (`minikube version`)
- **kubectl** (`kubectl version --client`)
- **Helm v3** (`helm version`)

---

### 🚀 Step-by-Step Deployment Guide

#### Step 1: Start Minikube Cluster
Start your local Minikube cluster using either the Hyper-V or Docker driver:

```powershell
# Using Hyper-V driver (Windows):
minikube start --driver=hyperv

# OR using Docker driver (cross-platform):
minikube start --driver=docker
```

Verify that the cluster node is ready:
```powershell
kubectl get nodes
```

#### Step 2: Build & Load Docker Images into Minikube
Since Minikube runs inside its own isolated VM/container runtime, build the images on your host and load them into Minikube's local cache:

```powershell
# 1. Build local container images
docker compose build

# 2. Load images into Minikube containerd cache
minikube image load deadswitch-backend:latest
minikube image load deadswitch-frontend:latest
minikube image load postgres:16-alpine
minikube image load redis:7-alpine
```

#### Step 3: Lint & Deploy with Helm
From the repository root directory, lint and deploy the `deadHand` chart:

```powershell
# Verify chart syntax
helm lint ./deadHand

# Deploy or upgrade the release
helm upgrade --install deadhand ./deadHand
```

#### Step 4: Verify Deployment Status
Check that all 7 pods transition to `Running` and `Ready` (1/1):

```powershell
kubectl get pods -l app.kubernetes.io/instance=deadhand
```

Expected output:
```text
NAME                                 READY   STATUS    RESTARTS   AGE
deadhand-backend-xxxxxxxxxx-xxxxx    1/1     Running   0          2m
deadhand-beat-xxxxxxxxxx-xxxxx       1/1     Running   0          2m
deadhand-flower-xxxxxxxxxx-xxxxx     1/1     Running   0          2m
deadhand-frontend-xxxxxxxxxx-xxxxx   1/1     Running   0          2m
deadhand-postgres-xxxxxxxxxx-xxxxx   1/1     Running   0          2m
deadhand-redis-xxxxxxxxxx-xxxxx      1/1     Running   0          2m
deadhand-worker-xxxxxxxxxx-xxxxx     1/1     Running   0          2m
```

---

### 🌐 Accessing the Application

#### Option A: Direct Minikube Browser Command
Run the following commands in your terminal to automatically open the services in your default browser:

```powershell
# Open React Frontend
minikube service deadhand-frontend

# Open Celery Flower Dashboard
minikube service deadhand-flower

# View all exposed cluster endpoints
minikube service list
```

#### Option B: Port-Forwarding to Localhost (Recommended for OAuth)
Because Google OAuth redirects to `http://localhost:8000/auth/callback` and `http://localhost:5173`, forwarding the ports to `localhost` ensures seamless Google authentication:

```powershell
# Terminal 1: Forward Frontend
kubectl port-forward svc/deadhand-frontend 5173:5173

# Terminal 2: Forward Backend (Required for Google OAuth login flow)
kubectl port-forward svc/backend 8000:8000

# Terminal 3: Forward Celery Flower (Optional)
kubectl port-forward svc/deadhand-flower 5555:5555
```

| Service | Local Endpoint | Description |
|---|---|---|
| **React Frontend** | [http://localhost:5173](http://localhost:5173) | Main user interface |
| **Backend Swagger Docs** | [http://localhost:8000/docs](http://localhost:8000/docs) (or [http://localhost:5173/docs](http://localhost:5173/docs)) | Interactive API documentation |
| **API Health Check** | [http://localhost:8000/health](http://localhost:8000/health) | Healthcheck endpoint (`{"status":"ok"}`) |
| **Celery Flower** | [http://localhost:5555](http://localhost:5555) | Celery task inspection UI |

---

### 🛠️ Useful Debugging & Operations Commands

```powershell
# Inspect backend logs (including Alembic auto-migrations):
kubectl logs -f deployment/deadhand-backend -c backend

# Inspect Celery worker task execution logs:
kubectl logs -f deployment/deadhand-worker -c celery-worker

# Inspect Celery beat scheduler logs:
kubectl logs -f deployment/deadhand-beat -c celery-beat

# Connect to PostgreSQL directly:
kubectl exec -it deployment/deadhand-postgres -- psql -U postgres -d deadswitch

# Connect to Redis CLI:
kubectl exec -it deployment/deadhand-redis -- redis-cli

# Teardown the Helm deployment (deletes pods, services, deployments):
helm uninstall deadhand
```

---

## Run tests

```bash
uv run pytest tests/ -v
```

All 20 tests run without a live DB or Redis (uses fakeredis).



## 🏗️ Visual Architecture & Lifecycle Flowcharts

### 1. End-to-End System Architecture

```mermaid
flowchart TD
    %% Clients
    subgraph CLIENTS["🖥️ Client Layer"]
        UI["⚛️ React SPA<br/>Vite · Modern Dashboard UI"]
        CLI["🌐 API Consumers<br/>REST Clients · Swagger UI"]
    end

    %% FastAPI Backend
    subgraph BACKEND["🛡️ FastAPI Application Layer"]
        direction TB
        RL["⏱️ Rate Limiter<br/>IP & User Throttles"]
        AUTH["🔑 Auth Engine<br/>OAuth 2.0 & JWT"]
        API["⚡ REST Endpoints<br/>/switches · /otp · /auth"]
        ENC["🔐 Fernet Cryptography<br/>In-Memory Cipher Engine"]
        RL --> AUTH --> API
        API <--> ENC
    end

    %% Data & State
    subgraph DATA["💾 Persistence & State Layer"]
        direction LR
        DB[("🗄️ Database<br/>SQLite / PostgreSQL")]
        REDIS[("📬 Redis<br/>Deadlines · Locks · OTP")]
    end

    %% Celery Workers
    subgraph WORKERS["⚙️ Celery Asynchronous Cluster"]
        direction LR
        BEAT["⏰ Celery Beat<br/>30s Periodic Scanner"]
        WORKER["👷 Celery Worker<br/>Reveal & Alert Tasks"]
        BEAT -->|"Enqueue Overdue"| WORKER
    end

    %% External
    subgraph EXTERNAL["☁️ External Services"]
        direction LR
        GOOGLE["🌐 Google OAuth"]
        SMTP["✉️ Gmail SMTP"]
        RECIPIENT["👥 Recipient Email"]
    end

    %% Connections
    CLIENTS -->|"HTTPS / JWT"| RL
    AUTH <-->|"Token Exchange"| GOOGLE

    API -->|"Persist Rows"| DB
    API -->|"Deadlines & OTP"| REDIS
    API -->|"Enqueue OTP Task"| WORKER

    WORKER -->|"Acquire Lock & ZREM"| REDIS
    WORKER -->|"Read Encrypted Secret"| DB
    WORKER -->|"Dispatch Mail"| SMTP
    SMTP -->|"Deliver Message"| RECIPIENT

    %% Styling
    style CLIENTS fill:#F0F7FF,stroke:#2563EB,stroke-width:1.5px,color:#1E3A8A
    style BACKEND fill:#FAF5FF,stroke:#9333EA,stroke-width:1.5px,color:#581C87
    style DATA fill:#ECFDF5,stroke:#059669,stroke-width:1.5px,color:#065F46
    style WORKERS fill:#FFFBEB,stroke:#D97706,stroke-width:1.5px,color:#92400E
    style EXTERNAL fill:#F8FAFC,stroke:#64748B,stroke-width:1.5px,color:#334155
```

---

### 2. Request-Response Sequence Diagram (Lifecycle Execution)

```mermaid
sequenceDiagram
    autonumber
    actor User as "👤 User"
    participant API as "⚡ FastAPI App"
    participant DB as "🗄️ Database"
    participant Redis as "📬 Redis (Memurai)"
    participant Beat as "⏰ Celery Beat"
    participant Worker as "⚙️ Celery Worker"
    participant SMTP as "✉️ Gmail SMTP"
    actor Recipient as "👥 Recipient"

    Note over User, Redis: Phase 1: Switch Creation
    User->>API: POST /switches (payload + otp_code)
    API->>Redis: Atomic GETDEL otp (verify code)
    API->>DB: INSERT switch (status='active', next_deadline)
    API->>Redis: ZADD switches:deadlines deadline_ts switch_id
    API-->>User: 201 Created (Switch Active)

    Note over Beat, Worker: Phase 2: Deadline Check (Every 30s)
    Beat->>Redis: ZRANGEBYSCORE switches:deadlines -inf now_timestamp
    Redis-->>Beat: List of overdue switch IDs
    Beat-->>Worker: Enqueue check_and_trigger_switches()

    Note over Worker, DB: Phase 3: Task 2 - Lock & Transition
    Worker->>Redis: SET lock:switch:id token NX EX 30
    alt Lock Acquired
        Worker->>DB: UPDATE switch SET status='triggering' WHERE status='active'
        Worker->>Worker: Enqueue send_reveal_email(switch_id)
        Worker->>Redis: Lua release_lock.lua (Delete lock if token matches)
    else Lock Held by Another Worker
        Worker-->>Beat: Skip processing (Prevent duplicate trigger)
    end

    Note over Worker, SMTP: Phase 4: Task 3 - Decrypt & Send Email
    Worker->>DB: SELECT switch WHERE id=switch_id
    Worker->>Worker: Decrypt secret ciphertext in-memory (Fernet)
    Worker->>SMTP: Send reveal email to recipient
    SMTP-->>Worker: 250 OK (Email Sent)
    Worker->>DB: UPDATE switch SET status='triggered', sent_at=now()
    Worker->>Redis: ZREM switches:deadlines switch_id
    SMTP-->>Recipient: Plaintext message delivered safely
```

---

### 3. End-to-End Lifecycle Phase Flowchart

```mermaid
flowchart TD
    %% Phase 1
    subgraph P1["1️⃣ Phase 1: Purpose-Bound OTP Request"]
        direction TB
        A1["👤 User Requests OTP in UI"] --> B1["⚡ POST /otp/request<br/>(Rate Limit: Max 3/10m)"]
        B1 --> C1["📬 Redis SET NX otp:hash<br/>(60s Cooldown Enforced)"]
        C1 --> D1["✉️ Celery send_otp_email<br/>(Delivered to User Gmail)"]
    end

    %% Phase 2
    subgraph P2["2️⃣ Phase 2: Switch Creation & Encryption"]
        direction TB
        A2["👤 User Submits Secret + OTP"] --> B2["🔑 Atomic GETDEL OTP<br/>(Single-use verification)"]
        B2 --> C2["🔐 Fernet In-Memory Encryption<br/>(Plaintext never logged)"]
        C2 --> D2["🗄️ DB: INSERT switch status=active"]
        C2 --> E2["📊 Redis: ZADD switches:deadlines<br/>(Score = Deadline Timestamp)"]
    end

    %% Phase 3
    subgraph P3["3️⃣ Phase 3: Periodic Heartbeat / Check-in"]
        direction TB
        A3["👤 Owner Checks In Before Deadline"] --> B3["⚡ POST /switches/:id/checkin<br/>(Validates status=active)"]
        B3 --> C3["🗄️ DB: Update next_deadline"]
        C3 --> D3["📊 Redis: ZADD New Timestamp"]
    end

    %% Phase 4
    subgraph P4["4️⃣ Phase 4: Expiry Scan & Automated Reveal"]
        direction TB
        A4["⏰ Celery Beat Scans (Every 30s)<br/>(ZRANGEBYSCORE overdue)"] --> B4["🔒 Acquire Lock: SET NX EX 30"]
        B4 --> C4["🗄️ DB Guard: status=triggering"]
        C4 --> D4["🔐 Decrypt Secret In-Memory<br/>& Dispatch Email via SMTP"]
        D4 --> E4["🎉 Recipient Receives Plaintext<br/>(status=triggered, ZREM deadline)"]
    end

    %% Transitions
    P1 ==>|"User Obtains OTP"| P2
    P2 ==>|"Switch Is Active"| P3
    P3 -.->|"Missed Deadline (Trigger)"| P4

    %% Styling
    style P1 fill:#F0F7FF,stroke:#2563EB,stroke-width:1.5px,color:#1E3A8A
    style P2 fill:#FAF5FF,stroke:#9333EA,stroke-width:1.5px,color:#581C87
    style P3 fill:#ECFDF5,stroke:#059669,stroke-width:1.5px,color:#065F46
    style P4 fill:#FFFBEB,stroke:#D97706,stroke-width:1.5px,color:#92400E
```

---

- **Swagger Documentation**: `http://localhost:8000/docs`
- **Google OAuth Login**: `http://localhost:8000/auth/login`

![Login & Dashboard](./static/screenshot-1.png)

![Create Switch Modal](./static/screenshot-2.png)

![OTP Verification](./static/screenshot-3.png)

![Switch Active Card](./static/screenshot-4.png)

![System Overview](./static/screenshot-5.png)