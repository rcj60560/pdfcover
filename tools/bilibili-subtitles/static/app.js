const $ = (id) => document.getElementById(id);

const state = {
  jobId: "",
  rows: [],
  fontScale: 1,
  englishSegments: [],
};

let transcribeTimer = null;

function setStatus(message, type = "loading") {
  const box = $("status");
  box.hidden = !message;
  box.className = "status " + type;
  box.textContent = message;
}

function setBusy(button, busy, busyText, normalText) {
  button.disabled = busy;
  button.textContent = busy ? busyText : normalText;
}

async function api(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let data;
  try { data = await response.json(); } catch { data = { ok: false, error: `HTTP ${response.status}` }; }
  if (!response.ok || !data.ok) throw new Error(data.error || "操作失败");
  return data;
}

function resetTranscribePanel() {
  if (transcribeTimer) { window.clearTimeout(transcribeTimer); transcribeTimer = null; }
  $("transcribe-progress").hidden = true;
  $("transcribe-phase").textContent = "准备中…";
  $("transcribe-log").textContent = "";
  renderStepTrack(null);
}

function renderStepTrack(stage) {
  // 步骤条三步：下载音频 → Whisper 转写 → 完成；服务端 step≥3 一律落到「完成」
  const active = stage ? Math.min(Number(stage.step) || 0, 3) : 0;
  document.querySelectorAll("#transcribe-steps .step").forEach((step) => {
    const order = Number(step.dataset.step);
    step.classList.toggle("active", order === active);
    step.classList.toggle("done", order < active);
  });
  const detail = $("transcribe-phase");
  if (stage && stage.detail) detail.textContent = stage.detail;
}

async function inspect(event) {
  event.preventDefault();
  const url = $("video-url").value.trim();
  if (!url) return;
  localStorage.setItem("bili-subtitle-url", url);
  localStorage.setItem("bili-subtitle-browser", $("browser").value);
  $("fetch-panel").hidden = true;
  $("reader").hidden = true;
  setStatus("正在连接 B 站读取视频信息，通常需要几秒…", "loading");
  const button = $("inspect-button");
  button.disabled = true;
  try {
    const data = await api("/api/inspect", { url, browser: $("browser").value });
    await startFetch(data);
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    button.disabled = false;
  }
}

async function startFetch(data) {
  state.jobId = data.job_id;
  const video = data.video;
  $("video-title").textContent = video.title;
  $("video-title").href = video.source_url;
  $("video-detail").textContent = [video.uploader, video.duration ? video.duration_text : ""].filter(Boolean).join(" · ");
  const warnings = $("warnings");
  warnings.hidden = !data.warnings.length;
  warnings.textContent = data.warnings.join("\n");
  resetTranscribePanel();
  $("fetch-panel").hidden = false;
  $("fetch-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  if (data.can_transcribe) {
    beginTranscribe();
  } else if ((data.tracks || []).length) {
    generateFromTrack(data);
  } else {
    setStatus("这个视频没有可用的字幕轨，也无法语音识别。", "error");
  }
}

async function generateFromTrack(data) {
  // 有字幕轨的视频：自动用推荐的英文轨生成（仅英文，中文走词典精翻）
  setStatus("使用视频英文字幕轨生成英文原文…", "loading");
  const tracks = data.tracks || [];
  let track = tracks.find((item) => item.id === (data.suggested && data.suggested.english));
  if (!track) track = tracks.find((item) => item.family === "english" || item.family === "bilingual");
  try {
    const result = await api("/api/generate", {
      job_id: state.jobId,
      english_track: track ? track.id : "",
      chinese_track: "",
    });
    renderRows(result);
    setStatus("已用英文字幕轨生成，点「📋 复制英文全文」去词典精翻。", "success");
  } catch (error) {
    setStatus(error.message, "error");
  }
}

const TRANSCRIBE_PHASE_TEXT = {
  running: "识别中：下载音频 → Whisper 转写（仅英文，约几分钟，请保持页面打开）",
  done: "识别完成",
  error: "识别失败",
};

