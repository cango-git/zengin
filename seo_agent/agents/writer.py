from __future__ import annotations

from typing import Any, Optional

from .base_agent import BaseAgent
from ..models.article_state import (
    ArticleSection,
    ArticleState,
    DiagramSpec,
    ImagePrompt,
)

SYSTEM_PROMPT = """あなたは日本語SEO記事の専門ライターです。
与えられたSEOプランに基づいて、高品質な記事を執筆します。

## 執筆ガイドライン
- 読者にとって価値ある情報を提供する
- キーワードを自然に組み込む（詰め込みすぎない）
- 各セクションは具体例・数字・事例を使って充実させる
- 図解が効果的な箇所ではdiagram_specを提出する
- 記事のアイキャッチ画像プロンプトも提出する

## ツール使用方法
- submit_section: 各セクションを執筆したら必ず呼び出す
- submit_diagram_spec: 図解が有効なセクション（最大3個）で呼び出す
- submit_image_prompt: 記事全体で1〜2個の画像プロンプトを提出する

アウトラインのすべてのH2・H3セクションを完成させてください。"""

TOOLS = [
    {
        "name": "submit_section",
        "description": "記事の1セクションを提出する",
        "input_schema": {
            "type": "object",
            "properties": {
                "heading": {"type": "string", "description": "見出しテキスト"},
                "level": {
                    "type": "integer",
                    "description": "見出しレベル（2=H2, 3=H3）",
                },
                "content_markdown": {
                    "type": "string",
                    "description": "セクション本文（Markdown形式）",
                },
                "diagram_id": {
                    "type": "string",
                    "description": "このセクションに関連する図解ID（fig_01等）、なければ省略",
                },
            },
            "required": ["heading", "level", "content_markdown"],
        },
    },
    {
        "name": "submit_diagram_spec",
        "description": "図解の仕様を提出する（Matplotlibで自動生成される）",
        "input_schema": {
            "type": "object",
            "properties": {
                "diagram_id": {
                    "type": "string",
                    "description": "図解ID（fig_01, fig_02...）",
                },
                "diagram_type": {
                    "type": "string",
                    "enum": [
                        "bar_chart",
                        "pie_chart",
                        "flow_diagram",
                        "comparison_table",
                    ],
                    "description": "図解タイプ",
                },
                "title_ja": {"type": "string", "description": "図解タイトル（日本語）"},
                "data": {
                    "type": "object",
                    "description": "図解データ。bar_chart/pie_chartは{labels:[], values:[]}、flow_diagramは{nodes:[{id,label}], edges:[{from,to,label}]}、comparison_tableは{headers:[], rows:[[...]]}",
                },
            },
            "required": ["diagram_id", "diagram_type", "title_ja", "data"],
        },
    },
    {
        "name": "submit_image_prompt",
        "description": "AI画像生成用のプロンプトを提出する",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt_en": {
                    "type": "string",
                    "description": "英語の画像プロンプト（DALL-E/Midjourney用）",
                },
                "prompt_ja": {"type": "string", "description": "画像の日本語説明"},
                "placement_hint": {
                    "type": "string",
                    "enum": ["アイキャッチ", "本文中"],
                    "description": "画像の配置場所",
                },
            },
            "required": ["prompt_en", "prompt_ja", "placement_hint"],
        },
    },
]


class WritingAgent(BaseAgent):
    """記事本文・図解仕様・画像プロンプト生成エージェント。"""

    def run(
        self, state: ArticleState, revision_instructions: Optional[str] = None
    ) -> ArticleState:
        if state.seo_plan is None:
            raise ValueError("WritingAgent: SEOプランが必要です。")

        plan = state.seo_plan
        sections: list[ArticleSection] = []
        diagram_specs: list[DiagramSpec] = []
        image_prompts: list[ImagePrompt] = []
        diagram_count = 0

        def on_tool_call(tool_name: str, tool_input: dict) -> Any:
            nonlocal diagram_count
            if tool_name == "submit_section":
                sections.append(
                    ArticleSection(
                        heading=tool_input["heading"],
                        level=tool_input["level"],
                        content_markdown=tool_input["content_markdown"],
                        diagram_id=tool_input.get("diagram_id"),
                    )
                )
                return {
                    "status": "success",
                    "message": f"セクション「{tool_input['heading']}」を受け付けました。",
                }
            elif tool_name == "submit_diagram_spec":
                diagram_count += 1
                diagram_specs.append(
                    DiagramSpec(
                        diagram_id=tool_input["diagram_id"],
                        diagram_type=tool_input["diagram_type"],
                        title_ja=tool_input["title_ja"],
                        data=tool_input["data"],
                    )
                )
                return {"status": "success", "message": f"図解仕様を受け付けました。"}
            elif tool_name == "submit_image_prompt":
                image_prompts.append(
                    ImagePrompt(
                        prompt_en=tool_input["prompt_en"],
                        prompt_ja=tool_input["prompt_ja"],
                        placement_hint=tool_input["placement_hint"],
                    )
                )
                return {"status": "success", "message": "画像プロンプトを受け付けました。"}
            return {"status": "error", "message": f"未知のツール: {tool_name}"}

        outline_text = "\n".join(
            f"{'  ' * (item.level - 2)}{('#' * item.level)} {item.heading}"
            for item in plan.outline
        )
        keywords_text = ", ".join(
            [plan.primary_keyword] + plan.secondary_keywords[:5]
        )
        target_per_section = max(
            200, state.target_word_count // max(len(plan.outline), 1)
        )

        revision_hint = ""
        if revision_instructions:
            revision_hint = f"\n\n## 修正指示\n{revision_instructions}\n上記の指示に従って修正した内容を執筆してください。"

        user_message = (
            f"以下のSEOプランに基づいて記事を執筆してください。\n\n"
            f"## 記事情報\n"
            f"- トピック: {plan.topic}\n"
            f"- メインキーワード: {plan.primary_keyword}\n"
            f"- 関連キーワード: {keywords_text}\n"
            f"- ターゲット読者: {plan.target_audience}\n"
            f"- 目標文字数: {state.target_word_count}文字（各セクション約{target_per_section}文字）\n\n"
            f"## アウトライン\n{outline_text}\n\n"
            f"すべてのセクションを submit_section で提出してください。"
            f"図解が効果的な箇所では submit_diagram_spec も呼び出してください（最大3個）。"
            f"アイキャッチ画像のプロンプトも submit_image_prompt で提出してください。"
            f"{revision_hint}"
        )

        self.run_tool_loop(
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            tools=TOOLS,
            on_tool_call=on_tool_call,
            max_iterations=30,
        )

        # アウトラインの80%以上カバーされているか確認
        outline_count = len(plan.outline)
        if outline_count > 0 and len(sections) < outline_count * 0.8:
            # 不足セクションを追加リクエスト
            missing = outline_count - len(sections)
            followup = (
                f"まだ {missing} セクションが不足しています。"
                f"残りのセクションも submit_section で提出してください。"
            )
            self.run_tool_loop(
                system=SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": user_message},
                    {
                        "role": "assistant",
                        "content": f"{len(sections)}セクション提出しました。",
                    },
                    {"role": "user", "content": followup},
                ],
                tools=TOOLS,
                on_tool_call=on_tool_call,
                max_iterations=15,
            )

        state.sections = sections
        state.diagram_specs = diagram_specs
        state.image_prompts = image_prompts
        return state
