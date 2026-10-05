# commit-msg-gen

零依赖的 **Git 提交信息生成器**：把一段 unified diff（`git diff` 输出）解析后，按 Conventional Commits 规范生成 `type(scope): subject` 风格的提交标题与正文。规则完全本地运行，无需 API key；可选接入 LLM 润色。

## 功能简介

- 解析 unified diff：统计新增 / 删除 / 修改的文件、增删行数。
- 按文件路径与改动关键词推断提交类型：`feat` / `fix` / `docs` / `style` / `refactor` / `perf` / `test` / `chore`。
- 自动识别常见 scope（`auth` / `api` / `db` / `ui` / `deps`）。
- 生成带改动文件列表与增删统计的正文。
- 内置一段示例 diff，开箱即可体验。

## 快速开始

```bash
# 使用内置示例 diff
python3 cli.py

# 从文件读取 diff
python3 cli.py --file my.patch

# 直接接管 git diff
git diff | python3 cli.py --stdin
```

输出形如：

```
fix(auth): update login.py

changed files: auth/login.py, tests/test_login.py, README.md
11 insertions(+), 1 deletions(-)
```

## 无 API key 如何运行

本项目**默认纯规则运行**，无需任何 key。所有解析与归类都在本地完成。
仅当你想要更自然的措辞时，才需要设置环境变量并加 `--llm`：

```bash
export OPENAI_API_KEY=sk-xxx
python3 cli.py --example --llm
```

## 目录说明

```
commit-msg-gen/
├── commit_msg_gen.py   # diff 解析 + 类型推断 + 信息生成 + 可选 LLM
├── cli.py             # 命令行入口
├── tests/
│   └── test_commit_msg.py
├── README.md
├── LICENSE
└── .gitignore
```

## 运行测试

```bash
python3 -m unittest discover -s tests
```

## License

MIT License，Copyright (c) 2026 ljiang9。