async function beginTranscribe() {
  $("transcribe-progress").hidden = false;
  $("transcribe-phase").textContent = TRANSCRIBE_PHASE_TEXT.running;
  $("transcribe-log").textContent = "正在启动语音识别（仅拉英文，跳过机翻）…\n";
  try {
    await api(`/api/jobs/${state.jobId}/transcribe`, {
      browser: localStorage.getItem("bili-subtitle-browser") || "none",
      translate: false,
    });
    transcribeTimer = window.setTimeout(pollTranscribe, 1500);
  } catch (error) {
    $("transcribe-phase").textContent = "启动失败";
    $("transcribe-log").textContent += `${error.message}\n`;
  }
}

async function pollTranscribe() {
  let data = null;
  try {
    const response = await fetch(`/api/jobs/${state.jobId}/transcribe/status`);
    data = await response.json().catch(() => ({ ok: false, error: `HTTP ${response.status}` }));
    if (!response.ok || !data.ok) throw new Error(data.error || "查询进度失败");
    $("transcribe-phase").textContent = TRANSCRIBE_PHASE_TEXT[data.phase] || data.phase;
    renderStepTrack(data.stage);
    if (data.log && data.log.length) {
      const logBox = $("transcribe-log");
      logBox.textContent = data.log.join("\n") + "\n";
      logBox.scrollTop = logBox.scrollHeight;
    }
    if (data.phase === "running") {
      transcribeTimer = window.setTimeout(pollTranscribe, 2500);
      return;
    }
    if (data.phase === "done") {
      renderRows({
        rows: data.rows,
        count: data.count,
        notice: data.notice,
      });
      setStatus("英文原文已就绪：点「📋 复制英文全文」丢给词典，中文粘到右侧一键排版。", "success");
      return;
    }
    if (data.phase === "error") {
      setStatus(`识别失败：${data.error}`, "error");
      $("transcribe-log").textContent += `${data.error}\n`;
    }
  } catch (error) {
    setStatus(error.message, "error");
    $("transcribe-log").textContent += `${error.message}\n`;
  }
}

function makeCue(row, index) {
  const article = document.createElement("article");
  article.className = "subtitle-card";
  article.dataset.search = `${row.english} ${row.chinese}`.toLowerCase();

  const time = document.createElement("div");
  time.className = "cue-time";
  time.append(document.createTextNode(`${row.start_text} → ${row.end_text}`));
  const number = document.createElement("span");
  number.className = "cue-num";
  number.textContent = `#${String(index + 1).padStart(3, "0")}`;
  time.append(number);

  const copy = document.createElement("div");
  copy.className = "cue-copy";
  const english = document.createElement("p");
  english.className = "cue-en" + (row.english ? "" : " empty");
  english.textContent = row.english || "No English subtitle";
  const chinese = document.createElement("p");
  chinese.className = "cue-zh" + (row.chinese ? "" : " empty");
  chinese.textContent = row.chinese || "无中文字幕";
  copy.append(english, chinese);
  article.append(time, copy);
  return article;
}

function renderRows(data) {
  state.rows = data.rows;
  const list = $("subtitle-list");
  const fragment = document.createDocumentFragment();
  data.rows.forEach((row, index) => fragment.append(makeCue(row, index)));
  list.replaceChildren(fragment);
  $("reader-summary").textContent = `${data.count} 条时间轴字幕 · 可搜索、调字号或导出`;
  $("reader-notice").hidden = !data.notice;
  $("reader-notice").textContent = data.notice;
  $("download-md").href = `/api/jobs/${state.jobId}/download/md`;
  $("subtitle-search").value = "";
  $("no-match").hidden = true;
  $("reader").hidden = false;
  $("reader").scrollIntoView({ behavior: "smooth", block: "start" });
  prepareCopySegments();
}

function filterRows() {
  const query = $("subtitle-search").value.trim().toLowerCase();
  let visible = 0;
  document.querySelectorAll(".subtitle-card").forEach((card) => {
    const show = !query || card.dataset.search.includes(query);
    card.hidden = !show;
    if (show) visible += 1;
  });
  $("no-match").hidden = visible > 0;
}

