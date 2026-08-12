from langgraph.graph import StateGraph, END
from .domain.models import MatcherState
from .nodes.fetch import fetch_node
from .nodes.filter_ import filter_node
from .nodes.extract import extract_node
from .nodes.score import score_node
from .nodes.rank import rank_node


def build_pipeline():
    graph = StateGraph(MatcherState)
    graph.add_node("fetch", fetch_node)
    graph.add_node("filter", filter_node)
    graph.add_node("extract", extract_node)
    graph.add_node("score", score_node)
    graph.add_node("rank", rank_node)

    graph.set_entry_point("fetch")
    graph.add_edge("fetch", "filter")
    graph.add_edge("filter", "extract")
    graph.add_edge("extract", "score")
    graph.add_edge("score", "rank")
    graph.add_edge("rank", END)

    return graph.compile()
