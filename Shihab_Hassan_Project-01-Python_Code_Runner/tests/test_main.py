"""Simple unit tests — no Docker required.

Run:  pytest -v
"""

from __future__ import annotations

import time

from app.main import validate_code, RateLimiter


# ── validate_code ───────────────────────────────────────────────────

class TestValidateCode:
    def test_valid_print(self):
        assert validate_code("print('hi')") is None

    def test_valid_math(self):
        assert validate_code("print(2 + 2)") is None

    def test_empty(self):
        assert validate_code("") is not None
        assert validate_code("   \n  ") is not None

    def test_too_long(self):
        long = "x = 1\n" * 2000
        err = validate_code(long)
        assert err and "long" in err.lower()

    def test_blocks_os_system(self):
        assert validate_code("import os; os.system('id')") is not None

    def test_blocks_subprocess(self):
        assert validate_code("import subprocess") is not None

    def test_blocks_eval(self):
        assert validate_code("eval('1+1')") is not None

    def test_blocks_exec(self):
        assert validate_code("exec('print(1)')") is not None

    def test_blocks_open_write(self):
        assert validate_code("open('x', 'w')") is not None

    def test_blocks_shutil(self):
        assert validate_code("import shutil") is not None

    def test_blocks_socket(self):
        assert validate_code("import socket") is not None

    def test_blocks_requests(self):
        assert validate_code("import requests") is not None


# ── RateLimiter ─────────────────────────────────────────────────────

class TestRateLimiter:
    def test_under_limit_allowed(self):
        rl = RateLimiter(max_requests=3, window_seconds=60)
        assert rl.check("ip1") is True
        assert rl.check("ip1") is True
        assert rl.check("ip1") is True

    def test_over_limit_blocked(self):
        rl = RateLimiter(max_requests=2, window_seconds=60)
        rl.check("ip1")
        rl.check("ip1")
        assert rl.check("ip1") is False

    def test_ips_independent(self):
        rl = RateLimiter(max_requests=1, window_seconds=60)
        assert rl.check("a") is True
        assert rl.check("b") is True   # different IP, fresh quota

    def test_window_expiry(self):
        rl = RateLimiter(max_requests=1, window_seconds=1)
        assert rl.check("x") is True
        assert rl.check("x") is False
        time.sleep(1.1)
        assert rl.check("x") is True
