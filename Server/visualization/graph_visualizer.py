"""PyVis-based Subtask Graph visualization module.

Standalone module - does NOT import from Memory class.
Directly reads subtask_graph.json and pages.csv.

Usage:
    python -m visualization.graph_visualizer --app com.example.app
    python -m visualization.graph_visualizer --app com.example.app --no-open
"""

import argparse
import csv
import json
import os
import webbrowser
from typing import Dict, List, Optional


def load_subtask_graph(app_name: str, memory_dir: str = "./memory") -> dict:
    """subtask_graph.json 로드.

    Args:
        app_name: 앱 패키지명 (e.g., com.google.android.deskclock)
        memory_dir: 메모리 루트 디렉토리

    Returns:
        {"nodes": [...], "edges": [...]}

    Raises:
        FileNotFoundError: subtask_graph.json이 없을 때
    """
    path = os.path.join(os.path.abspath(memory_dir), app_name, "subtask_graph.json")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No subtask graph found for '{app_name}' at {path}.\n"
            f"Run auto_explore first to build the graph:\n"
            f"  python main.py --mode auto_explore --app {app_name}"
        )

    with open(path, "r", encoding="utf-8") as f:
        graph = json.load(f)

    if "nodes" not in graph:
        graph["nodes"] = []
    if "edges" not in graph:
        graph["edges"] = []

    return graph


def load_page_summaries(app_name: str, memory_dir: str = "./memory") -> Dict[int, str]:
    """pages.csv에서 page_index -> summary 매핑 로드.

    Args:
        app_name: 앱 패키지명
        memory_dir: 메모리 루트 디렉토리

    Returns:
        {page_index: summary_text}
    """
    path = os.path.join(os.path.abspath(memory_dir), app_name, "pages.csv")
    summaries: Dict[int, str] = {}

    if not os.path.exists(path):
        return summaries

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                idx = int(row.get("index", -1))
                summary = row.get("summary", "") or ""
                summaries[idx] = summary.strip()
            except (ValueError, TypeError):
                continue

    return summaries


def build_visualization(
    subtask_graph: dict,
    page_summaries: Dict[int, str],
    title: str = "Subtask Graph",
) -> "Network":
    """PyVis Network 객체를 생성하여 그래프를 구축.

    Args:
        subtask_graph: 로드된 subtask graph
        page_summaries: 페이지 요약 매핑
        title: HTML 페이지 제목

    Returns:
        pyvis.network.Network 인스턴스
    """
    from pyvis.network import Network

    net = Network(
        height="800px",
        width="100%",
        directed=True,
        notebook=False,
        cdn_resources="remote",
    )

    nodes = subtask_graph.get("nodes", [])
    edges = subtask_graph.get("edges", [])

    if not nodes:
        return net

    # outgoing edge 수 계산
    outgoing_count: Dict[int, int] = {}
    for edge in edges:
        fp = edge["from_page"]
        outgoing_count[fp] = outgoing_count.get(fp, 0) + 1

    # 노드 추가
    for node_id in nodes:
        summary = page_summaries.get(node_id, "No summary available")
        out_count = outgoing_count.get(node_id, 0)
        size = min(20 + out_count * 5, 50)

        tooltip = f"Page {node_id}\nOutgoing subtasks: {out_count}"
        if summary:
            tooltip += f"\n\n{summary}"

        net.add_node(
            node_id,
            label=f"Page {node_id}",
            title=tooltip,
            size=size,
            color="#4FC3F7",
            font={"size": 14},
        )

    # Edge 추가
    for edge in edges:
        explored = edge.get("explored", False)
        color = "#66BB6A" if explored else "#EF5350"
        dashes = not explored
        width = 2 if explored else 1

        # Edge tooltip: action_sequence 요약
        actions = edge.get("action_sequence", [])
        action_lines = []
        for i, a in enumerate(actions):
            name = a.get("name", "?")
            desc = a.get("description", "")
            if len(desc) > 60:
                desc = desc[:57] + "..."
            action_lines.append(f"  {i + 1}. {name} - {desc}")
        action_desc = "\n".join(action_lines) if action_lines else "No actions recorded"

        tooltip = (
            f"Subtask: {edge['subtask']}\n"
            f"Explored: {explored}\n"
            f"Trigger UI: {edge.get('trigger_ui_index', '?')}\n"
            f"Actions:\n{action_desc}"
        )

        net.add_edge(
            edge["from_page"],
            edge["to_page"],
            label=edge["subtask"],
            title=tooltip,
            color=color,
            dashes=dashes,
            width=width,
            arrows="to",
        )

    # 레이아웃 설정
    if len(nodes) > 15:
        net.set_options(json.dumps({
            "layout": {
                "hierarchical": {
                    "enabled": True,
                    "direction": "UD",
                    "sortMethod": "directed",
                    "nodeSpacing": 200,
                    "levelSeparation": 200,
                }
            },
            "physics": {
                "hierarchicalRepulsion": {
                    "nodeDistance": 200,
                }
            },
            "edges": {
                "smooth": {"type": "cubicBezier"},
                "font": {"size": 10, "align": "top"},
            },
        }))
    else:
        net.set_options(json.dumps({
            "physics": {
                "forceAtlas2Based": {
                    "gravitationalConstant": -100,
                    "centralGravity": 0.01,
                    "springLength": 200,
                    "springConstant": 0.02,
                },
                "solver": "forceAtlas2Based",
                "stabilization": {"iterations": 150},
            },
            "edges": {
                "smooth": {"type": "curvedCW", "roundness": 0.2},
                "font": {"size": 10, "align": "top"},
            },
        }))

    return net


def visualize_app(
    app_name: str,
    memory_dir: str = "./memory",
    output_path: Optional[str] = None,
    open_browser: bool = True,
) -> str:
    """앱의 Subtask Graph를 시각화하여 HTML 파일 생성.

    Args:
        app_name: 앱 패키지명
        memory_dir: 메모리 루트 디렉토리
        output_path: HTML 출력 경로 (None이면 자동 생성)
        open_browser: True이면 브라우저에서 자동 열기

    Returns:
        생성된 HTML 파일 경로
    """
    graph = load_subtask_graph(app_name, memory_dir)
    summaries = load_page_summaries(app_name, memory_dir)

    node_count = len(graph.get("nodes", []))
    edge_count = len(graph.get("edges", []))
    print(f"Loaded subtask graph: {node_count} nodes, {edge_count} edges")

    if node_count == 0:
        print("Warning: Graph is empty (no nodes). Generating empty visualization.")

    title = f"Subtask Graph — {app_name}"
    net = build_visualization(graph, summaries, title=title)

    if output_path is None:
        output_path = os.path.join(
            os.path.abspath(memory_dir), app_name, "subtask_graph.html"
        )

    net.save_graph(output_path)
    print(f"Visualization saved to: {output_path}")

    if open_browser:
        webbrowser.open(f"file://{os.path.abspath(output_path)}")

    return output_path


def main():
    """CLI 진입점."""
    parser = argparse.ArgumentParser(
        description="Visualize Subtask Graph for a mobile app"
    )
    parser.add_argument(
        "--app",
        required=True,
        help="App package name (e.g., com.google.android.deskclock)",
    )
    parser.add_argument(
        "--memory-dir",
        default="./memory",
        help="Memory directory path (default: ./memory)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output HTML file path (default: ./memory/{app}/subtask_graph.html)",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open browser automatically",
    )
    args = parser.parse_args()

    visualize_app(
        app_name=args.app,
        memory_dir=args.memory_dir,
        output_path=args.output,
        open_browser=not args.no_open,
    )


if __name__ == "__main__":
    main()
