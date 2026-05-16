from __future__ import annotations

import json
from typing import Any

from .config import WorldGeneratorConfig
from .ids import NodePath, path_label


WORLD_TEMPLATE = """
你是架空世界设计 Agent。

任务：
为后续“时间结构 Agent、空间结构 Agent、人物 Agent、故事 Agent”提供稳定的世界底座。你只负责世界总体规则，不负责生成具体时间节点、地点节点或人物。

阅读顺序：
先理解用户提示词和个人要求，再设计世界规则、空间分层和时间分层；只输出后续 Agent 必须依赖的底层信息。

多样化要求：
主动避开最近常见的矿区/矿石、雾、晶体/晶化/晶能、海雾、潮汐、记忆、灯塔、译记员、年轻学徒等套路组合；世界规则、文明形态、核心矛盾和命名都要有明显新意。除非用户明确要求，不要把世界核心建立在“矿、雾、晶”任一母题上。

用户提示词：
{user_prompt}

个人要求：
{personal_requirements}

编号与存储约定：
1. 时间和空间都使用多层整数 path，格式样本为 {example_path}。
2. 每个世界创建时会存在第一级模板节点，格式样本为 {template_paths}；0 表示模板/父级占位，不表示具体叶子节点。
3. 编号越靠前的层级越大；共享前缀越长代表时间/空间距离越近；同父级且末位差 1 表示相邻节点。
4. 后续 Agent 会根据你的 space_structure_summary 与 history_summary 填充具体节点，所以这里必须给出清晰的分层原则。

输出要求：
1. world_overview 必须概括世界核心矛盾、文明形态、自然/超自然/科技规则。
2. world_rules 必须列出会影响故事行为边界的稳定规则；没有特殊规则时返回空数组。
3. space_structure_summary 必须说明空间层级如何理解，说明第 1/2/3/4 层分别代表什么。
4. history_summary 必须说明时间层级如何理解，说明各层级分别代表什么时间尺度。
5. world_rules 必须是底层规则：像物理法则、超自然机制、资源约束、社会运行底层机制一样，能长期支配人物选择和世界变化；不要把表层风俗、阵营口号、职业设定、地名介绍当作规则。
6. world_rules 最多 3 条，每条只能写一句话；只写有趣、富有想象力、能反复制造故事选择的特殊底层规则，其它未列出的自然规律、社会常识和人物行为默认符合现实。
7. 如果用户提示词是“随机的架空世界”或类似泛化要求，必须主动拉开题材差异，不要默认落入矿区、矿石能源、雾海、雾城、晶体、晶化病、晶能、潮汐、记忆沉淀、年轻译记员被多方争夺这类高频组合；除非用户明确要求，不要使用“潮历、星潮历、雾海、潮镜、林雾、林雾辞、晶核、晶能、晶化、矿镇、矿脉”等旧套路关键词。
8. 不要输出 schema 以外字段，不要使用 Markdown。

请严格返回 JSON 对象，字段必须完全匹配：
{output_format}

配置：
{config_json}
""".strip()

SPACE_INIT_TEMPLATE = """
你是架空世界空间结构 Agent。

任务：
在指定“当前时间点”下初始化空间节点。空间信息必须服从世界底座和当前时间关系；同一个空间编号在不同时间点下可以有不同状态，但不得违背世界规则。

阅读顺序：
先读世界底座 world_foundation，尤其是 world_rules；再读当前时间与空间关系；优先补全当前空间，邻近空间只给故事可引用的概要。

规则边界：
只能应用 world_foundation.world_rules，不能为当前地点创造新的物理法则、超自然机制、资源约束或社会底层规则；地点可以有地貌、资源、势力和危险，但这些必须是世界规则在本地的具体表现。如果 world_rules 为空，则当前地点必须按现实常识运行。

多样化要求：
同一世界内不同地点的地貌、功能、势力、危险和生活方式要明显不同，避免反复使用矿区、矿镇、雾城、晶体遗迹、港口、灯塔、学院等场景。

世界提示词：
{user_prompt}

世界底座：
{world_foundation_json}

要初始化的空间编号：
{space_paths}

当前空间编号：
{current_space_path}

当前时间与空间关系：
{relationship_context}

约束：
1. 必须为“要初始化的空间编号”中的每个编号返回一个节点，path 必须逐项完全一致。
2. 对当前空间编号返回完整信息：detail、faction、cities、creatures、population 都必须有具体内容。
3. 对其他空间编号只返回地理位置与概述；detail、faction、cities、creatures、population 可以为 null。
4. 编号中 0 表示模板/父级占位；除非请求列表中明确包含 0 节点，否则不要主动新增 0 节点。
5. 编号距离含义：共享前缀越长代表空间越近；同父级且末位差 1 表示相邻地点；更前层级不同代表更远的大区域差异。
6. name、geography、summary 要体现该节点在层级中的位置，以及它与当前时间点的关系。
7. 城市、生物、人口等字段应遵循配置中的数量和类型倾向。
8. 不要输出 schema 以外字段，不要使用 Markdown。

请严格返回 JSON 对象，字段必须完全匹配：
{output_format}

配置：
{config_json}
""".strip()

