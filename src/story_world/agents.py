from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Any, Protocol


class JsonAgent(Protocol):
    def generate_json(
        self,
        prompt: str,
        *,
        schema_name: str,
        schema: dict[str, Any],
    ) -> "AgentResult":
        ...


class AgentResult(dict):
    def __init__(self, payload: dict[str, Any], usage: dict[str, int] | None = None) -> None:
        super().__init__(payload)
        self.usage = usage or {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
        }


class DeterministicDemoAgent:
    """Local stand-in for a GPT-backed JSON agent."""

    def generate_json(
        self,
        prompt: str,
        *,
        schema_name: str,
        schema: dict[str, Any],
    ) -> AgentResult:
        digest = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:8]
        if prompt.startswith("你是架空世界空间结构 Agent"):
            if "需要补充的空间编号" in prompt:
                return AgentResult({"node": self._space_nodes(prompt, digest)[0]})
            return AgentResult({"nodes": self._space_nodes(prompt, digest)})
        if prompt.startswith("你是架空世界历史结构 Agent"):
            if "需要补充的时间编号" in prompt:
                return AgentResult({"node": self._history_nodes(prompt, digest)[0]})
            return AgentResult({"nodes": self._history_nodes(prompt, digest)})
        if prompt.startswith("你是故事人物管理 Agent"):
            return AgentResult(
                {
                    "characters": [
                        {
                            "id": "protagonist",
                            "name": "示例主角",
                            "role": "protagonist",
                            "summary": "正在被命运推向选择的主角。",
                            "detail": "主角熟悉当前地点，也被当前时代的公共事件牵连。",
                            "relationships": [
                                {
                                    "target_id": "companion_1",
                                    "type": "同伴",
                                    "closeness": 0.8,
                                    "summary": "彼此信任，但目标并不完全一致。",
                                }
                            ],
                            "active": True,
                        },
                        {
                            "id": "companion_1",
                            "name": "示例同伴",
                            "role": "other",
                            "summary": "与主角同行的本地人。",
                            "detail": "同伴知道一些当前地点的传闻，常在危险前提醒主角。",
                            "relationships": [
                                {
                                    "target_id": "protagonist",
                                    "type": "同伴",
                                    "closeness": 0.8,
                                    "summary": "愿意帮助主角，但保留自己的秘密。",
                                }
                            ],
                            "active": True,
                        },
                    ]
                }
            )
        if prompt.startswith("你是故事人物加入 Agent"):
            return AgentResult(
                {
                    "characters": [
                        {
                            "id": f"other_new_{digest}",
                            "name": "新加入人物",
                            "role": "other",
                            "summary": "因当前局势加入故事的新人物。",
                            "detail": "此人被当前时间地点的事件牵引而来，能为主角提供新线索或新冲突。",
                            "relationships": [
                                {
                                    "target_id": "protagonist",
                                    "type": "新相识",
                                    "closeness": 0.35,
                                    "summary": "刚与主角建立联系，互相仍有保留。",
                                }
                            ],
                            "active": True,
                        }
                    ]
                }
            )
        if prompt.startswith("你是互动小说引子 Agent"):
            return AgentResult(
                {
                    "intro": "在这个示例世界里，旧秩序还没有倒下，新危险已经靠近。主角站在一个看似普通的起点，却很快会发现，身边每个选择都牵动着更大的秘密。",
                    "known_world": [
                        "这个世界有稳定但陌生的规则。",
                        "当前时代正处在变化前夜。",
                        "主角与当前时间地点的事件有关。",
                    ],
                    "mysteries": [
                        "真正推动变化的力量是什么？",
                        "主角会被谁利用，又能相信谁？",
                    ],
                }
            )
        if prompt.startswith("你是严格遵守设定的互动故事创作 Agent"):
            return AgentResult(
                {
                    "story": f"示例主角在当前时间地点继续前进。周围的信息彼此呼应，旧事件留下的影响仍在发酵。前方传来新的动静，主角停下脚步，等着判断接下来该怎样靠近真相。",
                    "choices": [],
                    "new_events": [
                        {
                            "name": f"示例事件-{digest}",
                            "summary": "主角抵达选择节点，局势等待下一步行动。",
                            "impact": "后续管理器可据此推进事件链。",
                        }
                    ],
                    "state_notes": "demo story generated",
                }
            )
        if prompt.startswith("你是互动故事结束 Agent"):
            return AgentResult(
                {
                    "ending": "示例主角停下脚步，把眼前最紧急的危机处理完。这个故事到这里告一段落：主角保住了重要线索，也明白下一次行动不能再只靠运气。当前时间地点留下了新的痕迹，未来的故事还能从这里继续生长。",
                    "final_state": "当前故事结束，主角暂时安全，世界事件记录已留下后续影响。",
                    "resolved_events": ["主角完成了本次选择链的收束。"],
                    "open_mysteries": ["更大的世界矛盾仍未完全解释。"],
                }
            )
        return AgentResult({
            "world_overview": f"demo-world-{digest}",
            "world_rules": [],
            "space_structure_summary": "待生成",
            "history_summary": "待生成",
        })

    def _space_nodes(self, prompt: str, digest: str) -> list[dict]:
        paths = self._extract_paths(prompt, "要初始化的空间编号")
        if not paths:
            single = self._extract_label(prompt, "需要补充的空间编号")
            paths = [[int(part) for part in single.split(".")]] if single else []
        current = self._extract_label(prompt, "当前空间编号") or self._extract_label(prompt, "需要补充的空间编号")
        nodes = []
        for path in paths:
            label = ".".join(str(part) for part in path)
            node = {
                "path": path,
                "name": f"demo-space-{label}",
                "geography": f"geography-{digest}-{label}",
                "summary": f"summary-{digest}-{label}",
            }
            if label == current:
                node.update(
                    {
                        "detail": "完整空间详情",
                        "faction": "示例势力",
                        "cities": [{"name": "示例城市", "summary": "当前空间城市"}],
                        "creatures": [{"name": "示例生物", "summary": "当前空间生物"}],
                        "population": {"count": "约十万", "distribution": "沿交通线聚集"},
                    }
                )
            nodes.append(node)
        return nodes

    def _history_nodes(self, prompt: str, digest: str) -> list[dict]:
        paths = self._extract_paths(prompt, "要初始化的时间编号")
        if not paths:
            single = self._extract_label(prompt, "需要补充的时间编号")
            paths = [[int(part) for part in single.split(".")]] if single else []
        current = self._extract_label(prompt, "当前时间编号") or self._extract_label(prompt, "需要补充的时间编号")
        nodes = []
        for path in paths:
            label = ".".join(str(part) for part in path)
            node = {
                "path": path,
                "calendar": f"era-{digest}-{label}",
                "summary": f"history-{digest}-{label}",
            }
            if label == current:
                node.update(
                    {
                        "detail": "完整历史详情",
                        "ongoing_events": {
                            "public_events": [{"name": "示例公共事件", "summary": "影响世界格局"}],
                            "personal_events": [{"name": "示例个人事件", "summary": "影响关键人物"}],
                        },
                    }
                )
            nodes.append(node)
        return nodes

    def _extract_paths(self, prompt: str, label: str) -> list[list[int]]:
        pattern = rf"{label}：\n(\[[^\n]+\])"
        match = re.search(pattern, prompt)
        return json.loads(match.group(1)) if match else []

    def _extract_label(self, prompt: str, label: str) -> str:
        pattern = rf"{label}：\n([0-9.]+)"
        match = re.search(pattern, prompt)
        return match.group(1) if match else ""


