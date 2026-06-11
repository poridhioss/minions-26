# use official python image as base
FROM python:3.12-slim

# set working directory inside container
WORKDIR /app

# install git so worker can clone repos
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# copy requirements first for better caching
COPY requirements.txt .

# install all dependencies
RUN pip install --no-cache-dir -r requirements.txt

# copy all project files
COPY . .

# expose port 8000 for FastAPI
EXPOSE 8000

# start the FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]