HISTORY_INIT_TEMPLATE = """
你是架空世界历史结构 Agent。

任务：
初始化指定时间节点。你负责让每个时间编号在世界史中有清晰位置，并让当前时间点具备故事可用的完整时代状态。

阅读顺序：
先读世界底座 world_foundation，尤其是 world_rules；再读当前时间关系；优先补全当前时间，邻近时间只给故事可引用的概要。

规则边界：
只能应用 world_foundation.world_rules，不能为当前时代创造新的底层法则、超自然机制或社会运行根规则；时代差异只能来自政治、技术、灾害、战争、经济、文化和人物事件的变化。如果 world_rules 为空，则当前时代必须按现实常识运行。

多样化要求：
不同时间节点要有不同的主要矛盾、公共事件和人物压力，避免总是写矿产争夺、雾灾、晶化危机、同一种灾变、同一类追捕或同一套势力争夺。

世界提示词：
{user_prompt}

世界底座：
{world_foundation_json}

要初始化的时间编号：
{history_paths}

当前时间编号：
{current_history_path}

当前时间关系：
{relationship_context}

约束：
1. 必须为“要初始化的时间编号”中的每个编号返回一个节点，path 必须逐项完全一致。
2. 对当前时间编号返回完整信息：detail 与 ongoing_events 都必须有具体内容。
3. 对其他时间编号只返回 calendar 与 summary；detail 与 ongoing_events 可以为 null。
4. 编号中 0 表示模板/父级占位；除非请求列表中明确包含 0 节点，否则不要主动新增 0 节点。
5. 编号距离含义：共享前缀越长代表时间越近；同父级且末位差 1 表示相邻时间点；更前层级不同代表更远的大时代差异。
6. calendar 要体现该节点的层级意义，summary 要说明该时间相对当前时间的前后关系或差异。
7. ongoing_events 必须拆分为 public_events 与 personal_events。公共事件影响政权、经济、灾害、战争、社会结构；个人事件影响主角或关键人物。
8. 不要输出 schema 以外字段，不要使用 Markdown。

请严格返回 JSON 对象，字段必须完全匹配：
{output_format}

配置：
{config_json}
""".strip()

SPACE_ENRICH_TEMPLATE = """
你是架空世界空间结构 Agent。

任务：
把一个已存在的空间概要补全为完整空间节点。你必须保留已有事实，只补充缺失内容。

阅读顺序：
先读世界底座 world_foundation 和已有空间信息，再补缺；不得改写已有事实。

规则边界：
只能补充 world_foundation.world_rules 在该地点的具体影响，不能新增区别于世界底座的地点底层规则。如果 world_rules 为空，则该地点必须按现实常识运行。

多样化要求：
补全内容要突出这个地点独有的功能、风险、人物活动和日常生活，不要复用矿区、雾城、晶体遗迹、港口、灯塔、学院等固定模板。

世界提示词：
{user_prompt}

世界底座：
{world_foundation_json}

需要补充的空间编号：
{space_path}

已有空间信息：
{existing_node_json}

约束：
1. 保留已有事实，不要自相矛盾。
2. 将该空间节点补充为完整信息。
3. 必须补全 detail、faction、cities、creatures、population。
4. path 必须保持不变。
5. summary 可以润色但不能改变既有地理事实和势力事实。
6. detail 要说明地貌、社会秩序、资源、危险、可供故事使用的冲突。
7. 不要输出 schema 以外字段，不要使用 Markdown。

请严格返回 JSON 对象，字段必须完全匹配：
{output_format}

配置：
{config_json}
""".strip()

