"""Upload the fine-tuned Legal-BERT checkpoint to a Hugging Face Hub repo.

Why this exists
---------------
The Legal-BERT checkpoint lives in ``./saved_model/`` and is ~418 MB. That
is too large to commit to git or ship inside a Docker image for free-tier
hosting. Instead, this script pushes the checkpoint to a (private, if you
prefer) Hugging Face Hub model repo. The runtime (in ``app/main.py``) then
downloads it on cold start using the ``HF_MODEL_ID`` and ``HF_TOKEN`` env
vars.

Prerequisites
-------------
    pip install huggingface_hub
    # Authenticate once:
    huggingface-cli login
        -- or --
    set HF_TOKEN=hf_xxx...        (PowerShell: $env:HF_TOKEN="hf_xxx...")

Usage
-----
    # Create-or-update a public model repo (your namespace):
    python scripts/upload_to_hf.py --repo-id yourname/legal-bert-scotus

    # Private repo:
    python scripts/upload_to_hf.py --repo-id yourname/legal-bert-scotus --private

    # Push an alternative checkpoint directory:
    python scripts/upload_to_hf.py --repo-id yourname/legal-bert-scotus \\
        --local-dir ./checkpoints/v2

The script will create the repo if it does not exist, then upload every
file inside ``--local-dir`` (default: ``saved_model/``).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--repo-id",
        required=True,
        help="Target Hub repo, e.g. 'yourname/legal-bert-scotus'.",
    )
    p.add_argument(
        "--local-dir",
        default="saved_model",
        help="Directory whose contents will be uploaded (default: ./saved_model).",
    )
    p.add_argument(
        "--private",
        action="store_true",
        help="Create the repo as private (default: public).",
    )
    p.add_argument(
        "--commit-message",
        default="Upload Legal-BERT SCOTUS checkpoint",
        help="Git commit message for the upload.",
    )
    p.add_argument(
        "--token",
        default=os.environ.get("HF_TOKEN"),
        help="HF API token (default: $HF_TOKEN).",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    local_dir = Path(args.local_dir).resolve()
    if not local_dir.is_dir():
        print(f"error: {local_dir} is not a directory", file=sys.stderr)
        return 2

    # Lazy import so the script still --help's without huggingface_hub.
    from huggingface_hub import HfApi, create_repo

    api = HfApi(token=args.token)

    print(f"Ensuring repo {args.repo_id!r} exists (private={args.private})...")
    repo_url = create_repo(
        repo_id=args.repo_id,
        token=args.token,
        private=args.private,
        exist_ok=True,
        repo_type="model",
    )
    print(f"  -> {repo_url}")

    print(f"Uploading contents of {local_dir} ...")
    api.upload_folder(
        folder_path=str(local_dir),
        repo_id=args.repo_id,
        repo_type="model",
        commit_message=args.commit_message,
        token=args.token,
    )
    print("Done.")
    print()
    print("Next steps:")
    print(f"  1. Note the repo id:  {args.repo_id}")
    print("  2. When deploying your Space, set the env vars:")
    print(f"        HF_MODEL_ID={args.repo_id}")
    print("        HF_TOKEN=<your token>          # only needed if the repo is private")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
