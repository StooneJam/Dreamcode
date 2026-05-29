'use strict';

/* ── i18n ── */
const TEXTS = {
  zh: {
    eyebrow: 'AI 驱动的竞品分析平台',
    heroTitle: '开始你的\n专属竞品分析',
    heroSub: '多智能体协同分析 · 自动生成专业竞品报告 · 支持中英双语',
    heroSubEn: 'Start your exclusive competitive analysis',
    heroCta: '立即开始分析',
    heroMore: '了解更多 →',
    nav: ['产品介绍', '智能体', '开始分析', '登录'],
    sec1Label: '我们产品干什么',
    sec1Title: '全自动 AI 竞品分析，一键生成专业报告',
    sec1Sub: '输入目标产品，上传参考文档，多智能体自动完成竞品采集、情感分析与报告撰写',
    steps: [
      { num:'01', title:'输入 & 上传', desc:'输入目标产品名称和分析需求，可选择上传一份参考文档（PDF/Word）' },
      { num:'02', title:'多智能体分析', desc:'PM 制定计划 → Collector 联网采集 → Insight 情感分析，全程流式输出' },
      { num:'03', title:'报告预览 & 下载', desc:'在线预览 PDF 报告，包含 SWOT 分析、定价对比、竞品横向评分' },
    ],
    sec2Label: '智能体功能介绍',
    sec2Title: '多智能体协同工作流',
    agents: [
      { name:'PM Agent',  role:'制定计划', desc:'解析用户需求\n制定任务简报\n分配 Collect & Insight 任务' },
      { name:'Collector', role:'联网采集', desc:'联网搜索竞品\n采集定价 / 功能\nReAct 多轮探索' },
      { name:'Insight',   role:'情感分析', desc:'爬取用户评论\nBERT 情感分类\n提炼正负面观点' },
      { name:'Reporter',  role:'报告生成', desc:'SWOT 分析\n横向评分对比\n输出 PDF 报告' },
    ],
    formTitle: '开始分析',
    labelProduct: '目标产品名称',
    placeholderProduct: '例如：飞书、DingTalk、Slack',
    labelQuery: '分析需求描述',
    placeholderQuery: '描述分析需求，例如：比较飞书与钉钉的视频会议功能及定价策略...',
    labelFile: '上传参考文档（最多 1 个文件）',
    uploadMain: '点击上传或拖拽文件至此处',
    uploadSub: '支持 PDF、Word、TXT，仅限 1 个文件，最大 20MB',
    submitBtn: '开始分析',
    streamTitle: '智能体运行日志',
    thinkLabel: '思考中...',
    progressLabel: (pct, sec) => `分析进度 ${pct}% · 预计剩余 ${sec} 秒`,
    streamPlaceholder: '点击「开始分析」后，智能体实时日志将在此处显示\n您可以看到每个 Agent 的思考过程和工具调用',
    resultTitle: '竞品分析报告已生成',
    pdfFilename: '竞品分析报告.pdf',
    pageInfo: (cur, total) => `第 ${cur} / ${total} 页`,
    download: '↓  下载到本地',
    footerBrand: 'Dreamcode',
    footerTagline: 'AI 驱动的竞品分析平台',
    footerCols: [
      { title:'产品', links:['功能介绍','智能体','定价'] },
      { title:'支持', links:['文档','联系我们','关于'] },
      { title:'语言', links:['中文','English'] },
    ],
    copyright: '© 2024 Dreamcode · 保留所有权利',
  },
  en: {
    eyebrow: 'AI-powered Competitive Analysis',
    heroTitle: 'Your Exclusive\nCompetitor Analysis',
    heroSub: 'Multi-agent AI · Auto-generate professional reports · Chinese & English',
    heroSubEn: '开始你的专属竞品分析',
    heroCta: 'Start Analysis',
    heroMore: 'Learn more →',
    nav: ['Product', 'Agents', 'Analyze', 'Login'],
    sec1Label: 'What We Do',
    sec1Title: 'Full-auto AI Competitive Analysis',
    sec1Sub: 'Enter a target product, upload a reference doc, and our multi-agent system handles collection, sentiment analysis, and report writing',
    steps: [
      { num:'01', title:'Input & Upload', desc:'Enter the target product name and your analysis request. Optionally upload one reference document (PDF/Word).' },
      { num:'02', title:'Multi-agent Analysis', desc:'PM plans → Collector scrapes → Insight analyses sentiment. Full streaming output.' },
      { num:'03', title:'Preview & Download', desc:'Preview the PDF report online. Includes SWOT, pricing comparison, and cross-product scoring.' },
    ],
    sec2Label: 'Agent Features',
    sec2Title: 'Multi-agent Collaboration',
    agents: [
      { name:'PM Agent',  role:'Planning', desc:'Parses user needs\nCreates task briefs\nAssigns Collect & Insight tasks' },
      { name:'Collector', role:'Scraping', desc:'Web searches competitors\nCollects pricing & features\nReAct multi-round exploration' },
      { name:'Insight',   role:'Sentiment', desc:'Crawls user reviews\nBERT sentiment analysis\nExtracts positive/negative themes' },
      { name:'Reporter',  role:'Report Gen', desc:'SWOT analysis\nCross-product scoring\nOutputs PDF report' },
    ],
    formTitle: 'Start Analysis',
    labelProduct: 'Target Product',
    placeholderProduct: 'e.g. Feishu, DingTalk, Slack',
    labelQuery: 'Analysis Request',
    placeholderQuery: 'Describe your analysis needs, e.g. Compare video conferencing features and pricing between Feishu and DingTalk...',
    labelFile: 'Upload Reference Document (max 1 file)',
    uploadMain: 'Click to upload or drag file here',
    uploadSub: 'PDF, Word, TXT supported · 1 file max · 20 MB limit',
    submitBtn: 'Start Analysis',
    streamTitle: 'Agent Run Log',
    thinkLabel: 'Thinking...',
    progressLabel: (pct, sec) => `Progress ${pct}% · ~${sec}s remaining`,
    streamPlaceholder: 'Agent logs will stream here after you click Start Analysis.\nYou can follow each agent\'s reasoning and tool calls in real time.',
    resultTitle: 'Competitive Analysis Report Ready',
    pdfFilename: 'competitive_analysis.pdf',
    pageInfo: (cur, total) => `Page ${cur} of ${total}`,
    download: '↓  Download',
    footerBrand: 'Dreamcode',
    footerTagline: 'AI-powered Competitive Analysis',
    footerCols: [
      { title:'Product', links:['Features','Agents','Pricing'] },
      { title:'Support', links:['Docs','Contact','About'] },
      { title:'Language', links:['中文','English'] },
    ],
    copyright: '© 2024 Dreamcode · All rights reserved',
  },
};