HISTORY_ENRICH_TEMPLATE = """
你是架空世界历史结构 Agent。

任务：
把一个已存在的历史概要补全为完整时间节点。你必须保留已有事实，只补充缺失内容。

阅读顺序：
先读世界底座 world_foundation 和已有历史信息，再补缺；不得改写已有事实。

规则边界：
只能补充 world_foundation.world_rules 在该时间的具体影响，不能新增区别于世界底座的时代底层规则。如果 world_rules 为空，则该时间必须按现实常识运行。

多样化要求：
补全内容要突出这个时间节点独有的冲突、生活状态和事件压力，不要复用矿产争夺、雾灾、晶化危机、同一种灾变或同一类追捕模板。

世界提示词：
{user_prompt}

世界底座：
{world_foundation_json}

需要补充的时间编号：
{history_path}

已有历史信息：
{existing_node_json}

约束：
1. 保留已有事实，不要自相矛盾。
2. 将该时间节点补充为完整信息。
3. 必须补全 detail 与 ongoing_events。
4. path 必须保持不变。
5. detail 要说明政治、经济、文化、技术/超自然状态、主要矛盾和普通人的生活状态。
6. ongoing_events.public_events 与 ongoing_events.personal_events 都要非空，且事件必须适合后续故事引用。
7. 不要输出 schema 以外字段，不要使用 Markdown。

请严格返回 JSON 对象，字段必须完全匹配：
{output_format}

配置：
{config_json}
""".strip()

CHARACTER_INIT_TEMPLATE = """
你是故事人物管理 Agent。

任务：
根据世界底座、当前时间、当前空间、附近节点和用户要求，创建可直接进入互动故事的人物组。

阅读顺序：
先读 context_json.key_facts、current、world_foundation 和 path_distance_rule，再读主角与其它人物要求；人物必须服务当前时空和世界规则。
再读 context_json.reusable_spacetime_characters 与 context_json.reusable_story_context：如果时空相同或靠近，可以沿用部分旧人物作为当前故事 other 人物，也可以参考旧故事留下的关系、事件和后果。

规则边界：
人物能力、身份和动机只能来自已有世界规则、当前时空和用户要求，不能给人物发明新的底层规则或未知世界真相。

多样化要求：
人物的年龄、职业、性格、欲望、弱点、关系和社会位置要有差异；随机主角不要总是年轻学徒、记录员、译者、信使、矿工、晶体研究者、雾中幸存者或被多方争夺的特殊人。

世界与当前位置上下文：
{context_json}

主角要求：
{protagonist_prompt}

其它人物要求：
{other_characters_prompt}

约束：
1. 必须创建一个 role 为 protagonist 的主角。
2. 其它人物 role 为 other。
3. 每个人物都要有 summary、detail、relationships。
4. relationships 必须使用人物 id，closeness 取 0 到 1。
5. 人物要与当前时间和地点有关。
6. 主角 id 必须为 protagonist；其它人物 id 使用稳定短 id，例如 other_1、other_2。
7. 至少创建 1 个其它人物；除非其它人物要求明确限制，否则创建 2 到 4 个。
8. relationships 要双向可理解：重要关系最好在双方记录中互相出现。
9. active 表示开篇附近是否可直接出场；主角必须为 true。
10. 不要输出 schema 以外字段，不要使用 Markdown。
11. 理解 context_json.path_distance_rule：共享前缀越长代表时间/空间越近，人物关系应优先贴近当前时间地点与近邻节点。
12. 如果主角要求是随机身份，必须重新发明姓名、身份、职业、能力和核心困境；年龄、社会位置、主动性和生活负担都要有变化，不要默认写成年轻男性技术员、记录员、译记员或学徒；除非用户明确要求，不要使用“林雾、林雾辞、年轻译记员、测潮师学徒”等旧套路人物。
13. 可复用人物只适合做 other 人物，不能覆盖新故事的 protagonist；复用时保留其姓名、summary 的核心事实，并让 detail 说明他为何仍在或为何来到当前时空。
14. 如果 context_json.reusable_story_context 中有近邻旧故事，应让当前人物与旧故事影响保持一致，但不要逐字复述旧故事。

请严格返回 JSON 对象，字段必须完全匹配：
{output_format}
""".strip()

