from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

# Google API クライアントライブラリ
try:
    from google.oauth2.credentials import Credentials
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False

from ..models.article_state import ArticleState

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]

TOKEN_PATH = "credentials/token.json"


class GoogleDocsClient:
    """Google Docs・Drive APIクライアント。"""

    def __init__(self, credentials_path: str = "credentials/credentials.json"):
        self.credentials_path = credentials_path
        self._creds: Optional[object] = None
        self._docs_service = None
        self._drive_service = None

    def is_configured(self) -> bool:
        """Google認証情報が設定されているか確認する。"""
        if not GOOGLE_AVAILABLE:
            return False
        # サービスアカウントJSON または OAuth token.json のどちらかがあればOK
        sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if sa_json and Path(sa_json).exists():
            return True
        if Path(TOKEN_PATH).exists():
            return True
        return False

    def auth_method(self) -> str:
        """現在の認証方式を返す。'service_account' | 'oauth' | 'none'"""
        if not GOOGLE_AVAILABLE:
            return "none"
        sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if sa_json and Path(sa_json).exists():
            return "service_account"
        if Path(TOKEN_PATH).exists():
            return "oauth"
        return "none"

    def authenticate(self) -> bool:
        """
        Google認証を実行する。

        優先順位:
        1. GOOGLE_SERVICE_ACCOUNT_JSON 環境変数 → サービスアカウント認証（iPhone対応）
        2. credentials/token.json が存在 → OAuthトークンをリフレッシュ
        3. どちらもなし → RuntimeError
        """
        if not GOOGLE_AVAILABLE:
            raise RuntimeError("google-api-python-client がインストールされていません。")

        creds = None

        # 1. サービスアカウント認証（iPhoneなど外部端末からでも動作する）
        sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        if sa_json and Path(sa_json).exists():
            creds = service_account.Credentials.from_service_account_file(
                sa_json, scopes=SCOPES
            )
            self._creds = creds
            self._docs_service = build("docs", "v1", credentials=creds)
            self._drive_service = build("drive", "v3", credentials=creds)
            return True

        # 2. 既存OAuthトークンのリフレッシュ（デスクトップで事前認証済みの場合）
        if Path(TOKEN_PATH).exists():
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(TOKEN_PATH, "w") as f:
                    f.write(creds.to_json())
            if creds.valid:
                self._creds = creds
                self._docs_service = build("docs", "v1", credentials=creds)
                self._drive_service = build("drive", "v3", credentials=creds)
                return True

        raise RuntimeError(
            "Google認証情報が設定されていません。\n\n"
            "【推奨】サービスアカウントを使用（iPhoneからも動作）:\n"
            "  1. GCP Console でサービスアカウントを作成\n"
            "  2. JSONキーをダウンロードして credentials/service-account.json に配置\n"
            "  3. .env に GOOGLE_SERVICE_ACCOUNT_JSON=credentials/service-account.json を追加\n\n"
            "【代替】デスクトップで事前認証（token.json を生成する）:\n"
            "  python -c \"from seo_agent.integrations.google_docs import GoogleDocsClient; "
            "GoogleDocsClient().run_desktop_auth()\""
        )

    def run_desktop_auth(self) -> bool:
        """
        デスクトップ環境でのOAuth認証（事前セットアップ用）。
        一度実行すると credentials/token.json が生成され、以降はサーバーでも使える。
        iPhoneからは実行不可。PC/Mac で一度だけ実行する。
        """
        if not GOOGLE_AVAILABLE:
            raise RuntimeError("google-api-python-client がインストールされていません。")
        if not Path(self.credentials_path).exists():
            raise FileNotFoundError(
                f"OAuth credentials.json が見つかりません: {self.credentials_path}"
            )
        flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
        creds = flow.run_local_server(port=0)
        Path(TOKEN_PATH).parent.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
        print(f"✓ 認証完了。{TOKEN_PATH} に保存しました。")
        return True

    def _ensure_authenticated(self) -> None:
        if self._docs_service is None:
            self.authenticate()

    def _upload_image_to_drive(self, png_path: str) -> Optional[str]:
        """PNGをGoogle Driveにアップロードして共有URLを返す。"""
        try:
            file_metadata = {"name": Path(png_path).name}
            media = MediaFileUpload(png_path, mimetype="image/png")
            file = (
                self._drive_service.files()
                .create(body=file_metadata, media_body=media, fields="id")
                .execute()
            )
            file_id = file.get("id")

            # 閲覧権限を公開に設定
            self._drive_service.permissions().create(
                fileId=file_id,
                body={"type": "anyone", "role": "reader"},
            ).execute()

            # 直接表示URL
            return f"https://drive.google.com/uc?id={file_id}"
        except Exception as e:
            print(f"[GoogleDocsClient] 画像アップロードエラー: {e}")
            return None

    def save_article(self, state: ArticleState) -> str:
        """
        記事をGoogle Docsに保存してドキュメントURLを返す。

        Args:
            state: 記事の状態

        Returns:
            Google DocsのURL
        """
        self._ensure_authenticated()
        if state.seo_plan is None:
            raise ValueError("SEOプランが必要です。")

        plan = state.seo_plan

        # ドキュメント作成
        doc = self._docs_service.documents().create(
            body={"title": plan.meta_title}
        ).execute()
        doc_id = doc["documentId"]

        # ユーザーのGoogleアカウントへ共有（サービスアカウント使用時に必要）
        user_email = os.getenv("USER_GOOGLE_EMAIL")
        if user_email:
            try:
                self._drive_service.permissions().create(
                    fileId=doc_id,
                    body={"type": "user", "role": "writer", "emailAddress": user_email},
                ).execute()
            except Exception as e:
                print(f"[GoogleDocsClient] 共有設定エラー（無視して続行）: {e}")

        # 図解画像をDriveにアップロード
        image_urls: dict[str, str] = {}
        for spec in state.diagram_specs:
            if spec.png_path and Path(spec.png_path).exists():
                url = self._upload_image_to_drive(spec.png_path)
                if url:
                    image_urls[spec.diagram_id] = url

        # ドキュメントにコンテンツを挿入
        requests = self._build_insert_requests(state, image_urls)
        if requests:
            self._docs_service.documents().batchUpdate(
                documentId=doc_id,
                body={"requests": requests},
            ).execute()

        return f"https://docs.google.com/document/d/{doc_id}/edit"

    def _build_insert_requests(
        self, state: ArticleState, image_urls: dict[str, str]
    ) -> list[dict]:
        """Google Docs batchUpdate用のリクエストリストを構築する。"""
        requests = []
        # 末尾から先頭へ挿入する（インデックスがずれないように逆順で構築し、最後に反転）
        # シンプルな実装として先頭インデックス1から順に追記
        insert_index = 1

        def insert_text(text: str, style: Optional[str] = None) -> None:
            nonlocal insert_index
            requests.append({
                "insertText": {
                    "location": {"index": insert_index},
                    "text": text,
                }
            })
            end_index = insert_index + len(text)

            if style:
                requests.append({
                    "updateParagraphStyle": {
                        "range": {
                            "startIndex": insert_index,
                            "endIndex": end_index,
                        },
                        "paragraphStyle": {"namedStyleType": style},
                        "fields": "namedStyleType",
                    }
                })
            insert_index = end_index

        plan = state.seo_plan

        # メタ情報コメント
        insert_text(
            f"メタディスクリプション: {plan.meta_description}\n\n",
        )

        # H1タイトル
        insert_text(f"{plan.meta_title}\n", "HEADING_1")

        # セクションを順に挿入
        for section in state.sections:
            heading_style = f"HEADING_{section.level}"
            insert_text(f"{section.heading}\n", heading_style)

            # 本文（Markdownを簡易プレーンテキストに変換）
            plain = self._markdown_to_plain(section.content_markdown)
            insert_text(plain + "\n\n")

            # 図解画像の挿入
            if section.diagram_id and section.diagram_id in image_urls:
                requests.append({
                    "insertInlineImage": {
                        "location": {"index": insert_index - 1},
                        "uri": image_urls[section.diagram_id],
                        "objectSize": {
                            "height": {"magnitude": 300, "unit": "PT"},
                            "width": {"magnitude": 450, "unit": "PT"},
                        },
                    }
                })
                insert_text("\n")

        # 画像プロンプトセクション
        if state.image_prompts:
            insert_text("画像プロンプト一覧\n", "HEADING_2")
            for prompt in state.image_prompts:
                insert_text(
                    f"[{prompt.placement_hint}] {prompt.prompt_ja}\n"
                    f"英語プロンプト: {prompt.prompt_en}\n\n"
                )

        # SEOレビュー結果
        if state.review:
            insert_text("SEOレビュー結果\n", "HEADING_2")
            review = state.review
            insert_text(
                f"SEOスコア: {review.seo_score}/100\n"
                f"キーワード密度: {'✓' if review.keyword_density_ok else '✗'}\n"
                f"見出し構造: {'✓' if review.heading_structure_ok else '✗'}\n"
                f"メタ情報: {'✓' if review.meta_ok else '✗'}\n\n"
            )
            if review.issues:
                insert_text("改善点:\n")
                for issue in review.issues:
                    insert_text(f"• {issue}\n")
                insert_text("\n")
            if review.counter_arguments:
                insert_text("追加推奨の反証・注意点:\n")
                for arg in review.counter_arguments:
                    insert_text(f"• {arg}\n")

        return requests

    @staticmethod
    def _markdown_to_plain(md: str) -> str:
        """MarkdownをプレーンテキストにざっくりLift変換する。"""
        # コードブロック
        text = re.sub(r"```[\w]*\n(.*?)```", r"\1", md, flags=re.DOTALL)
        # インラインコード
        text = re.sub(r"`(.+?)`", r"\1", text)
        # 太字・イタリック
        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        # リンク
        text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
        # 見出し（既にH2/H3は別途挿入済みなのでここでは除去）
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        return text.strip()
