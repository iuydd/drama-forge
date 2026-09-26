#!/usr/bin/env python3
"""单独跑 providers.py 的离线自测；测试正文在 merged_selftest.py 的 test_video_produce_providers。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merged_selftest import test_video_produce_providers  # noqa: E402

if __name__ == "__main__":
    test_video_produce_providers()
    print("ok   test_video_produce_providers")