/* ── State ── */
let lang = 'zh';
let currentPage = 'home'; // 'home' | 'analyze' | 'result'
let uploadedFile = null;
let streamESS = null;
let pdfObjectUrl = null;

/* ── DOM refs ── */
const $ = id => document.getElementById(id);
const homePage    = $('page-home');
const analyzePage = $('page-analyze');
const resultPage  = $('page-result');

/* ── Helpers ── */
function showPage(name) {
  currentPage = name;
  [homePage, analyzePage, resultPage].forEach(p => p.classList.remove('active'));
  const pageMap = { home: homePage, analyze: analyzePage, result: resultPage };
  pageMap[name].classList.add('active');
  window.scrollTo(0, 0);
}

function t(key) {
  const val = TEXTS[lang][key];
  return typeof val === 'function' ? val : val;
}

/* ── Render ── */
function render() {
  const T = TEXTS[lang];

  // Navbar
  $('nav-links').innerHTML = T.nav.map((label, i) => {
    const ids = ['section-product', 'section-agents', 'nav-analyze', 'nav-login'];
    return `<a data-nav="${ids[i]}">${label}</a>`;
  }).join('');
  document.querySelectorAll('[data-nav]').forEach(a => {
    a.addEventListener('click', () => handleNav(a.dataset.nav));
  });

  // Lang buttons
  document.querySelectorAll('.lang-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.lang === lang);
  });

  // Hero
  $('eyebrow-text').textContent = T.eyebrow;
  $('hero-title').innerHTML = T.heroTitle.replace('\n', '<br>');
  $('hero-sub').textContent = T.heroSub;
  $('hero-sub-en').textContent = T.heroSubEn;
  $('hero-cta').textContent = T.heroCta;
  $('hero-more').textContent = T.heroMore;

  // Product section
  $('sec1-label').textContent = T.sec1Label;
  $('sec1-title').textContent = T.sec1Title;
  $('sec1-sub').textContent   = T.sec1Sub;
  $('step-cards').innerHTML = T.steps.map(s => `
    <div class="step-card">
      <div class="step-num">${s.num}</div>
      <h3>${s.title}</h3>
      <p>${s.desc}</p>
    </div>`).join('');

  // Agents section
  $('sec2-label').textContent = T.sec2Label;
  $('sec2-title').textContent = T.sec2Title;
  const agColors = [
    { dot:'#3B82F6', role:'rgba(59,130,246,.1)', roleText:'#3B82F6' },
    { dot:'#1EBF89', role:'rgba(30,191,137,.1)', roleText:'#1EBF89' },
    { dot:'#DF7F37', role:'rgba(223,127,55,.1)', roleText:'#DF7F37' },
    { dot:'#9159F2', role:'rgba(145,89,242,.1)', roleText:'#9159F2' },
  ];
  $('agent-flow').innerHTML = T.agents.map((ag, i) => {
    const c = agColors[i];
    const arrow = i < T.agents.length - 1
      ? `<div class="agent-arrow"></div>` : '';
    return `
      <div class="agent-card">
        <div class="agent-dot" style="background:${c.dot}"></div>
        <div class="agent-name">${ag.name}</div>
        <div class="agent-role" style="background:${c.role};color:${c.roleText}">${ag.role}</div>
        <div class="agent-desc">${ag.desc.replace(/\n/g,'<br>')}</div>
      </div>${arrow}`;
  }).join('');

  // Analyze form
  $('form-title').textContent     = T.formTitle;
  $('label-product').textContent  = T.labelProduct;
  $('input-product').placeholder  = T.placeholderProduct;
  $('label-query').textContent    = T.labelQuery;
  $('input-query').placeholder    = T.placeholderQuery;
  $('label-file').textContent     = T.labelFile;
  $('upload-main').textContent    = T.uploadMain;
  $('upload-sub').textContent     = T.uploadSub;
  $('submit-btn').textContent     = T.submitBtn;
  $('stream-title').textContent   = T.streamTitle;
  $('think-label').textContent    = T.thinkLabel + ' ';
  $('stream-placeholder').innerHTML = T.streamPlaceholder.replace(/\n/g,'<br>');

  // Result page
  $('result-title').textContent   = T.resultTitle;
  $('pdf-filename').textContent   = T.pdfFilename;
  $('pdf-download').textContent   = T.download;

  // Footer
  $('footer-brand').textContent   = T.footerBrand;
  $('footer-tagline').textContent = T.footerTagline;
  $('footer-cols').innerHTML = T.footerCols.map(col => `
    <div class="footer-col">
      <h4>${col.title}</h4>
      ${col.links.map(l => `<a href="#">${l}</a>`).join('')}
    </div>`).join('');
  $('footer-copy').textContent = T.copyright;
}

