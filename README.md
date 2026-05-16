# Bragi

现有小说 Agent 常常受限于短期记忆：写到后面忘记前文设定，角色关系互相打架，世界观越写越乱，想象力也被上下文窗口压得越来越窄。Bragi 试图解决这个问题。它把架空世界拆成可追踪、可扩展、可长期保存的时间、空间、角色和事件节点，让 AI 不只是临时编一段，而是带着世界记忆继续创作。

Bragi 是一个面向幻想创作者的 AI 架空世界与互动故事引擎。给它一句世界设定，它会像搭建一座会呼吸的宇宙一样，生成历史、地理、角色、事件和剧情，并在后续创作中持续记住这些设定。

它不是只写一段短故事的玩具。Bragi 会把世界拆成可追踪的时间路径和空间路径，只在需要时扩展节点，让故事既能不断变大，又不会把所有信息一次性塞进上下文。你可以用它生成架空大陆、未来都市、魔法王朝、诡异海域、群像冒险，甚至让同一个世界持续写成长期连载。

## 核心能力

- **一句话生成架空世界**：从简单提示开始，生成世界概览、底层规则、历史脉络和空间结构。
- **时间与空间双树结构**：用 `1,2,3` 这样的数字路径定位历史阶段和地点层级，方便持续扩展。
- **按需补全世界细节**：当前剧情所处的时间和地点保留完整内容，附近节点保留摘要，需要时再扩写。
- **自动生成角色网络**：生成主角、配角、关系、状态变化，并在故事推进时更新人物。
- **持续写故事**：根据世界观、当前地点、历史事件、角色状态和用户方向继续生成剧情。
- **事件与上下文管理**：自动记录公开事件、个人事件、主角选择、管理器提示和 token 用量。
- **CLI + Web UI**：既能在命令行跑完整流程，也能打开本地黑白可视化界面操作。
- **多 Agent 支持**：内置本地 Demo Agent，也支持 OpenAI 和 DeepSeek JSON Agent。

## 项目结构

```text
.
├── config/                 # 默认配置和示例配置
├── docs/                   # 架构说明
├── src/story_world/        # 核心代码
│   ├── agents.py           # Demo / OpenAI / DeepSeek Agent
│   ├── cli.py              # 命令行入口
│   ├── generator.py        # 世界生成与节点扩展
│   ├── story.py            # 故事会话管理
│   ├── characters.py       # 角色生成与更新
│   ├── storage.py          # 世界文件存储
│   └── web.py              # 本地 Web UI
├── tests/                  # 单元测试
└── runtime/                # 运行时生成内容，默认不提交
```

更细的模块边界见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 环境要求

- Python `3.10+`
- 推荐使用虚拟环境
- 可选：OpenAI API Key，用于真实 GPT 生成
- 可选：DeepSeek API Key，用于 DeepSeek 生成

本地 Demo Agent 不需要任何外部 API，适合先验证流程。

## 安装

克隆仓库：

```bash
git clone https://github.com/wailers9/bragi.git
cd bragi
```

创建虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

安装项目：

```bash
python -m pip install -U pip
python -m pip install -e .
```

如果你要运行测试：

```bash
python -m pip install pytest
python -m pytest -q
```

## 配置 API Key

### OpenAI

```bash
export OPENAI_API_KEY="你的 OpenAI API Key"
```

使用 OpenAI 时，默认模型写在 `config/worldgen.json`：

```json
{
  "agent": {
    "default_agent": "demo",
    "model": "gpt-5.5",
    "reasoning_effort": null,
    "temperature": 1.2,
    "top_p": 0.98
  }
}
```

你也可以在命令里临时覆盖：

```bash
--agent openai --model gpt-5.5
```

### DeepSeek

```bash
export DEEPSEEK_API_KEY="你的 DeepSeek API Key"
```

使用方式：

```bash
--agent deepseek --model deepseek-chat
```

## 配置文件

默认会读取：

```text
config/worldgen.json
```

如果你想保留自己的配置，可以复制示例：

```bash
cp config/worldgen.example.json config/worldgen.local.json
```

然后运行命令时指定：

```bash
--config config/worldgen.local.json
```

常用配置项：

- `runtime.worlds_root`：生成世界保存目录，默认 `runtime/worlds`
- `space_depth`：空间树深度
- `history_depth`：历史树深度
- `space_default_branching`：每层空间分支数量
- `history_default_branching`：每层历史分支数量
- `world_generation.personal_requirements`：世界生成偏好
- `story.generation_requirements`：故事写作风格要求
- `story.min_story_chars`：单段故事最低字数
- `story.story_length_mode`：故事长度模式，支持 `normal`、`long`、`infinite`
- `story.update_cadence`：时间和地点更新节奏，支持 `slower`、`normal`、`faster`

## 快速开始：本地 Demo

不配置 API，也可以先跑通完整世界初始化流程：

```bash
PYTHONPATH=src python -m story_world.cli init-demo \
  --prompt "一个漂浮群岛上的魔法工业时代" \
  --time-id 2,1,3 \
  --space-id 1,2,2 \
  --protagonist "年轻的飞艇机械师"
```

输出里会包含 `world_id`，后续扩展世界和写故事都要用它。

运行后生成内容会保存在：

```text
runtime/worlds/<world_id>/
```

## 一条命令开始写故事

用真实 Agent 创建世界并开始故事：