function changeFont(delta) {
  state.fontScale = Math.min(1.35, Math.max(.8, state.fontScale + delta));
  document.documentElement.style.setProperty("--subtitle-scale", state.fontScale.toFixed(2));
}

async function copyEnglish() {
  const button = $("copy-en");
  try {
    const response = await fetch(`/api/jobs/${state.jobId}/plain-text`);
    if (!response.ok) throw new Error("读取失败");
    const { english } = await response.json();
    if (!english) throw new Error("无英文内容");
    await navigator.clipboard.writeText(english);
    button.textContent = "已复制 ✓ 丢词典吧";
  } catch {
    button.textContent = "复制失败";
  }
  window.setTimeout(() => { button.textContent = "📋 复制英文全文"; }, 2200);
}

// 词典整段翻译有字符上限（欧路约15000含空格）：超限时长文自动改成分段复制，
// 每段在字幕块边界下刀、段内不换行；译文逐段粘回同一个粘贴区即可（换行分隔）。
async function prepareCopySegments() {
  try {
    const response = await fetch(`/api/jobs/${state.jobId}/plain-text`);
    if (!response.ok) return;
    const { english, segments } = await response.json();
    state.englishSegments = Array.isArray(segments) && segments.length ? segments : [english];
    const wrap = $("copy-segments");
    wrap.replaceChildren();
    const hint = $("seg-hint");
    if (state.englishSegments.length < 2) {
      $("copy-en").hidden = false;
      wrap.hidden = true;
      if (hint) hint.hidden = true;
      return;
    }
    $("copy-en").hidden = true;
    wrap.hidden = false;
    state.englishSegments.forEach((segment, index) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "copy-button";
      btn.textContent = `📋 复制第${index + 1}段(${(segment.length / 1000).toFixed(1)}k)`;
      btn.addEventListener("click", () => copySegment(index, btn));
      wrap.append(btn);
    });
    if (hint) {
      hint.textContent = `本文约 ${english.length} 字符，超出词典单次上限，已按句子边界分成 ${state.englishSegments.length} 段：` +
        `逐段复制→翻译→把每段中文依次粘到下面粘贴区（一段一行即可），全部粘完再点「🤖 一键排版」。`;
      hint.hidden = false;
    }
  } catch { /* 分段信息拿不到时保留单键整段复制 */ }
}

async function copySegment(index, button) {
  const label = button.textContent;
  try {
    await navigator.clipboard.writeText(state.englishSegments[index]);
    button.textContent = `第${index + 1}段已复制 ✓`;
  } catch {
    button.textContent = "复制失败";
  }
  window.setTimeout(() => { button.textContent = label; }, 2200);
}

function alignStatus(message, kind) {
  const status = $("align-status");
  status.textContent = message;
  status.className = "align-status " + kind;
  status.hidden = false;
}

async function autoAlign() {
  const button = $("auto-align");
  setBusy(button, true, "排版中…约 1-2 分钟", "🤖 一键排版");
  alignStatus("排版中：本机模型正在切分对齐，请勿关闭页面…", "ok");
  try {
    const data = await api(`/api/jobs/${state.jobId}/auto-align`, { text: $("raw-chinese-text").value });
    renderRows(data);
    alignStatus(`一键排版完成：已回填 ${data.count} 块中文，点「下载 Markdown」即为最终双语稿。`, "ok");
  } catch (error) {
    alignStatus(`${error.message}\n可重试，或点「保存，交给 Claude 排版」走对话兜底。`, "err");
  } finally {
    setBusy(button, false, "排版中…约 1-2 分钟", "🤖 一键排版");
  }
}

