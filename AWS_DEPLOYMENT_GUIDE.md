# 🏠 House Price Predictor - AWS Deployment Guide

This guide walks you through deploying the complete ML application (FastAPI backend + Next.js frontend) to AWS.

## 📋 Prerequisites

- AWS Account with appropriate permissions
- AWS CLI configured locally (`aws configure`)
- Docker and Docker Compose installed
- Git repository set up

## 🏗️ Project Structure

```
ml-fastapi-aws/
├── main.py                      # FastAPI backend
├── train.py                     # ML model training script
├── model.pkl                    # Trained ML model
├── columns.pkl                  # Feature columns
├── requirements.txt             # Python dependencies
├── Dockerfile                   # Backend container
├── docker-compose.yml           # Local orchestration
├── deploy-to-aws.sh            # AWS deployment script
├── frontend/                    # Next.js application
│   ├── app/
│   │   ├── page.tsx            # Main page
│   │   └── layout.tsx          # Layout
│   ├── components/
│   │   ├── PredictionForm.tsx  # Form component
│   │   └── ResultCard.tsx      # Result display
│   ├── Dockerfile
│   ├── package.json
│   └── .env.local
├── aws-backend-task-def.json    # ECS task definition
└── aws-frontend-task-def.json   # ECS task definition
```

## 🚀 Local Development

### 1. Run with Docker Compose

```bash
cd /home/iftakhar/ml-fastapi-aws
docker-compose up --build
```

- Backend will be available at `http://localhost:8000`
- Frontend will be available at `http://localhost:3000`

### 2. Manual Development

**Backend:**
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

## ☁️ AWS Deployment Steps

### Step 1: Prepare AWS Environment

```bash
# Set your AWS region
export AWS_REGION="us-east-1"
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Create CloudWatch log groups
aws logs create-log-group --log-group-name /ecs/ml-api-server --region $AWS_REGION
aws logs create-log-group --log-group-name /ecs/ml-app-frontend --region $AWS_REGION
```

### Step 2: Build and Push Docker Images

```bash
# Make the deployment script executable
chmod +x deploy-to-aws.sh

# Run the deployment script
./deploy-to-aws.sh
```

This will:
- Build Docker images
- Create ECR repositories
- Push images to Amazon ECR

### Step 3: Create ECS Cluster

```bash
# Create the ECS cluster
aws ecs create-cluster \
  --cluster-name ml-app-cluster \
  --region $AWS_REGION
```

### Step 4: Create VPC and Security Groups

```bash
# Create VPC (or use default VPC)
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=is-default,Values=true" --query "Vpcs[0].VpcId" --output text)

# Create security group for backend
BACKEND_SG=$(aws ec2 create-security-group \
  --group-name ml-backend-sg \
  --description "Security group for ML API backend" \
  --vpc-id $VPC_ID \
  --query 'GroupId' \
  --output text)

# Allow traffic on port 8000
aws ec2 authorize-security-group-ingress \
  --group-id $BACKEND_SG \
  --protocol tcp \
  --port 8000 \
  --cidr 0.0.0.0/0

# Create security group for frontend
FRONTEND_SG=$(aws ec2 create-security-group \
  --group-name ml-frontend-sg \
  --description "Security group for frontend" \
  --vpc-id $VPC_ID \
  --query 'GroupId' \
  --output text)

# Allow traffic on port 3000
aws ec2 authorize-security-group-ingress \
  --group-id $FRONTEND_SG \
  --protocol tcp \
  --port 3000 \
  --cidr 0.0.0.0/0
```

### Step 5: Create Task Definitions

```bash
# Update the account ID in the task definitions
sed -i "s/YOUR_AWS_ACCOUNT_ID/$AWS_ACCOUNT_ID/g" aws-backend-task-def.json
sed -i "s/YOUR_AWS_ACCOUNT_ID/$AWS_ACCOUNT_ID/g" aws-frontend-task-def.json

# Register backend task definition
aws ecs register-task-definition \
  --cli-input-json file://aws-backend-task-def.json \
  --region $AWS_REGION

# Register frontend task definition
aws ecs register-task-definition \
  --cli-input-json file://aws-frontend-task-def.json \
  --region $AWS_REGION
```

### Step 6: Create Load Balancer