class OpenAIJsonAgent:
    """Responses API-backed GPT agent with strict JSON-schema output."""

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        reasoning_effort: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> None:
        OpenAI = _load_openai_client()

        self.client = OpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
        self.model = _normalize_model_name(model or os.getenv("STORY_WORLD_MODEL", "gpt-5.4"))
        self.reasoning_effort = reasoning_effort or os.getenv("STORY_WORLD_REASONING_EFFORT")
        self.temperature = temperature
        self.top_p = top_p
        self.provider = "openai"
        self.base_url = "https://api.openai.com/v1"

    def generate_json(
        self,
        prompt: str,
        *,
        schema_name: str,
        schema: dict[str, Any],
    ) -> AgentResult:
        request: dict[str, Any] = {
            "model": self.model,
            "input": prompt,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        if self.reasoning_effort:
            request["reasoning"] = {"effort": self.reasoning_effort}
        if self.temperature is not None:
            request["temperature"] = self.temperature
        if self.top_p is not None:
            request["top_p"] = self.top_p

        try:
            response = self.client.responses.create(**request)
        except Exception as exc:
            raise RuntimeError(
                f"OpenAI agent request failed (provider={self.provider}, model={self.model}, base_url={self.base_url}): {exc}"
            ) from exc
        if not response.output_text:
            raise RuntimeError("OpenAI response did not include output_text.")
        usage = getattr(response, "usage", None)
        usage_payload = {
            "input_tokens": getattr(usage, "input_tokens", 0) or 0,
            "output_tokens": getattr(usage, "output_tokens", 0) or 0,
            "total_tokens": getattr(usage, "total_tokens", 0) or 0,
        }
        return AgentResult(_parse_agent_json(response.output_text, provider=self.provider), usage_payload)


class DeepSeekJsonAgent:
    """OpenAI-compatible DeepSeek chat completions JSON agent."""

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
    ) -> None:
        OpenAI = _load_openai_client()
        resolved_api_key = api_key or os.getenv("DEEPSEEK_API_KEY") or _shell_export_value("DEEPSEEK_API_KEY")
        if not resolved_api_key:
            raise RuntimeError(
                "DEEPSEEK_API_KEY is not set. Export it before using the DeepSeek agent."
            )

        self.provider = "deepseek"
        self.base_url = base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.client = OpenAI(
            api_key=resolved_api_key,
            base_url=self.base_url,
        )
        self.model = model or os.getenv("STORY_WORLD_DEEPSEEK_MODEL", "deepseek-chat")
        self.temperature = 1.05 if temperature is None else temperature
        self.top_p = 0.95 if top_p is None else top_p

    def generate_json(
        self,
        prompt: str,
        *,
        schema_name: str,
        schema: dict[str, Any],
    ) -> AgentResult:
        schema_prompt = (
            f"{prompt}\n\n"
            "你必须只输出一个合法 JSON 对象，不要输出 Markdown 或解释文字。\n"
            "JSON Schema 如下：\n"
            f"{json.dumps(schema, ensure_ascii=False, indent=2)}"
        )
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": schema_prompt}],
                response_format={"type": "json_object"},
                temperature=self.temperature,
                top_p=self.top_p,
            )
        except Exception as exc:
            raise RuntimeError(
                f"DeepSeek agent request failed (provider={self.provider}, model={self.model}, base_url={self.base_url}): {exc}"
            ) from exc
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("DeepSeek response did not include message content.")
        usage = getattr(response, "usage", None)
        usage_payload = {
            "input_tokens": getattr(usage, "prompt_tokens", 0) or 0,
            "output_tokens": getattr(usage, "completion_tokens", 0) or 0,
            "total_tokens": getattr(usage, "total_tokens", 0) or 0,
        }
        return AgentResult(_parse_agent_json(content, provider=self.provider), usage_payload)


