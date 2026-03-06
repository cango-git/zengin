from __future__ import annotations

import json
import os
from typing import Any, Callable, Optional

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")


class BaseAgent:
    """Claude API呼び出しの基底クラス。tool_useループを処理する。"""

    def __init__(self, api_key: Optional[str] = None):
        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY が設定されていません。")
        self.client = anthropic.Anthropic(api_key=key)
        self.model = MODEL

    def run_tool_loop(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        on_tool_call: Callable[[str, dict], Any],
        max_iterations: int = 20,
    ) -> list[dict]:
        """
        tool_useループを実行する。

        Args:
            system: システムプロンプト
            messages: 初期メッセージリスト
            tools: Claude toolsスキーマリスト
            on_tool_call: ツール呼び出し時のコールバック (tool_name, tool_input) -> result
            max_iterations: 最大ループ回数

        Returns:
            最終的なメッセージリスト
        """
        msgs = list(messages)

        for _ in range(max_iterations):
            response = self.client.messages.create(
                model=self.model,
                max_tokens=8192,
                system=system,
                messages=msgs,
                tools=tools,
            )

            # アシスタントの応答をメッセージに追加
            assistant_content = response.content
            msgs.append({"role": "assistant", "content": assistant_content})

            # stop_reason が tool_use でなければ終了
            if response.stop_reason != "tool_use":
                break

            # ツール呼び出し結果を収集
            tool_results = []
            for block in assistant_content:
                if block.type == "tool_use":
                    tool_input = block.input
                    tool_result = on_tool_call(block.name, tool_input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(tool_result, ensure_ascii=False)
                            if not isinstance(tool_result, str)
                            else tool_result,
                        }
                    )

            msgs.append({"role": "user", "content": tool_results})

        return msgs

    def simple_call(self, system: str, user_message: str) -> str:
        """シンプルなテキスト応答を取得する。"""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return ""