CHARACTER_ADDITION_TEMPLATE = """
你是故事人物加入 Agent。

任务：
根据当前世界、当前时间、当前空间、现有人物状态和最近互动，生成即将加入故事的新人物。你只生成新加入的 other 人物，不生成主角，不改写旧人物。

阅读顺序：
先读 context_json.key_facts、manager_notes、现有人物和加入原因；新人物必须从当前时空、事件压力、人物关系或主角选择中自然出现。

规则边界：
新人物不能带来新的世界底层规则或未知真相；只能带来局部线索、冲突、帮助、误导或个人秘密。

多样化要求：
新人物的出现方式、利益诉求、说话方式和与主角的关系要变化，不要总是导师、追兵、神秘商人、密探、矿场负责人、晶体研究者或雾中引路人。

世界与当前位置上下文：
{context_json}

现有人物：
{existing_characters_json}

本次需要新增的人数：
{new_character_count}

加入原因要求：
{arrival_reason}

约束：
1. 只返回 role 为 other 的新人物，禁止返回 protagonist。
2. 每个新人物都要有稳定 id，不能与现有人物 id 重复。建议使用 other_new_1、other_new_2 这种短 id。
3. 新人物必须与当前时间、当前空间、当前事件或主角最近选择有关。
4. summary 说明人物定位，detail 说明人物背景、动机、当前为何出现。
5. relationships 必须至少包含一条指向 protagonist 的关系，closeness 取 0 到 1。
6. active 必须为 true。
7. 不要输出 schema 以外字段，不要使用 Markdown。
8. 理解 context_json.path_distance_rule：共享前缀越长代表时间/空间越近，新人物加入原因应优先来自当前节点或近邻节点。

请严格返回 JSON 对象，字段必须完全匹配：
{output_format}
""".strip()

INTRO_TEMPLATE = """
你是互动小说引子 Agent。

任务：
在正式故事开始前，写一段引子，让读者大概了解这个世界、当前时代和主角即将进入的处境，同时保留神秘感。你只写引子，不生成选择，不推进剧情到选择点。

阅读顺序：
先读 context_json.key_facts、manager_notes.intro_variation、current、characters 和 events；引子只交代开篇必须知道的信息。

规则边界：
引子只能介绍已存在的世界规则、当前时空、人物和事件，不能新增地点规则、人物能力或世界真相。

多样化要求：
每次引子的开场动作、人物压力、事件切入点和悬念类型要变化，不要总用公告、密令、追捕、病症、神秘物件、矿难、雾灾、晶化异常或灾变开头。

全部可用信息如下：
{context_json}

创作要求：
{generation_requirements}

约束：
1. intro 要像小说开篇前的引子，简单易懂、生动、有悬念。
2. 故事表达必须尽量简单，小孩子也能读懂：少用抽象概念和复杂长句，关键因果、人物目标和危险要直接说清楚。
3. 减少景物描写，优先写世界规则、时代压力、人物即将面对的问题。
4. 不要解释所有秘密，必须保留 2 到 4 个 mysteries。
5. known_world 用短句列出读者现在可以确定知道的世界信息。
6. mysteries 用短句列出仍未解释但会吸引读者继续读的疑问。
7. 不要输出 schema 以外字段，不要使用 Markdown。
8. 理解 context_json.path_distance_rule：共享前缀越长代表时间/空间越近，引子应优先介绍当前节点和近邻关系，不要把远距离节点写成近处事实。
9. 尽量不要使用“不是……而是……”这类对照句式，减少总结腔、解释腔和 AI 味；用具体动作、具体处境和自然叙述推进。
10. 不要在引子里新增 context_json 中没有出现的人名、历法名、势力名或核心设定；如果 context_json 没有明确给出，不要自行引入“潮历、星潮历、雾海、林雾、林雾辞、晶核、晶能、晶化、矿镇、矿脉”等旧套路关键词。
11. 必须读取 context_json.manager_notes.intro_variation，并按其中 opening_mode 与 focus_mode 改变本次引子的开场方式和叙述重心。
12. 不要总用“某历某年/某某时代”开头；除非 context_json 已明确要求历法开场，否则第一段必须从具体动作、对话、物件、公告、日常麻烦或突发危机开始。
13. 不要按固定顺序写“世界概述、地点介绍、主角履历、多方势力名单”；引子可以只交代最必要的信息，把其它内容留到后续故事自然出现。

请严格返回 JSON 对象，字段必须完全匹配：
{output_format}
""".strip()

