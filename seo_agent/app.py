"""
SEO記事エージェント - Streamlit Web UI
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Optional

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from agents.orchestrator import OrchestratorAgent
from models.article_state import ArticleState

# ページ設定
st.set_page_config(
    page_title="SEO記事エージェント",
    page_icon="✍️",
    layout="wide",
)


def init_session_state() -> None:
    defaults = {
        "article_state": None,
        "generating": False,
        "progress_messages": [],
        "progress_step": 0,
        "progress_total": 7,
        "error_message": None,
        "google_authenticated": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def render_sidebar() -> tuple[str, str]:
    """サイドバーを描画し、(api_key, google_creds_path) を返す。"""
    st.sidebar.title("⚙️ 設定")

    api_key = st.sidebar.text_input(
        "Anthropic API Key",
        value=os.getenv("ANTHROPIC_API_KEY", ""),
        type="password",
        help="Claude APIキー（sk-ant-...）",
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("### Google Docs 連携")

    creds_path = os.getenv(
        "GOOGLE_CREDENTIALS_PATH", "credentials/credentials.json"
    )
    creds_exists = Path(creds_path).exists()

    if creds_exists:
        st.sidebar.success("✓ credentials.json が見つかりました")
        if st.sidebar.button("Google認証を実行"):
            try:
                from integrations.google_docs import GoogleDocsClient
                client = GoogleDocsClient(credentials_path=creds_path)
                client.authenticate()
                st.session_state.google_authenticated = True
                st.sidebar.success("✓ Google認証完了！")
            except Exception as e:
                st.sidebar.error(f"認証エラー: {e}")
    else:
        st.sidebar.warning(
            "credentials.json が見つかりません。\n\n"
            "Google Cloud Console から OAuth 2.0クライアントIDをダウンロードして "
            f"`{creds_path}` に配置してください。"
        )

    if st.session_state.google_authenticated or Path("credentials/token.json").exists():
        st.sidebar.success("✓ Google認証済み")

    st.sidebar.markdown("---")
    st.sidebar.markdown(
        "**使い方**\n"
        "1. APIキーを入力\n"
        "2. Google認証を実行\n"
        "3. トピックを入力して生成\n"
        "4. Google DocsのリンクからURLにアクセス"
    )

    return api_key, creds_path


def run_generation(
    topic: str,
    word_count: int,
    audience: str,
    api_key: str,
    creds_path: str,
) -> None:
    """バックグラウンドで記事生成を実行する。"""
    progress_messages = []

    def on_progress(msg: str, step: int, total: int) -> None:
        progress_messages.append(msg)
        st.session_state.progress_messages = list(progress_messages)
        st.session_state.progress_step = step
        st.session_state.progress_total = total

    try:
        orchestrator = OrchestratorAgent(
            api_key=api_key or None,
            google_credentials_path=creds_path,
        )
        state = orchestrator.run(
            topic=topic,
            target_word_count=word_count,
            target_audience=audience,
            output_dir=os.getenv("OUTPUT_DIR", "output"),
            on_progress=on_progress,
        )
        st.session_state.article_state = state
        st.session_state.error_message = None
    except Exception as e:
        st.session_state.error_message = str(e)
    finally:
        st.session_state.generating = False


def render_settings_tab(api_key: str, creds_path: str) -> None:
    """設定・入力タブを描画する。"""
    st.header("📝 記事の設定")

    topic = st.text_input(
        "トピック / ターゲットキーワード",
        placeholder="例: Python 機械学習 入門",
        help="SEO記事のメインテーマを入力してください",
    )

    col1, col2 = st.columns(2)
    with col1:
        word_count = st.selectbox(
            "目標文字数",
            options=[1000, 2000, 3000, 5000],
            index=1,
            format_func=lambda x: f"{x:,}文字",
        )
    with col2:
        audience = st.text_input(
            "ターゲット読者（任意）",
            placeholder="例: プログラミング初心者",
        )

    st.markdown("---")

    if st.button(
        "🚀 記事を生成する",
        type="primary",
        disabled=st.session_state.generating or not topic or not api_key,
    ):
        if not topic:
            st.warning("トピックを入力してください。")
            return
        if not api_key:
            st.warning("Anthropic API Keyをサイドバーに入力してください。")
            return

        st.session_state.generating = True
        st.session_state.progress_messages = []
        st.session_state.progress_step = 0
        st.session_state.article_state = None
        st.session_state.error_message = None

        thread = threading.Thread(
            target=run_generation,
            args=(topic, word_count, audience, api_key, creds_path),
            daemon=True,
        )
        thread.start()
        st.rerun()

    if not api_key:
        st.info("💡 サイドバーにAnthroic API Keyを入力してください。")


def render_progress_tab() -> None:
    """進捗タブを描画する。"""
    st.header("⏳ 生成進捗")

    if st.session_state.generating:
        total = st.session_state.progress_total
        step = st.session_state.progress_step
        progress = step / total if total > 0 else 0

        st.progress(progress, text=f"ステップ {step}/{total}")

        st.markdown("**処理ログ:**")
        for msg in st.session_state.progress_messages:
            st.markdown(f"✅ {msg}")

        if st.session_state.generating:
            st.spinner("処理中...")
            st.rerun()

    elif st.session_state.error_message:
        st.error(f"エラーが発生しました:\n\n{st.session_state.error_message}")

    elif st.session_state.article_state is not None:
        st.success("✅ 記事生成が完了しました！「結果」タブを確認してください。")
        for msg in st.session_state.progress_messages:
            st.markdown(f"✅ {msg}")
    else:
        st.info("「設定」タブからトピックを入力して生成を開始してください。")


def render_results_tab() -> None:
    """結果タブを描画する。"""
    state: Optional[ArticleState] = st.session_state.article_state

    if state is None:
        st.info("まだ記事が生成されていません。「設定」タブから生成を開始してください。")
        return

    # Google Docsリンク
    if state.google_docs_url:
        st.success(f"📄 Google Docsに保存されました: [{state.google_docs_url}]({state.google_docs_url})")
    else:
        st.warning("Google Docsへの保存に失敗しました。Google認証を確認してください。")

    st.markdown("---")

    # SEOプラン情報
    if state.seo_plan:
        with st.expander("📊 SEOプラン", expanded=True):
            plan = state.seo_plan
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**メインキーワード:** {plan.primary_keyword}")
                st.markdown(f"**メタタイトル:** {plan.meta_title}")
                st.markdown(f"**ターゲット読者:** {plan.target_audience}")
            with col2:
                st.markdown("**関連キーワード:**")
                for kw in plan.secondary_keywords:
                    st.markdown(f"• {kw}")
            st.markdown(f"**メタディスクリプション:** {plan.meta_description}")

    # SEOレビュー結果
    if state.review:
        with st.expander("🔍 SEOレビュー結果", expanded=True):
            review = state.review
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("SEOスコア", f"{review.seo_score}/100")
            col2.metric("キーワード密度", "✓" if review.keyword_density_ok else "✗")
            col3.metric("見出し構造", "✓" if review.heading_structure_ok else "✗")
            col4.metric("メタ情報", "✓" if review.meta_ok else "✗")

            if review.issues:
                st.markdown("**改善点:**")
                for issue in review.issues:
                    st.markdown(f"• {issue}")

            if review.counter_arguments:
                st.markdown("**追加推奨の反証・注意点:**")
                for arg in review.counter_arguments:
                    st.markdown(f"• {arg}")

    # 図解プレビュー
    if state.diagram_specs:
        with st.expander(f"🖼️ 図解 ({len(state.diagram_specs)}件)", expanded=True):
            cols = st.columns(min(len(state.diagram_specs), 3))
            for i, spec in enumerate(state.diagram_specs):
                with cols[i % 3]:
                    st.markdown(f"**{spec.title_ja}**")
                    if spec.png_path and Path(spec.png_path).exists():
                        st.image(spec.png_path, caption=spec.diagram_id)
                    else:
                        st.warning(f"図解の生成に失敗: {spec.diagram_id}")

    # 画像プロンプト
    if state.image_prompts:
        with st.expander(f"🎨 画像プロンプト ({len(state.image_prompts)}件)"):
            for prompt in state.image_prompts:
                st.markdown(f"**[{prompt.placement_hint}]** {prompt.prompt_ja}")
                st.code(prompt.prompt_en, language="text")

    # 記事プレビュー
    with st.expander("📄 記事プレビュー（Markdown）", expanded=False):
        article_md = state.full_article_markdown()
        st.markdown(article_md)

    # ダウンロードボタン
    if state.sections:
        article_md = state.full_article_markdown()
        st.download_button(
            label="📥 Markdownをダウンロード",
            data=article_md.encode("utf-8"),
            file_name=f"{state.slug()}.md",
            mime="text/markdown",
        )


def main() -> None:
    init_session_state()
    api_key, creds_path = render_sidebar()

    st.title("✍️ SEO記事エージェント")
    st.markdown("AIマルチエージェントシステムで高品質なSEO記事を自動生成します。")

    tab1, tab2, tab3 = st.tabs(["📝 設定", "⏳ 進捗", "📄 結果"])

    with tab1:
        render_settings_tab(api_key, creds_path)

    with tab2:
        render_progress_tab()

    with tab3:
        render_results_tab()

    # 生成中は自動更新
    if st.session_state.generating:
        import time
        time.sleep(2)
        st.rerun()


if __name__ == "__main__":
    main()