async function saveRawChinese() {
  const button = $("save-raw-ch");
  setBusy(button, true, "保存中…", "保存，交给 Claude 排版");
  try {
    const data = await api(`/api/jobs/${state.jobId}/raw-chinese`, { text: $("raw-chinese-text").value });
    alignStatus(`已保存 ${data.saved_chars} 字。现在对 Claude 说「排版」，完成后回来点「⟳ 应用排版结果」。`, "ok");
  } catch (error) {
    alignStatus(error.message, "err");
  } finally {
    setBusy(button, false, "保存中…", "保存，交给 Claude 排版");
  }
}

async function applyAlignedResult() {
  const button = $("apply-align");
  setBusy(button, true, "刷新中…", "⟳ 应用排版结果");
  try {
    const response = await fetch(`/api/jobs/${state.jobId}/rows`);
    if (!response.ok) throw new Error("读取失败");
    const data = await response.json();
    renderRows(data);
    const filled = data.rows.filter((row) => row.chinese).length;
    if (!filled) {
      alignStatus("还没有排版结果——先保存词典中文，再让 Claude 排版。", "err");
    } else {
      alignStatus(`已回填 ${filled}/${data.count} 块中文${filled === data.count ? "" : "（尚有缺块）"}；点「下载 Markdown」即为最终双语稿。`, "ok");
    }
  } catch (error) {
    alignStatus(error.message, "err");
  } finally {
    setBusy(button, false, "刷新中…", "⟳ 应用排版结果");
  }
}

async function stopServer() {
  // 批量队列在跑时给出专门警告:停服务=杀进程,正在转写的集子进度作废,还得手动恢复
  let batchHint = "";
  try {
    const data = await (await fetch("/api/batch/list", { cache: "no-store" })).json();
    const active = (data.batches || []).filter((b) => b.state === "running");
    const remaining = active.reduce((n, b) => n + (b.total - b.done - b.failed), 0);
    if (active.length && remaining > 0) {
      batchHint = `\n\n⚠️ 批量队列还在跑:剩 ${remaining} 集。停了这集转写白跑,重启后要去「已有批次」点恢复!挂机请直接关标签页,别停服务。`;
    }
  } catch { /* 拿不到批次信息就按普通提示 */ }
  const confirmed = window.confirm(
    `确定停止服务？进行中的任务会中断；已完成的转写会保留在本地缓存。${batchHint}`);
  if (!confirmed) return;
  const button = $("stop-server");
  button.disabled = true;
  button.textContent = "停止中…";
  try {
    await api("/api/shutdown", {});
  } catch { /* 进程退出导致连接断开属预期 */ }
  // 验证真的停了：探测到连不上才算数，避免"以为重启了其实没关"
  const deadline = Date.now() + 5000;
  let stopped = false;
  while (Date.now() < deadline) {
    await new Promise((resolve) => window.setTimeout(resolve, 500));
    try {
      await fetch("/api/health", { cache: "no-store" });
    } catch {
      stopped = true;
      break;
    }
  }
  if (transcribeTimer) { window.clearTimeout(transcribeTimer); transcribeTimer = null; }
  if (stopped) {
    button.textContent = "已停止";
    $("server-started").textContent = "";
    setStatus("服务已停止（已确认进程退出），可以关闭本页。", "success");
    window.close();
  } else {
    button.disabled = false;
    button.textContent = "停止服务";
    setStatus("服务似乎仍在运行：请到启动它的终端按 Ctrl+C 结束进程。", "error");
  }
}

async function loadServerStarted() {
  try {
    const response = await fetch("/api/health", { cache: "no-store" });
    const data = await response.json();
    if (data.ok && data.started_at) {
      $("server-started").textContent = `服务启动于 ${data.started_at}`;
    }
  } catch { /* 健康检查失败不打扰页面 */ }
}

function restoreForm() {
  const savedUrl = localStorage.getItem("bili-subtitle-url");
  const savedBrowser = localStorage.getItem("bili-subtitle-browser");
  if (savedUrl) $("video-url").value = savedUrl;
  if (["none", "edge", "chrome", "firefox"].includes(savedBrowser)) $("browser").value = savedBrowser;
}

