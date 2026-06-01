# 🏠 House Price Predictor - ML FastAPI + Next.js

A beautiful, production-ready ML application that predicts house prices using advanced machine learning. Built with FastAPI backend and Next.js frontend, fully containerized and ready for AWS deployment.

![Architecture](./docs/architecture.png)

## ✨ Features

- 🎯 **Accurate ML Model**: Trained on California housing dataset
- 🎨 **Beautiful UI**: Modern, responsive Next.js frontend with Tailwind CSS
- ⚡ **Fast API**: RESTful FastAPI backend with CORS support
- 🐳 **Fully Dockerized**: Both frontend and backend containerized
- ☁️ **AWS Ready**: Complete deployment guides and scripts
- 📊 **Real-time Predictions**: Get instant house price estimates
- 🔄 **Scalable**: Can be easily deployed to AWS ECS Fargate

## 🏗️ Architecture

```
┌─────────────────────────────────────────┐
│         Next.js Frontend                │
│     (Port 3000 - Beautiful UI)          │
└────────────┬────────────────────────────┘
             │ HTTP
             ↓
┌─────────────────────────────────────────┐
│         FastAPI Backend                 │
│    (Port 8000 - REST API)               │
│  - ML Model Integration                 │
│  - CORS Enabled                         │
└─────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.10+ (for local development)
- Node.js 20+ (for frontend development)
- AWS Account (for cloud deployment)

### Local Development with Docker

```bash
# Clone the repository
git clone <your-repo-url>
cd ml-fastapi-aws

# Start both services with Docker Compose
docker-compose up --build

# Application will be available at:
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
```

### Manual Local Development

**Start Backend:**
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

**Start Frontend:**
```bash
cd frontend
npm install
npm run dev
```

## 📁 Project Structure

```
ml-fastapi-aws/
├── main.py                        # FastAPI application
├── train.py                       # ML model training script
├── model.pkl                      # Trained sklearn model
├── columns.pkl                    # Feature columns for preprocessing
├── housing.csv                    # Training dataset
├── requirements.txt               # Python dependencies
├── Dockerfile                     # Backend container
├── docker-compose.yml             # Local orchestration
│
├── frontend/                      # Next.js application
│   ├── app/
│   │   ├── page.tsx              # Main prediction page
│   │   ├── layout.tsx            # Root layout
│   │   └── globals.css           # Global styles
│   ├── components/
│   │   ├── PredictionForm.tsx    # Input form component
│   │   └── ResultCard.tsx        # Result display component
│   ├── public/                   # Static assets
│   ├── Dockerfile                # Frontend container
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── .env.local                # Local environment variables
│   └── .dockerignore
│
├── AWS_DEPLOYMENT_GUIDE.md        # Comprehensive AWS deployment guide
├── deploy-to-aws.sh               # Automated AWS deployment script
├── aws-backend-task-def.json      # ECS task definition
├── aws-frontend-task-def.json     # ECS task definition
└── .gitignore

```

## 🎯 How to Use

1. **Visit the Frontend**: Open `http://localhost:3000` in your browser
2. **Enter Property Details**: Fill in the property information form
3. **Get Prediction**: Click "Predict Price" button
4. **View Results**: See the estimated house price instantly!

### Sample Input Values
- **Longitude**: -122.23
- **Latitude**: 37.88
- **Housing Median Age**: 41
- **Total Rooms**: 880
- **Total Bedrooms**: 129
- **Population**: 322
- **Households**: 126
- **Median Income**: 8.3252
- **Ocean Proximity**: <1H Ocean

## 🔧 API Endpoints

### GET /
Health check endpoint
```bash
curl http://localhost:8000/
```

### POST /predict
Make a price prediction
```bash
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "longitude": -122.23,
    "latitude": 37.88,
    "housing_median_age": 41,
    "total_rooms": 880,
    "total_bedrooms": 129,
    "population": 322,
    "households": 126,
    "median_income": 8.3252,
    "ocean_proximity": "<1H Ocean"
  }'
```

Response:
```json
{
  "predicted_house_price": "$452,600.00"
}
```

## ☁️ AWS Deployment

### Quick Deployment

```bash
# Make script executable
chmod +x deploy-to-aws.sh

# Run deployment
./deploy-to-aws.sh
```

This will:
- Build Docker images
- Create ECR repositories
- Push images to Amazon ECR
- Display next steps for ECS deployment

### Detailed Steps

See [AWS_DEPLOYMENT_GUIDE.md](./AWS_DEPLOYMENT_GUIDE.md) for:
- Complete step-by-step instructions
- Security best practices
- Cost optimization tips
- Monitoring and troubleshooting

## 🛠️ Technology Stack

### Backend
- **FastAPI**: Modern Python web framework
- **Uvicorn**: ASGI web server
- **scikit-learn**: ML model framework
- **pandas**: Data manipulation
- **joblib**: Model persistence

### Frontend
- **Next.js 16**: React framework with App Router
- **TypeScript**: Type-safe JavaScript
- **Tailwind CSS**: Utility-first CSS framework
- **React 19**: UI library

### DevOps
- **Docker**: Containerization
- **Docker Compose**: Multi-container orchestration
- **AWS ECS**: Container orchestration
- **AWS ECR**: Container registry
- **AWS Fargate**: Serverless containers

## 📊 ML Model Details

- **Algorithm**: Gradient Boosting Regressor
- **Dataset**: California Housing Dataset (20,640 samples)
- **Features**: 9 input variables (numerical and categorical)
- **Training Data**: housing.csv
- **Model File**: model.pkl (143 MB)

## 🔐 Security Features

- ✅ CORS enabled for frontend-backend communication
- ✅ Input validation with Pydantic
- ✅ Health checks on containers
- ✅ Proper error handling
- ✅ Environment-based configuration

## 📝 Environment Variables

**Frontend (.env.local):**
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

**Docker Compose:**
```
NEXT_PUBLIC_API_URL=http://backend:8000
```

**AWS Production:**
```
NEXT_PUBLIC_API_URL=http://backend-alb-dns:8000
```

## 🚀 Performance

- Frontend: Static Next.js build (~2 seconds first load)
- Backend: ML inference in < 100ms
- API Response: < 500ms total time

## 🐛 Troubleshooting

### Backend won't connect
- Check if FastAPI is running: `curl http://localhost:8000/`
- Check Docker logs: `docker-compose logs backend`

### Frontend shows error
- Check API URL in `.env.local`
- Open browser console (F12) for error messages
- Ensure backend is accessible

### Docker build issues
- Clear cache: `docker-compose down -v`
- Rebuild: `docker-compose up --build`

## 📚 Documentation

- [Backend API Docs](http://localhost:8000/docs) - Auto-generated Swagger UI
- [AWS Deployment Guide](./AWS_DEPLOYMENT_GUIDE.md)
- [Training Script](./train.py)

## 💡 Tips

- The model is pre-trained. To retrain: `python train.py`
- Frontend is fully responsive and mobile-friendly
- API includes automatic CORS handling for cross-origin requests
- Docker images are multi-stage for optimized size

## 🎓 Learning Resources

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Next.js Documentation](https://nextjs.org/docs)
- [Docker Documentation](https://docs.docker.com/)
- [AWS ECS Guide](https://docs.aws.amazon.com/ecs/)

## 📄 License

MIT License - feel free to use this project!

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📞 Support

For issues and questions:
1. Check the troubleshooting section
2. Review the AWS deployment guide
3. Open an issue on GitHub

---

**Built with ❤️ using FastAPI + Next.js**

*Ready to predict house prices with beautiful UI and scalable infrastructure!* 🚀
