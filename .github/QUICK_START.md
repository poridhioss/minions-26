# Quick Reference Guide

## 🚀 Getting Started with poridhioss Projects

### Clone Repository
```bash
git clone https://github.com/poridhioss/ml-fastapi-aws.git
cd ml-fastapi-aws
```

### Local Development

#### Backend Setup
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py  # Run FastAPI server (localhost:8000)
```

#### Frontend Setup
```bash
cd frontend
npm install
npm run dev  # Run Next.js server (localhost:3000)
```

#### Using Docker
```bash
docker-compose up --build
# Backend: http://localhost:8000
# Frontend: http://localhost:3000
# API Docs: http://localhost:8000/docs
```

### Running Tests

#### Backend Tests
```bash
pytest tests/ -v --cov
```

#### Frontend Tests
```bash
cd frontend
npm run test
npm run lint
```

### Code Quality Checks

#### Format Code
```bash
# Backend
black .
isort .

# Frontend
cd frontend
npm run prettier
npm run eslint
```

#### Run Pre-commit Checks
```bash
# Python
black --check .
flake8 .
mypy .

# JavaScript
cd frontend
npm run lint
```

## 📝 Git Workflow

### Create Feature Branch
```bash
git checkout develop
git pull origin develop
git checkout -b feature/your-feature-name
```

### Commit Changes
```bash
git add .
git commit -m "feat(scope): description of changes"
```

### Push and Create PR
```bash
git push origin feature/your-feature-name
# Then create PR on GitHub
```

### Update from Main
```bash
git fetch origin
git rebase origin/develop
git push origin feature/your-feature-name --force-with-lease
```

### After PR Approval
```bash
# PR auto-merges or manually:
git checkout develop
git pull origin develop
git branch -d feature/your-feature-name
```

## 🔍 GitHub Setup

### Enable Workflows
Go to **Settings → Actions → General**:
- [x] Allow all actions and reusable workflows
- [x] Allow GitHub-owned actions

### Configure Secrets
**Settings → Secrets and variables → Actions**:
```
AWS_ACCOUNT_ID          = your-account-id
AWS_ROLE_TO_ASSUME      = arn:aws:iam::ACCOUNT:role/ROLE-NAME
SONARCLOUD_TOKEN        = (optional)
```

### Branch Protection
**Settings → Branches → main**:
- [x] Require a pull request before merging
- [x] Require status checks to pass
- [x] Require branches to be up to date
- [x] Require code owner review

## 📦 Dependency Management

### Update Python Packages
```bash
pip install --upgrade pip
pip install -r requirements.txt --upgrade
pip freeze > requirements.txt
```

### Update Node Packages
```bash
cd frontend
npm update
npm audit fix
```

### Security Checks
```bash
# Python
pip-audit

# Node.js
npm audit
cd frontend
npm audit
```

## 🐛 Common Issues & Solutions

### Docker Port Already in Use
```bash
# Free up port
lsof -ti:8000 | xargs kill -9  # Backend
lsof -ti:3000 | xargs kill -9  # Frontend

# Or use different ports
docker-compose up -p 8001:8000 -p 3001:3000
```

### Module Not Found
```bash
# Backend
source venv/bin/activate
pip install -r requirements.txt

# Frontend
cd frontend
rm -rf node_modules package-lock.json
npm install
```

### Git Conflicts
```bash
# View conflicts
git diff

# Resolve manually, then:
git add .
git commit -m "chore: resolve merge conflicts"
```

### CI/CD Failures
1. Check **Actions** tab in GitHub
2. Review error logs
3. Common causes:
   - Missing secrets
   - Dependency version conflicts
   - Test failures

## 📚 Documentation Files

| File | Purpose |
|------|---------|
| [README.md](../README.md) | Project overview |
| [.github/CONTRIBUTING.md](.github/CONTRIBUTING.md) | How to contribute |
| [.github/ARCHITECTURE.md](.github/ARCHITECTURE.md) | System design |
| [SECURITY.md](../SECURITY.md) | Security practices |
| [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) | Community standards |
| [CHANGELOG.md](../CHANGELOG.md) | Version history |
| [AWS_DEPLOYMENT_GUIDE.md](../AWS_DEPLOYMENT_GUIDE.md) | AWS deployment |

## 🔗 Useful Commands

```bash
# Git
git status                    # Check status
git log --oneline -10         # Last 10 commits
git diff                      # Changes not staged
git blame filename            # View change history

# Docker
docker ps                     # Running containers
docker logs container-id      # Container logs
docker exec -it container-id bash  # Enter container

# Python
python -m venv venv           # Create virtual env
pip freeze                    # List packages
python -m pytest -v           # Verbose testing

# Node/npm
npm list                      # List packages
npm outdated                  # Check outdated packages
npm run build                 # Build frontend
```

## 🚀 Deployment

### Manual AWS Deployment
```bash
# Push to main branch (triggers automated deployment)
git push origin feature-branch
# Create PR → Merge to main → Auto-deploys

# Or manually trigger
gh workflow run deploy-aws.yml --ref main
```

### Create Release
```bash
# Tag a commit
git tag -a v1.0.0 -m "Release version 1.0.0"
git push origin v1.0.0

# Workflow automatically creates release and pushes images
```

## 💡 Best Practices

1. **Commit Often** - Small, focused commits
2. **Write Tests** - Aim for 80%+ coverage
3. **Keep PRs Small** - Easier to review
4. **Update Docs** - Always document changes
5. **Use Type Hints** - Especially in Python
6. **Follow Standards** - See ORGANIZATION_STANDARDS.md

## 🆘 Getting Help

1. Check existing [Issues](../../issues)
2. Search [Discussions](../../discussions)
3. Read [CONTRIBUTING.md](.github/CONTRIBUTING.md)
4. Contact [@poridhioss/maintainers](https://github.com/orgs/poridhioss/teams/maintainers)

---

**Last Updated**: June 4, 2024
**For**: poridhioss organization members
