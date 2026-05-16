const state = {
  sessionId: null,
  worldId: null,
  latest: null,
  worlds: [],
  stories: [],
  agentTouched: false,
};

const $ = (id) => document.getElementById(id);

$("startBtn").addEventListener("click", async () => {
  await startStory({useCurrentWorld: false});
});

$("refreshWorldsBtn").addEventListener("click", async () => {
  await loadWorlds();
});

$("newStoryBtn").addEventListener("click", async () => {
  await startStory({useCurrentWorld: true});
});

$("continueIntroBtn").addEventListener("click", async () => {
  await beginStory();
});

$("choiceForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.sessionId || !state.latest || !state.latest.started || state.latest.ended) return;
  await submitChoice();
});

$("agent").addEventListener("change", () => {
  state.agentTouched = true;
  alignModelWithAgent();
});

$("model").addEventListener("change", () => {
  state.agentTouched = true;
});

loadWorlds();

async function startStory({useCurrentWorld}) {
  setBusy(true, useCurrentWorld ? "正在当前世界中开始新故事，这可能需要几分钟..." : "正在初始化世界和引子，这可能需要几分钟...");
  try {
    const payload = {
      prompt: $("prompt").value.trim(),
      world_id: useCurrentWorld ? state.worldId : null,
      protagonist: $("protagonist").value.trim(),
      world_requirements: $("worldReq").value.trim(),
      generation_requirements: $("genReq").value.trim(),
      story_length_mode: $("storyMode").value,
      world_scale: $("worldScale").value,
      agent: $("agent").value || "openai",
      model: selectedModel(),
      debug_story_agent_input: true,
    };
    const result = await postJson("/api/start", payload);
    state.sessionId = result.story.session_id;
    state.worldId = result.story.world_id;
    state.latest = result.story;
    renderWorld(result.world);
    renderStory(result.story);
    $("newStoryBtn").disabled = false;
    $("status").textContent = "点击右上角以继续";
    await loadWorlds();
    await enterWorld(result.story.world_id);
  } catch (error) {
    showError(error);
  } finally {
    setBusy(false);
  }
}

async function loadWorlds() {
  try {
    const data = await getJson("/api/worlds");
    state.worlds = data.worlds || [];
    renderWorldList();
    if (!state.worldId && state.worlds.length) {
      await enterWorld(state.worlds[0].world_id, {renderOnly: true});
    }
  } catch (error) {
    showError(error);
  }
}

async function enterWorld(worldId, options = {}) {
  const previousWorldId = state.worldId;
  const data = await getJson(`/api/world?world_id=${encodeURIComponent(worldId)}`);
  state.worldId = data.world.world_id;
  state.stories = data.stories || [];
  $("worldTitle").textContent = worldName(data.world);
  if (!options.renderOnly && previousWorldId !== state.worldId) {
    clearStoryView();
  }
  renderWorldList();
  renderStoryList();
  $("newStoryBtn").disabled = false;
  if (!options.renderOnly) {
    $("status").textContent = "已进入世界";
  }
}

async function loadStory(sessionId) {
  setBusy(true, "正在载入故事...");
  try {
    const data = await getJson(`/api/session?session_id=${encodeURIComponent(sessionId)}`);
    state.sessionId = data.story.session_id;
    state.worldId = data.story.world_id;
    state.latest = data.story;
    renderStory(data.story);
    await enterWorld(data.story.world_id, {renderOnly: true});
    $("status").textContent = data.story.started ? "故事已载入" : "引子已载入";
  } catch (error) {
    showError(error);
  } finally {
    setBusy(false);
  }
}

async function beginStory() {
  setBusy(true, "正在生成第一段故事...");
  try {
    const result = await postJson("/api/begin", {
      session_id: state.sessionId,
      agent: $("agent").value || "openai",
      model: selectedModel(),
      generation_requirements: $("genReq").value.trim(),
      debug_story_agent_input: true,
    });
    state.latest = result.story;
    renderStory(result.story);
    await enterWorld(result.story.world_id, {renderOnly: true});
    $("status").textContent = "故事已开始";
  } catch (error) {
    showError(error);
  } finally {
    setBusy(false);
  }
}

