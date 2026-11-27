# TASK-004 任务合同：跨源同事件自动合并为单条多源新闻卡片（采集端 + Worker 展示端）

- **task_id**: `TASK-004`
- **contract_version**: `1`
- **owner**: `fanjie`（规划与独立验收：Antigravity；研发执行：Cursor via AO）
- **base_commit**: `8aab1d17df8bffc16ffaeca662ee8bc3f0288f01`（`main` 基线；工作分支为 `feat/event-clustering-merge`）
- **dependencies**: 无
- **role_bindings**:
  - `planner`: `antigravity`
  - `developer`: `cursor`（AO harness=`cursor`, model=`composer-2.5`）
  - `acceptor`: `antigravity`
- **limits**: `max_revisions=2; max_developer_runs=3; max_acceptor_runs=3; max_infrastructure_retries=1; timeout_min=60; allow_paid_api=false`

---

## 1. Objective（任务目标）

解决同一重大事件被多家媒体或跨轮次采集重复展示成多张卡片的问题（例如「感恩节大风暴洪水/延误/停电」和「两名意大利人在科威特袭击中丧生、伊朗否认负责」的多篇同类报道），在**采集端去重**与**Worker `/api/news` 展示聚类端**同步升级，将同一事件的多源报道**自动合并到同一张新闻卡片中**，保留各家媒体原文链接与多源背书，同时严防不同事件误合并。

---

## 2. Scope In（包含范围）

### 2.1 升级采集端同事件识别（`collector/events.py`）
- 扩展 `ALIASES` 同义词/译法归一化表，补充高频新闻同义表述：
  - 死亡类：`丧生` ← `死亡`, `身亡`, `遇难`, `致死`, `毙命`
  - 气象/灾害类：`风暴` ← `大风暴`, `暴风雨`, `强风暴`
  - 动作/表述类：`导致` ← `带来`, `造成`, `引发`, `致使`；`袭击` ← `袭击事件`, `空袭`, `无人机袭击`；`否认` ← `驳斥`, `拒绝承认`；`指控` ← `指责`, `控告`
- 增强 `same_event(a, b)` 的中文事件线索判断：
  - 过滤中文常见虚词/连接词（如 `的`, `在`, `中`, `给`, `被`, `对`, `此`, `和`, `与`, `、`, `，`, `了`, `将`, `称`, `表示`, `强大`）后再提取二元词组/关键实词，使核心事件词重合度不被修饰语稀释；
  - 在原有条件基础上，当时间差 `<= 72h` 且共享归一化中文二元词组 `>= 4`、占较短标题有效二元词组比例 `>= 0.40`（且无冲突地理/机构实体）时判定为同一事件；
  - 保留既有全部 `test_events.py` 正反例通过（包括 `无名烈士墓` vs `弹劾投票` 不合并、`法国学校炸弹威胁` vs `意大利学校炸弹威胁` 不合并）。

### 2.2 Worker `/api/news` 跨轮次同事件聚类合并（`worker/src/index.js`）
- 在 `worker/src/index.js` 中实现纯确定性的 `clusterNewsItems(items)`，在 `GET /api/news` 完成体育过滤后、返回响应前对当日列表执行跨轮次、跨媒体同事件聚类：
  - **归一化与相似度判定**：与 `collector/events.py` 同源的中文同义词归一化 + 虚词剔除 + 中英文词元/二元词组重合度计算（时间窗 `<= 72h`），并加入**冲突主体保护**（例如不同国家 `法国`/`意大利`/`日本`/`德国`、不同科技巨头 `OpenAI`/`Anthropic`/`谷歌`/`微软`、不同央行 `美联储`/`欧洲央行`/`日本央行` 若彼此互斥且缺乏共同事件地标则不误合并）。
  - **簇内合并策略**：
    - 选定主条目（优先信息最完整：正文 `reading_text` 更长或带配图，其次按时间较新）；
    - 将簇内其他报道整理为 `related_sources: [{ source_name, title, url, published_at }, ...]`（按 `url` 去重，排除主条目自身）；
    - 附加 `source_count`（`1 + related_sources.length`）；
    - 自动补齐主条目缺失的 `image_url`、`polymarket`；合并簇内 `community.hn` 与 `community.reddit`（按链接/标题去重）；
    - 确保 `fetchLimit` 足够大（如 `Math.min(Math.max(n * 3, 120), 250)`）以免聚类折叠后列表条数过少。

