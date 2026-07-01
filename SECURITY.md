# 🔒 Security Guidelines

## ⚠️ IMPORTANT: Never Commit Sensitive Data

### Files that should NEVER be committed to Git:
- `.env` - Contains database credentials and secrets
- `*.pem`, `*.key` - SSL certificates and private keys
- Any file containing passwords, API keys, or tokens

### How to Set Up Locally:

1. **Copy environment template:**
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` with your credentials:**
   ```bash
   nano .env  # or use your preferred editor
   ```

3. **Set secure database password:**
   ```bash
   DB_PASSWORD=your_secure_password_here
   ```

4. **Commit only `.env.example`, never `.env`:**
   ```bash
   git add .env.example
   git commit -m "Update environment template"
   git push origin main
   ```

### Production Deployment:

When deploying to Cloud Run or any production environment:

```bash
# Set environment variables via gcloud
gcloud run services update hooxi-cms \
  --set-env-vars="DB_PASSWORD=your_production_password,DEBUG=false" \
  --region=us-west1
```

### Security Best Practices:

- ✅ Use strong passwords (min. 12 characters)
- ✅ Rotate credentials regularly
- ✅ Never share `.env` files
- ✅ Use environment variables for secrets
- ✅ Enable HTTPS in production
- ✅ Keep dependencies updated

### Database Connection String Format:

```
postgresql://user:password@host:port/database_name
```

**Example:**
```
postgresql://hooxi:h00x1_s3cr3t!@localhost:5432/hooxi_cms
```

---

## 🚨 If You Suspect a Security Breach:

1. Rotate all credentials immediately
2. Revoke any compromised API keys
3. Review access logs
4. Update this SECURITY.md with incident details

---

*Last Updated: 2026-07-01*