async function submitChoice() {
  setBusy(true, "正在推进故事...");
  try {
    const result = await postJson("/api/choose", {
      session_id: state.sessionId,
      choice_id: $("choiceText").value.trim() ? "USER" : "CONTINUE",
      choice_text: $("choiceText").value.trim(),
      agent: $("agent").value || "openai",
      model: selectedModel(),
      generation_requirements: $("genReq").value.trim(),
      debug_story_agent_input: true,
    });
    state.latest = result.story;
    $("choiceText").value = "";
    renderStory(result.story);
    await enterWorld(result.story.world_id, {renderOnly: true});
    $("status").textContent = "故事已推进";
  } catch (error) {
    showError(error);
  } finally {
    setBusy(false);
  }
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok || data.error) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

async function getJson(url) {
  const response = await fetch(url);
  const data = await response.json();
  if (!response.ok || data.error) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

async function deleteJson(url) {
  const response = await fetch(url, {method: "DELETE"});
  const data = await response.json();
  if (!response.ok || data.error) {
    throw new Error(data.error || `HTTP ${response.status}`);
  }
  return data;
}

async function deleteWorld(worldId, prompt) {
  const label = prompt || worldId;
  const confirmed = window.confirm(`确定删除世界「${label}」吗？该世界下的所有故事、人物、事件和 token 记录都会被删除。`);
  if (!confirmed) return;
  setBusy(true, "正在删除世界...");
  try {
    await deleteJson(`/api/world?world_id=${encodeURIComponent(worldId)}`);
    if (state.worldId === worldId) {
      state.worldId = null;
      state.stories = [];
      clearStoryView();
      $("worldTitle").textContent = "请选择世界";
      renderStoryList();
    }
    await loadWorlds();
    $("status").textContent = "世界已删除";
  } catch (error) {
    showError(error);
  } finally {
    setBusy(false);
  }
}

function renderWorld(world) {
  state.worldId = world.world_id;
}

function clearStoryView() {
  state.sessionId = null;
  state.latest = null;
  $("turnBadge").textContent = "未开始";
  $("introText").textContent = "";
  $("storyHistory").innerHTML = "";
  $("storyText").textContent = "";
  $("endingText").textContent = "";
  $("endingBlock").hidden = true;
  $("choices").innerHTML = "";
  $("notices").innerHTML = `<div class="muted">选择一个故事继续。</div>`;
  $("currentNodes").textContent = "";
  $("characters").innerHTML = `<span class="muted">-</span>`;
  $("events").innerHTML = `<span class="muted">-</span>`;
  $("modeInfo").textContent = "-";
  $("progressInfo").textContent = "-";
  $("sessionTokens").textContent = "-";
  $("worldTokens").textContent = "-";
  setBusy(false);
}

function renderWorldList() {
  const root = $("worldList");
  if (!state.worlds.length) {
    root.innerHTML = `<div class="muted">暂无世界。</div>`;
    return;
  }
  root.innerHTML = "";
  state.worlds.forEach((world) => {
    const row = document.createElement("div");
    row.className = "listRow";
    const button = document.createElement("button");
    button.type = "button";
    button.className = `listItem ${world.world_id === state.worldId ? "selected" : ""}`;
    button.innerHTML = `
      <strong>${escapeHtml(worldName(world))}</strong>
      <span>${escapeHtml(scaleLabel(world.scale))} · ${world.story_count || 0} 个故事 · ${tokenText(world.token_usage)}</span>
    `;
    button.addEventListener("click", () => enterWorld(world.world_id));
    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "deleteWorld";
    deleteButton.textContent = "删除";
    deleteButton.addEventListener("click", () => deleteWorld(world.world_id, worldName(world)));
    row.appendChild(button);
    row.appendChild(deleteButton);
    root.appendChild(row);
  });
}

function renderStoryList() {
  const root = $("storyList");
  if (!state.worldId) {
    root.innerHTML = `<div class="muted">先选择一个世界。</div>`;
    return;
  }
  if (!state.stories.length) {
    root.innerHTML = `<div class="muted">这个世界还没有故事。</div>`;
    return;
  }
  root.innerHTML = "";
  state.stories.forEach((story) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `listItem ${story.session_id === state.sessionId ? "selected" : ""}`;
    button.innerHTML = `
      <strong>${escapeHtml(storyLabel(story))}</strong>
      <span>${escapeHtml(storyStatus(story))} · ${escapeHtml(modeLabel(story.story_length_mode))} · ${tokenText(story.token_usage)}</span>
      <span>${escapeHtml(story.title || "")}</span>
    `;
    button.addEventListener("click", () => loadStory(story.session_id));
    root.appendChild(button);
  });
}

