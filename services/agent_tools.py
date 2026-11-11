#=====================================================
# 文件名：services/agent_tools.py
# 作用：把 PolyDB 现有检索函数包装成 Agent 可调用的工具
#
# 安全说明：
#   advanced_search() 原本接受一段拼好的 extra_conditions 字符串直接拼进 SQL，
#   这里不把这段自由文本暴露给大模型，而是只允许模型传结构化的
#   {field, op, value}，字段/操作符白名单校验，value 强制转 float，
#   避免大模型被诱导拼出任意 SQL 片段。
# =====================================================

import json
from rdkit import Chem

from .polydb_service import (
    advanced_search,
    search_similar_molecules,
    find_by_smiles,
    find_similar_by_names,
    build_image_index,
)

MAX_ROWS_RETURNED = 20  # 避免把整页结果都塞给大模型，浪费 token、拖慢响应

ALLOWED_FIELDS = ['mw', 'tpsa', 'logp', 'energy', 'hba', 'hbd', 'rotb', 'sa', 'qed']
ALLOWED_OPS = ['>', '>=', '<', '<=', '=', '!=']


def _build_safe_condition(filters: list) -> str:
    """
    把结构化 filters 转成 SQL 条件片段。
    filters: [{"field": "mw", "op": "<=", "value": 500}, ...]
    字段/操作符经过白名单校验，value 强制转 float 后直接嵌入数字（非字符串），
    不存在大模型可控的文本被当作 SQL 片段执行的路径。
    """
    clauses = []
    for f in (filters or []):
        field = f.get("field")
        op = f.get("op")
        value = f.get("value")
        if field not in ALLOWED_FIELDS or op not in ALLOWED_OPS:
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        clauses.append(f"{field} {op} {value}")
    return " AND ".join(clauses)


def tool_search_compounds(category: str = "ALL", filters: list = None, limit: int = 20,
                           sort_by: str = "", sort_dir: str = "asc") -> str:
    """按类别 + 数值属性条件筛选 PolyDB 中的化合物，可选按某个数值字段排序"""
    try:
        extra_cond = _build_safe_condition(filters)

        # sort_by 同样走白名单校验，避免拼入未经许可的字段名
        safe_sort_by = sort_by if sort_by in ALLOWED_FIELDS else ""
        safe_sort_dir = "desc" if str(sort_dir).lower() == "desc" else "asc"

        df, total = advanced_search(
            category=category,
            extra_conditions=extra_cond,
            selected_columns=['id', 'name', 'smiles', 'mw', 'logp', 'tpsa', 'qed', 'category'],
            page=1,
            page_size=min(int(limit or 20), MAX_ROWS_RETURNED),
            sort_by=safe_sort_by,
            sort_dir=safe_sort_dir,
        )
        if df.empty:
            return json.dumps({"total_matching": int(total), "results": []}, ensure_ascii=False)

        return json.dumps({
            "total_matching": int(total),
            "returned": len(df),
            "sorted_by": safe_sort_by or None,
            "results": df.to_dict(orient="records"),
        }, ensure_ascii=False, default=str)

    except Exception as e:
        return f"工具执行失败，真实错误：{e}"


def tool_similarity_search(smiles: str, top_n: int = 10, sim_min: float = 0.4) -> str:
    """结构相似性搜索：输入 SMILES，返回库中相似的化合物"""
    try:
        if Chem.MolFromSmiles(smiles) is None:
            return "错误：无效的 SMILES，请检查化学结构式输入。"

        df = search_similar_molecules(
            smiles,
            top_n=min(int(top_n or 10), MAX_ROWS_RETURNED),
            sim_min=float(sim_min or 0.4),
            sim_max=1.0,
        )
        if df.empty:
            return json.dumps({"count": 0, "results": []}, ensure_ascii=False)

        cols = [c for c in ['id', 'name', 'smiles', 'similarity', 'mw', 'logp'] if c in df.columns]
        return json.dumps({
            "count": len(df),
            "results": df[cols].to_dict(orient="records"),
        }, ensure_ascii=False, default=str)

    except Exception as e:
        return f"工具执行失败，真实错误：{e}"


