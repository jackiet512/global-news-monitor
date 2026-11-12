# 全球新闻中心

网站从中文新闻订阅源收录国际政治、人工智能与科技、全球经济金融、社会与突发事件。点击标题可查看来源，采集记录列出候选数、新增数和来源错误数。收录条目仍待核实。

采集程序每小时第 7 和第 37 分钟计划运行，实际启动时间由 GitHub 调度。程序按链接去重，保留来源提供的中文摘要；聚合源只有重复标题时省略摘要。历史外文条目保留在数据库中。

## 部署与检查

采集配置位于 `collector/sources.json`，数据库结构位于 `migrations/`，网站和接口位于 `worker/`。部署步骤见 [部署说明](docs/CLOUDFLARE_SETUP.md)。

```sh
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```