### 2.3 前端多源合并卡片展示（`worker/src/index.js` 内 `PAGE`）
- 当新闻卡片包含 `related_sources`（长度 `>= 1`）时：
  - 在卡片页脚/头部展示清晰的多源标识（如 `多源报道 · 共 3 家` 或列出合并来源名）；
  - 在卡片正文下方提供克制紧凑的「同题相关报道 (N)」折叠区或分组列表（使用原生 `<details class="related-sources"><summary>同题报道（另有 N 家媒体）</summary><ul>...</ul></details>`，零 JS 复杂度、体验清爽），列出每篇被合并报道的来源名、标题与安全外链（所有文本经 `esc()` 转义、链接经 `safeHref()` 校验）；
  - 严禁在 `PAGE` 模板字符串中引入未转义正则 `\/`，确保 `test_inline_script_vm_gate` 的 `vm.Script` 语法解析门禁通过。

### 2.4 单元测试（`tests/test_events.py`、`tests/test_worker_pulse.py`）
- 在 `tests/test_events.py` 中新增真实案例回归测试：
  - 必须合并：
    1. `感恩节大风暴给美国带来洪水和航班延误` vs `强大的感恩节风暴导致洪水、停电`
    2. `两名意大利人在科威特袭击中丧生，伊朗否认对此负责` vs `伊朗被指控在科威特发动无人机袭击，造成两名意大利人死亡` vs `两名意大利人在科威特袭击事件中丧生，伊朗否认参与`
  - 严禁误合并：
    1. `OpenAI发布新一代推理模型` vs `Anthropic发布新一代代码模型`
    2. `美联储宣布维持利率不变` vs `欧洲央行宣布降息25个基点`
    3. `法国多所学校收到炸弹威胁` vs `意大利多所学校收到炸弹威胁邮件`
- 在 `tests/test_worker_pulse.py` 中新增 `test_api_news_clusters_same_event`：
  - 向内存 SQLite 写入上述 2 组重复新闻（共 5 条）+ 2 条不同主体的无关新闻（共 7 条），请求 `GET /api/news`；
  - 断言返回 **4 条**合并后的卡片（感恩节风暴 2 合 1、科威特袭击 3 合 1、2 条无关新闻各自独立），且合并卡片包含正确的 `source_count`、`related_sources`、继承的 `polymarket`/`image_url`，并且 `GET /` 渲染的 HTML 通过 `vm.Script` 校验且包含 `related-sources` / `同题报道` 渲染逻辑。

---

## 3. Scope Out（排除范围）

- 不改动数据库表结构或删除历史入库记录（保留原始多源记录，在读取聚类层动态合并，随时可追溯各家原文）；
- 不引入任何大模型或第三方付费 API；
- 不执行 `git push`、`gh pr create`、`wrangler deploy`。

---

## 4. Allowed Paths

- `collector/events.py`
- `worker/src/index.js`
- `tests/test_events.py`
- `tests/test_worker_pulse.py`

---

## 5. Acceptance Criteria

- **AC1**：`collector/events.py` 准确判定上述两组真实重复案例为 `same_event == True`，同时全部非同事件反例（含原有 `test_events.py` 用例及新增反例）均返回 `False`。
- **AC2**：`worker/src/index.js` 的 `GET /api/news` 将同一事件的多篇入库报道合并为 1 条卡片，正确填充 `source_count`、`related_sources`，继承补齐 `image_url`/`polymarket` 并去重合并 `community`；无关新闻绝不误合并。
- **AC3**：前端 `PAGE` 渲染多源徽章与 `<details class="related-sources">` 同题报道折叠列表，所有动态字段经 `esc()` 转义、外链经 `safeHref()` 校验，且 `node --check` 与 `test_inline_script_vm_gate`（有/无 Token 双分支 `vm.Script`）全部通过。
- **AC4**：`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v` 全部 `OK`（退出码 `0`）。

---

## 6. Deliverables & Test Commands

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

完成后在当前 AO worktree 本地 `git commit`，并通过 `/Users/fanjie/.local/bin/ao report --done` 上报（携带 `task_id: TASK-004`、`contract_version: 1`、`attempt: 1`、`result_sha`、测试退出码、`REVIEW_REQUIRED`），随后结束回合。