function renderStory(story) {
  $("turnBadge").textContent = story.ended ? "已结束" : story.started ? `第 ${story.interaction_count} 次互动` : "引子";
  renderIntro(story.intro);
  renderStoryHistory(story);
  renderStoryText(story);
  renderEnding(story);
  renderChoices(story.choices || []);
  renderNotices(story.manager_notes || {});
  renderCurrent(story.current || {});
  renderCharacters(story.characters || {});
  renderEvents(story.events || {}, story.new_events || []);
  renderSummaryFacts(story);
  renderStoryList();
  renderIntroPrompt(story);
}

function renderStoryText(story) {
  if (story.ending) {
    const segments = story.story_segments || [];
    $("storyText").textContent = segments.map((segment) => segment.story || "").filter(Boolean).join("\n\n");
    return;
  }
  $("storyText").textContent = story.story || "";
}

function renderEnding(story) {
  const ending = story.ending || null;
  if (!ending || !ending.ending) {
    $("endingText").textContent = "";
    $("endingBlock").hidden = true;
    return;
  }
  $("endingText").textContent = ending.ending;
  $("endingBlock").hidden = false;
}

function renderStoryHistory(story) {
  const root = $("storyHistory");
  const segments = story.story_segments || [];
  if (story.ending) {
    root.innerHTML = "";
    return;
  }
  const previous = story.ending ? segments : segments.slice(0, -1);
  if (!previous.length) {
    root.innerHTML = "";
    return;
  }
  root.innerHTML = `
    <details>
      <summary>上文回顾（${previous.length} 段）</summary>
      <div class="historyList">
        ${previous.map((segment) => renderHistorySegment(segment)).join("")}
      </div>
    </details>
  `;
}

function renderHistorySegment(segment) {
  const userInput = segment.user_input_after_segment;
  const inputText = userInput && userInput.text ? userInput.text : "";
  return `
    <section class="historySegment">
      <div class="historyMeta">第 ${(segment.turn || 0) + 1} 段</div>
      <div class="historyStory">${escapeHtml(segment.story || "")}</div>
      ${inputText ? `<div class="historyInput">导向：${escapeHtml(inputText)}</div>` : ""}
    </section>
  `;
}

function renderIntro(intro) {
  if (!intro || !intro.intro) {
    $("introText").textContent = "";
    return;
  }
  const mysteries = (intro.mysteries || []).map((item) => `? ${item}`).join("\n");
  $("introText").textContent = mysteries ? `${intro.intro}\n\n${mysteries}` : intro.intro;
}

function renderIntroPrompt(story) {
  const existing = document.querySelector(".continuePrompt");
  if (existing) existing.remove();
  if (!story || story.started || story.ended) return;
  const prompt = document.createElement("div");
  prompt.className = "continuePrompt";
  prompt.textContent = "点击右上角以继续。";
  $("introText").after(prompt);
}

function renderChoices(choices) {
  const root = $("choices");
  root.innerHTML = "";
  $("continueIntroBtn").disabled = !state.latest || state.latest.started || state.latest.ended;
  if (state.latest && state.latest.ended) {
    $("submitChoiceBtn").disabled = true;
    $("choiceText").disabled = true;
    return;
  }
  if (state.latest && !state.latest.started) {
    $("submitChoiceBtn").disabled = true;
    $("choiceText").disabled = true;
    return;
  }
  $("choiceText").disabled = false;
  $("submitChoiceBtn").disabled = false;
  if (choices.length) {
    root.innerHTML = choices.map((choice) => `<div class="notice">${escapeHtml(choice.text || "")}</div>`).join("");
  }
}

function renderSummaryFacts(story) {
  const labels = {
    long: "长故事",
    infinite: "无限故事",
    normal: "普通故事",
  };
  $("modeInfo").textContent = labels[story.story_length_mode] || story.story_length_mode || "-";
  $("progressInfo").textContent = story.ended
    ? "已结束"
    : story.started
      ? `${story.interaction_count} 次互动`
      : "等待继续";
  const usage = story.token_usage || {};
  $("sessionTokens").textContent = tokenText(usage.session);
  $("worldTokens").textContent = tokenText(usage.world);
}

function storyLabel(story) {
  return `故事 ${story.story_number || "-"}`;
}

function worldName(world) {
  return world.display_name || world.prompt || world.world_id || "未命名世界";
}

function selectedModel() {
  const agent = $("agent").value || "openai";
  const model = $("model").value;
  if (agent === "deepseek" && !model.startsWith("deepseek-")) return "deepseek-chat";
  if (agent === "openai" && model.startsWith("deepseek-")) return "gpt-5.5";
  return model || (agent === "deepseek" ? "deepseek-chat" : "gpt-5.5");
}

