'use strict';

/* ══════════════════════════════════════
   i18n — Chinese / English
══════════════════════════════════════ */
const I18N = {
  zh: {
    eyebrow: 'AI 驱动的竞品分析平台',
    heroTitle: '开始你的<br>专属竞品分析',
    heroSub: '多智能体协同分析 · 自动生成专业竞品报告 · 支持中英双语',
    heroSubEn: 'Start your exclusive competitive analysis',
    heroCta: '立即开始分析',
    heroMore: '了解更多 →',
    reportTitle: '竞品分析报告',
    reportFilename: '飞书竞品分析报告_2026.pdf',
    dlBtn: '下载 PDF',
    pLabel: '我们产品干什么',
    pTitle: '全自动 AI 竞品分析，一键生成专业报告',
    pSub: '输入目标产品，上传参考文档，多智能体自动完成竞品采集、情感分析与报告撰写',
    s1Title: '输入 & 上传', s1Desc: '输入目标产品名 + 分析需求，可上传一份参考文档（PDF/Word）',
    s2Title: '多智能体分析', s2Desc: 'PM 制定计划 → Collector 联网采集 → Insight 情感分析，全程流式输出',
    s3Title: '报告预览 & 下载', s3Desc: '在线预览 PDF 报告，包含 SWOT 分析、定价对比、竞品横向评分',
    aLabel: '智能体功能介绍', aTitle: '多智能体协同工作流',
    ag1Role: '制定计划', ag1Desc: '解析用户需求<br>制定任务简报<br>分配 Collect & Insight 任务',
    ag2Role: '联网采集', ag2Desc: '联网搜索竞品<br>采集定价 / 功能<br>ReAct 多轮探索',
    ag3Role: '情感分析', ag3Desc: '爬取用户评论<br>BERT 情感分类<br>提炼正负面观点',
    ag4Role: '报告生成', ag4Desc: 'SWOT 分析<br>横向评分对比<br>输出 PDF 报告',
    navLinks: ['产品介绍', '智能体', '开始分析', '登录'],
    formTitle: '开始分析',
    lblProduct: '目标产品名称', phProduct: '例如：飞书、DingTalk、Slack',
    lblQuery: '分析需求描述', phQuery: '请描述您的分析需求，例如：分析飞书与钉钉、Slack 的视频会议功能差异、定价策略对比...',
    lblFile: '上传参考文档（最多 1 个文件）',
    upMain: '点击上传或拖拽文件至此处',
    upSub: '支持 PDF、Word、TXT，仅限 1 个文件，最大 20MB',
    submitBtn: '开始分析',
    streamTitle: '智能体运行日志',
    thinkText: '思考中...',
    logPlaceholder: '点击「开始分析」后，智能体实时日志将在此处显示<br>您可以看到每个 Agent 的思考过程和工具调用',
    pdfTitle: '竞品分析报告已生成',
    pdfFname: '竞品分析报告_飞书_2024.pdf',
    pdfDl: '↓  下载到本地',
    pdfEmpty: '完成分析后，PDF 报告将在此处预览',
    pdfPageInfo: (c, t) => `第 ${c} / ${t} 页`,
    progress: (p, s) => `分析进度 ${p}% · 预计剩余 ${s} 秒`,
    footerTagline: 'AI 驱动的竞品分析平台',
    fc1Title: '产品', fc2Title: '支持',
    footerCopy: '© 2024 Dreamcode · 保留所有权利',
    errNoProduct: '请输入目标产品名称',
    errFiletype: '仅支持 PDF、Word、TXT 格式',
    errFilesize: '文件不能超过 20MB',
    loginMsg: '登录功能即将上线',
  },
  en: {
    eyebrow: 'AI-powered Competitive Analysis',
    heroTitle: 'Your Exclusive<br>Competitor Analysis',
    heroSub: 'Multi-agent AI · Auto-generate professional reports · Chinese & English',
    heroSubEn: '开始你的专属竞品分析',
    heroCta: 'Start Analysis',
    heroMore: 'Learn more →',
    reportTitle: 'Competitive Analysis Report',
    reportFilename: 'feishu_analysis_2026.pdf',
    dlBtn: 'Download PDF',
    pLabel: 'What We Do',
    pTitle: 'Full-auto AI Competitive Analysis',
    pSub: 'Enter a product, upload a doc — our multi-agent system handles collection, sentiment analysis, and report writing',
    s1Title: 'Input & Upload', s1Desc: 'Enter the target product and your analysis request. Optionally upload one reference document (PDF/Word).',
    s2Title: 'Multi-agent Analysis', s2Desc: 'PM plans → Collector scrapes → Insight analyses sentiment. Full real-time streaming output.',
    s3Title: 'Preview & Download', s3Desc: 'Preview the PDF report in-browser. Includes SWOT analysis, pricing comparison, and cross-product scoring.',
    aLabel: 'Agent Features', aTitle: 'Multi-agent Collaboration',
    ag1Role: 'Planning', ag1Desc: 'Parses user needs<br>Creates task briefs<br>Assigns Collect & Insight tasks',
    ag2Role: 'Scraping', ag2Desc: 'Web searches competitors<br>Collects pricing & features<br>ReAct multi-round exploration',
    ag3Role: 'Sentiment', ag3Desc: 'Crawls user reviews<br>BERT sentiment analysis<br>Extracts positive/negative themes',
    ag4Role: 'Report Gen', ag4Desc: 'SWOT analysis<br>Cross-product scoring<br>Outputs PDF report',
    navLinks: ['Product', 'Agents', 'Analyze', 'Login'],
    formTitle: 'Start Analysis',
    lblProduct: 'Target Product', phProduct: 'e.g. Feishu, DingTalk, Slack',
    lblQuery: 'Analysis Request', phQuery: 'Describe your analysis needs, e.g. Compare video conferencing features and pricing between Feishu and DingTalk...',
    lblFile: 'Upload Reference Document (max 1 file)',
    upMain: 'Click to upload or drag file here',
    upSub: 'PDF, Word, TXT supported · 1 file max · 20 MB limit',
    submitBtn: 'Start Analysis',
    streamTitle: 'Agent Run Log',
    thinkText: 'Thinking...',
    logPlaceholder: 'Agent logs will stream here after you click Start Analysis.<br>Follow each agent\'s reasoning and tool calls in real time.',
    pdfTitle: 'Competitive Analysis Report Ready',
    pdfFname: 'competitive_analysis_2024.pdf',
    pdfDl: '↓  Download',
    pdfEmpty: 'PDF report will appear here after analysis is complete.',
    pdfPageInfo: (c, t) => `Page ${c} of ${t}`,
    progress: (p, s) => `Progress ${p}% · ~${s}s remaining`,
    footerTagline: 'AI-powered Competitive Analysis',
    fc1Title: 'Product', fc2Title: 'Support',
    footerCopy: '© 2024 Dreamcode · All rights reserved',
    errNoProduct: 'Please enter a target product name',
    errFiletype: 'Only PDF, Word, TXT supported',
    errFilesize: 'File must be under 20 MB',
    loginMsg: 'Login coming soon',
  },
};

