import redis

# Connect to Redis
r = redis.Redis(host='localhost', port=6379, decode_responses=True)

# Set a test value
r.set("test_key", "Hello Redis")

# Get the value
value = r.get("test_key")
print("Value from Redis:", value)