from __future__ import annotations

from typing import Any, Optional

from .base_agent import BaseAgent
from ..models.article_state import ArticleState, OutlineItem, SEOPlan

SYSTEM_PROMPT = """あなたは日本語SEO記事の専門プランナーです。
与えられたトピックに対して、検索エンジン最適化を考慮した記事プランを作成します。

必ず create_seo_plan ツールを呼び出して構造化されたプランを提出してください。"""

CREATE_SEO_PLAN_TOOL = {
    "name": "create_seo_plan",
    "description": "SEO記事プランを作成して提出する",
    "input_schema": {
        "type": "object",
        "properties": {
            "primary_keyword": {
                "type": "string",
                "description": "メインターゲットキーワード（例: 'Python 機械学習 入門'）",
            },
            "secondary_keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "関連LSIキーワード（5〜8個）",
            },
            "meta_title": {
                "type": "string",
                "description": "SEO用メタタイトル（60文字以内）",
            },
            "meta_description": {
                "type": "string",
                "description": "メタディスクリプション（120文字以内）",
            },
            "target_audience": {
                "type": "string",
                "description": "ターゲット読者像",
            },
            "outline": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "level": {
                            "type": "integer",
                            "description": "見出しレベル（2=H2, 3=H3）",
                        },
                        "heading": {
                            "type": "string",
                            "description": "見出しテキスト",
                        },
                    },
                    "required": ["level", "heading"],
                },
                "description": "記事アウトライン（H2/H3構造）",
            },
        },
        "required": [
            "primary_keyword",
            "secondary_keywords",
            "meta_title",
            "meta_description",
            "target_audience",
            "outline",
        ],
    },
}


class PlanningAgent(BaseAgent):
    """キーワード分析・記事構成計画エージェント。"""

    def run(self, state: ArticleState) -> ArticleState:
        seo_plan_data: Optional[dict] = None

        def on_tool_call(tool_name: str, tool_input: dict) -> Any:
            nonlocal seo_plan_data
            if tool_name == "create_seo_plan":
                seo_plan_data = tool_input
                return {"status": "success", "message": "SEOプランを受け付けました。"}
            return {"status": "error", "message": f"未知のツール: {tool_name}"}

        audience_hint = (
            f"\nターゲット読者: {state.target_audience}" if state.target_audience else ""
        )
        user_message = (
            f"次のトピックについてSEO記事プランを作成してください。\n\n"
            f"トピック: {state.topic}\n"
            f"目標文字数: {state.target_word_count}文字{audience_hint}\n\n"
            f"アウトラインは目標文字数に合わせたセクション数（概ね1000文字ごとに2〜3個のH2）で作成してください。"
        )

        self.run_tool_loop(
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            tools=[CREATE_SEO_PLAN_TOOL],
            on_tool_call=on_tool_call,
        )

        if seo_plan_data is None:
            raise RuntimeError("PlanningAgent: SEOプランの生成に失敗しました。")

        state.seo_plan = SEOPlan(
            topic=state.topic,
            primary_keyword=seo_plan_data["primary_keyword"],
            secondary_keywords=seo_plan_data["secondary_keywords"],
            meta_title=seo_plan_data["meta_title"],
            meta_description=seo_plan_data["meta_description"],
            target_audience=seo_plan_data["target_audience"],
            outline=[
                OutlineItem(level=item["level"], heading=item["heading"])
                for item in seo_plan_data["outline"]
            ],
        )
        return state
