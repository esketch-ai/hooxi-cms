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
