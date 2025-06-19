#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
リポジトリセキュリティ監査ツール設定ファイル
"""

import os
import yaml
from typing import Dict, Any

# 設定ファイルのパス
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.yaml")

# デフォルト設定
DEFAULT_CONFIG = {
    "openai_api_key": None,
    "model": "gpt-4o-mini",
    "max_tokens": 1000,
    "temperature": 0.7,
    "max_retries": 3,
    "retry_delay": 2,
    "backoff_factor": 2,
    "data_dir": "./data"
}


def load_config() -> Dict[str, Any]:
    """
    設定ファイルを読み込む

    Returns:
        Dict[str, Any]: 設定情報
    """
    config = DEFAULT_CONFIG.copy()

    # 設定ファイルが存在する場合は読み込む
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                yaml_config = yaml.safe_load(f)
                if yaml_config:
                    config.update(yaml_config)
        except Exception as e:
            print(f"設定ファイルの読み込みに失敗しました: {e}")
            print("デフォルト設定を使用します。")

    # 環境変数からAPIキーを取得（設定ファイルよりも優先）
    if os.environ.get("OPENAI_API_KEY"):
        config["openai_api_key"] = os.environ.get("OPENAI_API_KEY")

    # データディレクトリの絶対パスを取得
    if not os.path.isabs(config["data_dir"]):
        config["data_dir"] = os.path.abspath(
            os.path.join(os.path.dirname(__file__), config["data_dir"])
        )

    # データディレクトリが存在しない場合は作成
    os.makedirs(config["data_dir"], exist_ok=True)

    return config


# 設定を読み込む
CONFIG = load_config()

# 設定値を変数として公開
OPENAI_API_KEY = CONFIG["openai_api_key"]
MODEL = CONFIG["model"]
MAX_TOKENS = CONFIG["max_tokens"]
TEMPERATURE = CONFIG["temperature"]
MAX_RETRIES = CONFIG["max_retries"]
RETRY_DELAY = CONFIG["retry_delay"]
BACKOFF_FACTOR = CONFIG["backoff_factor"]
DATA_DIR = CONFIG["data_dir"]