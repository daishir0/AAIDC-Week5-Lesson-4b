#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
リポジトリセキュリティ監査ツール

GitHubリポジトリを監査して、誤ってコミットされた可能性のある機密情報（.envファイルなど）を検出するツール。
LangChainとLangGraphを使用したカスタムツールの実装例。
"""

import os
import sys
import shutil
import zipfile
import argparse
import logging
import re
from typing import Dict, List, Optional, Union, Any, Tuple

import requests
from pydantic import BaseModel, Field
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END

from config import OPENAI_API_KEY, MODEL, MAX_TOKENS, TEMPERATURE, DATA_DIR
from openai_client import OpenAIClient

# ロガーの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# リポジトリの保存先ディレクトリ
REPO_DIR = os.path.join(DATA_DIR, "repo")

# APIキーのチェック
if not OPENAI_API_KEY:
    logger.error("APIキーが設定されていません。config.yamlを設定するか、環境変数OPENAI_API_KEYを設定してください。")
    sys.exit(1)

# 1. カスタムツールの定義
@tool
def download_and_extract_repo(repo_url: str) -> Union[str, bool]:
    """GitHubリポジトリをダウンロードして展開する。

    このツールはGitHubリポジトリをZIPファイルとしてダウンロードし、
    './data/repo'ディレクトリに展開します。

    Args:
        repo_url: GitHubリポジトリのURL

    Returns:
        展開されたリポジトリのパス（成功時）、またはFalse（失敗時）
    """
    output_dir = os.path.join(DATA_DIR, "repo")
    
    try:
        # 既存のリポジトリディレクトリが存在する場合は削除
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        
        # リポジトリURLの整形
        if repo_url.endswith(".git"):
            repo_url = repo_url[:-4]
        
        # ZIPダウンロードURLの作成
        download_url = f"{repo_url}/archive/refs/heads/main.zip"
        
        # リポジトリのダウンロード
        logger.info(f"リポジトリをダウンロードしています: {repo_url}")
        response = requests.get(download_url, stream=True)
        
        # mainブランチが存在しない場合はmasterブランチを試す
        if response.status_code == 404:
            download_url = f"{repo_url}/archive/refs/heads/master.zip"
            response = requests.get(download_url, stream=True)
        
        # ダウンロードに失敗した場合
        if response.status_code != 200:
            logger.error(f"リポジトリのダウンロードに失敗しました。ステータスコード: {response.status_code}")
            return False
        
        # ZIPファイルの保存
        zip_path = os.path.join(DATA_DIR, "repo.zip")
        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        # ZIPファイルの展開
        logger.info("ZIPファイルを展開しています...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(DATA_DIR)
            
            # 展開されたディレクトリ名を取得
            extracted_dir = zip_ref.namelist()[0].split('/')[0]
            extracted_path = os.path.join(DATA_DIR, extracted_dir)
            
            # 展開されたディレクトリをREPO_DIRにリネーム
            os.makedirs(REPO_DIR, exist_ok=True)
            for item in os.listdir(extracted_path):
                shutil.move(os.path.join(extracted_path, item), REPO_DIR)
            
            # 不要なディレクトリとZIPファイルを削除
            shutil.rmtree(extracted_path)
            os.remove(zip_path)
        
        logger.info(f"リポジトリを展開しました: {REPO_DIR}")
        return REPO_DIR
        
    except Exception as e:
        logger.error(f"リポジトリのダウンロードと展開中にエラーが発生しました: {e}")
        return False


@tool
def env_content(dir_path: str) -> Union[Dict[str, str], str]:
    """指定されたディレクトリから.envファイルを検索して内容を取得する。

    このツールは指定されたディレクトリとそのサブディレクトリを再帰的に検索し、
    見つかった.envファイルの内容を返します。

    Args:
        dir_path: 検索するディレクトリのパス

    Returns:
        Dict[str, str]: ファイルパスをキー、内容を値とする辞書（.envファイルが見つかった場合）
        str: メッセージ（.envファイルが見つからなかった場合）
    """
    env_files = {}
    
    try:
        logger.info(f"ディレクトリを検索しています: {dir_path}")
        
        # ディレクトリが存在しない場合
        if not os.path.exists(dir_path) or not os.path.isdir(dir_path):
            return f"指定されたディレクトリが存在しません: {dir_path}"
        
        # .envファイルを検索
        for root, _, files in os.walk(dir_path):
            for file in files:
                if file == ".env":
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(file_path, dir_path)
                    
                    # ファイルの内容を読み込む
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read()
                            env_files[relative_path] = content
                    except Exception as e:
                        logger.error(f"ファイルの読み込みに失敗しました: {file_path} - {e}")
                        env_files[relative_path] = f"ファイルの読み込みに失敗しました: {e}"
        
        # 結果の返却
        if env_files:
            logger.info(f"{len(env_files)}個の.envファイルが見つかりました。")
            return env_files
        else:
            logger.info(".envファイルは見つかりませんでした。")
            return ".envファイルは見つかりませんでした。"
            
    except Exception as e:
        logger.error(f".envファイルの検索中にエラーが発生しました: {e}")
        return f".envファイルの検索中にエラーが発生しました: {e}"


@tool
def analyze_env_file(content: str) -> Dict[str, Any]:
    """
    .envファイルの内容を分析して機密情報を検出する。

    このツールは.envファイルの内容を分析し、APIキーやパスワードなどの
    機密情報を検出します。

    Args:
        content: .envファイルの内容

    Returns:
        Dict[str, Any]: 分析結果
    """
    # 分析結果
    result = {
        "sensitive_info": [],
        "risk_level": "low",
        "recommendations": []
    }
    
    # 内容が空の場合
    if not content or content.strip() == "":
        result["risk_level"] = "none"
        result["recommendations"].append("ファイルは空です。機密情報はありません。")
        return result
    
    # 機密情報のパターン
    patterns = {
        "API_KEY": r'(?i)(\w+_?API_?KEY|api.?key)[\s=:]+[\'"]?([a-zA-Z0-9_\-\.]{10,})[\'"]*',
        "PASSWORD": r'(?i)(\w+_?PASS(WORD)?|pass(word)?)[\s=:]+[\'"]?([a-zA-Z0-9_\-\.!@#$%^&*]{8,})[\'"]*',
        "SECRET": r'(?i)(\w+_?SECRET|secret)[\s=:]+[\'"]?([a-zA-Z0-9_\-\.]{10,})[\'"]*',
        "TOKEN": r'(?i)(\w+_?TOKEN|token)[\s=:]+[\'"]?([a-zA-Z0-9_\-\.]{10,})[\'"]*',
        "PRIVATE_KEY": r'(?i)(PRIVATE_KEY|private.?key)[\s=:]+[\'"]?([a-zA-Z0-9_\-\.+/=]{10,})[\'"]*',
    }
    
    # 機密情報の検出
    for key, pattern in patterns.items():
        matches = re.findall(pattern, content)
        for match in matches:
            if len(match) >= 2:
                var_name = match[0]
                value = match[1]
                
                # 値が明らかにプレースホルダーの場合はスキップ
                if re.search(r'(?i)(your|placeholder|example|dummy|test)', value):
                    continue
                
                result["sensitive_info"].append({
                    "type": key,
                    "variable": var_name,
                    "value_preview": value[:3] + "*" * (len(value) - 6) + value[-3:] if len(value) > 6 else "***",
                    "line": content.split("\n").index([line for line in content.split("\n") if var_name in line][0]) + 1 if var_name in "\n".join(content.split("\n")) else -1
                })
    
    # リスクレベルの判定
    if len(result["sensitive_info"]) > 5:
        result["risk_level"] = "critical"
        result["recommendations"].append("多数の機密情報が検出されました。このファイルを直ちにリポジトリから削除し、すべての認証情報を更新してください。")
    elif len(result["sensitive_info"]) > 0:
        result["risk_level"] = "high"
        result["recommendations"].append("機密情報が検出されました。このファイルをリポジトリから削除し、検出された認証情報を更新することを検討してください。")
        result["recommendations"].append(".envファイルを.gitignoreに追加して、今後コミットされないようにしてください。")
    else:
        result["risk_level"] = "low"
        result["recommendations"].append("明確な機密情報は検出されませんでしたが、念のため.envファイルを.gitignoreに追加することをお勧めします。")
    
    return result


# 2. ツールレジストリの管理
def get_all_tools():
    """利用可能なすべてのカスタムツールを返す"""
    return [
        download_and_extract_repo,
        env_content,
        analyze_env_file
    ]

def create_tool_registry():
    """ツール名からツール関数へのマッピングを作成する"""
    tools = get_all_tools()
    return {tool.name: tool for tool in tools}


# 3. LangGraphの状態定義
class ChatState(BaseModel):
    """チャットの状態"""
    messages: List[Any] = []
    user_input: Optional[str] = None


# 4. LangGraphのノード関数
def llm_node(state: ChatState):
    """LLMの呼び出しを処理するノード"""
    tools = get_all_tools()
    
    # LLMの初期化
    llm = ChatOpenAI(
        api_key=OPENAI_API_KEY,
        model=MODEL,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS
    )
    
    # ツールをバインド
    llm_with_tools = llm.bind_tools(tools)
    
    # LLMの呼び出し
    response = llm_with_tools.invoke(state.messages)
    
    return {"messages": state.messages + [response]}


def tools_node(state: ChatState):
    """ツールの実行を処理するノード"""
    tool_registry = create_tool_registry()
    last_message = state.messages[-1]
    
    # ツール呼び出しがない場合
    if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
        return {"messages": state.messages}
    
    # ツールの実行
    tool_messages = []
    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = tool_call["args"]
        
        if tool_name in tool_registry:
            tool_function = tool_registry[tool_name]
            # ツール使用開始のログを表示
            print(f"\n🔧 ツール '{tool_name}' を使用します...")
            
            # ツール名に応じて適切な引数を渡す
            if tool_name == "download_and_extract_repo":
                repo_url = tool_args.get("repo_url", "")
                print(f"🔍 リポジトリをダウンロードします: {repo_url}")
                result = tool_function.invoke(repo_url)
            elif tool_name == "env_content":
                dir_path = tool_args.get("dir_path", "")
                print(f"🔍 ディレクトリ内の.envファイルを検索します: {dir_path}")
                result = tool_function.invoke(dir_path)
            elif tool_name == "analyze_env_file":
                print(f"🔍 .envファイルの内容を分析します")
                result = tool_function.invoke(tool_args.get("content", ""))
            else:
                # 未知のツールの場合
                result = f"Unknown tool: {tool_name}"
            
            tool_messages.append(
                ToolMessage(
                    content=str(result),
                    tool_call_id=tool_call["id"]
                )
            )
    
    return {"messages": state.messages + tool_messages}


def human_node(state: ChatState):
    """ユーザー入力を処理するノード"""
    if state.user_input:
        human_message = HumanMessage(content=state.user_input)
        return {"messages": state.messages + [human_message], "user_input": None}
    return {"messages": state.messages}


# 5. LangGraphの構築
def build_chat_graph():
    """チャットグラフを構築する"""
    # グラフの作成
    workflow = StateGraph(ChatState)
    
    # ノードの追加
    workflow.add_node("llm", llm_node)
    workflow.add_node("tools", tools_node)
    workflow.add_node("human", human_node)
    
    # エッジの追加
    workflow.add_edge("human", "llm")
    workflow.add_edge("llm", "tools")
    
    # 条件付きエッジの追加
    workflow.add_conditional_edges(
        "tools",
        lambda state: END if not any(isinstance(msg, ToolMessage) for msg in state.messages[-len(get_all_tools()):]) else "llm",
        {
            "llm": "llm",
            END: END
        }
    )
    
    # エントリーポイントの設定
    workflow.set_entry_point("human")
    
    return workflow.compile()


# 6. メイン関数
def main():
    """メイン関数"""
    # コマンドライン引数のパース
    parser = argparse.ArgumentParser(description="リポジトリセキュリティ監査ツール")
    parser.add_argument("--output", "-o", help="監査レポートの出力ファイル")
    args = parser.parse_args()
    
    # バナーの表示
    print("\n🔒==========================================================🔒")
    print("    リポジトリセキュリティ監査ツール")
    print("    GitHubリポジトリ内の機密情報を検出します")
    print("============================================================\n")
    
    # データディレクトリの作成
    os.makedirs(DATA_DIR, exist_ok=True)
    
    # システムメッセージの作成
    system_message = SystemMessage(
        content="""
        あなたはセキュリティ監査の専門家です。GitHubリポジトリ内の.envファイルを検索し、
        機密情報が誤ってコミットされていないか確認します。
        
        以下のツールを使用できます：
        - download_and_extract_repo: リポジトリをダウンロードして展開する
        - env_content: リポジトリ内の.envファイルを検索する
        - analyze_env_file: .envファイルの内容を分析する
        
        ユーザーの指示に従って、リポジトリの監査を行ってください。
        最初にユーザーにGitHubリポジトリのURLを尋ねてください。
        """
    )
    
    # グラフの構築
    graph = build_chat_graph()
    
    # 初期状態の設定
    initial_state = ChatState(
        messages=[system_message],
        user_input="GitHubリポジトリの監査を行いたいです。"
    )
    
    # 対話ループ
    print("🤖 セキュリティ監査エージェントが起動しました。")
    print("🤖 GitHubリポジトリのURLを入力すると、そのリポジトリの監査を行います。")
    print("🤖 'exit'または'quit'と入力すると終了します。\n")
    
    # 最初のメッセージを表示
    state = graph.invoke(initial_state, {"recursion_limit": 100})
    
    # AIの最初の応答を表示（最新のメッセージのみ）
    ai_messages = [msg for msg in state["messages"] if isinstance(msg, AIMessage)]
    if ai_messages:
        latest_ai_message = ai_messages[-1]
        print(f"\n🤖 {latest_ai_message.content}")
    
    # 対話ループ
    while True:
        # ユーザーからの入力を取得
        user_input = input("\n👤 ")
        
        # 終了条件
        if user_input.lower() in ["exit", "quit"]:
            print("\n🤖 セキュリティ監査エージェントを終了します。")
            break
        
        # 新しい状態を作成してグラフを実行
        new_state = {
            "messages": state["messages"],
            "user_input": user_input
        }
        state = graph.invoke(new_state, {"recursion_limit": 100})
        
        # AIの応答を表示
        ai_messages = []
        tool_messages = []
        
        # 新しいメッセージを抽出
        old_messages = new_state["messages"]
        new_messages = state["messages"]
        
        # 新しく追加されたメッセージを特定
        for i in range(len(old_messages), len(new_messages)):
            message = new_messages[i]
            if isinstance(message, AIMessage):
                ai_messages.append(message)
            elif isinstance(message, ToolMessage):
                tool_messages.append(message)
        
        # ツールメッセージを表示（ログに出力済みなので省略）
        # for message in tool_messages:
        #     content = str(message.content)
        #     if len(content) > 100:
        #         content = content[:100] + "..."
        #     print(f"🔧 ツール実行結果: {content}")
        
        # AIメッセージを表示（最新のメッセージのみ）
        if ai_messages:
            # 最新のAIメッセージのみを表示
            latest_ai_message = ai_messages[-1]
            print(f"\n🤖 {latest_ai_message.content}")
    
    # レポートの保存
    if args.output:
        # 最後のAIメッセージを保存
        for message in reversed(state["messages"]):
            if isinstance(message, AIMessage):
                with open(args.output, "w", encoding="utf-8") as f:
                    f.write(message.content)
                print(f"\n📄 レポートを保存しました: {args.output}")
                break


if __name__ == "__main__":
    main()