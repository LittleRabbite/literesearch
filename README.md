# 文献调研智能体

## 项目概览

### 定位

给定一个研究主题，自动完成「检索 → 去重 → 筛选 → 综述 → 引用核验 → BibTeX → 人工审核」全流程，产出**结构化综述 + 文献矩阵 Excel + 可导入 BibTeX** 的文献调研智能体。

### 解决了什么问题

| 传统痛点                                                                      | 本项目的解法                                                                                              |
| ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| 调研要在 arXiv / Semantic Scholar / CrossRef / DBLP 多平台反复横跳，搜集-去重-筛选-排版引用动辄数天 | 8 节点 LangGraph 流水线一次跑通，主题进、成果出                                                                      |
| 让 LLM 直接写综述 → **幻觉引用**（编造文献、张冠李戴），不敢用                                     | 综述强制 `[n]` 引用标注 + 每条引用回 **CrossRef 实名核验**（标题相似度+年份双阈值），BibTeX 从 arXiv/DOI/DBLP **三级真实拉取**，不生成任何编造条目 |
| 检索结果同一论文多版本重复入库                                                           | 嵌入语义去重：标题+摘要向量化，余弦相似度 ≥0.93 并查集聚类合并                                                                 |
| 纯自动化结果不可信，纯人工效率太低                                                         | **human-in-the-loop**：流程在人工审核点挂起，可剔除文献/提交意见重写/定向补检，AI 干活、人把关                                        |
| 流程黑箱、中途刷新全丢                                                               | SSE 实时推送每个节点进度；SqliteSaver 断点续跑，刷新页面快照恢复                                                            |

### 核心优势

1. **可信优先的架构**——「生成」与「核验」分离：writer 只写、verifier 逐条回查外部数据库，把 LLM 幻觉挡在出口处；核验不过的引用带标注留给人工裁决。
2. **人机协同是一等公民**——审核不是弹窗而是主界面：三按钮审核条 + 文献卡上直接剔除/定位引用，反馈驱动 LangGraph `interrupt/resume` 回流。
3. **质量可评估、可迭代**——screening 是漏斗咽喉，配套离线评估闭环（`backend/eval/`）：黄金集 + nDCG\@10 / Precision\@15 / Recall\@15 / 加权 kappa / 去重阈值扫描，接 Langfuse 后每次改 rubric/换模型跑一遍即可并排对比，筛选质量靠数据迭代而非凭感觉。
4. **工程可落地**——FastAPI SSE 事件协议 + Next.js 三区式工作台（流程面板/成果四 Tab/审核条）、引用 chip 双向联动、明暗主题、md/bib/xlsx 三格式导出、Zotero 一键入库。
5. **零成本演示**——`MOCK_LLM=1` 用假 LLM 跑通全流程（检索仍是真实的），无 API Key 也能完整体验产品闭环。

**实现要点**：

- 工具链：arXiv API / Semantic Scholar / CrossRef / Web of Science（有权限时）→ PDF 下载解析 → 向量化
- 多 Agent 分工（LangGraph 多智能体）：
  - **检索 Agent**：多源召回
  - **筛选 Agent**：按相关性/影响力/时效打分过滤
  - **综述 Agent**：分主题归纳、对比方法、找 research gap
  - **核验 Agent**：核对引用真实性（反幻觉关键步骤）
- 输出结构化综述 + 文献矩阵（Excel）


## 技术栈与接口设计

**前端**：Next.js + React + TypeScript；Zustand 管理会话状态；`react-markdown` 渲染综述（自定义 `[n]` chip 组件）；TanStack Table 做文献矩阵；SSE 用原生 `EventSource`。

**后端**：FastAPI，薄封装层，不重新实现逻辑：

```plain
POST /api/sessions              → 创建任务，返回 {session_id = LangGraph thread_id}
GET  /api/sessions/{id}/events  → SSE，透传 graph.stream 事件
                                  （节点进入/退出 + writer 的 token + 各 artifact）
POST /api/sessions/{id}/feedback → body: {action: approved|rewrite|refetch, comment}
                                   → update_state + stream(None) 续跑
GET  /api/sessions/{id}/export?format=md|bib|xlsx
```