def tool_synthesis_route_search(smiles: str, sim_min: float = 0.5, top_n: int = 10) -> str:
    """合成路径搜索：查找该化合物本身及库中结构相近的合成条目"""
    try:
        if Chem.MolFromSmiles(smiles) is None:
            return "错误：无效的 SMILES，请检查化学结构式输入。"

        exact_df = find_by_smiles(smiles)
        names_index = build_image_index()
        similar_df = find_similar_by_names(
            list(names_index.keys()), smiles, sim_min=float(sim_min or 0.5), sim_max=1.0
        )
        if not similar_df.empty:
            similar_df = similar_df.sort_values('similar', ascending=False).head(int(top_n or 10))

        return json.dumps({
            "exact_match": exact_df.to_dict(orient="records") if not exact_df.empty else [],
            "similar_matches": similar_df.to_dict(orient="records") if not similar_df.empty else [],
        }, ensure_ascii=False, default=str)

    except Exception as e:
        return f"工具执行失败，真实错误：{e}"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "tool_search_compounds",
            "description": "按类别（spermidine/spermine/other/ALL）和数值属性条件（分子量、LogP、TPSA等）筛选 PolyDB 中的化合物，支持按某个数值字段对全库结果排序后取前N个（例如“分子量最小的10个”应传 sort_by=mw, sort_dir=asc, limit=10，而不是先不排序再自己挑）",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["ALL", "spermidine", "spermine", "other"],
                        "description": "化合物类别，默认 ALL"
                    },
                    "filters": {
                        "type": "array",
                        "description": "数值属性筛选条件列表，例如 [{\"field\":\"mw\",\"op\":\"<=\",\"value\":500}]",
                        "items": {
                            "type": "object",
                            "properties": {
                                "field": {"type": "string", "enum": ALLOWED_FIELDS},
                                "op": {"type": "string", "enum": ALLOWED_OPS},
                                "value": {"type": "number"}
                            },
                            "required": ["field", "op", "value"]
                        }
                    },
                    "limit": {"type": "integer", "description": "返回结果数量上限，默认20"},
                    "sort_by": {
                        "type": "string",
                        "enum": ALLOWED_FIELDS,
                        "description": "按此字段对全库匹配结果排序后再取前 limit 个；不传则不排序，按数据库默认顺序返回"
                    },
                    "sort_dir": {
                        "type": "string",
                        "enum": ["asc", "desc"],
                        "description": "排序方向，asc=从小到大（默认），desc=从大到小"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tool_similarity_search",
            "description": "输入分子的 SMILES，进行结构相似性搜索，返回 PolyDB 库中相似的化合物",
            "parameters": {
                "type": "object",
                "properties": {
                    "smiles": {"type": "string", "description": "查询分子的 SMILES 字符串"},
                    "top_n": {"type": "integer", "description": "返回数量，默认10"},
                    "sim_min": {"type": "number", "description": "最小相似度阈值(0-1)，默认0.4"}
                },
                "required": ["smiles"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tool_synthesis_route_search",
            "description": "输入分子的 SMILES，查找该化合物在 PolyDB 中的精确条目及结构相近的合成路径条目",
            "parameters": {
                "type": "object",
                "properties": {
                    "smiles": {"type": "string", "description": "查询分子的 SMILES 字符串"},
                    "sim_min": {"type": "number", "description": "最小相似度阈值(0-1)，默认0.5"},
                    "top_n": {"type": "integer", "description": "相似条目返回数量，默认10"}
                },
                "required": ["smiles"]
            }
        }
    },
]

TOOL_MAP = {
    "tool_search_compounds": tool_search_compounds,
    "tool_similarity_search": tool_similarity_search,
    "tool_synthesis_route_search": tool_synthesis_route_search,
}