/* ══════════════════════════════════════
   State
══════════════════════════════════════ */
let lang = 'zh';
let uploadedFile = null;
let pdfPath = null;
let eventSource = null;

/* ══════════════════════════════════════
   Helpers
══════════════════════════════════════ */
function $(id) { return document.getElementById(id); }
function T(k)  { return I18N[lang][k]; }

function scrollTo(sectionId) {
  const el = document.getElementById(sectionId);
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  return false;
}

function handleLogin() {
  alert(T('loginMsg'));
}

function downloadPdf() {
  if (!pdfPath) { alert(T('pdfEmpty')); return; }
  const url = `/api/report/pdf?path=${encodeURIComponent(pdfPath)}&download=1`;
  const a = document.createElement('a');
  a.href = url;
  a.download = T('pdfFname');
  a.click();
}

/* ══════════════════════════════════════
   i18n render
══════════════════════════════════════ */
function applyLang() {
  const T = I18N[lang];

  // Navbar
  document.querySelectorAll('.lang-btn').forEach(b => b.classList.toggle('active', b.dataset.lang === lang));
  const links = document.querySelectorAll('.nav-links a');
  T.navLinks.forEach((txt, i) => { if (links[i]) links[i].textContent = txt; });

  // Hero
  setText('t-eyebrow', T.eyebrow);
  setHTML('t-hero-title', T.heroTitle);
  setText('t-hero-sub', T.heroSub);
  setText('t-hero-sub-en', T.heroSubEn);
  setText('t-hero-cta', T.heroCta);
  setText('t-hero-more', T.heroMore);
  setText('t-report-title', T.reportTitle);
  setText('t-report-filename', T.reportFilename);
  setText('t-dl-btn', T.dlBtn);

  // Product
  setText('t-p-label', T.pLabel);
  setText('t-p-title', T.pTitle);
  setText('t-p-sub', T.pSub);
  setText('t-s1-title', T.s1Title); setText('t-s1-desc', T.s1Desc);
  setText('t-s2-title', T.s2Title); setText('t-s2-desc', T.s2Desc);
  setText('t-s3-title', T.s3Title); setText('t-s3-desc', T.s3Desc);

  // Agents
  setText('t-a-label', T.aLabel);
  setText('t-a-title', T.aTitle);
  setText('t-ag1-role', T.ag1Role); setHTML('t-ag1-desc', T.ag1Desc);
  setText('t-ag2-role', T.ag2Role); setHTML('t-ag2-desc', T.ag2Desc);
  setText('t-ag3-role', T.ag3Role); setHTML('t-ag3-desc', T.ag3Desc);
  setText('t-ag4-role', T.ag4Role); setHTML('t-ag4-desc', T.ag4Desc);

  // Form
  setText('t-form-title', T.formTitle);
  setText('t-lbl-product', T.lblProduct);
  setAttr('input-product', 'placeholder', T.phProduct);
  setText('t-lbl-query', T.lblQuery);
  setAttr('input-query', 'placeholder', T.phQuery);
  setText('t-lbl-file', T.lblFile);
  setText('t-up-main', T.upMain);
  setText('t-up-sub', T.upSub);
  setText('submit-btn', T.submitBtn);

  // Stream
  setText('t-stream-title', T.streamTitle);
  setText('think-text', T.thinkText);
  setHTML('t-log-placeholder', T.logPlaceholder);

  // PDF
  setText('t-pdf-title', T.pdfTitle);
  setText('pdf-fname', T.pdfFname);
  setText('pdf-dl-btn', T.pdfDl);
  setText('t-pdf-empty', T.pdfEmpty);

  // Footer
  setText('t-footer-tagline', T.footerTagline);
  setText('t-fc1-title', T.fc1Title);
  setText('t-fc2-title', T.fc2Title);
  setText('t-footer-copy', T.footerCopy);
}

