from __future__ import annotations

from typing import Any, Optional

from .base_agent import BaseAgent
from ..models.article_state import ArticleState, SEOReview

SYSTEM_PROMPT = """あなたは日本語SEO記事の専門レビュアーです。
記事のSEO品質・事実確認・バランスを評価します。

## レビュー観点
1. **キーワード密度**: メインキーワードが1〜3%の密度で自然に使われているか
2. **見出し構造**: H2→H3の階層が論理的か、キーワードが含まれているか
3. **メタ情報**: タイトルが60文字以内、ディスクリプションが120文字以内か
4. **コンテンツ品質**: 具体例・数字・事例が含まれているか
5. **E-E-A-T**: 専門性・信頼性を示す表現があるか
6. **反証・バランス**: 一方的な主張に対する反証や注意点を提示する

必ず submit_review ツールを呼び出してレビュー結果を提出してください。"""

SUBMIT_REVIEW_TOOL = {
    "name": "submit_review",
    "description": "SEO記事レビュー結果を提出する",
    "input_schema": {
        "type": "object",
        "properties": {
            "seo_score": {
                "type": "integer",
                "description": "SEOスコア（0〜100）",
                "minimum": 0,
                "maximum": 100,
            },
            "keyword_density_ok": {
                "type": "boolean",
                "description": "キーワード密度が適切か",
            },
            "heading_structure_ok": {
                "type": "boolean",
                "description": "見出し構造が適切か",
            },
            "meta_ok": {
                "type": "boolean",
                "description": "メタ情報が適切か",
            },
            "issues": {
                "type": "array",
                "items": {"type": "string"},
                "description": "改善が必要な問題点のリスト",
            },
            "counter_arguments": {
                "type": "array",
                "items": {"type": "string"},
                "description": "追加すべき反証・注意点・バランス情報",
            },
            "revision_required": {
                "type": "boolean",
                "description": "修正が必要かどうか（スコア70未満の場合はtrue）",
            },
            "revision_instructions": {
                "type": "string",
                "description": "修正が必要な場合の具体的な修正指示",
            },
        },
        "required": [
            "seo_score",
            "keyword_density_ok",
            "heading_structure_ok",
            "meta_ok",
            "issues",
            "counter_arguments",
            "revision_required",
        ],
    },
}


class ReviewerAgent(BaseAgent):
    """SEOチェック・事実確認・反証エージェント。"""

    def run(self, state: ArticleState) -> ArticleState:
        if state.seo_plan is None:
            raise ValueError("ReviewerAgent: SEOプランが必要です。")

        review_data: Optional[dict] = None

        def on_tool_call(tool_name: str, tool_input: dict) -> Any:
            nonlocal review_data
            if tool_name == "submit_review":
                review_data = tool_input
                return {"status": "success", "message": "レビュー結果を受け付けました。"}
            return {"status": "error", "message": f"未知のツール: {tool_name}"}

        plan = state.seo_plan
        article_md = state.full_article_markdown()
        # 長すぎる場合は先頭5000文字に制限
        article_preview = article_md[:5000] + ("..." if len(article_md) > 5000 else "")

        diagram_summary = "\n".join(
            f"- {spec.diagram_id}: {spec.diagram_type} 「{spec.title_ja}」"
            for spec in state.diagram_specs
        )

        user_message = (
            f"以下の記事をSEO・品質・バランスの観点でレビューしてください。\n\n"
            f"## SEOプラン\n"
            f"- メインキーワード: {plan.primary_keyword}\n"
            f"- 関連キーワード: {', '.join(plan.secondary_keywords[:5])}\n"
            f"- メタタイトル: {plan.meta_title}\n"
            f"- メタディスクリプション: {plan.meta_description}\n\n"
            f"## 図解一覧\n{diagram_summary or 'なし'}\n\n"
            f"## 記事本文（抜粋）\n{article_preview}\n\n"
            f"submit_review ツールでレビュー結果を提出してください。"
        )

        self.run_tool_loop(
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            tools=[SUBMIT_REVIEW_TOOL],
            on_tool_call=on_tool_call,
        )

        if review_data is None:
            # レビュー失敗時はデフォルト値で続行
            state.review = SEOReview(
                seo_score=70,
                revision_required=False,
                keyword_density_ok=True,
                heading_structure_ok=True,
                meta_ok=True,
                issues=["レビューの取得に失敗しました。"],
                counter_arguments=[],
            )
        else:
            state.review = SEOReview(
                seo_score=review_data["seo_score"],
                revision_required=review_data["revision_required"],
                keyword_density_ok=review_data["keyword_density_ok"],
                heading_structure_ok=review_data["heading_structure_ok"],
                meta_ok=review_data["meta_ok"],
                issues=review_data.get("issues", []),
                counter_arguments=review_data.get("counter_arguments", []),
                revision_instructions=review_data.get("revision_instructions"),
            )

        return state
