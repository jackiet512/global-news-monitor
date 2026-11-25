# 全球新闻中心

网站从中文新闻订阅源收录国际政治、人工智能与科技、全球经济金融、社会与突发事件，并整合 Hacker News 科技热榜、Polymarket 预测市场概率标签及 HN/Reddit 社区讨论脉络。点击标题可查看来源，展开「社区与市场脉络」可查看关联盘口与讨论；采集记录列出候选数、新增数和来源错误数。收录条目仍待核实。

采集程序每小时第 7 和第 37 分钟计划运行，实际启动时间由 GitHub 调度。程序按链接去重，保留来源提供的中文摘要；聚合源只有重复标题时省略摘要。历史外文条目保留在数据库中。

## 部署与检查

采集配置位于 `collector/sources.json`，数据库结构位于 `migrations/`，网站和接口位于 `worker/`。部署步骤见 [部署说明](docs/CLOUDFLARE_SETUP.md)。

```sh
python3 -m pip install -r requirements.txt
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

新增 `migrations/0002_context.sql` 用于 `news_context` 表（Polymarket / 社区脉络缓存）。Worker 提供 `/api/pulse?fingerprint=...` 按需查询接口。
