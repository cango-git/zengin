from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch

# 非対話モードで実行（Streamlit互換）
matplotlib.use("Agg")

# 日本語フォント設定
try:
    import japanize_matplotlib  # noqa: F401
except ImportError:
    pass

from ..models.article_state import ArticleState, DiagramSpec


class DiagramRenderer:
    """DiagramSpecからMatplotlibでPNGを生成するレンダラー。"""

    DPI = 150
    FIGSIZE = (10, 6)

    def render_all(self, state: ArticleState) -> ArticleState:
        """全図解をレンダリングしてpng_pathを更新する。"""
        slug = state.slug()
        out_dir = Path(state.output_dir) / slug
        out_dir.mkdir(parents=True, exist_ok=True)

        for spec in state.diagram_specs:
            try:
                png_path = self._render_one(spec, out_dir)
                spec.png_path = str(png_path)
            except Exception as e:
                print(f"[DiagramRenderer] {spec.diagram_id} の生成に失敗: {e}")

        return state

    def _render_one(self, spec: DiagramSpec, out_dir: Path) -> Path:
        out_path = out_dir / f"{spec.diagram_id}.png"
        handlers = {
            "bar_chart": self._render_bar_chart,
            "pie_chart": self._render_pie_chart,
            "flow_diagram": self._render_flow_diagram,
            "comparison_table": self._render_comparison_table,
        }
        handler = handlers.get(spec.diagram_type)
        if handler is None:
            raise ValueError(f"未対応の図解タイプ: {spec.diagram_type}")
        handler(spec, out_path)
        return out_path

    def _render_bar_chart(self, spec: DiagramSpec, out_path: Path) -> None:
        data = spec.data
        labels = data.get("labels", [])
        values = data.get("values", [])

        fig, ax = plt.subplots(figsize=self.FIGSIZE, dpi=self.DPI)
        bars = ax.bar(labels, values, color="#4C72B0", edgecolor="white", linewidth=0.5)

        for bar, val in zip(bars, values):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(values) * 0.01,
                str(val),
                ha="center",
                va="bottom",
                fontsize=10,
            )

        ax.set_title(spec.title_ja, fontsize=14, pad=15)
        ax.set_ylabel(data.get("y_label", ""))
        ax.set_xlabel(data.get("x_label", ""))
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        plt.tight_layout()
        plt.savefig(out_path, dpi=self.DPI, bbox_inches="tight")
        plt.close(fig)

    def _render_pie_chart(self, spec: DiagramSpec, out_path: Path) -> None:
        data = spec.data
        labels = data.get("labels", [])
        values = data.get("values", [])

        colors = plt.cm.Set3.colors[: len(labels)]  # type: ignore

        fig, ax = plt.subplots(figsize=(8, 8), dpi=self.DPI)
        wedges, texts, autotexts = ax.pie(
            values,
            labels=labels,
            autopct="%1.1f%%",
            colors=colors,
            startangle=90,
            pctdistance=0.8,
        )
        for text in autotexts:
            text.set_fontsize(10)

        ax.set_title(spec.title_ja, fontsize=14, pad=20)
        plt.tight_layout()
        plt.savefig(out_path, dpi=self.DPI, bbox_inches="tight")
        plt.close(fig)

    def _render_flow_diagram(self, spec: DiagramSpec, out_path: Path) -> None:
        data = spec.data
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])

        if not nodes:
            return

        fig, ax = plt.subplots(figsize=(12, 8), dpi=self.DPI)
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 10)
        ax.axis("off")
        ax.set_title(spec.title_ja, fontsize=14, pad=15)

        # ノード位置を自動計算（横並び or 縦並び）
        n = len(nodes)
        positions: dict[str, tuple[float, float]] = {}
        cols = min(n, 4)
        rows = (n + cols - 1) // cols

        for i, node in enumerate(nodes):
            col = i % cols
            row = i // cols
            x = 1.5 + col * (8 / max(cols - 1, 1)) if cols > 1 else 5.0
            y = 8 - row * (6 / max(rows - 1, 1)) if rows > 1 else 5.0
            positions[node["id"]] = (x, y)

            # ノードボックスを描画
            bbox = dict(boxstyle="round,pad=0.5", facecolor="#AED6F1", edgecolor="#2980B9", linewidth=1.5)
            ax.text(
                x, y, node.get("label", node["id"]),
                ha="center", va="center",
                fontsize=10, bbox=bbox,
                wrap=True,
            )

        # エッジを描画
        for edge in edges:
            src = positions.get(edge.get("from", ""))
            dst = positions.get(edge.get("to", ""))
            if src and dst:
                ax.annotate(
                    "",
                    xy=dst,
                    xytext=src,
                    arrowprops=dict(
                        arrowstyle="->",
                        color="#555555",
                        lw=1.5,
                        connectionstyle="arc3,rad=0.1",
                    ),
                )
                # エッジラベル
                if edge.get("label"):
                    mx = (src[0] + dst[0]) / 2
                    my = (src[1] + dst[1]) / 2
                    ax.text(mx, my, edge["label"], fontsize=8, color="#333333", ha="center")

        plt.tight_layout()
        plt.savefig(out_path, dpi=self.DPI, bbox_inches="tight")
        plt.close(fig)

    def _render_comparison_table(self, spec: DiagramSpec, out_path: Path) -> None:
        data = spec.data
        headers = data.get("headers", [])
        rows = data.get("rows", [])

        if not headers or not rows:
            return

        fig, ax = plt.subplots(
            figsize=(max(8, len(headers) * 2), max(4, len(rows) * 0.6 + 1.5)),
            dpi=self.DPI,
        )
        ax.axis("off")
        ax.set_title(spec.title_ja, fontsize=14, pad=15)

        table = ax.table(
            cellText=rows,
            colLabels=headers,
            cellLoc="center",
            loc="center",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 1.8)

        # ヘッダー行のスタイル
        for j in range(len(headers)):
            table[0, j].set_facecolor("#2980B9")
            table[0, j].set_text_props(color="white", fontweight="bold")

        # 交互行の背景色
        for i in range(1, len(rows) + 1):
            for j in range(len(headers)):
                if i % 2 == 0:
                    table[i, j].set_facecolor("#EBF5FB")

        plt.tight_layout()
        plt.savefig(out_path, dpi=self.DPI, bbox_inches="tight")
        plt.close(fig)