$("inspect-form").addEventListener("submit", inspect);
$("stop-server").addEventListener("click", stopServer);
$("subtitle-search").addEventListener("input", filterRows);
$("font-smaller").addEventListener("click", () => changeFont(-.1));
$("font-larger").addEventListener("click", () => changeFont(.1));
$("copy-en").addEventListener("click", copyEnglish);
$("auto-align").addEventListener("click", autoAlign);
$("save-raw-ch").addEventListener("click", saveRawChinese);
$("apply-align").addEventListener("click", applyAlignedResult);
$("to-top").addEventListener("click", () => $("reader").scrollIntoView({ behavior: "smooth" }));
restoreForm();
loadServerStarted();

// ---- 批量模式 ----
const batchState = { episodes: [], batchId: "", timer: null };

// B站标题可能带引号/尖括号，进 innerHTML 前必须转义
const escHtml = (s) => String(s)
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

function batchStatusBadge(status) {
  return { queued: "⏳ 排队", running: "🔄 进行中", done: "✅ 完成", failed: "❌ 失败" }[status] || status;
}

async function listBatchEpisodes() {
  const url = $("batch-url").value.trim();
  if (!url) return;
  const btn = $("batch-list-btn");
  setBusy(btn, true, "枚举中…", "列出集数");
  try {
    const data = await api("/api/batch/list", { url });
    batchState.episodes = data.items;
    const list = $("batch-episode-list");
    list.replaceChildren();
    data.items.forEach((ep) => {
      const row = document.createElement("label");
      row.className = "batch-episode";
      row.innerHTML = `<input type="checkbox" data-p="${ep.p}">` +
        `<span class="p">p${ep.p}</span><span class="t" title="${escHtml(ep.title)}">${escHtml(ep.title)}</span>` +
        `<span class="d">${Math.round(ep.duration / 60)} 分钟</span>`;
      list.append(row);
    });
    $("batch-episodes").hidden = false;
  } catch (error) {
    setStatus(error.message, "error");
  } finally { setBusy(btn, false, "", "列出集数"); }
}

function checkedBatchPs() {
  return [...document.querySelectorAll("#batch-episode-list input:checked")]
    .map((el) => Number(el.dataset.p));
}

function setBatchChecked(ps) {
  const want = new Set(ps);
  document.querySelectorAll("#batch-episode-list input").forEach((el) => {
    el.checked = want.has(Number(el.dataset.p));
  });
}

async function startBatch() {
  const ps = checkedBatchPs();
  if (!ps.length) { setStatus("先勾选要拉取的集数", "error"); return; }
  const totalMin = batchState.episodes
    .filter((ep) => ps.includes(ep.p))
    .reduce((sum, ep) => sum + ep.duration / 4 + Number($("batch-interval").value || 60), 0) / 60;
  if (ps.length > 30 &&
      !window.confirm(`选中 ${ps.length} 集，预计约 ${Math.round(totalMin)} 分钟（挂机慢跑，可随时停服务暂停）。继续？`)) return;
  const url = $("batch-url").value.trim();
  try {
    const data = await api("/api/batch/start", {
      url, ps, interval: Number($("batch-interval").value || 60),
    });
    batchState.batchId = data.batch_id;
    $("batch-episodes").hidden = true;
    $("batch-run").hidden = false;
    pollBatch();
  } catch (error) { setStatus(error.message, "error"); }
}

function pollBatch() {
  if (batchState.timer) window.clearTimeout(batchState.timer);
  fetch(`/api/batch/${batchState.batchId}`)
    .then((r) => r.json())
    .then((data) => {
      if (!data.ok) return;
      renderBatch(data.batch);
      const unfinished = data.batch.items.filter((i) => i.status === "queued" || i.status === "running").length;
      if (unfinished > 0 || data.batch.state === "running") {
        batchState.timer = window.setTimeout(pollBatch, 3000);
      }
    })
    .catch(() => { batchState.timer = window.setTimeout(pollBatch, 5000); });
}