STORY_CREATE_TEMPLATE = """
你是严格遵守设定的互动故事创作 Agent。

任务：
基于全部可用信息创作一个互动故事片段，在适当位置停下，并输出本段新增事件。你不是世界设定 Agent，不能扩展未知设定为事实。

阅读顺序：
先读 key_facts，再读 manager_notes、story_phase、story_history、characters、current 和 events；只在这些信息支持的范围内写故事。
再读 reusable_spacetime_characters 和 reusable_story_context；如果当前时空与旧时空相同或靠近，可以让旧人物、旧事件后果或旧故事余波自然进入本段。

规则边界：
故事只能使用已有世界规则、当前时空、人物和事件；不能新增地点底层规则、人物隐藏规则、未知历史真相或新的超自然机制。

多样化要求：
每段故事的主要阻力、行动方式、对话对象、风险来源和停顿点要变化，不要总是追兵逼近、神秘人递线索、主角发现隐藏实验、矿井/矿脉异常、雾气逼近、晶体失控、突然眩晕或门后传来声响。

全部可用信息如下：
{collected_context_json}

用户导向历史：
{choice_history_json}

创作要求补充：
{generation_requirements}

最低字数要求：
故事正文 story 字段不少于 {min_story_chars} 个中文字符。除非创作要求补充明确要求更长，否则不要少于这个长度。

创作要求：
1. 只能使用上面信息中已经存在的设定，不要编造未知世界规则、未知地点、未知历史事实。
2. 如果信息不足，用人物的不确定观察、传闻、猜测来表达，不要写成事实。
3. 如果全部可用信息里的 story_phase.is_story_start 为 true，本段是整个故事开头：必须像开篇一样建立场景、主角处境、当前矛盾与行动动机，不要写得像已经发生过很多情节。
4. 如果 story_phase.is_story_start 为 false，本段是续写：必须承接用户导向历史、事件记录、story_history 和管理器状态说明。
5. 减少景物描写：环境描写最多占 story 的 20%，不要连续写大段景物，不要堆砌华丽比喻。
6. story 第一句必须从人物动作、问题、对话或冲突开始，不要以夜色、天气、海风、城市外观等景物开头。
7. 主要写人物正在做什么、为什么必须行动、遇到什么阻力，以及下一步选择会带来什么风险。
8. 故事要有宏大感：让个人行动能牵连时代变化、世界规则、群体命运或长期冲突；即使场景很近，也要让读者感到背后有更大的世界正在运转。
9. 语言要接近小说，但必须尽量简单，小孩子也能读懂：少用抽象概念、复杂长句和术语堆叠；必要术语第一次出现时用短句解释。
10. 描述一段故事，在一个自然的悬念、行动前或局势变化处停下，让用户可以输入导向或直接推进。
11. 不要替用户列出选项，不要明确要求用户在 A/B/C 或三项方案中选择；choices 必须返回空数组。
12. 输出本段新增事件，用于写回当前时间数据库。
13. 必须优先阅读全部可用信息里的 manager_notes.critical_story_notice 和 manager_notes.critical_character_notice。
14. 如果 manager_notes.time_or_space_changed 为 true，必须自然体现时间或地点变化后的新处境；不得继续把角色写在 previous_history_path 或 previous_space_path 对应的旧时空。
15. 如果 manager_notes.character_roster_changed 为 true，必须解释 departed_characters 中旧人物为何暂时离开，以及 joined_characters 中新人物为何此刻加入；解释必须来自当前时空、事件压力、人物关系或主角选择。
16. 用户可以自由输入下一步导向，也可以留空直接推进；故事正文只需要停在适合互动的位置。
17. new_events 只记录本段已经发生的事实，不记录未来可能发生的事。
18. state_notes 用简短文字说明下回合应保留的悬念、风险或人物状态。
19. 不要输出 schema 以外字段，不要使用 Markdown。
20. 理解全部可用信息里的 path_distance_rule：共享前缀越长代表时间/空间越近，写故事时当前节点最重要，近邻节点只能作为附近背景或可前往方向，远距离节点不能写成当前现场事实。
21. 故事必须让所有人都能看懂，尤其要让小孩子也能读懂：关键因果、人物目标、危险和选择后果都要写清楚；不用读者记住复杂设定也能理解本段发生了什么。
22. 尽量不要使用“不是……而是……”这类对照句式，减少总结腔、解释腔和 AI 味；优先写具体动作、对话、阻力和后果。
23. 必须优先阅读全部可用信息里的 story_history。续写时必须承接 story_history.recent_full_segments 的最后一段、最近用户导向、人物状态和事件结果；story_history.older_segments_compact 只用于长期一致性，不要逐字复述。即使时间或地点更新，也要自然写出角色如何从前一段进入新时空，禁止突然重启、跳切或忽略上一段结尾。
24. 必须优先阅读全部可用信息里的 key_facts；如果 key_facts.story_scope 表示这是已知世界的新故事，开篇必须围绕 world_rules、current、events 和 characters 中已有信息展开，但主角与当前随机时空可以是新的。
25. 如果 reusable_spacetime_characters 或 reusable_story_context 与当前时空相近，可以沿用其中部分旧人物和旧故事后果；沿用时必须符合当前人物名单、距离关系和已有事件，不要强行让所有旧人物同时出现。

请严格返回 JSON 对象，字段必须完全匹配：
{output_format}
""".strip()

