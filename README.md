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
