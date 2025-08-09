# 🚀 Blockchain Watermarking System - CI/CD Production Setup

A Django-based blockchain watermarking system with automated CI/CD deployment pipeline.

## 📋 Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [CI/CD Pipeline](#cicd-pipeline)
- [Environment Configuration](#environment-configuration)
- [Deployment](#deployment)
- [Development](#development)
- [Monitoring](#monitoring)
- [Backup & Maintenance](#backup--maintenance)
- [Troubleshooting](#troubleshooting)

## ✨ Features

- **Blockchain-based watermarking** for image integrity
- **Real-time WebSocket communication** for mining and blockchain updates
- **Automated CI/CD pipeline** with GitHub Actions
- **Docker containerization** for consistent deployments
- **Redis caching** for improved performance
- **PostgreSQL database** for production reliability
- **Nginx reverse proxy** with SSL support
- **Monitoring stack** (Prometheus + Grafana)
- **Automated backups** and maintenance

## 🔧 Prerequisites

- Docker and Docker Compose
- Git
- GitHub repository with Actions enabled
- Production server with SSH access

## 🚀 Quick Start

### 1. Clone the Repository
```bash
git clone <your-repo-url>
cd watermarking
```

### 2. Configure GitHub Secrets
Set up the following secrets in your GitHub repository settings (`Settings > Secrets and variables > Actions`):

```bash
# Database Configuration
POSTGRES_DB=watermarker_prod
POSTGRES_USER=watermarker
POSTGRES_PASSWORD=your-secure-password

# Redis Configuration
REDIS_PASSWORD=your-redis-password

# Django Configuration
DJANGO_ALLOWED_HOSTS=your-domain.com,www.your-domain.com

# Docker Hub (for image storage)
DOCKERHUB_USERNAME=your-dockerhub-username
DOCKERHUB_TOKEN=your-dockerhub-token

# Server Access
SSH_HOST=your-server-ip
SSH_USERNAME=your-server-username
SSH_PRIVATE_KEY=your-ssh-private-key
SSH_PORT=22  # Optional, defaults to 22
```

### 3. Deploy
Push to the `main` branch to trigger automatic deployment:
```bash
git push origin main
```

## 🔄 CI/CD Pipeline

The system uses GitHub Actions for automated deployment with three main workflows:

### 1. Production Deployment (`deploy.yml`)
**Triggered**: On push to `main` branch
**Features**:
- Automated testing before deployment
- Docker image building and pushing
- Environment file generation
- Database migrations
- Health checks
- ASGI server validation

### 2. Development Server (`dev-server.yml`)
**Triggered**: Manual workflow dispatch
**Features**:
- Redis setup and validation
- Development environment setup
- ASGI server startup
- WebSocket endpoint testing

### 3. Backup & Maintenance (`backup-maintenance.yml`)
**Triggered**: Daily at 2 AM (configurable)
**Features**:
- Automated database backups
- Media file backups
- System cleanup
- Log rotation
- Service health checks

## 🌍 Environment Configuration

The CI/CD pipeline automatically generates a `.env` file with the following structure:

```env
# Security
DJANGO_SECRET_KEY=auto-generated-secure-key
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=your-configured-hosts

# Database
POSTGRES_DB=your-db-name
POSTGRES_USER=your-db-user
POSTGRES_PASSWORD=your-db-password
DATABASE_URL=postgresql://user:pass@db:5432/dbname

# Cache
REDIS_PASSWORD=your-redis-password
```

## 🚀 Deployment

### Automatic Deployment
1. Push changes to the `main` branch
2. GitHub Actions automatically:
   - Runs tests
   - Builds Docker images
   - Deploys to production
   - Runs health checks

### Manual Deployment
Trigger deployment manually from GitHub Actions:
1. Go to `Actions` tab in your repository
2. Select `Deploy to Production` workflow
3. Click `Run workflow`

### Development Environment
Start a development server:
1. Go to `Actions` tab
2. Select `Development Server` workflow
3. Choose environment (development/staging)
4. Click `Run workflow`

## 📊 Monitoring

Access the monitoring stack after deployment:

- **Application**: `http://your-domain.com`
- **Grafana**: `http://your-domain.com:3000`
- **Prometheus**: `http://your-domain.com:9090`
- **Redis Insight**: `http://your-domain.com:8001`
- **Admin Panel**: `http://your-domain.com/admin`

### WebSocket Endpoints
- Blockchain updates: `ws://your-domain.com/ws/blockchain/`
- Mining status: `ws://your-domain.com/ws/mining/`

## 💾 Backup & Maintenance

### Automated Backups
- **Schedule**: Daily at 2 AM UTC
- **Retention**: 7 days
- **Includes**: Database, media files, logs
- **Location**: `backups/` directory on server

### Manual Backup
Trigger backup manually from GitHub Actions:
1. Go to `Actions` tab
2. Select `Backup and Maintenance` workflow
3. Click `Run workflow`

### Restore from Backup
```bash
# On your server
cd /home/beb/PycharmProjects/watermarking
tar -xzf backups/prod_backup_YYYYMMDD_HHMMSS.tar.gz
docker compose exec -T db psql -U $POSTGRES_USER -d $POSTGRES_DB < backup_folder/database.sql
```

## 🛠️ Development

### Local Development Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Start Redis
redis-server

# Run migrations
cd watermarker
python manage.py migrate

# Start development server
python manage.py runserver
# Or start ASGI server
daphne -p 8000 watermarker.asgi:application
```

### Docker Development
```bash
# Start development stack
docker compose up -d

# Run commands in container
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

## 🔍 Troubleshooting

### Common Issues

1. **Deployment Fails**
   - Check GitHub Actions logs
   - Verify all secrets are configured
   - Ensure server has Docker installed

2. **Database Connection Issues**
   - Verify PostgreSQL credentials
   - Check network connectivity
   - Ensure database container is running

3. **Redis Connection Issues**
   - Verify Redis password
   - Check Redis container status
   - Test connection: `redis-cli ping`

4. **WebSocket Connection Issues**
   - Check ASGI server logs
   - Verify WebSocket URLs
   - Test with browser developer tools

### Logs and Monitoring
```bash
# View application logs
docker compose logs -f web

# View all service logs
docker compose logs -f

# Check service status
docker compose ps

# Monitor resource usage
docker stats
```

### Health Checks
The deployment pipeline includes automatic health checks:
- Database connectivity
- Redis connectivity
- ASGI server status
- WebSocket endpoint availability

## 📚 Architecture

```
┌─────────────────┐    ┌──────────────┐    ┌─────────────┐
│   GitHub        │    │   Docker     │    │   Server    │
│   Actions       │───▶│   Hub        │───▶│   Deploy    │
│   CI/CD         │    │   Registry   │    │   Production│
└─────────────────┘    └──────────────┘    └─────────────┘
                                                   │
                                           ┌───────▼───────┐
                                           │ Load Balancer │
                                           │   (Nginx)     │
                                           └───────┬───────┘
                                                   │
                                    ┌──────────────▼──────────────┐
                                    │     Django ASGI Server      │
                                    │    (Daphne + WebSockets)    │
                                    └──────────────┬──────────────┘
                                                   │
                              ┌────────────────────┼───────────────────┐
                              │                    │                   │
                    ┌─────────▼────────┐  ┌────────▼────────┐  ┌───────▼───────┐
                    │   PostgreSQL     │  │     Redis       │  │   Monitoring  │
                    │   Database       │  │     Cache       │  │ (Prometheus + │
                    │                  │  │                 │  │   Grafana)    │
                    └──────────────────┘  └─────────────────┘  └───────────────┘
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Push to your fork
5. Create a Pull Request

The CI/CD pipeline will automatically test your changes when you create a PR.

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
