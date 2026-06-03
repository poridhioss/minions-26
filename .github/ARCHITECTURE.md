# Architecture Guide

## System Overview

```
┌─────────────────────────────────────────────┐
│          Users / Clients                    │
└────────────────┬────────────────────────────┘
                 │
                 ↓ HTTP/HTTPS
┌─────────────────────────────────────────────┐
│       Next.js Frontend (Port 3000)          │
│  - React Components                         │
│  - Tailwind CSS Styling                     │
│  - Client-side Form Validation              │
└────────────────┬────────────────────────────┘
                 │
                 ↓ REST API Calls (JSON)
┌─────────────────────────────────────────────┐
│      FastAPI Backend (Port 8000)            │
│  - Pydantic Models & Validation             │
│  - ML Model Integration                     │
│  - CORS Enabled                             │
│  - Health Checks                            │
└────────────────┬────────────────────────────┘
                 │
                 ↓ File I/O
┌─────────────────────────────────────────────┐
│      Machine Learning Models                │
│  - model.pkl (Trained Model)                │
│  - columns.pkl (Feature Metadata)           │
└─────────────────────────────────────────────┘
```

## Component Architecture

### Frontend (Next.js)
- **Framework**: Next.js 14+ with TypeScript
- **Styling**: Tailwind CSS
- **Components**:
  - `PredictionForm`: User input form
  - `ResultCard`: Display prediction results
- **Pages**:
  - `/`: Home/main prediction page

### Backend (FastAPI)
- **Framework**: FastAPI (async-capable)
- **Runtime**: Uvicorn ASGI server
- **Features**:
  - RESTful API endpoints
  - Input validation with Pydantic
  - CORS middleware
  - Health check endpoint

### ML Model
- **Language**: Python/scikit-learn
- **Input**: 8 features (housing attributes)
- **Output**: Predicted house price
- **Format**: Pickle (pkl) files

## Deployment Architecture

### Docker Containerization

```
Docker Image (Backend)
├── Python 3.11 Base
├── Dependencies (requirements.txt)
├── Application Code (main.py, train.py)
└── ML Models (model.pkl, columns.pkl)

Docker Image (Frontend)
├── Node 20 Base
├── Next.js Build
├── Static Assets
└── Configuration
```

### Docker Compose Orchestration
```yaml
Services:
├── backend: FastAPI service
├── frontend: Next.js service
└── Network: ml-app-network
```

### AWS ECS Deployment
```
AWS Account
├── ECR (Elastic Container Registry)
│   ├── Backend Image Repository
│   └── Frontend Image Repository
├── ECS Cluster (ml-fastapi-cluster)
│   ├── Backend Service
│   ├── Frontend Service
│   └── Load Balancer
├── RDS (Optional: Database)
└── S3 (Optional: Model Storage)
```

## Data Flow

### Prediction Request Flow

1. **User Interaction**
   - User fills form with housing attributes
   - Frontend validates input

2. **API Request**
   - Frontend sends POST request to `/predict`
   - Request body contains feature values

3. **Backend Processing**
   - FastAPI validates request data
   - Loads ML model from pickle file
   - Generates prediction
   - Returns JSON response

4. **UI Update**
   - Frontend receives prediction
   - Displays result in ResultCard component

### Training Flow

1. **Data Preparation**
   - Load housing.csv dataset
   - Feature engineering
   - Train-test split

2. **Model Training**
   - Scikit-learn algorithm training
   - Hyperparameter tuning
   - Model evaluation

3. **Model Persistence**
   - Save model.pkl
   - Save columns.pkl (feature names)

## Key Features

### Security
- Input validation (Pydantic)
- CORS configuration
- HTTPS support
- Environment variable management
- Dependency scanning

### Scalability
- Containerized architecture
- Horizontal scaling via ECS
- Load balancing
- Stateless services

### Reliability
- Health checks
- Error handling
- Logging
- Monitoring (CloudWatch)

### Developer Experience
- Docker Compose for local development
- GitHub Actions CI/CD
- Automated testing
- Code quality checks

## Technology Stack

### Backend
- **Framework**: FastAPI
- **Server**: Uvicorn
- **ML**: scikit-learn
- **Data**: pandas, numpy
- **Validation**: Pydantic
- **Testing**: pytest

### Frontend
- **Framework**: Next.js
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **Testing**: Jest (optional)

### DevOps
- **Containerization**: Docker
- **Orchestration**: Docker Compose, AWS ECS
- **Registry**: GitHub Container Registry, Amazon ECR
- **CI/CD**: GitHub Actions
- **Cloud**: AWS (ECS, ECR, CloudWatch)

## File Structure

```
ml-fastapi-aws/
├── main.py                 # FastAPI application
├── train.py               # ML model training script
├── model.pkl              # Trained ML model
├── columns.pkl            # Feature names
├── requirements.txt       # Python dependencies
├── Dockerfile             # Backend container
├── docker-compose.yml     # Local development
├── housing.csv            # Training dataset
│
├── frontend/
│   ├── package.json       # Node dependencies
│   ├── next.config.ts     # Next.js config
│   ├── tsconfig.json      # TypeScript config
│   ├── Dockerfile         # Frontend container
│   │
│   ├── app/
│   │   ├── page.tsx       # Home page
│   │   ├── layout.tsx     # Root layout
│   │   └── globals.css    # Global styles
│   │
│   └── components/
│       ├── PredictionForm.tsx
│       └── ResultCard.tsx
│
├── .github/
│   ├── workflows/
│   │   ├── ci-cd.yml      # Main CI/CD pipeline
│   │   ├── deploy-aws.yml # AWS deployment
│   │   └── code-quality.yml
│   │
│   ├── CONTRIBUTING.md    # Contribution guidelines
│   ├── CODEOWNERS         # Code ownership
│   ├── dependabot.yml     # Dependency updates
│   │
│   └── ISSUE_TEMPLATE/
│       ├── bug_report.md
│       ├── feature_request.md
│       └── documentation.md
│
└── .editorconfig          # Editor settings
```

## Performance Considerations

- **Backend**: Async operations with FastAPI
- **Frontend**: Static site generation (SSG) when possible
- **Caching**: Browser caching for static assets
- **Model Loading**: Loaded once on startup
- **Database**: N/A (stateless design)

## Monitoring & Logging

- **Application Logs**: CloudWatch (AWS)
- **Container Logs**: Docker logs
- **Metrics**: CloudWatch metrics
- **Alerts**: CloudWatch alarms
- **Health Checks**: Regular endpoint monitoring

## Future Enhancements

- [ ] Add database for prediction history
- [ ] Implement user authentication
- [ ] Add batch prediction capability
- [ ] Multi-model support
- [ ] Real-time model retraining
- [ ] Advanced analytics dashboard
- [ ] GraphQL API option

---

For implementation details, refer to [README.md](../README.md) and the deployment guide [AWS_DEPLOYMENT_GUIDE.md](../AWS_DEPLOYMENT_GUIDE.md).
