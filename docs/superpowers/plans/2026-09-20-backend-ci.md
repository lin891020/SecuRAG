# SecuRAG 補 CI 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 `backend/tests/` 在 GitHub Actions 上跑，README 與履歷的測試數字對回實際值。

**Architecture:** 一個 workflow、一個 job。測試已經用 in-memory SQLite 並 mock 掉 Postgres、ChromaDB、LLM（見 `backend/tests/conftest.py`），所以 CI 不需要 docker compose，直接 `pip install -e ".[dev]"` 後跑 pytest。不動任何程式碼。

**Tech Stack:** GitHub Actions、Python 3.11、pip（backend 沒有 uv.lock，`pyproject.toml` 是 setuptools）。

**Spec:** `~/Projects/claude-config/docs/superpowers/specs/2026-09-20-workflow-overhaul-design.md` 第 4 節 SecuRAG 那一列。

## Global Constraints

- 不改 `backend/app/` 任何檔案。
- 不改測試。測試失敗的話記錄下來，不硬修。
- README 第 374 行的數字必須等於 CI 實際跑出的數字。

---

### Task 1: 在本機不用 docker 跑一次測試，拿到真實數字

**Files:**
- 不建檔。只是量。

- [x] **Step 1: 建一個乾淨的 venv 裝 dev 依賴**

```bash
cd ~/Projects/SecuRAG/backend
uv venv -p 3.11 .venv-ci -q
source .venv-ci/bin/activate
uv pip install -e ".[dev]" 2>&1 | tail -3
```
Expected: 最後一行沒有 error。sentence-transformers 會拉 torch，幾分鐘。

- [x] **Step 2: 跑測試**

```bash
python -m pytest tests/ -q 2>&1 | tail -15
```
Expected: 最後一行像 `N passed` 或 `N passed, M failed`。把 N 和 M 抄下來。README 說 132，實際數字以這裡為準。

- [x] **Step 3: 如果有 fail，先判斷是環境還是程式**

```bash
python -m pytest tests/ -q -x 2>&1 | grep -E "Error|error|assert" | head -5
```
規則：`ModuleNotFoundError`、`ConnectionRefused`、找不到 `host.docker.internal` 這類是環境問題，記進 Task 2 的 workflow 註解，用 `-k "not <名字>"` 或 `-m` 跳過並在 CI log 印出跳過的清單（照 aoi-agent 的 "What this job did not run" 那段）。`AssertionError` 是程式問題，**不修**，記進 HANDOFF.md 讓 Mike 決定。

- [x] **Step 4: 清掉 venv**

```bash
deactivate; rm -rf .venv-ci
```

---

### Task 2: 寫 workflow

**Files:**
- Create: `.github/workflows/tests.yml`

**Interfaces:**
- Produces: 一個叫 `tests` 的 job，push 與 PR 都跑。

- [x] **Step 1: 寫檔**

```yaml
# backend/tests 用 in-memory SQLite，並 mock 掉 Postgres、ChromaDB 與 LLM
# （見 backend/tests/conftest.py），所以這裡不起 docker compose，直接裝套件跑。
# Makefile 的 `make test-backend` 走 docker，是給本機用的；兩條路跑的是同一批測試。
name: tests

on:
  push:
  pull_request:

jobs:
  backend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
          cache-dependency-path: backend/pyproject.toml

      - name: Install
        run: pip install -e ".[dev]"

      - name: Tests
        # -rs 讓被 skip 的測試在 log 裡有名字，綠燈不能靠悄悄縮水的套件。
        run: python -m pytest tests/ -rs -q

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npm test
```

如果 Task 1 Step 3 有要跳過的測試，在 `Tests` 那步的指令後面加 `-k "not <名字>"`，並在上一行加註解寫為什麼。

- [x] **Step 2: 確認 frontend 有 lockfile 與 test script**

```bash
ls ~/Projects/SecuRAG/frontend/package-lock.json && grep -n '"test"' ~/Projects/SecuRAG/frontend/package.json
```
Expected: 兩個都有。沒有 `package-lock.json` 就把 `cache:` 兩行拿掉、`npm ci` 改 `npm install`；沒有 `test` script 就整個 `frontend` job 刪掉。

- [x] **Step 3: 本機語法檢查**

```bash
python3 -c "import yaml,sys; yaml.safe_load(open('$HOME/Projects/SecuRAG/.github/workflows/tests.yml')); print('yaml ok')"
```
Expected: `yaml ok`

- [x] **Step 4: Commit 並推**

```bash
cd ~/Projects/SecuRAG
git add .github/workflows/tests.yml
git commit -m "補 CI：backend 測試不用 docker 也能跑，過去只在本機 make test 跑過

conftest 用 in-memory SQLite 並 mock 掉外部服務，所以 Actions 上直接 pip install 就能跑。
README 的 132 tests 從此有一個公開的來源。

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
git push
```

- [x] **Step 5: 等 CI 結果**

```bash
sleep 90; gh run list --limit 1; gh run view --log-failed 2>/dev/null | tail -20
```
Expected: `completed success`。失敗就讀 log，回到 Task 1 Step 3 的規則判斷。

---

### Task 3: 數字對齊

**Files:**
- Modify: `README.md:374`
- Modify: `~/Projects/career-ops/cv.md`（SecuRAG 那段的「109 tests, 0 failures」）

- [x] **Step 1: 從 CI log 抓數字**

```bash
cd ~/Projects/SecuRAG && gh run view --log 2>/dev/null | grep -oE "[0-9]+ passed[^\n]*" | tail -1
```

- [x] **Step 2: 改 README 第 374 行的 `132 tests, 0 failures` 成實際數字；改 cv.md 的 `109 tests` 成同一個數字，並在 README 的 badge 區加一行**

```markdown
[![tests](https://github.com/lin891020/SecuRAG/actions/workflows/tests.yml/badge.svg)](https://github.com/lin891020/SecuRAG/actions/workflows/tests.yml)
```

- [x] **Step 3: Commit**

```bash
cd ~/Projects/SecuRAG && git add README.md && git commit -m "README 的測試數字改成 CI 跑出來的那個，加 badge

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" && git push
cd ~/Projects/career-ops && git add cv.md && git commit -m "SecuRAG 測試數對回 CI 實際值

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [x] **Step 4: 補 HANDOFF.md（這個 repo 還沒有）**

```bash
cat > ~/Projects/SecuRAG/HANDOFF.md <<'H'
# HANDOFF

最後更新：<今天日期>。

## 現在在哪一步
專案已完成，維護模式。<日期> 補了 CI（`.github/workflows/tests.yml`），backend 測試不用 docker 也能跑。

## 已驗證
- CI 綠燈：<N> passed（run <url>）

## 只是寫了、還沒驗證
- （無）

## 已知但沒修
- （Task 1 Step 3 記下的東西，若有）
H
cd ~/Projects/SecuRAG && git add HANDOFF.md && git commit -m "加 HANDOFF.md

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>" && git push
```