```bash
# Create Application Load Balancer for backend
BACKEND_ALB=$(aws elbv2 create-load-balancer \
  --name ml-backend-alb \
  --subnets $(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --query "Subnets[].SubnetId" --output text | tr '\t' ' ') \
  --security-groups $BACKEND_SG \
  --region $AWS_REGION \
  --query 'LoadBalancers[0].LoadBalancerArn' \
  --output text)

# Create target group for backend
BACKEND_TARGET_GROUP=$(aws elbv2 create-target-group \
  --name ml-backend-tg \
  --protocol HTTP \
  --port 8000 \
  --vpc-id $VPC_ID \
  --target-type ip \
  --health-check-enabled \
  --health-check-path "/" \
  --region $AWS_REGION \
  --query 'TargetGroups[0].TargetGroupArn' \
  --output text)

# Create listener for backend ALB
aws elbv2 create-listener \
  --load-balancer-arn $BACKEND_ALB \
  --protocol HTTP \
  --port 8000 \
  --default-actions Type=forward,TargetGroupArn=$BACKEND_TARGET_GROUP \
  --region $AWS_REGION

# Similar steps for frontend ALB...
```

### Step 7: Create ECS Services

```bash
# Get subnets and security group IDs
SUBNETS=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --query "Subnets[0:2].SubnetId" --output text | tr '\t' ',')

# Create backend service
aws ecs create-service \
  --cluster ml-app-cluster \
  --service-name ml-api-server \
  --task-definition ml-api-server:1 \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$BACKEND_SG],assignPublicIp=ENABLED}" \
  --region $AWS_REGION

# Create frontend service
aws ecs create-service \
  --cluster ml-app-cluster \
  --service-name ml-app-frontend \
  --task-definition ml-app-frontend:1 \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNETS],securityGroups=[$FRONTEND_SG],assignPublicIp=ENABLED}" \
  --region $AWS_REGION
```

## 📊 Monitoring

### CloudWatch Logs

```bash
# View backend logs
aws logs tail /ecs/ml-api-server --follow --region $AWS_REGION

# View frontend logs
aws logs tail /ecs/ml-app-frontend --follow --region $AWS_REGION
```

### ECS Tasks

```bash
# List running tasks
aws ecs list-tasks --cluster ml-app-cluster --region $AWS_REGION

# Describe task
aws ecs describe-tasks \
  --cluster ml-app-cluster \
  --tasks <task-arn> \
  --region $AWS_REGION
```

## 🔗 Access Your Application

Once deployed:

1. Get the frontend ALB DNS:
```bash
aws elbv2 describe-load-balancers \
  --region $AWS_REGION \
  --query "LoadBalancers[?LoadBalancerName=='ml-frontend-alb'].DNSName" \
  --output text
```

2. Open the DNS name in your browser to access the beautiful UI!

## 🛡️ Security Considerations

1. **CORS**: Update the CORS origins in `main.py` to your frontend domain
2. **API Gateway**: Consider adding AWS API Gateway for additional security
3. **IAM Roles**: Use proper IAM roles for ECS tasks
4. **Secrets Manager**: Store sensitive data in AWS Secrets Manager
5. **SSL/TLS**: Use AWS Certificate Manager for HTTPS

## 💰 Cost Optimization

- Use AWS Fargate Spot for cost savings on non-critical tasks
- Implement auto-scaling based on CPU/memory metrics
- Use Amazon RDS if you need persistent storage
- Consider CloudFront for frontend distribution

## 🐛 Troubleshooting

### Container won't start
```bash
aws ecs describe-tasks --cluster ml-app-cluster --tasks <task-arn> --region $AWS_REGION
```

### Check service events
```bash
aws ecs describe-services \
  --cluster ml-app-cluster \
  --services ml-api-server \
  --region $AWS_REGION
```

### View container logs
```bash
aws logs tail /ecs/ml-api-server --follow --region $AWS_REGION
```

## 📚 Additional Resources

- [AWS ECS Documentation](https://docs.aws.amazon.com/ecs/)
- [AWS ECR Documentation](https://docs.aws.amazon.com/ecr/)
- [Fargate Pricing](https://aws.amazon.com/fargate/pricing/)
- [Application Load Balancer](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/)

## 🎉 Success!

Your ML-powered house price predictor is now running on AWS with a beautiful frontend interface!
