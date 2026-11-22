---
name: spend-gate-wizard
description: 给现有仓库接入 agent-spend-gate —— 扫描付费 API 调用、问清楚哪些要人批、包装代码、一次指纹配好白名单。触发词：接入 spend-gate、包装付费调用、加花钱闸门、spend gate wizard、setup spend-gate。
---

# spend-gate 接入向导

目标：把一个现有仓库里所有付费 API 调用找出来，包装成 human-in-the-loop，并且**只让用户按一次指纹**就把白名单配完。

## 步骤

### 1. 扫描

```bash
python3 <this-skill-dir>/scan_paid_calls.py <repo-root>
```

输出 JSON，每个条目是 `{file, line, vendor, snippet, kind}`。`kind` 是 `sdk`（import 了付费 SDK）或 `url`（硬编码了付费端点）。

先向用户报告扫描结果，按 vendor 汇总：

```
openai      12 处（8 个文件）
dashscope    5 处
elevenlabs   3 处
```

如果扫不到，明说「没找到」，不要编。

### 2. 一次问清楚（关键步骤）

**不要自己决定白名单。** 用 AskUserQuestion 一次问完，最多四个问题：

1. **哪些供应商可以免批？**（multiSelect，选项是扫描到的 vendor）
   - 说明：免批=不弹窗，但仍受限额约束；超限照样问。
2. **全局日/周/月限额设多少？**（单选：不设 / 保守 / 宽松 / 自定义）
   - 保守示例：日 5、周 20、月 60
   - 宽松示例：日 50、周 200、月 600
3. **免批的供应商要不要单独限额？**（单选：跟他们一样 / 更紧 / 不设）
4. **超限时的默认行为？**（单选：弹窗让我决定 / 直接拒绝）

### 3. 生成策略文件并一次载入

把答案写成 JSON：

```json
{
  "currency": "CNY",
  "daily_limit": 5,
  "weekly_limit": 20,
  "monthly_limit": 60,
  "hard_limit": false,
  "vendors": {
    "openai": {"trusted": true, "daily_limit": 3},
    "dashscope": {"trusted": true}
  }
}
```

然后**只调用一次**：

```bash
spend-gate policy load /tmp/spend-gate-policy.json
```

这一次会弹一次确认框 + 一次指纹。告诉用户：接下来按一次指纹就好。

不要用 `policy set` 循环配——那样每配一个 vendor 弹一次。

### 4. 包装代码

对每个调用点：

1. 文件顶部加 `from spend_gate import require_approval`
2. 在付费调用**之前**插入：

```python
require_approval(
    amount=<估算>,          # 能算就算；算不出用 envelope
    currency="CNY",
    vendor="<vendor>",
    purpose="<这个调用在做什么>",
    quantity="<数量，可选>",
)
```

金额怎么估：
- 有明确单价的（图片 0.2/张、token 按量）→ 用调用参数算，比如 `n * 0.2`
- 算不出来的 → 改用 `open_envelope(max_amount=..., ttl_hours=...)` 包住整段循环
- **不要写 `amount=0` 占位**，那会让免批策略误放行

### 5. 报告

给用户一张表：

| 文件:行 | vendor | 处理方式 |
|---|---|---|
| x.py:42 | openai | 已包装，amount=0.02 |
| y.py:88 | dashscope | 改用 envelope |
| z.py:15 | elevenlabs | **未包装**，原因：金额依赖运行时 |

**必须列出没包装的**。漏掉不报等于骗人。

## 边界（要跟用户讲清楚）

- 这个库靠自觉：没包装的调用完全不设防，也不会报错。
- agent 如果能改自己的代码，能绕过。
- 白名单只免打扰，不免限额。

## 不要做的事

- 不要替用户决定哪些 vendor 免批。
- 不要为了「跑通」把 `amount` 填 0。
- 不要设置 `SPEND_GATE_BYPASS`。
- 不要在没跑测试的情况下声称「全部覆盖」。
