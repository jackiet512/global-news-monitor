# TASK-002 任务合同：修复 Worker 内嵌前端脚本模板转义语法错误并增加 `vm.Script` 解析门禁

- **task_id**: `TASK-002`
- **contract_version**: `1`
- **owner**: `fanjie`（规划与独立验收：Antigravity；研发执行：Cursor via AO）
- **base_commit**: `85d8bc8b6646ccb707b532b67f6f2e27d6153bc6`（`main` 基线；工作分支基线为 `fix/inline-script-escape`）
- **dependencies**: 无
- **role_bindings**:
  - `planner`: `antigravity`
  - `developer`: `cursor`（AO harness=`cursor`, model=`composer-2.5`）
  - `acceptor`: `antigravity`
- **limits**: `max_revisions=2; max_developer_runs=3; max_acceptor_runs=3; max_infrastructure_retries=1; timeout_min=60; allow_paid_api=false`

---

## 1. Objective（任务目标）

修复线上页面一直停留在 `正在连接… / 当天新闻 / 加载中…` 的 P0 缺陷，并在单元测试中新增浏览器内嵌 `<script>` 真实解析与执行门禁，彻底杜绝同类模板字符串转义故障再次漏检。

### 根因确认
`worker/src/index.js` 第 220 行在外层 JS 模板字符串 `` const PAGE = `...` `` 中编写了：
```js
function safeHref(u){return /^https?:\/\//i.test(u||'')?u:''}
```
外层模板字符串会把 `\/` 吞掉反斜杠变成 `/`，导致下发给浏览器的 HTML 内嵌脚本变成：
```js
function safeHref(u){return /^https?:///i.test(u||'')?u:''}
```
其中的 `//` 注释掉了该行剩余部分与闭合大括号 `}`，浏览器抛出 `SyntaxError: Unexpected end of input`，整段前端脚本无法执行。

---

## 2. Scope In（包含范围）

1. **修复 `worker/src/index.js`**：
   - 修正 `PAGE` 内 `safeHref(u)` 实现，使用无反斜杠转义歧义的写法（例如 `/^https?:\\/\\//i` 或更直观的 `const s=String(u||'');return /^https?:/i.test(s)&&(s.slice(0,8).toLowerCase()==='https://'||s.slice(0,7).toLowerCase()==='http://')?s:''` 或 `new RegExp('^https?://','i').test(u||'')?u:''`），保证下发给浏览器的 HTML 内嵌 `<script>` 100% 合法可解析。
   - 排查整个 `PAGE` 字符串及 `GET /` 两种分支（有/无 `GITHUB_ACTIONS_TOKEN`）中所有反斜杠与正则字面量，确保不存在其他模板字符串转义问题。
2. **加固 `tests/test_worker_pulse.py`**：
   - 在 Node 运行时测试中分别请求 `GET /`（分别测试 `GITHUB_ACTIONS_TOKEN: "tok"` 与 `GITHUB_ACTIONS_TOKEN: ""` 两种环境变量分支），正则提取 `<script>...</script>` 正文并通过 `new vm.Script(code)` 校验浏览器内嵌脚本语法 100% 通过；
   - 在隔离 `vm` 上下文中实测内嵌函数 `safeHref` 与 `renderPulse`：
     - `safeHref('https://polymarket.com/event/x')` 返回原链接；
     - `safeHref('http://example.com/a')` 返回原链接；
     - `safeHref('javascript:alert(1)')`、`safeHref('https:evil')`、`safeHref('')` 返回 `''`；
     - `renderPulse` 对 `<script>alert(1)</script>` 做 `esc()` 转义且不生成 `javascript:` 链接。

---

## 3. Scope Out（排除范围）

- 不修改任何 `collector/` Python 模块或 `migrations/` 文件；
- 不执行 `git push`、`gh pr create`、`wrangler deploy`。

---

## 4. Allowed Paths

- `worker/src/index.js`
- `tests/test_worker_pulse.py`

---

## 5. Acceptance Criteria

- **AC1**：`worker/src/index.js` 经 `node --check` 退出码 `0`，且 `GET /` 在有/无 `GITHUB_ACTIONS_TOKEN` 两种模式下渲染出的 `<script>...</script>` 均通过 Node `new vm.Script(code)` 语法校验。
- **AC2**：`safeHref` 放行 `https://` 与 `http://`（不区分大小写），阻断 `javascript:`、`data:`、`https:no-slashes` 及空值；`renderPulse` 正常渲染并完成 XSS 转义。
- **AC3**：`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v` 全部 `OK`（退出码 `0`）。

---

## 6. Deliverables & Test Commands

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

完成后在当前 AO worktree 本地 `git commit`，并通过 `/Users/fanjie/.local/bin/ao report --done` 上报（携带 `task_id: TASK-002`、`contract_version: 1`、`attempt: 1`、`result_sha`、测试结果、`REVIEW_REQUIRED`），随后结束回合。