```bash
PYTHONPATH=src python -m story_world.cli play \
  --agent openai \
  --model gpt-5.5 \
  --prompt "一个被月亮潮汐撕裂的海上王国" \
  --protagonist "年轻的灯塔学徒" \
  --world-requirements "底层规则简单易懂，但必须有强烈的新鲜感" \
  --generation-requirements "减少景物堆砌，像小说一样清楚、生动、有悬念"
```

`play` 默认会进入互动模式。生成一段故事后，你可以直接输入下一步方向，例如：

```text
调查昨夜消失的船队
```

输入 `q` 退出。

只生成一段并退出：

```bash
PYTHONPATH=src python -m story_world.cli play \
  --agent openai \
  --prompt "一座建在巨兽背上的移动城市" \
  --protagonist "被流放的城市医生" \
  --once
```

打印完整内部上下文：

```bash
PYTHONPATH=src python -m story_world.cli play \
  --agent openai \
  --world-id "<world_id>" \
  --protagonist "年轻的灯塔学徒" \
  --full
```

## Web 可视化界面

启动本地 Web UI：

```bash
PYTHONPATH=src python3 -m story_world.web --host 127.0.0.1 --port 8765
```

打开：

```text
http://127.0.0.1:8765
```

Web UI 可以完成：

- 创建世界
- 初始化时间、空间和角色
- 生成当前故事片段
- 提交用户方向继续剧情
- 查看当前时间路径、空间路径、节点摘要、角色变化、事件更新和管理器提示

## 常用 CLI 流程

### 1. 创建世界并初始化当前位置

```bash
PYTHONPATH=src python -m story_world.cli init-demo \
  --agent openai \
  --prompt "一个所有影子都拥有记忆的王国" \
  --time-id 1,2,3 \
  --space-id 2,1,1 \
  --protagonist "失去影子的书记官"
```

### 2. 扩写某个历史节点

```bash
PYTHONPATH=src python -m story_world.cli enrich-history \
  --agent openai \
  --world-id "<world_id>" \
  --prompt "一个所有影子都拥有记忆的王国" \
  --time-id 1,2,2
```

### 3. 扩写某个空间节点

```bash
PYTHONPATH=src python -m story_world.cli enrich-space \
  --agent openai \
  --world-id "<world_id>" \
  --prompt "一个所有影子都拥有记忆的王国" \
  --space-id 2,1,2
```

### 4. 构建故事上下文

```bash
PYTHONPATH=src python -m story_world.cli build-context \
  --world-id "<world_id>" \
  --time-id 1,2,3 \
  --space-id 2,1,1
```

### 5. 初始化角色

```bash
PYTHONPATH=src python -m story_world.cli init-characters \
  --agent openai \
  --world-id "<world_id>" \
  --time-id 1,2,3 \
  --space-id 2,1,1 \
  --protagonist "失去影子的书记官" \
  --others "生成2到4个和主线强相关的角色"
```

### 6. 开始故事会话

```bash
PYTHONPATH=src python -m story_world.cli story-start \
  --agent openai \
  --world-id "<world_id>" \
  --time-id 1,2,3 \
  --space-id 2,1,1 \
  --protagonist "失去影子的书记官" \
  --generation-requirements "像通俗幻想小说，节奏快，人物行动明确"
```

### 7. 提交选择并继续

```bash
PYTHONPATH=src python -m story_world.cli story-choose \
  --agent openai \
  --session-id "<session_id>" \
  --choice-text "去档案馆寻找第一任国王的影子记录"
```

## 数据如何保存

每个世界都有独立目录：

```text
runtime/worlds/<world_id>/
```

常见文件：

```text
runtime/worlds/<world_id>/manifest.json
runtime/worlds/<world_id>/index.json
runtime/worlds/<world_id>/usage.json
runtime/worlds/<world_id>/events/<history_path>.json
runtime/worlds/<world_id>/sessions/<session_id>.json
```

时间节点会按路径嵌套保存。比如 `1,3,3` 可能保存为：

```text
runtime/worlds/<world_id>/history/1.0.0/1.3.0/1.3.3/node.json
```

空间节点会挂在当前时间节点下面。比如当前时间是 `1,3,3`，空间是 `2,1,1`：

```text
runtime/worlds/<world_id>/history/1.0.0/1.3.0/1.3.3/space/2.0.0/2.1.0/2.1.1/node.json
```

`index.json` 会记录节点状态：

- `summary`：只有摘要
- `full`：完整节点
- `pending_agent_completion`：等待 Agent 补全

## 调试与 token 用量

每次 Agent 调用都会记录用量：

```text
runtime/worlds/<world_id>/usage.json
```

如果 `config/worldgen.json` 中启用：

```json
{
  "story": {
    "debug_story_agent_input": true,
    "print_story_agent_input": false
  }
}
```

故事 Agent 的输入会保存到：

```text
runtime/worlds/<world_id>/debug/story_agent_input_turn_0000.txt
```

如果你想直接在终端打印完整提示词，可以加：

```bash
--print-story-agent-input
```

## 开发

安装开发依赖：

```bash
python -m pip install -e .
python -m pip install pytest
```

运行测试：

```bash
python -m pytest -q
```

运行 Web UI：

```bash
PYTHONPATH=src python3 -m story_world.web --host 127.0.0.1 --port 8765
```

## 适合用来做什么

- 架空世界设定生成器
- 长篇小说或跑团世界观辅助工具
- 互动小说原型
- AI Agent 叙事系统实验
- 世界状态、角色状态、事件状态持续演化的故事沙盒