/* ── Navigation ── */
function handleNav(target) {
  if (target === 'nav-analyze') { showPage('analyze'); return; }
  if (target === 'nav-login')   { alert(lang === 'zh' ? '登录功能即将上线' : 'Login coming soon'); return; }
  showPage('home');
  setTimeout(() => {
    const el = document.getElementById(target);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, 50);
}

/* ── File upload ── */
function setupUpload() {
  const area    = $('upload-area');
  const input   = $('file-input');
  const info    = $('upload-file-info');
  const nameEl  = $('upload-file-name');
  const removeBtn = $('upload-file-remove');

  area.addEventListener('click', () => input.click());

  area.addEventListener('dragover', e => {
    e.preventDefault(); area.classList.add('drag-over');
  });
  area.addEventListener('dragleave', () => area.classList.remove('drag-over'));
  area.addEventListener('drop', e => {
    e.preventDefault(); area.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) setFile(file);
  });

  input.addEventListener('change', () => {
    if (input.files[0]) setFile(input.files[0]);
    input.value = '';
  });

  removeBtn.addEventListener('click', e => {
    e.stopPropagation();
    uploadedFile = null;
    info.classList.remove('show');
    area.style.display = 'block';
  });

  function setFile(file) {
    const allowed = ['application/pdf', 'application/msword',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'text/plain'];
    if (!allowed.includes(file.type) && !file.name.match(/\.(pdf|doc|docx|txt)$/i)) {
      alert(lang === 'zh' ? '仅支持 PDF、Word、TXT 格式' : 'Only PDF, Word, TXT supported');
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      alert(lang === 'zh' ? '文件不能超过 20MB' : 'File must be under 20MB');
      return;
    }
    uploadedFile = file;
    nameEl.textContent = file.name;
    info.classList.add('show');
    area.style.display = 'none';
  }
}