ENDING_TEMPLATE = """
你是互动故事结束 Agent。

任务：
根据全部可用信息和主角选择历史，为当前故事写一个清楚、有收束感的结尾。你只结束当前故事，不结束整个世界；世界事件仍会保留，供同一世界下其它故事引用。

阅读顺序：
先读 key_facts、manager_notes.ending_outcome、story_history、主角选择历史和最近故事片段；结尾必须收束当前故事，并保留可供同世界后续故事引用的变化。

规则边界：
结尾只能收束已有规则、人物、事件和选择造成的后果；不能用新规则、新真相或突然出现的新势力解决问题。

多样化要求：
结尾的代价、成果、遗留问题和世界变化要根据本故事自然生成，不要总写成“暂时安全、留下线索、未来还能继续”的同一种收束。

全部可用信息如下：
{collected_context_json}

主角选择历史：
{choice_history_json}

最近故事片段：
{latest_story_json}

创作要求补充：
{generation_requirements}

约束：
1. ending 要像小说结尾，清楚说明主角此刻做成了什么、付出了什么、世界留下了什么变化。
2. 故事必须尽量简单，小孩子也能读懂；不要依赖复杂术语，不要突然引入未知新规则作为真相。
3. 可以留下少量余味，但必须给当前故事一个明确收束。
4. final_state 用一句话说明故事结束后的主角和当前时空状态。
5. resolved_events 列出本结尾明确解决或改变的事件。
6. open_mysteries 列出仍可供同一世界其它故事继续使用的问题；没有则返回空数组。
7. 不要输出 schema 以外字段，不要使用 Markdown。
8. 尽量不要使用“不是……而是……”这类对照句式，减少总结腔、解释腔和 AI 味；结尾要像自然小说收束。
9. 必须读取全部可用信息里的 manager_notes.ending_outcome：good 表示偏好好结局，bad 表示偏好坏结局；无论好坏都要合理承接已发生情节，不要强行反转。
10. 必须读取全部可用信息里的 key_facts，用当前世界规则、当前时空、人物和事件收束，不要脱离已知世界信息。

请严格返回 JSON 对象，字段必须完全匹配：
{output_format}
""".strip()


def world_prompt(user_prompt: str, config: WorldGeneratorConfig) -> str:
    path_depth = max(config.history_depth, config.space_depth) + 1
    example_path = [1] + [3] * (path_depth - 1)
    template_paths = [[0] * path_depth, [1] + [0] * (path_depth - 1)]
    output = {
        "world_overview": "世界总体介绍",
        "world_rules": ["世界区别于现实世界的基本规则，如无则为空数组"],
        "space_structure_summary": "空间结构总体框架",
        "history_summary": "世界史总体框架",
    }
    return WORLD_TEMPLATE.format(
        user_prompt=user_prompt,
        personal_requirements=config.world_generation.personal_requirements or "无",
        example_path=json.dumps(example_path, ensure_ascii=False, separators=(",", ":")),
        template_paths="、".join(
            json.dumps(path, ensure_ascii=False, separators=(",", ":")) for path in template_paths
        ),
        output_format=json.dumps(output, ensure_ascii=False, indent=2),
        config_json=json.dumps(config.to_dict(), ensure_ascii=False, indent=2),
    )


