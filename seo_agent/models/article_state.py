from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


class OutlineItem(BaseModel):
    level: int  # 2=H2, 3=H3
    heading: str


class SEOPlan(BaseModel):
    topic: str
    primary_keyword: str
    secondary_keywords: list[str] = Field(default_factory=list)
    meta_title: str
    meta_description: str
    target_audience: str
    outline: list[OutlineItem] = Field(default_factory=list)


class ArticleSection(BaseModel):
    heading: str
    level: int  # 2=H2, 3=H3
    content_markdown: str
    diagram_id: Optional[str] = None


class DiagramSpec(BaseModel):
    diagram_id: str
    diagram_type: str  # "bar_chart"|"pie_chart"|"flow_diagram"|"comparison_table"
    title_ja: str
    data: dict[str, Any] = Field(default_factory=dict)
    png_path: Optional[str] = None


class ImagePrompt(BaseModel):
    prompt_en: str
    prompt_ja: str
    placement_hint: str  # "アイキャッチ"|"本文中"


class SEOReview(BaseModel):
    seo_score: int
    revision_required: bool
    keyword_density_ok: bool
    heading_structure_ok: bool
    meta_ok: bool
    issues: list[str] = Field(default_factory=list)
    counter_arguments: list[str] = Field(default_factory=list)
    revision_instructions: Optional[str] = None


class ArticleState(BaseModel):
    topic: str
    target_word_count: int = 2000
    target_audience: str = ""
    seo_plan: Optional[SEOPlan] = None
    sections: list[ArticleSection] = Field(default_factory=list)
    diagram_specs: list[DiagramSpec] = Field(default_factory=list)
    image_prompts: list[ImagePrompt] = Field(default_factory=list)
    review: Optional[SEOReview] = None
    google_docs_url: Optional[str] = None
    output_dir: str = "output"

    def full_article_markdown(self) -> str:
        """記事全体のMarkdownテキストを生成する。"""
        parts: list[str] = []
        if self.seo_plan:
            parts.append(f"# {self.seo_plan.meta_title}\n")
        for section in self.sections:
        	prefix = "#" * section.level
        	parts.append(f"{prefix} {section.heading}\n\n{section.content_markdown}\n")
        return "\n".join(parts)

    def slug(self) -> str:
        """ファイル名用のslugを生成する。"""
        import re
        s = self.topic.lower()
        s = re.sub(r"[^\w\s-]", "", s)
        s = re.sub(r"[\s]+", "-", s.strip())
        return s[:50] or "article"
