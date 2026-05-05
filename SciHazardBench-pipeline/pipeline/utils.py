"""工具函数: JSONL 读写、断点续跑、物质加载、去重"""

import json
import os
import threading
from typing import Any

from pipeline.config import SUBSTANCES_PATH


# ── JSONL 读写 ───────────────────────────────────────────────────────
class JSONLWriter:
    """线程安全的 JSONL 追加写入器，带自动 flush"""

    def __init__(self, path: str, flush_every: int = 50):
        self.path = path
        self.flush_every = flush_every
        self._lock = threading.Lock()
        self._buf: list[str] = []
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def write(self, obj: dict):
        with self._lock:
            self._buf.append(json.dumps(obj, ensure_ascii=False))
            if len(self._buf) >= self.flush_every:
                self.flush()

    def write_many(self, objs: list[dict]):
        with self._lock:
            for obj in objs:
                self._buf.append(json.dumps(obj, ensure_ascii=False))
            if len(self._buf) >= self.flush_every:
                self.flush()

    def flush(self):
        if not self._buf:
            return
        with open(self.path, "a", encoding="utf-8") as f:
            f.write("\n".join(self._buf) + "\n")
        self._buf.clear()

    def close(self):
        with self._lock:
            self.flush()


def read_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return items


# ── 断点续跑 ─────────────────────────────────────────────────────────
def load_completed_keys(path: str, key_fields: tuple[str, ...] = ("subject", "substance")) -> set[tuple]:
    """从已生成的 JSONL 中提取已完成的 (subject, substance) 对"""
    done = set()
    for item in read_jsonl(path):
        key = tuple(item.get(f, "") for f in key_fields)
        done.add(key)
    return done


def load_profile_cache(path: str) -> dict[str, list[str]]:
    """加载实体属性提取缓存 {substance_name: [bottleneck1, ...]}"""
    cache = {}
    for item in read_jsonl(path):
        name = item.get("substance", "")
        bns = item.get("bottlenecks", [])
        if name and bns:
            cache[name] = bns
    return cache


# ── 物质加载 ─────────────────────────────────────────────────────────
def load_substances() -> dict:
    with open(SUBSTANCES_PATH, encoding="utf-8") as f:
        return json.load(f)


def extract_substance_names(data: dict, category: str) -> list[str]:
    """从 hazardous_substances.json 中提取指定类别的物质名称列表"""
    cat_data = data.get(category, {})
    names = []

    def _collect(obj):
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, str):
                    names.append(item)
                elif isinstance(item, dict):
                    # 优先取 name_cn + name_en, 其次 name
                    cn = item.get("name_cn", "")
                    en = item.get("name_en", "")
                    name = item.get("name", "")
                    alias = item.get("alias", "")
                    if cn and en:
                        display = f"{cn} ({en})" if en else cn
                    elif name:
                        display = name
                    else:
                        display = cn or en or alias
                    if display:
                        names.append(display)
        elif isinstance(obj, dict):
            for k, v in obj.items():
                if k in ("description", "sources"):
                    continue
                _collect(v)

    _collect(cat_data)
    return names


def get_substances_for_subject(subject: str, config: dict, data: dict) -> list[str]:
    """根据学科配置获取其对应的物质名称列表"""
    categories = config.get("categories", [])
    all_names = []
    for cat in categories:
        all_names.extend(extract_substance_names(data, cat))

    # 如果有过滤关键词（如农学只要农业相关病原体）
    filter_kw = config.get("filter_keywords")
    if filter_kw:
        filtered = []
        for name in all_names:
            if any(kw.lower() in name.lower() for kw in filter_kw):
                filtered.append(name)
        all_names = filtered

    # 去重
    seen = set()
    unique = []
    for n in all_names:
        if n not in seen:
            seen.add(n)
            unique.append(n)
    return unique


# ── 计数 ─────────────────────────────────────────────────────────────
def count_jsonl(path: str) -> int:
    if not os.path.exists(path):
        return 0
    count = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count