def space_init_prompt(
    user_prompt: str,
    world_foundation: dict[str, Any],
    paths: list[NodePath],
    current_path: NodePath,
    config: WorldGeneratorConfig,
    relationship_context: dict[str, Any] | None = None,
) -> str:
    output: dict[str, Any] = {
        "nodes": [
            {
                "path": [1, 2, 2, 2],
                "name": "空间名称",
                "geography": "地理位置",
                "summary": "概述",
                "detail": "详细描述，仅当前节点必填",
                "faction": "所属势力，仅当前节点必填",
                "cities": [{"name": "城市名", "summary": "城市概述"}],
                "creatures": [{"name": "生物名", "summary": "生物概述"}],
                "population": {"count": "人口规模", "distribution": "人口分布"},
            }
        ]
    }
    return SPACE_INIT_TEMPLATE.format(
        user_prompt=user_prompt,
        world_foundation_json=json.dumps(world_foundation or {}, ensure_ascii=False, indent=2),
        space_paths=json.dumps([list(path) for path in paths], ensure_ascii=False),
        current_space_path=path_label(current_path),
        relationship_context=json.dumps(relationship_context or {}, ensure_ascii=False, indent=2),
        output_format=json.dumps(output, ensure_ascii=False, indent=2),
        config_json=json.dumps(config.to_dict(), ensure_ascii=False, indent=2),
    )


def history_init_prompt(
    user_prompt: str,
    world_foundation: dict[str, Any],
    paths: list[NodePath],
    current_path: NodePath,
    config: WorldGeneratorConfig,
    relationship_context: dict[str, Any] | None = None,
) -> str:
    output: dict[str, Any] = {
        "nodes": [
            {
                "path": [1, 3, 3, 3],
                "calendar": "纪年",
                "summary": "世界概况",
                "detail": "世界详细情况，仅当前节点必填",
                "ongoing_events": {
                    "public_events": [{"name": "公共事件", "summary": "事件概述"}],
                    "personal_events": [{"name": "个人事件", "summary": "事件概述"}],
                },
            }
        ]
    }
    return HISTORY_INIT_TEMPLATE.format(
        user_prompt=user_prompt,
        world_foundation_json=json.dumps(world_foundation or {}, ensure_ascii=False, indent=2),
        history_paths=json.dumps([list(path) for path in paths], ensure_ascii=False),
        current_history_path=path_label(current_path),
        relationship_context=json.dumps(relationship_context or {}, ensure_ascii=False, indent=2),
        output_format=json.dumps(output, ensure_ascii=False, indent=2),
        config_json=json.dumps(config.to_dict(), ensure_ascii=False, indent=2),
    )


def space_enrich_prompt(
    user_prompt: str,
    world_foundation: dict[str, Any],
    path: NodePath,
    existing_node: dict[str, Any],
    config: WorldGeneratorConfig,
) -> str:
    output = {
        "node": {
            "path": list(path),
            "name": "空间名称",
            "geography": "地理位置",
            "summary": "概述",
            "detail": "详细描述",
            "faction": "所属势力",
            "cities": [{"name": "城市名", "summary": "城市概述"}],
            "creatures": [{"name": "生物名", "summary": "生物概述"}],
            "population": {"count": "人口规模", "distribution": "人口分布"},
        }
    }
    return SPACE_ENRICH_TEMPLATE.format(
        user_prompt=user_prompt,
        world_foundation_json=json.dumps(world_foundation or {}, ensure_ascii=False, indent=2),
        space_path=path_label(path),
        existing_node_json=json.dumps(existing_node, ensure_ascii=False, indent=2),
        output_format=json.dumps(output, ensure_ascii=False, indent=2),
        config_json=json.dumps(config.to_dict(), ensure_ascii=False, indent=2),
    )


def history_enrich_prompt(
    user_prompt: str,
    world_foundation: dict[str, Any],
    path: NodePath,
    existing_node: dict[str, Any],
    config: WorldGeneratorConfig,
) -> str:
    output = {
        "node": {
            "path": list(path),
            "calendar": "纪年",
            "summary": "世界概况",
            "detail": "世界详细情况",
            "ongoing_events": {
                "public_events": [{"name": "公共事件", "summary": "事件概述"}],
                "personal_events": [{"name": "个人事件", "summary": "事件概述"}],
            },
        }
    }
    return HISTORY_ENRICH_TEMPLATE.format(
        user_prompt=user_prompt,
        world_foundation_json=json.dumps(world_foundation or {}, ensure_ascii=False, indent=2),
        history_path=path_label(path),
        existing_node_json=json.dumps(existing_node, ensure_ascii=False, indent=2),
        output_format=json.dumps(output, ensure_ascii=False, indent=2),
        config_json=json.dumps(config.to_dict(), ensure_ascii=False, indent=2),
    )