function setText(id, val) { const el = $(id); if (el) el.textContent = val; }
function setHTML(id, val) { const el = $(id); if (el) el.innerHTML  = val; }
function setAttr(id, attr, val) { const el = $(id); if (el) el[attr] = val; }

function setLang(l) {
  lang = l;
  applyLang();
}

/* ══════════════════════════════════════
   File upload
══════════════════════════════════════ */
function initUpload() {
  const area   = $('upload-area');
  const input  = $('file-input');
  const info   = $('file-info');
  const nameEl = $('file-name-text');
  const removeBtn = $('file-remove');

  area.addEventListener('click', () => input.click());
  area.addEventListener('dragover', e => { e.preventDefault(); area.classList.add('drag-over'); });
  area.addEventListener('dragleave', () => area.classList.remove('drag-over'));
  area.addEventListener('drop', e => {
    e.preventDefault(); area.classList.remove('drag-over');
    const f = e.dataTransfer.files[0];
    if (f) setFile(f);
  });
  input.addEventListener('change', () => { if (input.files[0]) setFile(input.files[0]); input.value = ''; });
  removeBtn.addEventListener('click', e => {
    e.stopPropagation();
    uploadedFile = null;
    info.classList.remove('show');
    area.style.display = '';
  });

  function setFile(f) {
    if (!f.name.match(/\.(pdf|doc|docx|txt)$/i)) { alert(T('errFiletype')); return; }
    if (f.size > 20 * 1024 * 1024) { alert(T('errFilesize')); return; }
    uploadedFile = f;
    nameEl.textContent = f.name;
    info.classList.add('show');
    area.style.display = 'none';
  }
}