function renderBatch(batch) {
  const done = batch.items.filter((i) => i.status === "done").length;
  $("batch-progress-text").textContent =
    `${batch.title} —— ${done}/${batch.items.length} 完成` +
    (batch.items.some((i) => i.status === "failed") ? `，${batch.items.filter((i) => i.status === "failed").length} 失败` : "");
  $("batch-progress-fill").style.width = `${(done / batch.items.length) * 100}%`;
  const tbody = $("batch-tbody");
  tbody.replaceChildren();
  batch.items.forEach((item) => {
    const tr = document.createElement("tr");
    const ops = [];
    if (item.status === "done") {
      ops.push(`<a href="javascript:void(0)" onclick="openBatchJob('${item.job_id}')">去处理</a>`);
    } else if (item.status === "failed") {
      ops.push(`<button onclick="retryBatchItem(${item.p})">重试</button>`);
    }
    tr.innerHTML = `<td>p${item.p}</td><td title="${escHtml(item.title)}">${escHtml(item.title.slice(0, 40))}</td>` +
      `<td class="st st-${item.status}">${batchStatusBadge(item.status)}</td>` +
      `<td class="op">${ops.join(" ")}</td>`;
    tbody.append(tr);
  });
}

async function retryBatchItem(p) {
  try { await api(`/api/batch/${batchState.batchId}/retry`, { p }); pollBatch(); }
  catch (error) { setStatus(error.message, "error"); }
}

async function openBatchJob(jobId) {
  state.jobId = jobId;
  const response = await fetch(`/api/jobs/${jobId}/transcribe/status`);
  const payload = await response.json();
  if (!payload.ok) { setStatus(payload.error || "任务已过期", "error"); return; }
  renderRows({ rows: payload.rows || [], count: (payload.rows || []).length, notice: "" });
}

async function loadSavedBatches() {
  try {
    const response = await fetch("/api/batch/list");
    const data = await response.json();
    const wrap = $("batch-saved");
    wrap.replaceChildren();
    const batches = data.batches || [];
    $("batch-saved-wrap").hidden = !batches.length;
    batches.forEach((b) => {
      const row = document.createElement("div");
      row.className = "batch-saved-item";
      const resume = b.resumable
        ? `<button onclick="resumeBatch('${b.batch_id}')">恢复</button>` : "";
      const view = b.state === "running" || b.done
        ? `<a href="javascript:void(0)" onclick="viewBatch('${b.batch_id}')">查看</a>` : "";
      row.innerHTML = `<b>${escHtml(b.title.slice(0, 26))}</b><span>${b.done}/${b.total} · ` +
        `${b.state === "finished" ? "已完成" : "未完成"}</span>${view}${resume}`;
      wrap.append(row);
    });
  } catch { /* 静默 */ }
}

async function resumeBatch(batchId) {
  try { await api(`/api/batch/${batchId}/resume`, {}); viewBatch(batchId); }
  catch (error) { setStatus(error.message, "error"); }
}

async function viewBatch(batchId) {
  batchState.batchId = batchId;
  $("batch-episodes").hidden = true;
  $("batch-run").hidden = false;
  pollBatch();
}

$("batch-list-btn").addEventListener("click", listBatchEpisodes);
$("batch-select-all").addEventListener("click", () =>
  setBatchChecked(batchState.episodes.map((ep) => ep.p)));
$("batch-clear").addEventListener("click", () => setBatchChecked([]));
$("batch-range-btn").addEventListener("click", () => {
  // 范围解析在前端复刻 batch_core.parse_ps 语义：1-10,15 → 勾选这些集
  const available = batchState.episodes.length;
  const want = new Set();
  for (const token of $("batch-range").value.split(",")) {
    const m = token.trim().match(/^(\d+)\s*-\s*(\d+)$|^(\d+)$/);
    if (!m) continue;
    if (m[3]) want.add(Number(m[3]));
    else { const [a, b] = [Number(m[1]), Number(m[2])].sort((x, y) => x - y);
      for (let p = a; p <= b; p++) want.add(p); }
  }
  setBatchChecked([...want].filter((p) => p >= 1 && p <= available));
});
$("batch-start").addEventListener("click", startBatch);
loadSavedBatches();