/* ── Streaming output ── */
function appendLog(agent, text, dim = false, color = null) {
  const body = $('log-body');
  const placeholder = body.querySelector('.log-placeholder');
  if (placeholder) placeholder.remove();

  const line = document.createElement('div');
  line.className = 'log-line';
  line.innerHTML = `
    <span class="log-agent" style="color:${color||'#8890B0'}">[${agent}]</span>
    <span class="log-text${dim?' dim':''}">${escHtml(text)}</span>`;
  body.appendChild(line);
  body.scrollTop = body.scrollHeight;
}

function escHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function setThink(show, elapsed = 0) {
  const badge = $('think-badge');
  badge.classList.toggle('show', show);
  if (show) $('think-time').textContent = elapsed > 0 ? ` 已用时 ${elapsed}s` : '';
}

function setProgress(pct, secLeft) {
  $('progress-fill').style.width = pct + '%';
  $('progress-label').textContent = TEXTS[lang].progressLabel(pct, secLeft);
}

/* ── Submit analysis ── */
async function submitAnalysis(e) {
  e.preventDefault();

  const product = $('input-product').value.trim();
  const query   = $('input-query').value.trim();

  if (!product) {
    $('input-product').focus();
    alert(lang === 'zh' ? '请输入目标产品名称' : 'Please enter a target product');
    return;
  }

  const btn = $('submit-btn');
  btn.disabled = true;

  // Clear log
  $('log-body').innerHTML = '';
  setThink(false);
  setProgress(0, 0);
  $('progress-label').textContent = '';

  const formData = new FormData();
  formData.append('target_product', product);
  formData.append('user_query', query || product);
  if (uploadedFile) formData.append('file', uploadedFile);

  try {
    // POST to backend
    const res = await fetch('/api/analyze', { method: 'POST', body: formData });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const { job_id } = await res.json();

    // Open SSE stream
    openStream(job_id, btn);
  } catch (err) {
    // Dev fallback: simulate streaming
    simulateStream(btn);
  }
}

function openStream(jobId, btn) {
  if (streamESS) streamESS.close();

  streamESS = new EventSource(`/api/stream/${jobId}`);
  let thinkStart = Date.now();
  let elapsed = 0;
  let thinkTimer;

  const agentColors = {
    'PM Agent': '#3B82F6', 'Collector': '#1EBF89',
    'Insight': '#DF7F37', 'Reporter': '#9159F2',
  };

  streamESS.onmessage = ev => {
    const msg = JSON.parse(ev.data);
    if (msg.type === 'thinking') {
      setThink(true, msg.elapsed || 0);
    } else if (msg.type === 'tool_call') {
      setThink(false);
      appendLog(msg.agent, `→ ${msg.tool}(${msg.args})`, true, agentColors[msg.agent]);
    } else if (msg.type === 'tool_result') {
      appendLog(msg.agent, `← ${msg.tool} (${msg.size}) ${msg.preview}`, true, agentColors[msg.agent]);
    } else if (msg.type === 'log') {
      appendLog(msg.agent, msg.text, false, agentColors[msg.agent]);
    } else if (msg.type === 'progress') {
      setProgress(msg.pct, msg.sec_left);
    } else if (msg.type === 'done') {
      streamESS.close();
      setThink(false);
      setProgress(100, 0);
      btn.disabled = false;
      if (msg.pdf_path) loadResult(msg.pdf_path);
    } else if (msg.type === 'error') {
      streamESS.close();
      setThink(false);
      btn.disabled = false;
      appendLog('Error', msg.message, false, '#ef4444');
    }
  };

  streamESS.onerror = () => { streamESS.close(); btn.disabled = false; };
}