SSE 事件协议（前后端契约）：

```json
{"type": "node_start", "node": "screening"}
{"type": "artifact", "node": "screening", "data": {"screened": [...]}}
{"type": "token", "node": "writer", "content": "近年来..."}
{"type": "interrupt", "node": "human_review"}        ← 前端据此弹出审核条
{"type": "done"}
```


***
### 系统LangGraph 状态图
<img width="960" height="912" alt="image" src="https://github.com/user-attachments/assets/403240d0-f3c6-4119-a833-13e9fe57ac71" />


## 配置说明

### 1. S2\_API\_KEY 的申请

`S2_API_KEY` 是 Semantic Scholar Academic Graph API 的鉴权密钥。在本项目里用于 tools.py 的`search_semantic_scholar` ——retriever 节点多源检索的第二路来源（第一路是 arXiv，arXiv 不需要 key）。

- 不填也能跑 ：走公开共享池，限速约 1000 次/5分钟，高峰期容易 429（代码里已做了 3 次指数退避重试，仍失败就降级跳过该来源，不影响流程）
- 填了的好处 ：独享配额（约 1 req/s 稳定通道），检索命中更稳定，429 明显减少

申请路径：

1. 打开 <https://www.semanticscholar.com/product/api>
2. 点击页面中的 "Request API Key" （表单直达： <https://www.semanticscholar.org/product/api#api-key-form> ）
3. 填写姓名、邮箱、用途描述（学术用途免费，一般 1\~3 个工作日发到邮箱）
4. 收到 key 后填入 .env 的`S2_API_KEY=` 即可，重启后端生效
   如果只是先用 Mock 模式演示或以 arXiv 为主的调研，不填也完全够用。

### 2. Zotero API Key 的申请

① 登录账号‌：进入 Zotero 官网，使用你的 Zotero 账号登录。

② 进入密钥页面‌：点击右上角头像进入设置，找到 ‌Security（安全）‌ 或直接访问密钥管理页 <https://www.zotero.org/settings/keys。>

③ 创建新密钥‌：点击 ‌Create new private key‌，输入任意名称（如 "MCP Server"）。

④ ‌勾选权限‌：根据用途勾选权限。如果只是读取文献库，勾选 ‌Allow library access‌ 的只读权限即可；如需写入则勾选读写权限。

⑤ 保存并复制‌：点击保存后，页面会弹出 API Key，‌只显示一次‌，务必立即复制备份。‌‌

⚠️ 注意事项
API Key 生成后不会再次完整显示，建议先保存到密码管理器，再继续配置。如果怀疑泄露，可在同一页面删除旧 Key 并重新生成。‌‌

📌 补充说明

‌用户 ID 获取‌：拿到 Key 后，如需获取 userID，可运行 `curl -H "Zotero-API-Key: 你的密钥" https://api.zotero.org/keys/current`，返回的> JSON 中 userID 字段即是。

<br />

### 3. 嵌入模型

有 GPU 时把`.env` 的`EMBED_MODEL` 换回`BAAI/bge-m3` 提升去重质量（已用单例缓存，进程内只加载一次）

## 多用户与历史记录

### 多用户认证

- 注册/登录后使用，用户名 2–32 字符、密码至少 6 位；密码以 **pbkdf2\_sha256（20 万轮加盐）** 哈希存储，不落明文
- 登录签发 30 天会话令牌，通过 **HttpOnly Cookie** 自动携带（fetch 与 SSE 均无需手动附加）
- 除健康检查与认证接口外，**全部接口要求登录**；访问/删除/导出/推送他人的会话一律返回 404（不暴露存在性）
- 每个用户的调研会话、历史记录、导出与 Zotero 推送完全隔离
- **存量迁移**：升级前创建的历史会话（user\_id 为空）自动归属**第一个注册的用户**

### 历史调研记录