def character_init_prompt(
    context: dict[str, Any],
    protagonist_prompt: str,
    other_characters_prompt: str,
) -> str:
    output = {
        "characters": [
            {
                "id": "protagonist",
                "name": "主角名",
                "role": "protagonist",
                "summary": "人物概述",
                "detail": "人物详细描述",
                "relationships": [
                    {
                        "target_id": "other_1",
                        "type": "关系类型",
                        "closeness": 0.8,
                        "summary": "关系概述",
                    }
                ],
                "active": True,
            }
        ]
    }
    return CHARACTER_INIT_TEMPLATE.format(
        context_json=json.dumps(context, ensure_ascii=False, indent=2),
        protagonist_prompt=protagonist_prompt,
        other_characters_prompt=other_characters_prompt,
        output_format=json.dumps(output, ensure_ascii=False, indent=2),
    )


def character_addition_prompt(
    context: dict[str, Any],
    existing_characters: list[dict[str, Any]],
    new_character_count: int,
    arrival_reason: str,
) -> str:
    output = {
        "characters": [
            {
                "id": "other_new_1",
                "name": "新人物名",
                "role": "other",
                "summary": "人物概述",
                "detail": "人物详细描述",
                "relationships": [
                    {
                        "target_id": "protagonist",
                        "type": "关系类型",
                        "closeness": 0.4,
                        "summary": "与主角的关系概述",
                    }
                ],
                "active": True,
            }
        ]
    }
    return CHARACTER_ADDITION_TEMPLATE.format(
        context_json=json.dumps(context, ensure_ascii=False, indent=2),
        existing_characters_json=json.dumps(existing_characters, ensure_ascii=False, indent=2),
        new_character_count=new_character_count,
        arrival_reason=arrival_reason,
        output_format=json.dumps(output, ensure_ascii=False, indent=2),
    )


def intro_prompt(
    context: dict[str, Any],
    generation_requirements: str,
) -> str:
    output = {
        "intro": "故事引子正文",
        "known_world": ["读者可以确定知道的世界信息"],
        "mysteries": ["仍未解释的关键疑问"],
    }
    return INTRO_TEMPLATE.format(
        context_json=json.dumps(context, ensure_ascii=False, indent=2),
        generation_requirements=generation_requirements,
        output_format=json.dumps(output, ensure_ascii=False, indent=2),
    )


def story_create_prompt(
    collected_context: dict[str, Any],
    choice_history: list[dict[str, Any]],
    generation_requirements: str,
    min_story_chars: int,
) -> str:
    output = {
        "story": "故事正文，在适合用户输入导向或直接推进的位置停下",
        "choices": [],
        "new_events": [{"name": "事件名", "summary": "事件摘要", "impact": "影响"}],
        "state_notes": "给管理器的状态备注",
    }
    return STORY_CREATE_TEMPLATE.format(
        collected_context_json=json.dumps(collected_context, ensure_ascii=False, indent=2),
        choice_history_json=json.dumps(choice_history, ensure_ascii=False, indent=2),
        generation_requirements=generation_requirements,
        min_story_chars=min_story_chars,
        output_format=json.dumps(output, ensure_ascii=False, indent=2),
    )


def story_ending_prompt(
    collected_context: dict[str, Any],
    choice_history: list[dict[str, Any]],
    latest_story: dict[str, Any] | None,
    generation_requirements: str,
) -> str:
    output = {
        "ending": "故事结尾正文",
        "final_state": "故事结束后的状态",
        "resolved_events": ["已经解决或改变的事件"],
        "open_mysteries": ["仍可留给其它故事的问题"],
    }
    return ENDING_TEMPLATE.format(
        collected_context_json=json.dumps(collected_context, ensure_ascii=False, indent=2),
        choice_history_json=json.dumps(choice_history, ensure_ascii=False, indent=2),
        latest_story_json=json.dumps(latest_story or {}, ensure_ascii=False, indent=2),
        generation_requirements=generation_requirements,
        output_format=json.dumps(output, ensure_ascii=False, indent=2),
    )