/* Dev simulation (no backend) */
function simulateStream(btn) {
  const T = TEXTS[lang];
  const steps = [
    { d:400,  fn:()=>{ setThink(true,0); } },
    { d:1200, fn:()=>{ appendLog('PM Agent', lang==='zh'?'分析用户查询，制定竞品分析计划...':'Parsing user query, creating analysis plan...', false,'#3B82F6'); } },
    { d:800,  fn:()=>{ setThink(false); appendLog('PM Agent','→ initial_brief({...})',true,'#3B82F6'); setProgress(8,90); } },
    { d:1000, fn:()=>{ setThink(true,3); } },
    { d:600,  fn:()=>{ setThink(false); appendLog('Collector', lang==='zh'?'联网搜索竞品官网...':'Searching competitor websites...', false,'#1EBF89'); setProgress(18,78); } },
    { d:700,  fn:()=>{ appendLog('Collector','→ web_search({ query: "target pricing 2024" })',true,'#1EBF89'); } },
    { d:900,  fn:()=>{ appendLog('Collector','← web_search (2.1KB) pricing data fetched...',true,'#6870A0'); setProgress(30,62); } },
    { d:600,  fn:()=>{ appendLog('Collector', lang==='zh'?'采集竞品功能特性...':'Collecting feature details...', false,'#1EBF89'); } },
    { d:800,  fn:()=>{ appendLog('Collector','→ fetch_page({ url: "..." })',true,'#1EBF89'); setProgress(42,50); } },
    { d:700,  fn:()=>{ appendLog('Collector','← fetch_page (4.8KB) feature list extracted',true,'#6870A0'); } },
    { d:500,  fn:()=>{ setThink(true,12); } },
    { d:1000, fn:()=>{ setThink(false); appendLog('Insight', lang==='zh'?'App Store 情感分析，抓取用户评论...':'App Store sentiment analysis...', false,'#DF7F37'); setProgress(55,38); } },
    { d:700,  fn:()=>{ appendLog('Insight','→ appstore_search({ product: "...", region: "cn" })',true,'#DF7F37'); } },
    { d:900,  fn:()=>{ appendLog('Insight','← appstore_search (3.2KB) 320 reviews fetched',true,'#6870A0'); setProgress(68,26); } },
    { d:600,  fn:()=>{ appendLog('Insight', lang==='zh'?'BERT 情感分类完成，提炼正负面观点...':'BERT sentiment classification done...', false,'#DF7F37'); } },
    { d:800,  fn:()=>{ setProgress(78,18); appendLog('Reporter', lang==='zh'?'开始生成竞品分析报告...':'Generating competitive analysis report...', false,'#9159F2'); } },
    { d:700,  fn:()=>{ appendLog('Reporter','→ submit_dimension_ranking({...})',true,'#9159F2'); } },
    { d:800,  fn:()=>{ appendLog('Reporter','→ finalize_swot({...})',true,'#9159F2'); setProgress(88,8); } },
    { d:900,  fn:()=>{ appendLog('Reporter', lang==='zh'?'报告撰写完成，正在渲染 PDF...':'Report done, rendering PDF...', false,'#9159F2'); } },
    { d:1200, fn:()=>{ setProgress(100,0); setThink(false); btn.disabled=false; showResult(); } },
  ];

  let delay = 0;
  steps.forEach(s => {
    delay += s.d;
    setTimeout(s.fn, delay);
  });
}

function showResult() {
  showPage('result');
  // In real use, pdf_path from backend would be set here
  $('pdf-content').innerHTML = `
    <div class="pdf-placeholder">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
      </svg>
      <p>${lang==='zh'?'PDF 预览将在报告生成后显示':'PDF preview will appear after report generation'}</p>
      <p style="margin-top:8px;font-size:12px">${lang==='zh'?'（此为演示模式）':'(Demo mode)'}</p>
    </div>`;
}

function loadResult(pdfPath) {
  showPage('result');
  const url = `/api/report/pdf?path=${encodeURIComponent(pdfPath)}`;
  $('pdf-content').innerHTML = `<iframe src="${url}" title="PDF Report"></iframe>`;
  $('pdf-download').onclick = () => {
    const a = document.createElement('a');
    a.href = url + '&download=1';
    a.download = TEXTS[lang].pdfFilename;
    a.click();
  };
}

/* ── Boot ── */
function init() {
  render();
  setupUpload();

  // Language switch
  document.querySelectorAll('.lang-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      lang = btn.dataset.lang;
      render();
    });
  });

  // Logo → home
  document.querySelector('.logo').addEventListener('click', () => showPage('home'));

  // Hero CTAs
  $('hero-cta').addEventListener('click', () => showPage('analyze'));
  $('hero-more').addEventListener('click', () => {
    document.getElementById('section-product')
      .scrollIntoView({ behavior: 'smooth' });
  });

  // Analyze form
  $('analyze-form').addEventListener('submit', submitAnalysis);

  // PDF download (placeholder until result loaded)
  $('pdf-download').addEventListener('click', () => {
    alert(lang === 'zh' ? '报告尚未生成' : 'Report not yet generated');
  });

  // Back to analyze from result
  $('back-to-analyze').addEventListener('click', () => showPage('analyze'));
}

document.addEventListener('DOMContentLoaded', init);