- 会话元数据持久化于 `backend/data/sessions.sqlite`（完整状态由 LangGraph checkpointer `checkpoints.sqlite` 持有），后端重启不丢
- 首页与工作台顶栏的「历史调研」抽屉支持：按主题搜索、一键恢复会话（SSE 快照续看）、行内二次确认删除
- 列表项直接展示漏斗统计：原始 → 入选 → 核验通过率；后端重启时执行中的会话会标记为「后端重启，执行被中断」

### 公网部署安全建议

- 域名走 HTTPS 后，在反向代理（Nginx/Caddy）层追加 `Secure` Cookie 标志与 HSTS
- LLM/Zotero 等 API Key 仅存于服务端 `.env`，不下发前端；建议为 Zotero Key 单独创建最小写权限

***

## 最近更新（2026-09）

### 1. 数据源扩展：4 路多源检索

- 在 arXiv、Semantic Scholar 之外新增 **OpenAlex** 与 **ChinaXiv** 两路国内/国际学术数据源
- OpenAlex 无需密钥；ChinaXiv 接口维护中时自动降级跳过，不阻塞主流程
- retriever 节点并行检索四路来源，统一去重入库

### 2. 前端体验改版（输入页 / 工作台 / 审核区）

- **输入页**：「开始调研」改品牌琥珀金主按钮（hover 抬升 + loading 态）；年份/上限 number 联动校验（起始 ≤ 截止，红框行内提示）；示例主题 chips 一键填入；新增「你将得到」输出预览区；数据源品牌徽标；窄屏单列堆叠
- **核验一级信号**（最重要）：核验未全过时内容区顶部琥珀警告横幅（可直达核验报告）、正文未核验引用上标黄警 + 删除线 + 悬停提示、流程栏 verifier 琥珀态、「通过并导出」弹确认对话框拦截
- **流程栏**：每步显示耗时、可展开查看该步日志（检索式/命中数）、底部漏斗统计条「第 X 轮 · 原始 63 → 入选 15 → 通过 6/15」、去重筛选节点直接标注「63 → 15」
- **顶栏收敛**：4 个导出按钮合并为「导出 ▾」下拉（Zotero 独立保留），待审核时标注「草稿导出」，会话号收纳进菜单
- **审核区**：「提交意见重写」升为主按钮、定向补检收纳进「更多 ▾」、快捷意见 chips 点选即填、新增「综述字数 · 撰写耗时 · 修订轮次」元信息行

### 3. 历史记录 + 多用户（详见上文）

- 后端：会话元数据 SQLite 持久化、`GET /api/sessions` 列表 / `DELETE /api/sessions/:id`、重启恢复 + 旧会话自动迁移
- 前端：历史调研抽屉（搜索/恢复/删除）+ 双入口
- 多用户认证与数据隔离全量上线

***

## 运行命令

```
# 后端
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --port 8000

# 前端-开发模式
npm run dev
```

### 生产模式（可选）

```
# 前端构建 + 启动
npm run build
npm run start
# 后端同上；注意 SSE 长连接，uvicorn 保持单 worker，不要加 --workers N
```

### Docker 部署（前端）

前端采用 Next.js standalone 输出，多阶段构建（构建产物约 200MB 级，不含源码与完整 node\_modules）：

```
cd frontend
docker compose up -d --build     # 构建并启动，访问 http://localhost:3000
docker compose logs -f frontend  # 查看日志
```

- 后端地址通过环境变量 `BACKEND_URL` 注入（默认 `http://host.docker.internal:8000`，即宿主机上运行的后端；后端保持用本命令方式跑在宿主机即可）
- Linux 宿主机需保留 compose 中的 `extra_hosts: host.docker.internal:host-gateway`
- 后端也可容器化：取消 `docker-compose.yml` 中 backend 段的注释，并把 `BACKEND_URL` 改为 `http://backend:8000`（后端镜像需自行构建，注意嵌入模型与 PyTorch 体积较大）
- SSE 实时推送已通过 `compress: false` 与 `X-Accel-Buffering: no` 保障，若外层再加 Nginx 需对其 `proxy_buffering off`

### 测试

```
# 持久化层测试（12 项）
.venv\Scripts\python.exe backend\tests\test_persistence.py
# 多用户认证与隔离测试（19 项）
.venv\Scripts\python.exe backend\tests\test_auth.py

```

