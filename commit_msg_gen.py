"""commit-msg-gen：把 unified diff 文本解析为 Conventional Commits 风格信息。

规则（无 LLM 时的核心逻辑）：
- 统计新增 / 删除 / 修改的文件；
- 根据文件名路径与改动关键词推断 type：feat / fix / docs / style / refactor /
  perf / test / chore；
- 挑出最有代表性的一句作为 subject；
- 在 body 里列出主要改动文件与增删行数统计。
可选：有 OPENAI_API_KEY 时调用 LLM 润色成更自然的提交信息。
"""

from __future__ import annotations

import json
import os
import re
import urllib.request

TYPE_RULES: list[tuple[str, list[str]]] = [
    ("test", [r"tests?/", r"_test\.", r"test_", r"\.test\.", r"testing/"]),
    ("docs", [r"docs?/", r"\.md$", r"README", r"CHANGES?", r"comment", r"docstring"]),
    ("fix", [r"fix", r"bugfix", r"hotfix", r"patch", r"correct"]),
    ("feat", [r"feat", r"feature", r"add", r"support", r"introduce", r"create"]),
    ("perf", [r"perf", r"optimize", r"speed", r"slow", r"faster", r"cache"]),
    ("refactor", [r"refactor", r"cleanup", r"restruct", r"rename", r"move"]),
    ("style", [r"style", r"format", r"lint", r"whitespace", r"black", r"prettier"]),
    ("chore", [r"chore", r"ci", r"workflow", r"release", r"bump", r"version",
               r"\.gitignore", r"lock"]),
]

SCOPE_HINTS = {
    "auth": r"auth|login|session|token",
    "api": r"api|route|endpoint|controller",
    "db": r"model|migration|schema|db|sql",
    "ui": r"ui|view|component|css|template|page",
    "deps": r"requirements|package|pyproject|lock|toml",
}

EXAMPLE_DIFF = """diff --git a/auth/login.py b/auth/login.py
index 111..222 100644
--- a/auth/login.py
+++ b/auth/login.py
@@ -10,6 +10,10 @@ def login(user):
+# fix: handle expired token gracefully
+def refresh_token(user):
+    return user.token.refresh()
+
-def create_session(user):
+def create_session(user, remember=False):
diff --git a/tests/test_login.py b/tests/test_login.py
new file mode 100644
index 000..333
--- /dev/null
+++ b/tests/test_login.py
@@ -0,0 +1,5 @@
+def test_refresh_token():
+    assert True
+
+def test_login():
+    assert True
diff --git a/README.md b/README.md
index 444..555 100644
--- a/README.md
+++ b/README.md
@@ -1,3 +1,4 @@
 # My App
+Added login docs.
"""


def parse_diff(diff_text: str) -> dict:
    """解析 unified diff，返回结构化统计。

    返回字段：files(list)、added(list)、deleted(list)、modified(list)、
    insertions(int)、deletions(int)、keywords(set)、file_keywords(dict)。
    """
    files: list[str] = []
    insertions = 0
    deletions = 0
    keywords: set[str] = set()
    file_keywords: dict[str, set[str]] = {}

    cur: str | None = None

    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            m = re.search(r" b/(.+)$", line)
            cur = m.group(1) if m else None
            if cur and cur not in files:
                files.append(cur)
                file_keywords.setdefault(cur, set())
        elif line.startswith("+++ b/"):
            cur = line[len("+++ b/"):].strip()
            if cur and cur not in files:
                files.append(cur)
                file_keywords.setdefault(cur, set())
        elif line.startswith("+") and not line.startswith("+++"):
            insertions += 1
            for kw in re.findall(r"[A-Za-z_]{3,}", line[1:]):
                w = kw.lower()
                keywords.add(w)
                if cur:
                    file_keywords.setdefault(cur, set()).add(w)
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
            for kw in re.findall(r"[A-Za-z_]{3,}", line[1:]):
                w = kw.lower()
                keywords.add(w)
                if cur:
                    file_keywords.setdefault(cur, set()).add(w)

    added, deleted, modified = _classify_files(diff_text)
    return {
        "files": files,
        "added": added,
        "deleted": deleted,
        "modified": modified,
        "insertions": insertions,
        "deletions": deletions,
        "keywords": keywords,
        "file_keywords": file_keywords,
    }


def _classify_files(diff_text: str) -> tuple[list[str], list[str], list[str]]:
    added: list[str] = []
    deleted: list[str] = []
    modified: list[str] = []
    cur: str | None = None
    is_new = False
    is_del = False
    for line in diff_text.splitlines():
        if line.startswith("diff --git"):
            if cur:
                if is_new:
                    added.append(cur)
                elif is_del:
                    deleted.append(cur)
                else:
                    modified.append(cur)
            m = re.search(r" b/(.+)$", line)
            cur = m.group(1) if m else None
            is_new = False
            is_del = False
        elif line.startswith("new file mode"):
            is_new = True
        elif line.startswith("deleted file mode"):
            is_del = True
    if cur:
        if is_new:
            added.append(cur)
        elif is_del:
            deleted.append(cur)
        else:
            modified.append(cur)
    return added, deleted, modified