def _parse_agent_json(content: str, *, provider: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        try:
            return json.loads(content, strict=False)
        except json.JSONDecodeError as exc:
            preview = content[:500].replace("\n", "\\n")
            raise RuntimeError(
                f"{provider} returned invalid JSON: {exc}. Response preview: {preview}"
            ) from exc


def _load_openai_client() -> Any:
    try:
        from openai import OpenAI

        return OpenAI
    except ModuleNotFoundError as exc:
        if exc.name != "openai":
            raise
        site_packages = _local_venv_site_packages()
        if site_packages and str(site_packages) not in sys.path:
            sys.path.insert(0, str(site_packages))
            from openai import OpenAI

            return OpenAI
        raise


def _local_venv_site_packages() -> Path | None:
    candidates = [
        Path.cwd() / ".venv",
        Path(__file__).resolve().parents[2] / ".venv",
    ]
    for venv in candidates:
        lib_dir = venv / "lib"
        if not lib_dir.exists():
            continue
        for site_packages in lib_dir.glob("python*/site-packages"):
            if (site_packages / "openai").exists():
                return site_packages
    return None


def _shell_export_value(name: str) -> str | None:
    bashrc = Path.home() / ".bashrc"
    if not bashrc.exists():
        return None
    pattern = re.compile(rf"^\s*export\s+{re.escape(name)}=(.+?)\s*$")
    for line in bashrc.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        try:
            parts = shlex.split(match.group(1))
        except ValueError:
            return None
        return parts[0] if parts else ""
    return None


def _normalize_model_name(model: str) -> str:
    if model == "gpt5-nano":
        return "gpt-5-nano"
    if model == "gpt-5.4mini":
        return "gpt-5.4-mini"
    return model