/* ══════════════════════════════════════
   Streaming log
══════════════════════════════════════ */
const AGENT_COLORS = {
  'PM Agent': '#40c4d0',
  'Collector': '#1eab7a',
  'Insight': '#df7f37',
  'Reporter': '#9259f2',
};

function appendLog(agent, msg, dim) {
  const body = $('log-body');
  const placeholder = body.querySelector('.log-placeholder');
  if (placeholder) placeholder.remove();

  const line = document.createElement('div');
  line.className = 'log-line';
  const color = AGENT_COLORS[agent] || '#9999b2';
  line.innerHTML =
    `<span class="log-agent" style="color:${color}">[${esc(agent)}]</span>` +
    `<span class="log-msg ${dim ? 'log-dim' : 'log-bright'}">${esc(msg)}</span>`;
  body.appendChild(line);
  body.scrollTop = body.scrollHeight;
}

function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function setThink(show) {
  $('think-badge').classList.toggle('show', show);
}

function setProgress(pct, secLeft) {
  $('progress-fill').style.width = pct + '%';
  $('progress-text').textContent = pct > 0 ? T('progress')(pct, secLeft) : '';
}

/* ══════════════════════════════════════
   Submit
══════════════════════════════════════ */
async function handleSubmit(e) {
  e.preventDefault();

  const product = $('input-product').value.trim();
  if (!product) { $('input-product').focus(); alert(T('errNoProduct')); return; }

  const btn = $('submit-btn');
  btn.disabled = true;

  // Reset log
  $('log-body').innerHTML = `<p class="log-placeholder" id="t-log-placeholder"></p>`;
  setThink(false);
  setProgress(0, 0);

  const fd = new FormData();
  fd.append('target_product', product);
  fd.append('user_query', $('input-query').value.trim() || product);
  if (uploadedFile) fd.append('file', uploadedFile);

  try {
    const res = await fetch('/api/analyze', { method: 'POST', body: fd });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const { job_id } = await res.json();
    openSSE(job_id, btn);
  } catch (_) {
    // No backend — run local simulation
    simulate(btn);
  }
}

/* ══════════════════════════════════════
   SSE stream (real backend)
══════════════════════════════════════ */
function openSSE(jobId, btn) {
  if (eventSource) eventSource.close();
  eventSource = new EventSource(`/api/stream/${jobId}`);

  eventSource.onmessage = ev => {
    const msg = JSON.parse(ev.data);
    switch (msg.type) {
      case 'thinking':
        setThink(true);
        break;
      case 'tool_call':
        setThink(false);
        appendLog(msg.agent, `→ ${msg.tool}(${msg.args})`, true);
        break;
      case 'tool_result':
        appendLog(msg.agent, `← ${msg.tool} (${msg.size}) ${msg.preview}`, true);
        break;
      case 'log':
        appendLog(msg.agent, msg.text, false);
        break;
      case 'progress':
        setProgress(msg.pct, msg.sec_left);
        break;
      case 'done':
        eventSource.close();
        setThink(false);
        setProgress(100, 0);
        btn.disabled = false;
        if (msg.pdf_path) showPdf(msg.pdf_path, msg.filename);
        break;
      case 'error':
        eventSource.close();
        setThink(false);
        btn.disabled = false;
        appendLog('Error', msg.message, false);
        break;
    }
  };
  eventSource.onerror = () => { eventSource.close(); btn.disabled = false; };
}