def _is_test_path(p: str) -> bool:
    return bool(re.search(r"(^|/)tests?/|test_|\.test\.|_test\.py$", p))


def infer_type(parsed: dict) -> str:
    """根据文件路径与改动关键词推断 conventional commit type。

    优先级：
    1. 全部改动都是测试文件 -> test；
    2. 对【非测试、非纯文档】的源码改动，用其路径 + 自身改动关键词匹配规则；
    3. 若仍无结果，再用全部文件路径匹配；
    4. 兜底 chore。
    """
    files = parsed["files"]
    if not files:
        return "chore"

    real_test_only = all(_is_test_path(f) for f in files)
    if real_test_only:
        return "test"

    file_keywords = parsed.get("file_keywords", {})

    def _guess(candidates: list[str]) -> str:
        path_hay = " ".join(candidates)
        for ctype, patterns in TYPE_RULES:
            for pat in patterns:
                if re.search(pat, path_hay, re.IGNORECASE):
                    return ctype
        kw_hay = " ".join(w for f in candidates for w in file_keywords.get(f, set()))
        for ctype, patterns in TYPE_RULES:
            for pat in patterns:
                if re.search(pat, kw_hay, re.IGNORECASE):
                    return ctype
        return ""

    code = [f for f in files
            if not _is_test_path(f) and not _is_doc_path(f)]
    t = _guess(code)
    if t:
        return t
    return _guess(files) or "chore"


def _is_doc_path(p: str) -> bool:
    return bool(re.search(r"(^|/)docs?/|(^|_)changelog|\.md$|\.rst$|\.txt$", p))


def infer_scope(parsed: dict) -> str | None:
    haystack = " ".join(parsed["files"])
    for scope, pat in SCOPE_HINTS.items():
        if re.search(pat, haystack, re.IGNORECASE):
            return scope
    return None


def summarize(parsed: dict) -> str:
    """生成一句英文 subject 摘要。优先描述被修改的源码，而非新增测试。"""
    def _is_test(p: str) -> bool:
        return bool(re.search(r"(^|/)tests?/|test_|\.test\.|_test\.py$", p))

    modified_src = [f for f in parsed["modified"] if not _is_test(f)]
    added_src = [f for f in parsed["added"] if not _is_test(f)]

    if modified_src:
        return f"update {_base(modified_src[0])}"
    if added_src:
        return f"add {_base(added_src[0])}"
    if parsed["deleted"]:
        return f"remove {_base(parsed['deleted'][0])}"
    if parsed["added"]:
        return f"add {_base(parsed['added'][0])}"
    if parsed["modified"]:
        return f"update {_base(parsed['modified'][0])}"
    return "update codebase"


def _base(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def build_commit_message(diff_text: str, use_llm: bool = False) -> str:
    """统一入口：解析 diff 生成 conventional commit message。"""
    parsed = parse_diff(diff_text)
    ctype = infer_type(parsed)
    scope = infer_scope(parsed)
    subj = summarize(parsed)
    header = f"{ctype}({scope}): {subj}" if scope else f"{ctype}: {subj}"

    body_lines = []
    stat = f"{parsed['insertions']} insertions(+), {parsed['deletions']} deletions(-)"
    files_line = "changed files: " + ", ".join(parsed["files"]) if parsed["files"] else ""
    if files_line:
        body_lines.append(files_line)
    body_lines.append(stat)

    msg = header + "\n\n" + "\n".join(body_lines)

    if use_llm and os.environ.get("OPENAI_API_KEY"):
        try:
            return polish_llm(msg, diff_text)
        except Exception as exc:
            print(f"[warn] LLM 润色失败，使用规则结果：{exc}")
    return msg


# ---------------------------------------------------------------------------
# 可选 LLM
# ---------------------------------------------------------------------------

def polish_llm(ruled_msg: str, diff_text: str, api_key: str | None = None,
               base_url: str | None = None, model: str | None = None) -> str:
    api_key = api_key or os.environ.get("OPENAI_API_KEY")
    base_url = (base_url or os.environ.get("OPENAI_BASE_URL")
                or "https://api.openai.com/v1").rstrip("/")
    model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    if not api_key:
        raise RuntimeError("未设置 OPENAI_API_KEY")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是 Git 提交信息助手，输出符合 Conventional Commits 的一行标题加简短正文，不要解释。"},
            {"role": "user", "content": f"基于以下 diff 与规则草稿，生成一条更好的 commit message：\n\n规则草稿：\n{ruled_msg}\n\nDIFF:\n{diff_text[:4000]}"},
        ],
        "temperature": 0.3,
    }
    req = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()