function setAgentModel(agent, model, options = {}) {
  $("agent").value = agent;
  $("model").value = model;
  state.agentTouched = Boolean(options.markTouched);
}

function alignModelWithAgent() {
  const agent = $("agent").value || "openai";
  const model = $("model").value;
  if (agent === "deepseek" && !model.startsWith("deepseek-")) {
    $("model").value = "deepseek-chat";
  }
  if (agent === "openai" && model.startsWith("deepseek-")) {
    $("model").value = "gpt-5.5";
  }
}

function storyStatus(story) {
  if (story.ended) return "已结束";
  if (story.started) return `${story.interaction_count || 0} 次互动`;
  return "引子";
}

function modeLabel(mode) {
  const labels = {long: "长故事", infinite: "无限故事", normal: "普通故事"};
  return labels[mode] || mode || "-";
}

function scaleLabel(scale) {
  const labels = {small: "小规模", medium: "中等规模", large: "大规模"};
  return labels[scale] || scale || "-";
}

function renderNotices(notes) {
  const notices = [];
  if (state.latest && state.latest.ending) notices.push(state.latest.ending.final_state);
  if (notes.critical_story_notice) notices.push(notes.critical_story_notice);
  if (notes.critical_character_notice) notices.push(notes.critical_character_notice);
  if (notes.time_or_space_changed) {
    notices.push(`时空更新：${pathText(notes.previous_history_path)} / ${pathText(notes.previous_space_path)} -> ${pathText(notes.current_history_path)} / ${pathText(notes.current_space_path)}`);
  }
  if (notes.character_roster_changed) {
    const left = (notes.departed_characters || []).map((item) => item.name || item.id).join("、") || "无";
    const joined = (notes.joined_characters || []).map((item) => item.name || item.id).join("、") || "无";
    notices.push(`人物变化：离开 ${left}；加入 ${joined}`);
  }
  $("notices").innerHTML = notices.length
    ? notices.map((item) => `<div class="notice">${escapeHtml(item)}</div>`).join("")
    : `<div class="muted">暂无变化。</div>`;
}

function renderCurrent(current) {
  const history = current.history || {};
  const space = current.space || {};
  $("currentNodes").textContent = [
    history.name || "",
    history.summary || "",
    "",
    space.name || "",
    space.summary || "",
  ].join("\n").trim();
}

function renderCharacters(characters) {
  const protagonist = characters.protagonist;
  const others = characters.others || [];
  const active = characters.active_ids || [];
  const blocks = [];
  if (protagonist) {
    blocks.push(`<div class="item"><strong>${escapeHtml(protagonist.name)}</strong><br><span class="muted">${escapeHtml(protagonist.summary)}</span></div>`);
  }
  others.forEach((item) => {
    const marker = active.includes(item.id) ? "active" : "inactive";
    blocks.push(`<div class="item"><strong>${escapeHtml(item.name)}</strong> <span class="muted">${marker}</span><br>${escapeHtml(item.summary || "")}</div>`);
  });
  $("characters").innerHTML = blocks.length ? blocks.join("") : `<span class="muted">暂无人物。</span>`;
}

function renderEvents(events, newEvents) {
  const all = [
    ...(newEvents || []).map((event) => ({...event, label: "new"})),
    ...((events.current_time_events || []).slice(-3).map((event) => ({...event, label: "current"}))),
  ];
  $("events").innerHTML = all.length
    ? all.map((event) => `<div class="item"><strong>${escapeHtml(event.name || event.label)}</strong><br>${escapeHtml(event.summary || "")}</div>`).join("")
    : `<span class="muted">暂无事件。</span>`;
}

function pathText(path) {
  return Array.isArray(path) ? `[${path.join(",")}]` : "[-]";
}

function setBusy(isBusy, text = "") {
  $("startBtn").disabled = isBusy;
  $("newStoryBtn").disabled = isBusy || !state.worldId;
  $("continueIntroBtn").disabled = isBusy || !state.latest || state.latest.started || state.latest.ended;
  $("choiceText").disabled = isBusy || !state.latest || state.latest.ended || !state.latest.started;
  $("submitChoiceBtn").disabled = isBusy || !state.latest || state.latest.ended || !state.latest.started;
  if (text) $("status").textContent = text;
}

function tokenText(usage) {
  if (!usage) return "-";
  const total = usage.total_tokens || 0;
  const input = usage.input_tokens || 0;
  const output = usage.output_tokens || 0;
  return `${total} (${input}/${output})`;
}

function showError(error) {
  $("status").textContent = `错误：${error.message}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