/* ══════════════════════════════════════
   PDF viewer
══════════════════════════════════════ */
function showPdf(path, filename) {
  pdfPath = path;
  const url = `/api/report/pdf?path=${encodeURIComponent(path)}`;
  $('pdf-content').innerHTML = `<iframe src="${url}" title="PDF Report"></iframe>`;
  if (filename) $('pdf-fname').textContent = filename;
  $('pdf-section').scrollIntoView({ behavior: 'smooth' });
}

/* ══════════════════════════════════════
   Dev simulation (no backend)
══════════════════════════════════════ */
function simulate(btn) {
  const zh = lang === 'zh';
  const steps = [
    [300,  () => setThink(true)],
    [1000, () => { appendLog('PM Agent', zh?'分析用户查询，制定竞品分析计划...':'Parsing user query, creating analysis plan...'); setThink(false); }],
    [600,  () => { appendLog('PM Agent', '→ initial_brief({...})', true); setProgress(8, 90); }],
    [900,  () => { setThink(true); }],
    [800,  () => { setThink(false); appendLog('Collector', zh?'联网搜索竞品官网...':'Searching competitor websites...'); setProgress(20, 75); }],
    [600,  () => appendLog('Collector', '→ web_search({ query: "target pricing 2024" })', true)],
    [900,  () => { appendLog('Collector', '← web_search (2.1KB) pricing data fetched...', true); setProgress(32, 62); }],
    [500,  () => appendLog('Collector', zh?'采集竞品功能特性...':'Collecting feature details...')],
    [700,  () => { appendLog('Collector', '→ fetch_page({ url: "..." })', true); setProgress(44, 50); }],
    [800,  () => appendLog('Collector', '← fetch_page (4.8KB) feature list extracted', true)],
    [600,  () => setThink(true)],
    [900,  () => { setThink(false); appendLog('Insight', zh?'App Store 情感分析，抓取用户评论...':'App Store sentiment analysis, crawling reviews...'); setProgress(56, 38); }],
    [600,  () => appendLog('Insight', '→ appstore_search({ product: "...", region: "cn" })', true)],
    [900,  () => { appendLog('Insight', '← appstore_search (3.2KB) 320 reviews fetched', true); setProgress(68, 26); }],
    [600,  () => appendLog('Insight', zh?'BERT 情感分类完成，提炼观点...':'BERT classification done, extracting themes...')],
    [700,  () => { appendLog('Reporter', zh?'开始生成竞品分析报告...':'Generating competitive analysis report...'); setProgress(78, 18); }],
    [700,  () => appendLog('Reporter', '→ submit_dimension_ranking({...})', true)],
    [800,  () => { appendLog('Reporter', '→ finalize_swot({...})', true); setProgress(88, 8); }],
    [900,  () => appendLog('Reporter', zh?'报告撰写完成，正在渲染 PDF...':'Report done, rendering PDF...')],
    [1200, () => {
      setProgress(100, 0);
      setThink(false);
      btn.disabled = false;
      // Show placeholder in PDF section since no real backend
      $('pdf-content').innerHTML = `
        <div class="pdf-empty">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path stroke-linecap="round" stroke-linejoin="round"
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
          </svg>
          <p>${zh?'演示模式：实际部署后 PDF 将在此预览':'Demo mode: PDF preview available after deployment'}</p>
        </div>`;
      $('pdf-section').scrollIntoView({ behavior: 'smooth' });
    }],
  ];

  let delay = 0;
  steps.forEach(([d, fn]) => { delay += d; setTimeout(fn, delay); });
}

/* ══════════════════════════════════════
   Boot
══════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', () => {
  applyLang();
  initUpload();
  $('analyze-form').addEventListener('submit', handleSubmit);
});
