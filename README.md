# hooxi-cms
## 🗄️ Database Setup

### Local Development (Docker Compose)
```bash
docker-compose up -d postgres backend frontend
```

### Cloud Run with External PostgreSQL
Set environment variables:
```bash
gcloud run services update hooxi-cms \
  --set-env-vars="DATABASE_URL=postgresql://user:pass@host:5432/dbname" \
  --region=us-west1
```

### Database Schema
See `db_init.sql` for initial schema.

## 📋 System Overview (IA-based CRM)

### Core Features:
1. **Customer Management**: Client info, contacts, contract tracking
2. **Workflow Automation**: FMS integration, cost management, reporting
3. **AI Chatbot**: FAQ-based auto-response for customer inquiries
4. **Document Management**: Upload/edit customer documents with version control

### Database Schema:
- `clients`: Main client information table
- `contracts`: Contract details and billing
- `service_requests`: FMS integration requests  
- `chat_logs`: AI chatbot conversation history

See `db_init.sql` for complete schema.

## 📊 Implementation Status

### ✅ Completed (45%)
- [x] Frontend UI Components (5 views)
- [x] Database Schema Design
- [x] Docker Compose Configuration  
- [x] Backend API Endpoints (CRUD operations)
- [x] CORS & Security Headers

### 🔄 In Progress (30%)
- [ ] PostgreSQL Integration
- [ ] Frontend ↔ Backend Connection
- [ ] Authentication System
- [ ] File Upload System

### ⏳ Planned (25%)
- [ ] AI Chatbot Integration
- [ ] Dashboard Charts/Visualization
- [ ] Admin Panel Features

---

## 🚀 Quick Start

### Local Development
```bash
# Start all services
docker-compose up -d postgres backend frontend

# Access URLs:
# Frontend: http://localhost:5173
# Backend API: http://localhost:8000/api/health
# Database: localhost:5432 (PostgreSQL)
```

### Production Deployment
```bash
# Build and push to GitHub
git add . && git commit -m "Update" && git push origin main

# Cloud Run will auto-deploy
# URL: https://hooxi-cms-<region>.run.app
```

---

## 📁 Project Structure

```
hooxi-cms/
├── frontend/              # React SPA (5 views)
│   ├── src/
│   │   ├── App.tsx       # Main app with navigation
│   │   └── views/        # Dashboard, Clients, Chat, Assets, Settings
│   └── package.json
├── backend/               # FastAPI Backend
│   ├── main.py           # API endpoints (CRUD)
│   └── requirements.txt
├── Dockerfile            # Multi-stage build
├── docker-compose.yml    # Service orchestration
└── db_init.sql           # Database schema
```

---

## 🔌 API Endpoints

### Client Management
- `GET /api/clients` - List all clients
- `POST /api/clients` - Create client
- `PUT /api/clients/{id}` - Update client
- `DELETE /api/clients/{id}` - Delete client

### Contracts  
- `GET /api/contracts` - List contracts
- `POST /api/contracts` - Create contract

### Service Requests (FMS)
- `GET /api/service-requests` - List requests
- `POST /api/service-requests` - Create request

### Chat Logs (AI Bot)
- `GET /api/chat-logs/{client_id}` - Get chat history
- `POST /api/chat-logs/{client_id}` - Add message

### Dashboard Stats
- `GET /api/dashboard/stats` - Statistics overview

---

*Last Updated: 2026-07-01 | Status: In Development*
