#!/bin/bash

# AWS Deployment Script for ML FastAPI House Price Predictor
# This script builds Docker images and deploys to AWS ECR and ECS

set -e

# Configuration
AWS_REGION="us-east-1"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
BACKEND_REPO_NAME="ml-api-server"
FRONTEND_REPO_NAME="ml-app-frontend"
IMAGE_TAG="latest"

echo "🚀 Starting AWS Deployment Process..."
echo "AWS Region: $AWS_REGION"
echo "AWS Account ID: $AWS_ACCOUNT_ID"

# Step 1: Login to ECR
echo "📝 Logging in to Amazon ECR..."
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_REGISTRY

# Step 2: Create ECR repositories if they don't exist
echo "📦 Creating ECR repositories..."
aws ecr create-repository --repository-name $BACKEND_REPO_NAME --region $AWS_REGION || echo "Backend repo already exists"
aws ecr create-repository --repository-name $FRONTEND_REPO_NAME --region $AWS_REGION || echo "Frontend repo already exists"

# Step 3: Build and push backend image
echo "🔨 Building backend Docker image..."
docker build -t $ECR_REGISTRY/$BACKEND_REPO_NAME:$IMAGE_TAG .
echo "📤 Pushing backend image to ECR..."
docker push $ECR_REGISTRY/$BACKEND_REPO_NAME:$IMAGE_TAG

# Step 4: Build and push frontend image
echo "🔨 Building frontend Docker image..."
docker build -t $ECR_REGISTRY/$FRONTEND_REPO_NAME:$IMAGE_TAG ./frontend
echo "📤 Pushing frontend image to ECR..."
docker push $ECR_REGISTRY/$FRONTEND_REPO_NAME:$IMAGE_TAG

echo "✅ Docker images built and pushed to ECR successfully!"
echo ""
echo "Backend Image: $ECR_REGISTRY/$BACKEND_REPO_NAME:$IMAGE_TAG"
echo "Frontend Image: $ECR_REGISTRY/$FRONTEND_REPO_NAME:$IMAGE_TAG"
echo ""
echo "📋 Next Steps:"
echo "1. Create ECS cluster: aws ecs create-cluster --cluster-name ml-app-cluster --region $AWS_REGION"
echo "2. Create task definitions and services using the image URIs above"
echo "3. Update security groups to allow traffic between frontend and backend"
echo "4. Configure Application Load Balancer (ALB) for frontend access"
