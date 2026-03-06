from __future__ import annotations

from typing import Callable, Optional

from .planner import PlanningAgent
from .writer import WritingAgent
from .reviewer import ReviewerAgent
from ..diagram.renderer import DiagramRenderer
from ..integrations.google_docs import GoogleDocsClient
from ..models.article_state import ArticleState


ProgressCallback = Callable[[str, int, int], None]


class OrchestratorAgent:
    """
    SEO記事生成パイプラインの統合エージェント。

    フロー:
      1. PlanningAgent → SEOPlan
      2. WritingAgent → sections, diagram_specs, image_prompts
      3. DiagramRenderer → PNG files
      4. ReviewerAgent → SEOReview
      5. [スコア < 70 の場合] WritingAgent (修正) → ReviewerAgent (再評価)
      6. GoogleDocsClient → Google Docs URL
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        google_credentials_path: Optional[str] = None,
    ):
        self.api_key = api_key
        self.google_credentials_path = google_credentials_path

        self.planner = PlanningAgent(api_key=api_key)
        self.writer = WritingAgent(api_key=api_key)
        self.reviewer = ReviewerAgent(api_key=api_key)
        self.renderer = DiagramRenderer()
        self.docs_client = GoogleDocsClient(
            credentials_path=google_credentials_path or "credentials/credentials.json"
        )

    def run(
        self,
        topic: str,
        target_word_count: int = 2000,
        target_audience: str = "",
        output_dir: str = "output",
        on_progress: Optional[ProgressCallback] = None,
    ) -> ArticleState:
        """
        記事生成パイプラインを実行する。

        Args:
            topic: 記事トピック
            target_word_count: 目標文字数
            target_audience: ターゲット読者
            output_dir: PNG出力ディレクトリ
            on_progress: 進捗コールバック (message, current_step, total_steps)

        Returns:
            完成したArticleState
        """
        total_steps = 7
        step = 0

        def progress(msg: str) -> None:
            nonlocal step
            step += 1
            if on_progress:
                on_progress(msg, step, total_steps)

        state = ArticleState(
            topic=topic,
            target_word_count=target_word_count,
            target_audience=target_audience,
            output_dir=output_dir,
        )

        # Step 1: プランニング
        progress("プランニングエージェント実行中...")
        state = self.planner.run(state)

        # Step 2: ライティング
        progress("ライティングエージェント実行中...")
        state = self.writer.run(state)

        # Step 3: 図解レンダリング
        progress("図解（PNG）を生成中...")
        state = self.renderer.render_all(state)

        # Step 4: SEOレビュー
        progress("SEOレビューエージェント実行中...")
        state = self.reviewer.run(state)

        # Step 5: スコアが低い場合は修正
        if state.review and state.review.revision_required:
            progress("修正ライティング実行中...")
            state = self.writer.run(
                state,
                revision_instructions=state.review.revision_instructions,
            )
            # 図解も再レンダリング
            state = self.renderer.render_all(state)
            # 再レビュー
            state = self.reviewer.run(state)
        else:
            step += 1  # 修正ステップをスキップ

        # Step 6: Google Docsに保存
        progress("Google Docsに保存中...")
        try:
            docs_url = self.docs_client.save_article(state)
            state.google_docs_url = docs_url
        except Exception as e:
            print(f"[Orchestrator] Google Docs保存エラー: {e}")
            state.google_docs_url = None

        progress("完了！")
        return state
