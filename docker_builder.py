import docker
import os

def build_image(job_id, clone_dir):
    # create docker client inside function, not at module level
    client = docker.from_env()
    
    dockerfile_path = os.path.join(clone_dir, "Dockerfile")
    if not os.path.exists(dockerfile_path):
        return False, "Dockerfile not found in repo"

    image_tag = f"build-runner/{job_id}:latest"

    try:
        image, logs = client.images.build(
            path=clone_dir,
            tag=image_tag,
            rm=True
        )

        for log in logs:
            if "stream" in log:
                print(log["stream"].strip())

        return True, image_tag

    except docker.errors.BuildError as e:
        return False, str(e)
    except Exception as e:
        return False, str(e)