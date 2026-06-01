'use strict';

/* ══════════════════════════════════════
   i18n
══════════════════════════════════════ */
const I18N = {
  zh: {
    eyebrow:'AI 驱动的竞品分析平台', heroTitle:'开始你的<br>专属竞品分析',
    heroSub:'多智能体协同分析 · 自动生成专业竞品报告', heroSubEn:'Start your exclusive competitive analysis',
    heroCta:'立即开始分析', reportTitle:'竞品分析报告', reportFilename:'飞书竞品分析报告_2026.pdf', dlBtn:'下载 PDF',
    pLabel:'产品目标', pTitle:'全自动 AI 竞品分析，一键生成专业报告',
    pSub:'输入目标产品，上传参考文档，多智能体自动完成竞品采集、情感分析与报告撰写',
    s1Title:'输入 & 上传', s1Desc:'输入目标产品名 + 分析需求，可上传一份参考文档（PDF/Word）',
    s2Title:'多智能体分析', s2Desc:'PM 制定计划 → Collector 联网采集 → Insight 情感分析，全程流式输出',
    s3Title:'报告预览 & 下载', s3Desc:'在线预览 PDF 报告，包含 SWOT 分析、定价对比、竞品横向评分',
    aLabel:'智能体功能介绍', aTitle:'多智能体协同工作流',
    ag1Role:'制定计划', ag1Desc:'解析用户需求<br>制定任务简报<br>分配 Collect & Insight 任务',
    ag2Role:'联网采集', ag2Desc:'联网搜索竞品<br>采集定价 / 功能<br>ReAct 多轮探索',
    ag3Role:'情感分析', ag3Desc:'爬取用户评论<br>BERT 情感分类<br>提炼正负面观点',
    ag4Role:'报告生成', ag4Desc:'SWOT 分析<br>横向评分对比<br>输出 PDF 报告',
    navLinks:['首页','产品介绍','智能体','开始分析'], navLoginBtn:'登录',
    formTitle:'开始分析', lblProduct:'目标产品名称', phProduct:'例如：飞书、DingTalk、Slack',
    lblQuery:'分析需求描述', phQuery:'请描述您的分析需求，例如：分析飞书与钉钉、Slack 的视频会议功能差异...',
    upMain:'点击上传或拖拽文件至此处', upSub:'支持 PDF、Word、TXT，仅限 1 个文件，最大 20MB',
    submitBtn:'开始分析', navDlBtn:'报告生成与下载', optionalTag:'可选',
    lblFileText:'上传参考文档（最多 1 个文件）', streamTitle:'智能体运行日志', thinkText:'思考中...',
    logHintText:'点击「开始分析」后，智能体实时日志将在此处显示<br>您可以看到每个 Agent 的思考过程和工具调用',
    pdfTitle:'运行日志与报告下载', pdfFname:'竞品分析报告_飞书_2026.pdf', pdfDl:'↓  下载到本地',
    pdfEmpty:'完成分析后，PDF 报告将在此处预览',
    phase1Title:'第一阶段分析完成', phase1Skip:'跳过，继续生成', phase1Submit:'提交修改建议',
    phase1InputPh:'请输入您对分析结果的修改建议（可选）...',
    qaTitle:'向 Agent 提问', qaHint:'报告生成完成，您可以向 Agent 提问关于报告中的任何问题',
    qaInputPh:'输入您的问题...', qaSend:'发送',
    pdfPageInfo:(c,t)=>`第 ${c} / ${t} 页`, progress:(p,s)=>`分析进度 ${p}% · 预计剩余 ${s} 秒`,
    footerTagline:'AI 驱动的竞品分析平台', fc1Title:'产品', fc2Title:'支持',
    footerCopy:'© 2026 Dreamcode · 保留所有权利',
    errNoProduct:'请输入目标产品名称', errFiletype:'仅支持 PDF、Word、TXT 格式',
    errFilesize:'文件不能超过 20MB', loginMsg:'登录功能即将上线',
    galleryLabel:'报告样本展示', galleryHint:'点击圆点或箭头切换图表',
    // Modal
    modalTitle:'选择接入方式', modalSub:'选择一种方式以启动本次分析', modalNext:'下一步 →',
    optKeyTitle:'自行配置 API Key', optKeyDesc:'使用自己的 Key，数据更安全<br>支持跨模型协作，报告质量更优',
    optPayTitle:'购买单次报告', optPayDesc:'无需配置，即买即用<br>我们代为调用，服务更稳定',
    modalKeyTitle:'配置 API Key', aiKeysTitle:'AI 模型 API Keys',
    aiKeysDesc:'支持 OpenAI / DeepSeek / Doubao 等兼容协议的模型。<br>多个来自不同厂商的 Key 可跨模型协作，显著提升报告客观性。',
    tavilyTitle:'Tavily Search API Key', requiredTag:'必填',
    tavilyDesc:'用于联网采集竞品信息、用户评论等数据。<br>申请地址：<a href="https://app.tavily.com" target="_blank">app.tavily.com</a>（免费额度足够基础使用）',
    modalSubmitBtn:'开始分析', modalPayTitle:'购买报告',
    payDesc:'单次竞品分析报告', payWechat:'微信支付', payAlipay:'支付宝支付',
    payF1:'✓ 完整竞品分析报告 1 份，含 SWOT、定价对比、维度评分',
    payF2:'✓ 多模型协作生成，减少单一模型自我偏好',
    payF3:'✓ 支持 PDF 下载，分析周期约 3–5 分钟',
    payNote:'实际 API 调用成本约 ¥10，定价 ¥15 含服务费',
    keyWarn:'仅配置 1 个槽位时，模型可能对自家产品存在自我偏好风险，建议至少填写 2 个来自不同厂商的 Key。',
  },
  en: {
    eyebrow:'AI-powered Competitive Analysis', heroTitle:'Your Exclusive<br>Competitor Analysis',
    heroSub:'Multi-agent AI · Auto-generate professional reports', heroSubEn:'开始你的专属竞品分析',
    heroCta:'Start Analysis', reportTitle:'Competitive Analysis Report',
    reportFilename:'feishu_analysis_2026.pdf', dlBtn:'Download PDF',
    pLabel:'Product Goals', pTitle:'Full-auto AI Competitive Analysis',
    pSub:'Enter a product, upload a doc — multi-agent system handles collection, sentiment, and report writing',
    s1Title:'Input & Upload', s1Desc:'Enter the target product and request. Optionally upload one reference doc (PDF/Word).',
    s2Title:'Multi-agent Analysis', s2Desc:'PM plans → Collector scrapes → Insight analyses sentiment. Full streaming output.',
    s3Title:'Preview & Download', s3Desc:'Preview the PDF in-browser. Includes SWOT, pricing comparison, cross-product scoring.',
    aLabel:'Agent Features', aTitle:'Multi-agent Collaboration',
    ag1Role:'Planning', ag1Desc:'Parses user needs<br>Creates task briefs<br>Assigns Collect & Insight tasks',
    ag2Role:'Scraping', ag2Desc:'Web searches competitors<br>Collects pricing & features<br>ReAct multi-round',
    ag3Role:'Sentiment', ag3Desc:'Crawls user reviews<br>BERT sentiment analysis<br>Extracts themes',
    ag4Role:'Report Gen', ag4Desc:'SWOT analysis<br>Cross-product scoring<br>Outputs PDF report',
    navLinks:['Home','Product','Agents','Analyze'], navLoginBtn:'Login',
    formTitle:'Start Analysis', lblProduct:'Target Product', phProduct:'e.g. Feishu, DingTalk, Slack',
    lblQuery:'Analysis Request', phQuery:'Describe needs, e.g. Compare video conferencing between Feishu and DingTalk...',
    upMain:'Click to upload or drag file here', upSub:'PDF, Word, TXT · 1 file max · 20 MB limit',
    submitBtn:'Start Analysis', navDlBtn:'Report Generation', optionalTag:'Optional',
    lblFileText:'Upload Reference Document (max 1 file)', streamTitle:'Agent Run Log', thinkText:'Thinking...',
    logHintText:'Agent logs will stream here after you click Start Analysis.',
    pdfTitle:'Logs & Report Download', pdfFname:'competitive_analysis_2026.pdf', pdfDl:'↓  Download',
    pdfEmpty:'PDF report will appear here after analysis.',
    phase1Title:'Phase 1 Analysis Done', phase1Skip:'Skip, continue generation', phase1Submit:'Submit feedback',
    phase1InputPh:'Enter your feedback on the analysis (optional)...',
    qaTitle:'Ask the Agent', qaHint:'Report ready. Ask the Agent any question about the report.',
    qaInputPh:'Ask a question...', qaSend:'Send',
    pdfPageInfo:(c,t)=>`Page ${c} of ${t}`, progress:(p,s)=>`Progress ${p}% · ~${s}s`,
    footerTagline:'AI-powered Competitive Analysis', fc1Title:'Product', fc2Title:'Support',
    footerCopy:'© 2026 Dreamcode · All rights reserved',
    errNoProduct:'Please enter a target product name', errFiletype:'Only PDF, Word, TXT supported',
    errFilesize:'File must be under 20 MB', loginMsg:'Login coming soon',
    galleryLabel:'Report Samples', galleryHint:'Click dots or arrows to switch charts',
    // Modal
    modalTitle:'API Access Method', modalSub:'Choose how to power this analysis', modalNext:'Next →',
    optKeyTitle:'Configure API Keys', optKeyDesc:'Use your own keys — data stays private<br>Multi-model collaboration improves report quality',
    optPayTitle:'Buy Report', optPayDesc:'No setup needed, ready instantly<br>We handle the API calls for you',
    modalKeyTitle:'Configure API Keys', aiKeysTitle:'AI Model API Keys',
    aiKeysDesc:'Supports OpenAI / DeepSeek / Doubao and compatible providers.<br>Multiple keys from different providers reduce self-preference bias.',
    tavilyTitle:'Tavily Search API Key', requiredTag:'Required',
    tavilyDesc:'Used to fetch competitor info and user reviews from the web.<br>Get your key at: <a href="https://app.tavily.com" target="_blank">app.tavily.com</a>',
    modalSubmitBtn:'Start Analysis', modalPayTitle:'Purchase Report',
    payDesc:'One-time competitive analysis report', payWechat:'WeChat Pay', payAlipay:'Alipay',
    payF1:'✓ Full report with SWOT, pricing comparison, scoring',
    payF2:'✓ Multi-model collaboration reduces self-preference bias',
    payF3:'✓ PDF download, analysis takes ~3–5 minutes',
    payNote:'Estimated API cost ~¥10; ¥15 price includes service fee',
    keyWarn:'With only 1 slot configured, the model may show self-preference bias. Using 2+ keys from different providers improves objectivity.',
  },
};

/* ── Scroll track content ── */
const SCROLL_I18N = {
  zh:{
    pageTitle:'竞品分析报告',
    chips:[{cls:'chip-teal',label:'飞书'},{cls:'chip-green',label:'钉钉'},{cls:'chip-orange',label:'Slack'}],
    swotTitle:'SWOT 分析',
    swot:[
      {type:'rs-strength',text:'即时通讯功能完备，生态整合度高'},
      {type:'rs-strength',text:'视频会议支持超大规模会议室'},
      {type:'rs-weakness',text:'定价偏高，中小企业渗透率受限'},
      {type:'rs-opportunity',text:'企业数字化转型加速，需求扩大'},
      {type:'rs-threat',text:'国际竞品具备明显价格优势'},
    ],
    pricingTitle:'定价对比',
    pricing:[
      {name:'飞书 商业版',pct:55,color:'#40c4d0',value:'¥15/月'},
      {name:'钉钉 专业版',pct:44,color:'#49bf8a',value:'¥12/月'},
      {name:'Slack Pro',pct:72,color:'#df7f37',value:'$7.25/月'},
    ],
    featureTitle:'功能评分', sentimentTitle:'用户情感分析', summaryTitle:'报告摘要',
    sentiment:[{name:'飞书',pct:78,colors:'#40c4d0,#2ca8b3'},{name:'钉钉',pct:71,colors:'#49bf8a,#1eab7a'},{name:'Slack',pct:84,colors:'#df7f37,#c46a25'}],
  },
  en:{
    pageTitle:'Competitive Analysis Report',
    chips:[{cls:'chip-teal',label:'Feishu'},{cls:'chip-green',label:'DingTalk'},{cls:'chip-orange',label:'Slack'}],
    swotTitle:'SWOT Analysis',
    swot:[
      {type:'rs-strength',text:'Comprehensive messaging, high ecosystem integration'},
      {type:'rs-strength',text:'Video conferencing for large-scale rooms'},
      {type:'rs-weakness',text:'High pricing, limited SME penetration'},
      {type:'rs-opportunity',text:'Enterprise digital transformation drives demand'},
      {type:'rs-threat',text:'International competitors hold significant price edge'},
    ],
    pricingTitle:'Pricing Comparison',
    pricing:[
      {name:'Feishu Business',pct:55,color:'#40c4d0',value:'¥15/mo'},
      {name:'DingTalk Pro',pct:44,color:'#49bf8a',value:'¥12/mo'},
      {name:'Slack Pro',pct:72,color:'#df7f37',value:'$7.25/mo'},
    ],
    featureTitle:'Feature Scores', sentimentTitle:'User Sentiment', summaryTitle:'Report Summary',
    sentiment:[{name:'Feishu',pct:78,colors:'#40c4d0,#2ca8b3'},{name:'DingTalk',pct:71,colors:'#49bf8a,#1eab7a'},{name:'Slack',pct:84,colors:'#df7f37,#c46a25'}],
  },
};

function buildScrollContent(l) {
  const t = SCROLL_I18N[l];
  const chips = t.chips.map(c=>`<span class="chip ${c.cls}">${c.label}</span>`).join('');
  const swot = t.swot.map(s=>`<div class="rs-row"><div class="rs-dot ${s.type}"></div><span class="rs-text">${s.text}</span></div>`).join('');
  const price = t.pricing.map(p=>`<div class="rs-price-row"><span class="rs-price-name" style="color:${p.color}">${p.name}</span><div class="rs-price-bar-wrap"><div class="rs-price-bar" style="width:${p.pct}%;background:${p.color}"></div></div><span class="rs-price-val">${p.value}</span></div>`).join('');
  const sent = t.sentiment.map(s=>`<div class="rs-sentiment-row"><span class="rs-s-name" style="color:${s.colors.split(',')[0]}">${s.name}</span><div class="rs-s-bar-wrap"><div class="rs-s-bar" style="width:${s.pct}%;background:linear-gradient(90deg,${s.colors})"></div></div><span class="rs-s-pct">${s.pct}%</span></div>`).join('');
  return `<div class="rs-page-header"><span class="rs-page-title">${t.pageTitle}</span><span class="rs-page-date">2026-05</span></div><div class="rs-chip-row">${chips}</div><div class="rs-section"><div class="rs-section-hd">${t.swotTitle}</div>${swot}</div><div class="rs-divider"></div><div class="rs-section"><div class="rs-section-hd">${t.pricingTitle}</div>${price}</div><div class="rs-divider"></div><div class="rs-section"><div class="rs-section-hd">${t.featureTitle}</div><div class="mini-chart"><div class="bar-grp"><div class="bar" style="height:58px;background:#40c4d0"></div><div class="bar" style="height:46px;background:#49bf8a"></div><div class="bar" style="height:52px;background:#df7f37"></div></div><div class="bar-grp"><div class="bar" style="height:46px;background:#40c4d0"></div><div class="bar" style="height:58px;background:#49bf8a"></div><div class="bar" style="height:40px;background:#df7f37"></div></div><div class="bar-grp"><div class="bar" style="height:52px;background:#40c4d0"></div><div class="bar" style="height:46px;background:#49bf8a"></div><div class="bar" style="height:60px;background:#df7f37"></div></div><div class="bar-grp"><div class="bar" style="height:40px;background:#40c4d0"></div><div class="bar" style="height:58px;background:#49bf8a"></div><div class="bar" style="height:36px;background:#df7f37"></div></div></div></div><div class="rs-divider"></div><div class="rs-section"><div class="rs-section-hd">${t.sentimentTitle}</div>${sent}</div><div class="rs-divider"></div><div class="rs-section"><div class="rs-section-hd">${t.summaryTitle}</div><div class="summary-lines"><div class="summary-line" style="width:100%"></div><div class="summary-line" style="width:90%"></div><div class="summary-line" style="width:80%"></div><div class="summary-line" style="width:86%"></div><div class="summary-line" style="width:64%"></div></div></div><div class="rs-spacer"></div>`;
}

/* ══════════════════════════════════════
   State
══════════════════════════════════════ */
let lang = 'zh';
let uploadedFile = null;
let pdfPath = null;
let eventSource = null;
let navJumping   = false;
let lastWheelTime = 0;        // timestamp-based cooldown — replaces scrollLocked
let currentSnapIdx = 0;       // authoritative section tracker
let heroScrollTl = null;
let galleryIdx = 0;
let apiOption = 'key';
const GALLERY_TOTAL = 4;
let particleRafId = null;
let currentJobId = null;
let isSimulateMode = false;
let simBtn = null;
let simProduct = '';
let analysisStartTime = 0;
let timerInterval = null;

/* ══════════════════════════════════════
   Helpers
══════════════════════════════════════ */
function $(id){ return document.getElementById(id); }
function T(k){ return I18N[lang][k]; }
const SECTION_NAV_MAP = { hero:0, product:1, gallery:1, agents:2, analyze:3, 'pdf-section':4 };

function updateNavActive(id){
  const idx = SECTION_NAV_MAP[id];
  document.querySelectorAll('.nav-links a').forEach((a,i)=>a.classList.toggle('active',i===idx));
}
function triggerSnapIn(el){
  el.classList.remove('snap-in'); void el.offsetHeight; el.classList.add('snap-in');
}

function jumpTo(id){
  const el = document.getElementById(id);
  if(!el) return false;
  const veil = $('page-veil');
  const html = document.documentElement;
  updateNavActive(id);
  navJumping = true;
  veil.classList.add('visible');
  // Sync section index so wheel handler stays coherent
  const els = getSnapElements();
  const idx = els.findIndex(e=>e.id===id || e===el);
  if(idx>=0) currentSnapIdx = idx;
  if(id==='gallery'){ galleryIdx=0; _resetGalleryToFirst(); }
  setTimeout(()=>{
    html.style.setProperty('scroll-snap-type','none');
    el.scrollIntoView({block:'start',behavior:'instant'});
    requestAnimationFrame(()=>requestAnimationFrame(()=>{
      html.style.setProperty('scroll-behavior','auto');
      html.style.removeProperty('scroll-snap-type');
      requestAnimationFrame(()=>html.style.removeProperty('scroll-behavior'));
      veil.classList.remove('visible');
      triggerSnapIn(el);
    }));
    setTimeout(()=>{ navJumping=false; },1200);
  },650);
  return false;
}
function handleLogin(){ alert(T('loginMsg')); }
function downloadPdf(){
  if(!pdfPath){ alert(T('pdfEmpty')); return; }
  const a = document.createElement('a');
  a.href=`/api/report/pdf?path=${encodeURIComponent(pdfPath)}&download=1`;
  a.download=T('pdfFname'); a.click();
}

/* ══════════════════════════════════════
   Theme
══════════════════════════════════════ */
function toggleTheme(){
  const html = document.documentElement;
  const next = (html.getAttribute('data-theme')||'dark')==='dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  localStorage.setItem('dc-theme', next);
}
function initTheme(){
  document.documentElement.setAttribute('data-theme', localStorage.getItem('dc-theme')||'dark');
}

/* ══════════════════════════════════════
   i18n
══════════════════════════════════════ */
function applyLang(){
  const t = I18N[lang];
  document.querySelectorAll('.lang-btn').forEach(b=>b.classList.toggle('active',b.dataset.lang===lang));
  document.querySelectorAll('.nav-links a').forEach((a,i)=>{ if(t.navLinks[i]) a.textContent=t.navLinks[i]; });
  const set=(id,v)=>{ const e=$(id); if(e) e.textContent=v; };
  const setH=(id,v)=>{ const e=$(id); if(e) e.innerHTML=v; };
  const setA=(id,k,v)=>{ const e=$(id); if(e) e[k]=v; };

  set('t-nav-login',t.navLoginBtn); set('t-eyebrow',t.eyebrow);
  setH('t-hero-title',t.heroTitle); set('t-hero-sub',t.heroSub);
  set('t-hero-sub-en',t.heroSubEn); set('t-hero-cta',t.heroCta);
  set('t-report-title',t.reportTitle); set('t-report-filename',t.reportFilename); set('t-dl-btn',t.dlBtn);
  set('t-p-label',t.pLabel); set('t-p-title',t.pTitle); set('t-p-sub',t.pSub);
  set('t-s1-title',t.s1Title); set('t-s1-desc',t.s1Desc);
  set('t-s2-title',t.s2Title); set('t-s2-desc',t.s2Desc);
  set('t-s3-title',t.s3Title); set('t-s3-desc',t.s3Desc);
  set('t-gallery-label',t.galleryLabel); set('gallery-hint',t.galleryHint);
  set('t-a-label',t.aLabel); set('t-a-title',t.aTitle);
  set('t-ag1-role',t.ag1Role); setH('t-ag1-desc',t.ag1Desc);
  set('t-ag2-role',t.ag2Role); setH('t-ag2-desc',t.ag2Desc);
  set('t-ag3-role',t.ag3Role); setH('t-ag3-desc',t.ag3Desc);
  set('t-ag4-role',t.ag4Role); setH('t-ag4-desc',t.ag4Desc);
  set('t-form-title',t.formTitle); set('t-lbl-product',t.lblProduct);
  setA('input-product','placeholder',t.phProduct); set('t-lbl-query',t.lblQuery);
  setA('input-query','placeholder',t.phQuery); set('t-up-main',t.upMain);
  set('t-up-sub',t.upSub); set('submit-btn',t.submitBtn);
  set('t-stream-title',t.streamTitle); set('think-text',t.thinkText);
  setH('t-log-hint-text',t.logHintText); set('t-nav-dl',t.navDlBtn);
  set('t-optional1',t.optionalTag); set('t-optional2',t.optionalTag);
  set('t-lbl-file-text',t.lblFileText);
  set('t-pdf-title',t.pdfTitle); set('pdf-fname',t.pdfFname);
  set('pdf-dl-btn',t.pdfDl); set('t-pdf-empty',t.pdfEmpty);
  set('t-phase1-title',t.phase1Title); set('t-phase1-skip',t.phase1Skip);
  set('t-phase1-submit',t.phase1Submit); setA('phase1-input','placeholder',t.phase1InputPh);
  set('t-qa-title',t.qaTitle); set('t-qa-hint',t.qaHint);
  setA('qa-input','placeholder',t.qaInputPh); set('t-qa-send',t.qaSend);
  set('t-footer-tagline',t.footerTagline);
  set('t-fc1-title',t.fc1Title); set('t-fc2-title',t.fc2Title);
  set('t-footer-copy',t.footerCopy);

  // Modal translations
  set('t-modal-title',t.modalTitle); set('t-modal-sub',t.modalSub); set('t-modal-next',t.modalNext);
  set('t-opt-key-title',t.optKeyTitle); setH('t-opt-key-desc',t.optKeyDesc);
  set('t-opt-pay-title',t.optPayTitle); setH('t-opt-pay-desc',t.optPayDesc);
  set('t-modal-key-title',t.modalKeyTitle); set('t-ai-keys-title',t.aiKeysTitle);
  setH('t-ai-keys-desc',t.aiKeysDesc); set('t-tavily-title',t.tavilyTitle);
  set('t-required-tag',t.requiredTag); setH('t-tavily-desc',t.tavilyDesc);
  set('t-modal-submit-btn',t.modalSubmitBtn); set('t-modal-pay-title',t.modalPayTitle);
  set('t-pay-desc',t.payDesc); set('t-pay-wechat',t.payWechat); set('t-pay-alipay',t.payAlipay);
  set('t-pay-f1',t.payF1); set('t-pay-f2',t.payF2); set('t-pay-f3',t.payF3);
  set('t-pay-note',t.payNote);
  // Update dynamic warn text
  const warnEl=$('api-warn'); if(warnEl) warnEl.textContent=t.keyWarn;
}
function setLang(l){
  lang=l; applyLang(); renderScrollTrack();
  // Rebuild gallery charts in the new language
  const vp=document.querySelector('.gallery-viewport');
  if(vp) initGallery();
}

/* ══════════════════════════════════════
   File upload
══════════════════════════════════════ */
function initUpload(){
  const area=$('upload-area'), input=$('file-input'), info=$('file-info'),
        nameEl=$('file-name-text'), rm=$('file-remove');
  area.addEventListener('click',()=>input.click());
  area.addEventListener('dragover',e=>{ e.preventDefault(); area.classList.add('drag-over'); });
  area.addEventListener('dragleave',()=>area.classList.remove('drag-over'));
  area.addEventListener('drop',e=>{ e.preventDefault(); area.classList.remove('drag-over'); const f=e.dataTransfer.files[0]; if(f) setFile(f); });
  input.addEventListener('change',()=>{ if(input.files[0]) setFile(input.files[0]); input.value=''; });
  rm.addEventListener('click',e=>{ e.stopPropagation(); uploadedFile=null; info.classList.remove('show'); area.style.display=''; });
  function setFile(f){
    if(!f.name.match(/\.(pdf|doc|docx|txt)$/i)){ alert(T('errFiletype')); return; }
    if(f.size>20*1024*1024){ alert(T('errFilesize')); return; }
    uploadedFile=f; nameEl.textContent=f.name; info.classList.add('show'); area.style.display='none';
  }
}

/* ══════════════════════════════════════
   GSAP — Hero scroll animation
══════════════════════════════════════ */
function renderScrollTrack(){
  const track = $('report-scroll-track');
  if(!track) return;
  if(typeof gsap!=='undefined' && heroScrollTl){ heroScrollTl.kill(); gsap.set(track,{y:0}); }
  const single = buildScrollContent(lang);
  track.innerHTML = single + single;
  if(typeof gsap==='undefined') return;
  requestAnimationFrame(()=>{
    const h = track.scrollHeight / 2;
    heroScrollTl = gsap.timeline({repeat:-1});
    heroScrollTl.to(track,{y:-h,duration:22,ease:'none'});
    heroScrollTl.set(track,{y:0});
  });
}

/* ══════════════════════════════════════
   GSAP — Global particle galaxy (fixed canvas, all pages)
══════════════════════════════════════ */
function initParticles(){
  const canvas = document.getElementById('bg-particles');
  if(!canvas || typeof gsap==='undefined') return;
  const ctx = canvas.getContext('2d');
  let W, H, particles=[];

  function gauss(std){
    const u=Math.random(), v=Math.random();
    return std * Math.sqrt(-2*Math.log(u||1e-9)) * Math.cos(2*Math.PI*v);
  }

  /* Main galaxy band: S-curved diagonal crossing the full viewport */
  function bandCenter(t){
    return [
      t * W,
      H*0.82 - t*H*0.65 + Math.sin(t*Math.PI*1.1)*H*0.08,
    ];
  }
  function bandNormal(t){
    const dt=0.01;
    const [x1,y1]=bandCenter(Math.max(0,t-dt));
    const [x2,y2]=bandCenter(Math.min(1,t+dt));
    const dx=x2-x1, dy=y2-y1, len=Math.sqrt(dx*dx+dy*dy)||1;
    return [-dy/len, dx/len];
  }

  function buildParticles(){
    particles=[];
    const N=820;
    for(let i=0;i<N;i++){
      const t=Math.random();
      const [cx,cy]=bandCenter(t);
      const [nx,ny]=bandNormal(t);
      const spread=gauss(H*0.09);
      const z=Math.random();
      const r=Math.random();
      let baseR,baseG,baseB;
      if(r<0.50){       baseR=195+Math.floor(Math.random()*60); baseG=205+Math.floor(Math.random()*50); baseB=255; }
      else if(r<0.78){  baseR=64;  baseG=196; baseB=208; }
      else if(r<0.92){  baseR=146; baseG=89;  baseB=242; }
      else{              baseR=255; baseG=168; baseB=80;  }

      // 12% are "hyper-blink" — sharp, high-frequency flash
      const hyperBlink = Math.random() < 0.12;
      particles.push({
        x:  cx + nx*spread,
        baseY: cy + ny*spread,
        yOffset: 0,
        size: hyperBlink ? 0.8+z*1.8 : 0.4+z*2.8,
        opacity: 0.12 + z*0.88,
        r:baseR, g:baseG, b:baseB,
        tp: Math.random()*Math.PI*2,
        // hyper-blink particles (slightly slower than before)
        ts: hyperBlink ? 2.2+Math.random()*2.5 : 0.5+Math.random()*1.6,
        hyper: hyperBlink,
      });
    }
  }

  function resize(){
    W = canvas.width  = window.innerWidth;
    H = canvas.height = window.innerHeight;
    buildParticles();
  }

  function render(time){
    requestAnimationFrame(render);
    ctx.clearRect(0,0,W,H);
    const t = time * 0.0013; // base time — slightly slower than before
    particles.forEach(p=>{
      let tw;
      if(p.hyper){
        // Sharp sawtooth-like blink: squares a sine to make bright peaks narrow, dark valleys wide
        const raw = Math.sin(t * p.ts + p.tp);
        tw = 0.05 + 0.95 * raw * raw;
      } else {
        // Normal gentle twinkle but faster and higher contrast than before
        tw = 0.18 + 0.82 * Math.abs(Math.sin(t * p.ts + p.tp));
      }
      const alpha = p.opacity * tw;
      ctx.beginPath();
      ctx.arc(p.x, p.baseY + p.yOffset, p.size, 0, Math.PI*2);
      ctx.fillStyle = `rgba(${p.r},${p.g},${p.b},${alpha.toFixed(3)})`;
      ctx.fill();
    });
  }

  resize();
  window.addEventListener('resize', resize);
  requestAnimationFrame(render);

  // GSAP wave: mouse moves anywhere on the page ripples the stars
  document.addEventListener('mousemove', e=>{
    const mx=e.clientX, my=e.clientY;
    particles.forEach(p=>{
      const dx=p.x-mx, dy=(p.baseY+p.yOffset)-my;
      const dist=Math.sqrt(dx*dx+dy*dy);
      if(dist<150){
        const strength=(1-dist/150)**2 * 32;
        gsap.to(p,{
          yOffset:-strength, duration:0.3, ease:'power2.out', overwrite:'auto',
          onComplete(){ gsap.to(p,{yOffset:0,duration:1.2,ease:'elastic.out(1,0.35)',overwrite:'auto'}); }
        });
      }
    });
  });
}

/* ══════════════════════════════════════
   GSAP — Gallery charts (redesigned)
══════════════════════════════════════ */

/* ── Chart 1: Word Cloud — office-domain sentiment words ── */
function buildWordCloudSVG(l='zh'){
  const W=560, H=300;
  const zh=l==='zh';

  // Positive words
  const pos= zh ? [
    {x:196,y:102,s:44,t:'高效',   c:'#40c4d0'},
    {x:95, y:86, s:32,t:'协作',   c:'#49bf8a'},
    {x:322,y:82, s:30,t:'智能',   c:'#3dd68c'},
    {x:160,y:146,s:24,t:'流畅',   c:'#40c4d0'},
    {x:294,y:154,s:22,t:'便捷',   c:'#2ec4b6'},
    {x:50, y:124,s:20,t:'稳定',   c:'#4ecdc4'},
    {x:400,y:132,s:20,t:'安全',   c:'#40c4d0'},
    {x:350,y:184,s:18,t:'创新',   c:'#49bf8a'},
    {x:78, y:178,s:18,t:'专业',   c:'#3dd68c'},
    {x:226,y:196,s:16,t:'快速',   c:'#40c4d0'},
    {x:430,y:170,s:16,t:'清晰',   c:'#4ecdc4'},
    {x:148,y:220,s:15,t:'实用',   c:'#49bf8a'},
    {x:304,y:228,s:14,t:'易上手', c:'#3dd68c'},
    {x:400,y:218,s:14,t:'跨平台', c:'#40c4d0'},
    {x:40, y:216,s:14,t:'响应快', c:'#4ecdc4'},
    {x:108,y:254,s:13,t:'界面优雅',c:'#2ec4b6'},
    {x:270,y:260,s:12,t:'集成性强',c:'#40c4d0'},
    {x:400,y:258,s:12,t:'生态完善',c:'#3dd68c'},
    {x:200,y:254,s:12,t:'通话清晰',c:'#49bf8a'},
  ] : [
    // English positive words
    {x:196,y:100,s:40,t:'Efficient',   c:'#40c4d0'},
    {x:84, y:84, s:28,t:'Seamless',   c:'#49bf8a'},
    {x:326,y:80, s:26,t:'Intelligent',c:'#3dd68c'},
    {x:158,y:144,s:22,t:'Intuitive',  c:'#40c4d0'},
    {x:298,y:152,s:20,t:'Reliable',   c:'#2ec4b6'},
    {x:44, y:124,s:18,t:'Agile',      c:'#4ecdc4'},
    {x:402,y:130,s:18,t:'Secure',     c:'#40c4d0'},
    {x:354,y:182,s:16,t:'Innovative', c:'#49bf8a'},
    {x:72, y:178,s:16,t:'Pro-grade',  c:'#3dd68c'},
    {x:234,y:196,s:20,t:'Fast',       c:'#40c4d0'},
    {x:432,y:166,s:16,t:'Crisp',      c:'#4ecdc4'},
    {x:142,y:218,s:15,t:'Flexible',   c:'#49bf8a'},
    {x:302,y:226,s:18,t:'Easy',       c:'#3dd68c'},
    {x:402,y:214,s:14,t:'Robust',     c:'#40c4d0'},
    {x:36, y:214,s:14,t:'Responsive', c:'#4ecdc4'},
    {x:104,y:252,s:13,t:'Polished UI',c:'#2ec4b6'},
    {x:274,y:258,s:12,t:'Integrated', c:'#40c4d0'},
    {x:406,y:256,s:12,t:'Ecosystem',  c:'#3dd68c'},
    {x:198,y:252,s:12,t:'HD calls',   c:'#49bf8a'},
  ];

  const neg= zh ? [
    {x:466,y:86, s:22,t:'卡顿',   c:'#df7f37'},
    {x:488,y:124,s:18,t:'收费高', c:'#e07050'},
    {x:464,y:162,s:16,t:'崩溃',   c:'#df7f37'},
    {x:452,y:200,s:15,t:'占内存', c:'#c8692a'},
    {x:470,y:238,s:14,t:'广告多', c:'#df7f37'},
    {x:372,y:266,s:13,t:'更新频繁',c:'#c8692a'},
    {x:216,y:274,s:14,t:'隐私问题',c:'#e07050'},
    {x:46, y:266,s:16,t:'难用',   c:'#df7f37'},
    {x:136,y:274,s:15,t:'复杂',   c:'#c8692a'},
    {x:22, y:244,s:18,t:'慢',     c:'#e07050'},
  ] : [
    // English negative words
    {x:466,y:86, s:22,t:'Laggy',     c:'#df7f37'},
    {x:488,y:124,s:18,t:'Pricey',    c:'#e07050'},
    {x:464,y:162,s:16,t:'Buggy',     c:'#df7f37'},
    {x:452,y:200,s:15,t:'Bloated',   c:'#c8692a'},
    {x:470,y:238,s:14,t:'Ad-heavy',  c:'#df7f37'},
    {x:366,y:268,s:13,t:'Frequent updates',c:'#c8692a'},
    {x:210,y:274,s:13,t:'Privacy concerns',c:'#e07050'},
    {x:40, y:266,s:16,t:'Hard',      c:'#df7f37'},
    {x:134,y:272,s:15,t:'Confusing', c:'#c8692a'},
    {x:20, y:244,s:18,t:'Slow',      c:'#e07050'},
  ];

  let s=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg"><defs>
    <radialGradient id="wc-glow" cx="36%" cy="40%" r="52%">
      <stop offset="0%" stop-color="rgba(64,196,208,.07)"/>
      <stop offset="100%" stop-color="transparent"/>
    </radialGradient>
  </defs>
  <ellipse cx="196" cy="158" rx="210" ry="135" fill="url(#wc-glow)"/>`;

  // Subtle vertical divider
  s+=`<line x1="442" y1="50" x2="442" y2="${H-38}" stroke="rgba(255,255,255,.06)" stroke-width="1" stroke-dasharray="3,5"/>`;

  const word=(w,isPos)=>`<text class="wc-word"
      x="${w.x}" y="${w.y}" text-anchor="middle"
      font-size="${w.s}"
      fill="${w.c}"
      font-weight="${w.s>=30?700:w.s>=20?600:500}"
      font-family="'PingFang SC','Microsoft YaHei',Inter,sans-serif"
      opacity="${isPos?0.82:0.76}">${w.t}</text>`;

  pos.forEach(w=>{ s+=word(w,true);  });
  neg.forEach(w=>{ s+=word(w,false); });

  // Legend
  const posLabel=zh?'正面词汇':'Positive', negLabel=zh?'负面词汇':'Negative';
  s+=`<circle cx="18" cy="15" r="5" fill="#40c4d0"/>
  <text x="28" y="20" font-size="11" fill="rgba(255,255,255,.58)" font-family="Inter">${posLabel}</text>
  <circle cx="${zh?106:112}" cy="15" r="5" fill="#df7f37"/>
  <text x="${zh?116:122}" y="20" font-size="11" fill="rgba(255,255,255,.58)" font-family="Inter">${negLabel}</text>`;

  return s+'</svg>';
}

/* ── Chart 2: Smoothed Area + Line — MAU 增长指数 ── */
function buildLineChartSVG(l='zh'){
  const zh=l==='zh';
  const W=560,H=330, mx=54,my=18,mxr=12,myb=52;
  const cw=W-mx-mxr, ch=H-my-myb;
  // Index base=100, Jan–Dec 2025
  const prodNames = zh ? ['飞书','钉钉','Slack'] : ['Feishu','DingTalk','Slack'];
  const raw={};
  raw[prodNames[0]]=[100,106,112,119,127,135,143,152,161,170,181,192];
  raw[prodNames[1]]=[100,101,102,103,104,104,105,106,106,107,108,108];
  raw[prodNames[2]]=[100,103,101,106,110,113,116,118,122,120,125,128];
  const colors=['#40c4d0','#49bf8a','#df7f37'];
  const prods=Object.keys(raw);
  const allVals=Object.values(raw).flat();
  const vMin=90, vMax=200;
  const months=['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'];
  const N=12;

  function pt(i,v){
    return [mx+(i/(N-1))*cw, my+ch-((v-vMin)/(vMax-vMin))*ch];
  }
  function smoothPath(vals){
    const pts=vals.map((v,i)=>pt(i,v));
    return pts.map(([x,y],i)=>{
      if(i===0) return `M${x.toFixed(1)},${y.toFixed(1)}`;
      const cx1=(pts[i-1][0]+x)/2;
      return `C${cx1.toFixed(1)},${pts[i-1][1].toFixed(1)} ${cx1.toFixed(1)},${y.toFixed(1)} ${x.toFixed(1)},${y.toFixed(1)}`;
    }).join('');
  }
  function areaPath(vals){
    const [lx,ly]=pt(N-1,vals[N-1]), [fx]=pt(0,vals[0]);
    return smoothPath(vals)+`L${lx.toFixed(1)},${(my+ch).toFixed(1)} L${fx.toFixed(1)},${(my+ch).toFixed(1)}Z`;
  }

  let s=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg"><defs>`;
  colors.forEach((c,i)=>{
    s+=`<linearGradient id="ag${i}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="${c}" stop-opacity=".3"/>
      <stop offset="100%" stop-color="${c}" stop-opacity=".02"/>
    </linearGradient>
    <clipPath id="lc${i}">
      <rect class="lcr" data-cw="${cw}" x="${mx}" y="${my-2}" width="0" height="${ch+4}"/>
    </clipPath>`;
  });
  s+='</defs>';

  // Y grid + labels
  [100,120,140,160,180,200].forEach(v=>{
    const y=(my+ch-((v-vMin)/(vMax-vMin))*ch).toFixed(1);
    s+=`<line x1="${mx}" y1="${y}" x2="${W-mxr}" y2="${y}" stroke="rgba(255,255,255,.07)" stroke-width="1" stroke-dasharray="3,4"/>`;
    s+=`<text x="${mx-7}" y="${y}" text-anchor="end" dominant-baseline="middle" font-size="9.5" fill="rgba(255,255,255,.35)" font-family="Inter">${v}</text>`;
  });
  // Unit label
  s+=`<text x="${mx}" y="${my-6}" font-size="9" fill="rgba(255,255,255,.3)" font-family="Inter">${zh?'指数 (1月=100)':'Index (Jan=100)'}</text>`;

  // X axis
  s+=`<line x1="${mx}" y1="${my+ch}" x2="${W-mxr}" y2="${my+ch}" stroke="rgba(255,255,255,.12)" stroke-width="1"/>`;
  months.forEach((m,i)=>{
    if(i%2===0){ const [x]=pt(i,vMin); s+=`<text x="${x.toFixed(1)}" y="${H-myb+16}" text-anchor="middle" font-size="9.5" fill="rgba(255,255,255,.42)" font-family="Inter">${m}</text>`; }
  });

  // Area fills + lines
  prods.forEach((p,pi)=>{
    const vals=raw[p];
    s+=`<path d="${areaPath(vals)}" fill="url(#ag${pi})"/>`;
    s+=`<path class="gl" d="${smoothPath(vals)}" fill="none" stroke="${colors[pi]}" stroke-width="2.4" stroke-linecap="round" clip-path="url(#lc${pi})"/>`;
    // End dot
    const [ex,ey]=pt(N-1,vals[N-1]);
    s+=`<circle class="ldot" cx="${ex.toFixed(1)}" cy="${ey.toFixed(1)}" r="4" fill="${colors[pi]}" opacity="0"/>`;
    // End value label
    s+=`<text class="lval" x="${(ex+7).toFixed(1)}" y="${ey.toFixed(1)}" dominant-baseline="middle" font-size="10" font-weight="600" fill="${colors[pi]}" opacity="0">${vals[N-1]}</text>`;
  });

  // Legend
  prods.forEach((p,i)=>{
    const lx=mx+i*130;
    s+=`<line x1="${lx}" y1="${H-13}" x2="${lx+18}" y2="${H-13}" stroke="${colors[i]}" stroke-width="2.5" stroke-linecap="round"/>`;
    s+=`<circle cx="${lx+9}" cy="${H-13}" r="3" fill="${colors[i]}"/>`;
    s+=`<text x="${lx+24}" y="${H-9}" font-size="11" fill="rgba(255,255,255,.72)" font-family="Inter">${p}</text>`;
  });
  return s+'</svg>';
}

/* ── Chart 3: Radar — 5 维综合竞争力 ── */
function buildRadarGallerySVG(l='zh'){
  const zh=l==='zh';
  const W=560,H=330;
  const cx=W/2-20, cy=H/2+8, r=118;
  const n=5;
  const labels=zh?['即时通讯','视频会议','文件协作','企业生态','移动端']:['Messaging','Video','Files','Enterprise','Mobile'];
  // Estimated benchmark: each product has a characteristic strength
  const data=[
    [92,88,85,90,88],   // 飞书: strong across all
    [89,80,78,85,92],   // 钉钉: mobile-strong
    [85,82,90,70,80],   // Slack: file collab king
  ];
  const colors=['#40c4d0','#49bf8a','#df7f37'];
  const prods=zh?['飞书','钉钉','Slack']:['Feishu','DingTalk','Slack'];

  function pt(i,v){ const a=(i/n)*Math.PI*2-Math.PI/2; return [cx+v*Math.cos(a),cy+v*Math.sin(a)]; }
  function ring(rv){ return Array.from({length:n},(_,i)=>pt(i,rv).map(v=>v.toFixed(1)).join(',')).join(' '); }

  let s=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;

  // Grid rings (5 levels) + ring value labels on first axis
  [20,40,60,80,100].forEach((v,li)=>{
    const rv=r*v/100;
    s+=`<polygon points="${ring(rv)}" fill="${li===4?'rgba(64,196,208,.06)':'none'}" stroke="${li===4?'rgba(64,196,208,.35)':'rgba(255,255,255,.08)'}" stroke-width="${li===4?1.2:.6}"/>`;
    // Label on top axis
    const [lx,ly]=pt(0,rv);
    s+=`<text x="${(lx+4).toFixed(1)}" y="${(ly).toFixed(1)}" font-size="8.5" fill="rgba(255,255,255,.3)" font-family="Inter" dominant-baseline="middle">${v}</text>`;
  });

  // Axis lines
  for(let i=0;i<n;i++){
    const [x,y]=pt(i,r);
    s+=`<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="rgba(255,255,255,.1)" stroke-width=".8"/>`;
  }

  // Data polygons
  const cStr=Array(n).fill(`${cx.toFixed(1)},${cy.toFixed(1)}`).join(' ');
  data.forEach((vals,di)=>{
    const fStr=vals.map((v,i)=>pt(i,r*v/100).map(w=>w.toFixed(1)).join(',')).join(' ');
    s+=`<polygon class="rp" data-final="${fStr}" data-cx="${cx.toFixed(1)}" data-cy="${cy.toFixed(1)}"
        points="${cStr}"
        fill="${colors[di]}" fill-opacity=".16"
        stroke="${colors[di]}" stroke-width="2" stroke-linejoin="round"/>`;
    // Dot at each vertex (initially hidden)
    vals.forEach((v,i)=>{
      const [px,py]=pt(i,r*v/100);
      s+=`<circle class="rdot" cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="3.5" fill="${colors[di]}" opacity="0"/>`;
    });
  });

  // Axis labels
  labels.forEach((lbl,i)=>{
    const [lx,ly]=pt(i,r+22);
    const anchor=lx<cx-4?'end':lx>cx+4?'start':'middle';
    s+=`<text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="${anchor}" dominant-baseline="middle"
          font-size="10.5" fill="rgba(255,255,255,.6)" font-family="Inter" font-weight="500">${lbl}</text>`;
  });

  // Legend (right side)
  prods.forEach((p,i)=>{
    const ly=H/2-20+i*26;
    s+=`<rect x="${W-78}" y="${ly-6}" width="12" height="12" rx="3" fill="${colors[i]}"/>`;
    s+=`<text x="${W-62}" y="${ly+3}" font-size="11" fill="rgba(255,255,255,.72)" font-family="Inter">${p}</text>`;
  });
  return s+'</svg>';
}

/* ── Chart 4: Donut — 2026 Q1 国内市场份额 ── */
function buildDonutSVG(l='zh'){
  const zh=l==='zh';
  const W=560, H=330;
  const cx=210, cy=162, Ro=120, Ri=70;
  // Source: estimated 2026 Q1 China enterprise messaging market
  const segs= zh ? [
    {label:'钉钉',   sub:'Alibaba',  v:41,c:'#49bf8a'},
    {label:'飞书',   sub:'ByteDance',v:28,c:'#40c4d0'},
    {label:'企业微信',sub:'Tencent',  v:22,c:'#9259f2'},
    {label:'Slack/Teams',sub:'海外',  v:9, c:'#df7f37'},
  ] : [
    {label:'DingTalk',sub:'Alibaba',  v:41,c:'#49bf8a'},
    {label:'Feishu',  sub:'ByteDance',v:28,c:'#40c4d0'},
    {label:'WeCom',   sub:'Tencent',  v:22,c:'#9259f2'},
    {label:'Slack/Teams',sub:'Intl.',  v:9,c:'#df7f37'},
  ];
  let s=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg">`;

  // Subtle background circle
  s+=`<circle cx="${cx}" cy="${cy}" r="${Ro+6}" fill="rgba(255,255,255,.03)" stroke="rgba(255,255,255,.06)" stroke-width="1"/>`;

  let start=-Math.PI/2;
  segs.forEach((seg,si)=>{
    const ang=(seg.v/100)*Math.PI*2, end=start+ang, la=ang>Math.PI?1:0;
    const gap=0.018; // small gap between segments
    const s0=start+gap, e0=end-gap;
    const x1=(cx+Ro*Math.cos(s0)).toFixed(1), y1=(cy+Ro*Math.sin(s0)).toFixed(1);
    const x2=(cx+Ro*Math.cos(e0)).toFixed(1), y2=(cy+Ro*Math.sin(e0)).toFixed(1);
    const x3=(cx+Ri*Math.cos(e0)).toFixed(1), y3=(cy+Ri*Math.sin(e0)).toFixed(1);
    const x4=(cx+Ri*Math.cos(s0)).toFixed(1), y4=(cy+Ri*Math.sin(s0)).toFixed(1);
    s+=`<path class="ds" data-cx="${cx}" data-cy="${cy}"
          d="M${x1},${y1} A${Ro},${Ro} 0 ${la},1 ${x2},${y2} L${x3},${y3} A${Ri},${Ri} 0 ${la},0 ${x4},${y4}Z"
          fill="${seg.c}"/>`;

    // Leader line + label
    const ma=start+ang/2;
    const mx0=cx+(Ro+14)*Math.cos(ma), my0=cy+(Ro+14)*Math.sin(ma);
    const mx1=cx+(Ro+36)*Math.cos(ma), my1=cy+(Ro+36)*Math.sin(ma);
    const anchor=mx1>cx?'start':'end';
    const tx=mx1+(anchor==='start'?6:-6);
    s+=`<line x1="${mx0.toFixed(1)}" y1="${my0.toFixed(1)}" x2="${mx1.toFixed(1)}" y2="${my1.toFixed(1)}" stroke="${seg.c}" stroke-width="1.2" opacity=".7"/>`;
    s+=`<circle cx="${mx1.toFixed(1)}" cy="${my1.toFixed(1)}" r="2" fill="${seg.c}"/>`;
    s+=`<text x="${tx.toFixed(1)}" y="${(my1-5).toFixed(1)}" text-anchor="${anchor}" font-size="11" font-weight="600" fill="rgba(255,255,255,.85)" font-family="Inter">${seg.label}</text>`;
    s+=`<text x="${tx.toFixed(1)}" y="${(my1+8).toFixed(1)}" text-anchor="${anchor}" font-size="10" fill="${seg.c}" font-family="Inter">${seg.v}%</text>`;
    start=end;
  });

  // Center text
  s+=`<text x="${cx}" y="${cy-14}" text-anchor="middle" font-size="28" font-weight="800" fill="white" font-family="Inter" letter-spacing="-1">${zh?'市场':'Market'}</text>`;
  s+=`<text x="${cx}" y="${cy+10}" text-anchor="middle" font-size="13" fill="rgba(255,255,255,.45)" font-family="Inter">${zh?'份额 2026':'Share 2026'}</text>`;

  // Right legend table
  const lx0=W-130;
  s+=`<text x="${lx0}" y="44" font-size="10" font-weight="600" fill="rgba(255,255,255,.35)" font-family="Inter">产品</text>`;
  s+=`<text x="${W-32}" y="44" text-anchor="middle" font-size="10" font-weight="600" fill="rgba(255,255,255,.35)" font-family="Inter">占比</text>`;
  segs.forEach((seg,i)=>{
    const ly=66+i*40;
    s+=`<rect x="${lx0-4}" y="${ly-10}" width="${W-lx0+4}" height="32" rx="6" fill="rgba(255,255,255,.04)"/>`;
    s+=`<circle cx="${lx0+7}" cy="${ly+6}" r="5" fill="${seg.c}"/>`;
    s+=`<text x="${lx0+18}" y="${ly+2}" font-size="11" font-weight="600" fill="rgba(255,255,255,.8)" font-family="Inter">${seg.label}</text>`;
    s+=`<text x="${lx0+18}" y="${ly+14}" font-size="9.5" fill="rgba(255,255,255,.38)" font-family="Inter">${seg.sub}</text>`;
    s+=`<text x="${W-28}" y="${ly+7}" text-anchor="middle" font-size="15" font-weight="700" fill="${seg.c}" font-family="Inter">${seg.v}%</text>`;
  });
  return s+'</svg>';
}

function initGallery(){
  const vp = document.querySelector('.gallery-viewport');
  if(!vp || typeof gsap==='undefined') return;

  const cardW = vp.clientWidth || 1000;
  const l = lang;
  const zh = l==='zh';
  const cards = [
    {title: zh?'用户情感词云':'User Sentiment Cloud', tag:'Word Cloud', svg:buildWordCloudSVG(l)},
    {title: zh?'用户增长趋势':'MAU Growth Index',    tag:'Line Chart', svg:buildLineChartSVG(l)},
    {title: zh?'综合竞争力雷达':'Capability Radar',   tag:'Radar Chart',svg:buildRadarGallerySVG(l)},
    {title: zh?'市场份额分布':'Market Share 2026',   tag:'Donut Chart',svg:buildDonutSVG(l)},
  ];

  const track = $('gallery-track');
  track.innerHTML = cards.map(c=>`
    <div class="gallery-card" style="width:${cardW}px;height:420px">
      <div class="gallery-card-hd">
        <span class="gallery-card-title">${c.title}</span>
        <span class="gallery-card-tag">${c.tag}</span>
      </div>
      <div class="gallery-card-body">${c.svg}</div>
    </div>`).join('');

  gsap.set(track,{x:0});
  galleryIdx=0;

  // Click handlers for nav dots
  document.querySelectorAll('.gallery-nav-dot').forEach((dot,i)=>{
    dot.onclick=()=>showGalleryCard(i);
    dot.classList.toggle('active',i===0);
  });

  // Arrow buttons state
  const pBtn=$('gallery-prev'), nBtn=$('gallery-next');
  if(pBtn){ pBtn.disabled=true; }
  if(nBtn){ nBtn.disabled=GALLERY_TOTAL<=1; }

  // Touch / swipe support
  let tx0=0;
  vp.addEventListener('touchstart',e=>{tx0=e.touches[0].clientX;},{passive:true});
  vp.addEventListener('touchend',e=>{
    const dx=e.changedTouches[0].clientX-tx0;
    if(Math.abs(dx)>50) galleryNav(dx<0?1:-1);
  },{passive:true});

  // Animate first card
  animateGalleryChart(0);
}

function galleryNav(dir){
  const next=Math.max(0,Math.min(GALLERY_TOTAL-1,galleryIdx+dir));
  if(next!==galleryIdx) showGalleryCard(next);
}

function showGalleryCard(idx){
  const vp = document.querySelector('.gallery-viewport');
  if(!vp || typeof gsap==='undefined') return;
  const cardW = vp.clientWidth || 1000;
  gsap.to($('gallery-track'),{x:-idx*cardW, duration:0.65, ease:'power3.inOut'});
  galleryIdx=idx;

  document.querySelectorAll('.gallery-nav-dot').forEach((d,i)=>d.classList.toggle('active',i===idx));

  const pBtn=$('gallery-prev'), nBtn=$('gallery-next');
  if(pBtn) pBtn.disabled=idx===0;
  if(nBtn) nBtn.disabled=idx===GALLERY_TOTAL-1;

  animateGalleryChart(idx);
}

function animateGalleryChart(idx){
  if(typeof gsap==='undefined') return;
  const vp = document.querySelector('.gallery-viewport');
  if(!vp) return;
  const cardW = vp.clientWidth||1000;
  // Only animate elements in the active card
  const card = $('gallery-track').children[idx];
  if(!card) return;

  if(idx===0){ // Word cloud — stagger fade-in words
    card.querySelectorAll('.wc-word').forEach((w,i)=>{
      gsap.from(w,{opacity:0, scale:0.25, duration:0.45, ease:'back.out(1.6)', delay:i*0.038});
    });

  } else if(idx===1){ // Line chart — draw lines left-to-right via clip-rect
    card.querySelectorAll('.lcr').forEach((rect,i)=>{
      const chartW = parseFloat(rect.dataset.cw) || 480;
      gsap.fromTo(rect,
        {attr:{width:0}},
        {attr:{width:chartW}, duration:1.5, ease:'power2.out', delay:i*0.18}
      );
    });
    // Fade in end dots + labels after lines finish
    card.querySelectorAll('.ldot,.lval').forEach((el,i)=>{
      gsap.to(el,{opacity:1, duration:0.4, ease:'power2.out', delay:1.7+i*0.05});
    });

  } else if(idx===2){ // Radar — expand polygons from center
    card.querySelectorAll('.rp').forEach((poly,i)=>{
      const fs=poly.dataset.final;
      const pcx=poly.dataset.cx, pcy=poly.dataset.cy;
      const cs=Array(5).fill(`${pcx},${pcy}`).join(' ');
      gsap.fromTo(poly,
        {attr:{points:cs}},
        {attr:{points:fs}, duration:1.3, ease:'power3.out', delay:i*0.22}
      );
    });
    // Fade in vertex dots
    card.querySelectorAll('.rdot').forEach((dot,i)=>{
      gsap.to(dot,{opacity:1, duration:0.3, ease:'power2.out', delay:1.4+i*0.03});
    });

  } else if(idx===3){ // Donut — scale segments from center
    card.querySelectorAll('.ds').forEach((seg,i)=>{
      const pcx=seg.dataset.cx||'210', pcy=seg.dataset.cy||'162';
      gsap.from(seg,{scale:0, svgOrigin:`${pcx} ${pcy}`, duration:0.72, ease:'back.out(1.5)', delay:i*0.14});
    });
  }
}


/* ══════════════════════════════════════
   GSAP — Agent dots & connector (replacing CSS)
══════════════════════════════════════ */
function initAgentAnimations(){
  if(typeof gsap==='undefined') return;

  // Glow pulse on each agent dot
  document.querySelectorAll('.agent-dot').forEach((dot,i)=>{
    gsap.to(dot, {
      boxShadow:'0 0 12px 5px rgba(64,196,208,.95)',
      opacity:.7,
      duration:1.2,
      ease:'sine.inOut',
      repeat:-1,
      yoyo:true,
      delay:i*0.6,
    });
  });

  // Eyebrow dots
  document.querySelectorAll('.eyebrow-dot').forEach((dot,i)=>{
    gsap.to(dot,{
      boxShadow:'0 0 12px 5px rgba(64,196,208,.95)',
      opacity:.7,
      duration:1.4,
      ease:'sine.inOut',
      repeat:-1,
      yoyo:true,
      delay:i*0.3,
    });
  });

  // Electric flow particles on connector lines
  document.querySelectorAll('.agent-sep-line').forEach((line,i)=>{
    const particle = document.createElement('div');
    Object.assign(particle.style,{
      position:'absolute', top:'50%', left:'-8px',
      transform:'translateY(-50%)',
      width:'8px', height:'8px', borderRadius:'50%',
      background:'#40c4d0',
      boxShadow:'0 0 8px 3px rgba(64,196,208,.85)',
      opacity:'0',
    });
    line.style.position='relative';
    line.appendChild(particle);
    gsap.to(particle,{
      left:'calc(100% + 4px)',
      opacity:1,
      duration:1.0,
      ease:'none',
      repeat:-1,
      delay:i*0.8,
      repeatDelay:0.4,
      keyframes:[
        {left:'-8px',opacity:0,duration:0},
        {left:'10%', opacity:1,duration:0.1},
        {left:'90%', opacity:1,duration:0.8},
        {left:'calc(100% + 4px)',opacity:0,duration:0.1},
      ],
    });
  });
}

/* ══════════════════════════════════════
   Analysis timer
══════════════════════════════════════ */
function elapsedStr(ms){
  const s=Math.floor(ms/1000), m=Math.floor(s/60);
  return `${String(m).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`;
}

function startTimer(){
  analysisStartTime=Date.now();
  const el=$('stream-timer');
  if(el){ el.textContent='00:00'; el.style.display=''; }
  clearInterval(timerInterval);
  timerInterval=setInterval(()=>{
    const el=$('stream-timer');
    if(el) el.textContent=elapsedStr(Date.now()-analysisStartTime);
  },1000);
}

function stopTimer(){
  clearInterval(timerInterval);
  timerInterval=null;
}

/* ══════════════════════════════════════
   Log helpers
══════════════════════════════════════ */
const AGENT_COLORS={'PM Agent':'#40c4d0','Collector':'#1eab7a','Insight':'#df7f37','Reporter':'#9259f2'};

function clearPreview(){ const p=$('log-preview'); if(p) p.style.display='none'; }
function appendLog(agent,msg,dim){
  const body=$('log-body'); clearPreview();
  const line=document.createElement('div'); line.className='log-line';
  const color=AGENT_COLORS[agent]||'#9999b2';
  const ts=analysisStartTime?`<span class="log-ts">+${elapsedStr(Date.now()-analysisStartTime)}</span>`:'';
  line.innerHTML=`${ts}<span class="log-agent" style="color:${color}">[${esc(agent)}]</span><span class="log-msg ${dim?'log-dim':'log-bright'}">${esc(msg)}</span>`;
  body.appendChild(line); body.scrollTop=body.scrollHeight;
}
function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

/* ── Log block helpers ── */
function appendLogBlock(html){
  const body=$('log-body'); clearPreview();
  const wrap=document.createElement('div');
  wrap.innerHTML=html;
  body.appendChild(wrap.firstChild);
  body.scrollTop=body.scrollHeight;
}

function renderDomainSeed(msg){
  const zh=lang==='zh';
  const dims=(msg.dimension_candidates||[]).join('、');
  const comps=(msg.competitor_mentions||[]).join('、');
  const hint=msg.product_type_hint||'';
  let h=`<div class="log-block log-block-seed"><div class="log-block-title">${zh?'文档解析完成':'Document Parsed'}</div>`;
  if(hint) h+=`<div class="log-block-row"><span class="log-block-label">${zh?'产品赛道':'Type'}</span><span class="log-bright">${esc(hint)}</span></div>`;
  if(dims) h+=`<div class="log-block-row"><span class="log-block-label">${zh?'维度候选':'Dimensions'}</span><span class="log-dim">${esc(dims)}</span></div>`;
  if(comps) h+=`<div class="log-block-row"><span class="log-block-label">${zh?'竞品提及':'Competitors'}</span><span class="log-dim">${esc(comps)}</span></div>`;
  const terms=msg.terminology&&Object.keys(msg.terminology).length?Object.entries(msg.terminology).map(([k,v])=>`${k}：${v}`).join('、'):'';
  if(terms) h+=`<div class="log-block-row"><span class="log-block-label">${zh?'术语表':'Terms'}</span><span class="log-dim">${esc(terms)}</span></div>`;
  h+=`</div>`;
  appendLogBlock(h);
}

function renderReviewUpdate(units){
  const zh=lang==='zh';
  const STATUS={
    passed:{label:zh?'通过':'Passed',cls:'rs-passed'},
    needs_retry:{label:zh?'返工':'Retry',cls:'rs-retry'},
    forced:{label:zh?'强制通过':'Forced',cls:'rs-forced'},
  };
  const CLRS={collector:'#1eab7a',insight:'#df7f37'};
  let h=`<div class="log-block log-block-review"><div class="log-block-title">${zh?'PM 评审结果':'PM Review'}</div>`;
  (units||[]).forEach(u=>{
    const s=STATUS[u.status]||{label:u.status,cls:''};
    const c=CLRS[u.agent]||'#9999b2';
    h+=`<div class="log-block-review-row"><span class="log-block-agent" style="color:${c}">${esc(u.agent)}</span><span class="log-block-product">${esc(u.product_name)}</span><span class="review-status-badge ${s.cls}">${s.label}</span>`;
    if(u.pm_note) h+=`<span class="log-block-note">${esc(u.pm_note)}</span>`;
    h+=`</div>`;
    if(u.qa_flags&&u.qa_flags.length) h+=`<div class="log-block-flags">${u.qa_flags.map(esc).join(' · ')}</div>`;
  });
  h+=`</div>`;
  appendLogBlock(h);
}

function renderReroute(msg){
  const zh=lang==='zh';
  const PH={'phase_1':zh?'阶段一':'Phase 1','phase_2':zh?'阶段二':'Phase 2','phase_3':zh?'阶段三':'Phase 3'};
  const ph=PH[msg.phase]||msg.phase||'';
  const text=zh
    ?`触发返工（第 ${msg.count} 次），回溯至 ${ph}${msg.reason?' · '+msg.reason:''}`
    :`Reroute ×${msg.count} → ${ph}${msg.reason?' · '+msg.reason:''}`;
  appendLog('PM Agent',text,false);
}

function renderDebateResult(msg){
  const zh=lang==='zh';
  const VERDICT={
    accepted:{label:zh?'接受':'Accepted',cls:'verdict-accepted'},
    rejected:{label:zh?'拒绝':'Rejected',cls:'verdict-rejected'},
    accepted_with_revision:{label:zh?'修订后接受':'Revised',cls:'verdict-revised'},
  };
  const v=VERDICT[msg.final_verdict]||{label:msg.final_verdict,cls:''};
  const TGT={pm_taskplan:'TaskPlan',report:'Report',pm_initial_brief:'InitialBrief'};
  const tgt=TGT[msg.target]||msg.target||'';
  let h=`<div class="log-block log-block-debate"><div class="log-block-title">Debate · ${esc(tgt)} <span class="verdict-badge ${v.cls}">${v.label}</span></div>`;
  if(msg.judge_rationale) h+=`<div class="log-block-rationale">${esc(msg.judge_rationale)}</div>`;
  h+=`</div>`;
  appendLogBlock(h);
}

function renderQaResult(results){
  const zh=lang==='zh';
  let h=`<div class="log-block log-block-qa-result"><div class="log-block-title">${zh?'报告终审':'Report QA'}</div>`;
  (results||[]).forEach(r=>{
    const cls=r.passed?'qa-passed':'qa-failed';
    const lbl=r.passed?(zh?'通过':'Pass'):(zh?'未通过':'Fail');
    h+=`<div class="log-block-review-row"><span class="log-block-product">${esc(r.product_name)}</span><span class="review-status-badge ${cls}">${lbl}</span>`;
    if(r.note) h+=`<span class="log-block-note">${esc(r.note)}</span>`;
    h+=`</div>`;
    if(r.failed_checks&&r.failed_checks.length) h+=`<div class="log-block-flags qa-failed-checks">${r.failed_checks.map(esc).join(' · ')}</div>`;
  });
  h+=`</div>`;
  appendLogBlock(h);
}

function renderSignal(msg){
  const KIND_ZH={data_gap:'数据缺口',pm_challenge:'PM 挑战',insight_lead:'Insight 线索',other:'信号'};
  const KIND_EN={data_gap:'Data Gap',pm_challenge:'PM Challenge',insight_lead:'Insight Lead',other:'Signal'};
  const k=(lang==='zh'?KIND_ZH:KIND_EN)[msg.kind]||msg.kind||'Signal';
  appendLog(msg.from_agent||'Agent',`[${k}] ${(msg.payload&&msg.payload.claim)||''}`,true);
}

function showReportStatus(status){
  const zh=lang==='zh';
  const badge=$('report-status-badge');
  if(!badge) return;
  const M={
    passed:{label:zh?'QA 通过':'QA Passed',cls:'status-passed'},
    failed:{label:zh?'QA 未通过':'QA Failed',cls:'status-failed'},
    unreviewed:{label:zh?'未审核':'Unreviewed',cls:'status-unreviewed'},
    pending:{label:zh?'审核中':'Reviewing',cls:'status-pending'},
  };
  const s=M[status]||{label:status,cls:'status-unreviewed'};
  badge.textContent=s.label;
  badge.className=`report-status-badge ${s.cls}`;
  badge.style.display='';
}

function setThink(show){ $('think-badge').classList.toggle('show',show); }
function setProgress(pct,s){
  $('progress-fill').style.width=pct+'%';
  $('progress-text').textContent=pct>0?T('progress')(pct,s):'';
}

/* ══════════════════════════════════════
   API Config Modal
══════════════════════════════════════ */
function openApiModal(){
  $('api-modal').classList.add('show');
  showModalStep('api-step-1');
  selectOption(apiOption);
  updateKeyWarning();
}
function closeApiModal(){ $('api-modal').classList.remove('show'); }
function showModalStep(id){
  ['api-step-1','api-step-key','api-step-pay'].forEach(s=>{ const el=$(s); if(el) el.style.display='none'; });
  const el=$(id); if(el) el.style.display='block';
}
function selectOption(type){
  apiOption=type;
  ['key','pay'].forEach(t=>{ const el=$('opt-'+t); if(el) el.classList.toggle('selected',t===type); });
}
function goToModalStep2(){
  showModalStep(apiOption==='key'?'api-step-key':'api-step-pay');
  updateKeyWarning();
}
function goModalBack(){ showModalStep('api-step-1'); }

function updateKeyWarning(){
  const filled=['gpt5','deepseek','doubao'].filter(s=>$(`${s}-key`)?.value.trim()).length;
  const w=$('api-warn'); if(w) w.style.display=filled<=1?'':'none';
}
async function submitWithKeys(){
  const anyFilled=['gpt5','deepseek','doubao'].some(s=>$(`${s}-key`)?.value.trim());
  if(!anyFilled){ alert('请至少为 1 个槽位填写 API Key'); return; }
  const tv=$('tavily-key')?.value.trim();
  if(!tv){ alert('请填写 Tavily Search API Key'); return; }
  closeApiModal();
  startAnalysis();
}
function handlePayment(){ alert('支付功能即将上线，敬请期待。'); }

/* ══════════════════════════════════════
   Submit
══════════════════════════════════════ */
function handleSubmit(e){
  e.preventDefault();
  const product=$('input-product').value.trim();
  if(!product){ $('input-product').focus(); alert(T('errNoProduct')); return; }
  openApiModal();
}

async function startAnalysis(){
  const product=$('input-product').value.trim();
  const btn=$('submit-btn'); btn.disabled=true;
  $('log-body').innerHTML=''; setThink(false); setProgress(0,0);
  $('phase1-box').classList.remove('show');
  $('qa-box').classList.remove('show');
  const _rsb=$('report-status-badge'); if(_rsb) _rsb.style.display='none';
  startTimer();
  jumpTo('pdf-section');
  const fd=new FormData();
  fd.append('target_product',product);
  fd.append('user_query',$('input-query').value.trim()||product);
  if(uploadedFile) fd.append('file',uploadedFile);
  ['gpt5','deepseek','doubao'].forEach(fam=>{
    const key=$(`${fam}-key`)?.value.trim();
    if(key) fd.append(`${fam}_key`,key);
  });
  const tv=$('tavily-key')?.value.trim(); if(tv) fd.append('tavily_key',tv);
  try{
    const res=await fetch('/api/analyze',{method:'POST',body:fd});
    if(!res.ok) throw new Error('HTTP '+res.status);
    const {job_id}=await res.json();
    currentJobId=job_id; isSimulateMode=false;
    openSSE(job_id,btn);
  } catch(_){ isSimulateMode=true; simulate(btn,product); }
}

function openSSE(jobId,btn){
  if(eventSource) eventSource.close();
  eventSource=new EventSource(`/api/stream/${jobId}`);
  eventSource.onmessage=ev=>{
    const msg=JSON.parse(ev.data);
    switch(msg.type){
      case 'thinking': setThink(true); break;
      case 'tool_call': setThink(false); appendLog(msg.agent,`→ ${msg.tool}(${msg.args})`,true); break;
      case 'tool_result': appendLog(msg.agent,`← ${msg.tool} (${msg.size}) ${msg.preview}`,true); break;
      case 'log': appendLog(msg.agent,msg.text,false); break;
      case 'progress': setProgress(msg.pct,msg.sec_left); break;
      case 'phase1_checkpoint':
        setThink(false); showPhase1Box(msg.summary); break;
      case 'done':
        eventSource.close(); setThink(false); setProgress(100,0); btn.disabled=false;
        stopTimer();
        if(msg.pdf_path) showPdf(msg.pdf_path,msg.filename);
        else showChartDashboard(DEMO_DATA);
        showQaBox();
        break;
      case 'domain_seed':   renderDomainSeed(msg); break;
      case 'review_update': renderReviewUpdate(msg.units); break;
      case 'reroute':       renderReroute(msg); break;
      case 'debate_result': renderDebateResult(msg); break;
      case 'report_status': showReportStatus(msg.status); break;
      case 'qa_result':     renderQaResult(msg.results); break;
      case 'signal':        renderSignal(msg); break;
      case 'error':
        eventSource.close(); setThink(false); stopTimer(); btn.disabled=false; appendLog('Error',msg.message,false); break;
    }
  };
  eventSource.onerror=()=>{ eventSource.close(); btn.disabled=false; };
}

function showPdf(path,filename){
  pdfPath=path;
  $('pdf-content').innerHTML=`<iframe src="/api/report/pdf?path=${encodeURIComponent(path)}" title="PDF Report"></iframe>`;
  if(filename) $('pdf-fname').textContent=filename;
}

/* ══════════════════════════════════════
   Phase 1 interaction & Q&A
══════════════════════════════════════ */
function showPhase1Box(summary){
  const box=$('phase1-box'), el=$('phase1-summary');
  if(el) el.innerHTML=summary||'';
  if(box) box.classList.add('show');
}

function showQaBox(){
  const box=$('qa-box');
  if(box) box.classList.add('show');
}

async function sendPhase1Feedback(skip){
  const input=$('phase1-input');
  const feedback=skip?'':(input?.value.trim()||'');
  const box=$('phase1-box');
  if(box) box.classList.remove('show');
  const label=skip
    ?(lang==='zh'?'继续生成报告...':'Continuing report generation...')
    :(lang==='zh'?`已提交修改建议：${feedback}`:`Feedback submitted: ${feedback}`);
  appendLog('System',label,false);
  if(isSimulateMode){ continueSimulateAfterPhase1(); return; }
  try{
    await fetch(`/api/jobs/${currentJobId}/feedback`,{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({raw_feedback:feedback||null,approved:skip}),
    });
  } catch(_){}
}

async function sendReportQuestion(){
  const input=$('qa-input');
  const text=input?.value.trim();
  if(!text) return;
  appendQaMessage('user',text);
  if(input) input.value='';
  if(isSimulateMode){
    const reply=lang==='zh'
      ?'这是模拟回答。实际运行中，Agent 会根据报告内容回答您的具体问题。'
      :'This is a simulated answer. In production, the Agent answers based on the actual report content.';
    setTimeout(()=>appendQaMessage('agent',reply),1200);
    return;
  }
  try{
    const res=await fetch(`/api/jobs/${currentJobId}/question`,{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({question:text}),
    });
    const {answer}=await res.json();
    appendQaMessage('agent',answer);
  } catch(_){
    appendQaMessage('agent',lang==='zh'?'回答失败，请重试':'Failed to get answer, please retry');
  }
}

function appendQaMessage(role,text){
  const msgs=$('qa-messages');
  if(!msgs) return;
  const el=document.createElement('div');
  el.className=`qa-msg ${role}`;
  el.textContent=text;
  msgs.appendChild(el);
  msgs.scrollTop=msgs.scrollHeight;
}

/* ══════════════════════════════════════
   PDF chart dashboard
══════════════════════════════════════ */
const DEMO_DATA={
  products:['飞书','钉钉','Slack'], colors:['#40c4d0','#49bf8a','#df7f37'],
  radar:{labels:['功能完整性','用户体验','定价合理性','市场份额','创新能力'],scores:[[85,88,72,78,90],[90,78,85,88,72],[82,92,65,70,88]]},
  pricing:[{name:'飞书 商业版',value:'¥15/月',pct:55,color:'#40c4d0'},{name:'钉钉 专业版',value:'¥12/月',pct:44,color:'#49bf8a'},{name:'Slack Pro',value:'$7.25/月',pct:72,color:'#df7f37'}],
  sentiment:[78,71,84],
};

function showChartDashboard(data){
  const content=$('pdf-content');
  content.style.alignItems='stretch';
  content.innerHTML=buildDashboardHTML(data);
  requestAnimationFrame(()=>{ animateRadar(data); animateBars(); animateSentimentArcs(data); });
}

function buildDashboardHTML(data){
  const n=data.radar.labels.length, cx=110, cy=110, r=88;
  function pxy(i,v){ const a=(i/n)*Math.PI*2-Math.PI/2; return [cx+v*Math.cos(a),cy+v*Math.sin(a)]; }
  function ring(rv){ return Array.from({length:n},(_,i)=>pxy(i,rv).map(v=>v.toFixed(1)).join(',')).join(' '); }
  let rs=`<svg id="radar-svg" viewBox="0 0 220 220" xmlns="http://www.w3.org/2000/svg" style="width:200px;height:200px;display:block">`;
  for(let l=1;l<=5;l++){ const rv=r*l/5; rs+=`<polygon points="${ring(rv)}" fill="none" stroke="${l===5?'#40c4d044':'#1e2242'}" stroke-width="${l===5?1:.6}"/>`; }
  for(let i=0;i<n;i++){ const[x,y]=pxy(i,r); rs+=`<line x1="${cx}" y1="${cy}" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="#1e2242" stroke-width=".6"/>`; }
  const cStr=Array(n).fill(`${cx},${cy}`).join(' ');
  data.radar.scores.forEach((sc,di)=>{
    const fs=sc.map((v,i)=>pxy(i,r*v/100).map(w=>w.toFixed(1)).join(',')).join(' ');
    rs+=`<polygon class="radar-poly" data-final="${fs}" points="${cStr}" fill="${data.colors[di]}" fill-opacity=".15" stroke="${data.colors[di]}" stroke-width="1.5" stroke-linejoin="round"/>`;
  });
  data.radar.labels.forEach((lbl,i)=>{ const[lx,ly]=pxy(i,r+16); const anc=lx<cx-4?'end':lx>cx+4?'start':'middle'; rs+=`<text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="${anc}" dominant-baseline="middle" font-size="8.5" fill="#7880a0" font-family="Inter">${lbl}</text>`; });
  rs+='</svg>';
  const bars=data.pricing.map(p=>`<div class="bar-h-item"><span class="bar-h-label" style="color:${p.color}">${p.name}</span><div class="bar-h-track"><div class="bar-h-fill" data-pct="${p.pct}" style="background:${p.color}"></div></div><span class="bar-h-val">${p.value}</span></div>`).join('');
  const arcs=data.products.map((n,i)=>`<div class="sentiment-item"><div class="sentiment-arc-wrap"><svg viewBox="0 0 72 72"><circle class="sentiment-arc-bg" cx="36" cy="36" r="28"/><circle class="sentiment-arc-fill" cx="36" cy="36" r="28" data-pct="${data.sentiment[i]}" stroke="${data.colors[i]}"/></svg><span class="sentiment-pct">${data.sentiment[i]}%</span></div><span class="sentiment-name" style="color:${data.colors[i]}">${n}</span></div>`).join('');
  const legend=data.products.map((n,i)=>`<span><i style="background:${data.colors[i]}"></i>${n}</span>`).join('');
  return `<div class="chart-dashboard"><div class="chart-panel"><div class="chart-panel-title">综合能力评估</div>${rs}<div class="radar-legend">${legend}</div></div><div class="chart-panel"><div class="chart-panel-title">定价对比</div>${bars}<div class="chart-divider"></div><div class="chart-panel-title">用户正面情感占比</div><div class="sentiment-row">${arcs}</div></div></div>`;
}

function animateRadar(data){
  if(typeof gsap==='undefined') return;
  document.querySelectorAll('.radar-poly').forEach((p,di)=>{
    gsap.to(p,{attr:{points:p.dataset.final},duration:1.6,ease:'power3.out',delay:.2+di*.2});
  });
}
function animateBars(){
  if(typeof gsap==='undefined') return;
  document.querySelectorAll('.bar-h-fill').forEach((f,i)=>{
    gsap.to(f,{width:f.dataset.pct+'%',duration:1.2,ease:'power2.out',delay:.1+i*.15});
  });
}
function animateSentimentArcs(){
  if(typeof gsap==='undefined') return;
  const circ=2*Math.PI*28;
  document.querySelectorAll('.sentiment-arc-fill').forEach((arc,i)=>{
    gsap.to(arc,{attr:{'stroke-dashoffset':circ*(1-parseFloat(arc.dataset.pct)/100)},duration:1.4,ease:'power2.out',delay:.4+i*.2});
  });
}

/* ══════════════════════════════════════
   Simulate (no backend)
══════════════════════════════════════ */
function simulate(btn,product){
  simBtn=btn; simProduct=product;
  const zh=lang==='zh';
  const steps=[
    [300,()=>setThink(true)],
    [1000,()=>{ appendLog('PM Agent',zh?'分析用户查询，制定竞品分析计划...':'Parsing query, creating plan...'); setThink(false); }],
    [600,()=>{
      appendLog('PM Agent','→ initial_brief({...})',true); setProgress(8,90);
      // 若用户上传了参考文档，模拟 domain_seed 事件
      if(uploadedFile){
        renderDomainSeed({
          product_type_hint: zh?'企业协作与通讯软件':'Enterprise collaboration & communication',
          dimension_candidates: zh
            ?['视频会议','文档协作','即时通讯','定价策略','移动端体验']
            :['Video conferencing','Doc collaboration','Messaging','Pricing','Mobile UX'],
          competitor_mentions: zh?['钉钉','企业微信','Slack']:['DingTalk','WeCom','Slack'],
        });
      }
    }],
    [900,()=>setThink(true)],
    [800,()=>{ setThink(false); appendLog('Collector',zh?'联网搜索竞品官网...':'Searching competitor websites...'); setProgress(20,75); }],
    [600,()=>appendLog('Collector','→ web_search({ query: "target pricing 2026" })',true)],
    [900,()=>{ appendLog('Collector','← web_search (2.1KB) pricing data fetched...',true); setProgress(32,62); }],
    [600,()=>setThink(true)],
    [900,()=>{ setThink(false); appendLog('Insight',zh?'App Store 情感分析，抓取用户评论...':'App Store sentiment, crawling reviews...'); setProgress(56,38); }],
    [600,()=>appendLog('Insight','→ appstore_search({ product: "...", region: "cn" })',true)],
    [900,()=>{ appendLog('Insight','← appstore_search (3.2KB) 320 reviews',true); setProgress(68,26); }],
    [600,()=>appendLog('Insight',zh?'BERT 情感分类完成...':'BERT classification done...')],
    [700,()=>{
      setProgress(75,22);
      // PM 评审结果
      const mockUnits=[
        {agent:'collector',product_name:zh?'钉钉':'DingTalk',status:'passed',qa_flags:[],pm_note:null},
        {agent:'collector',product_name:'Slack',status:'passed',qa_flags:[],pm_note:null},
        {agent:'insight',product_name:zh?'钉钉':'DingTalk',status:'passed',qa_flags:[],pm_note:null},
        {agent:'insight',product_name:'Slack',status:'passed',qa_flags:[],pm_note:null},
      ];
      renderReviewUpdate(mockUnits);
    }],
    [400,()=>{
      // Debate 结果（TaskPlan 被接受）
      renderDebateResult({
        target:'pm_taskplan',
        verdict:'accepted',
        judge_rationale:zh
          ?'竞品列表合理，维度覆盖充分，采纳 PM 原始方案。'
          :'Competitor list and dimension coverage are sound. PM plan accepted as-is.',
      });
      const summary=zh
        ?'<strong>发现竞品：</strong> 钉钉、Slack、企业微信<br><strong>分析维度：</strong> 功能对比 · 定价策略 · 用户情感 · 市场份额<br><strong>主要发现：</strong> 飞书在视频会议和文档协作上领先，钉钉移动端体验更优'
        :'<strong>Competitors found:</strong> DingTalk, Slack, WeCom<br><strong>Dimensions:</strong> Features · Pricing · Sentiment · Market Share<br><strong>Key finding:</strong> Feishu leads in video & docs; DingTalk excels on mobile';
      appendLog('System',zh?'第一阶段分析完成，等待用户确认...':'Phase 1 complete, awaiting your feedback...',false);
      showPhase1Box(summary);
    }],
  ];
  let delay=0;
  steps.forEach(([d,fn])=>{ delay+=d; setTimeout(fn,delay); });
}

function continueSimulateAfterPhase1(){
  const zh=lang==='zh';
  const btn=simBtn, product=simProduct;
  const steps=[
    [500,()=>{ appendLog('Reporter',zh?'开始生成报告...':'Generating report...'); setProgress(78,18); }],
    [800,()=>{ appendLog('Reporter','→ finalize_swot({...})',true); setProgress(88,8); }],
    [900,()=>{
      // 报告终审 debate（call_report_reviewer）
      renderDebateResult({
        target:'report',
        verdict:'accepted_with_revision',
        judge_rationale:zh
          ?'报告结构合理，部分定价数据需补充来源引用，其余内容已采纳。'
          :'Report structure is sound; minor pricing citations added. Accepted with revision.',
      });
    }],
    [500,()=>{
      // qa_results 终审汇总
      const prods=product?[product,zh?'钉钉':'DingTalk','Slack']:[zh?'飞书':'Feishu',zh?'钉钉':'DingTalk','Slack'];
      renderQaResult(prods.map((n,i)=>({
        product_name:n,
        passed:i<2,
        failed_checks:i<2?[]:[zh?'情感数据来源不足':'Insufficient sentiment sources'],
        note:i===0?(zh?'数据完整，评分可信':'Complete data, high confidence'):null,
      })));
      showReportStatus('passed');
      setProgress(100,0);
    }],
    [400,()=>{
      setThink(false); stopTimer(); btn.disabled=false;
      const d=Object.assign({},DEMO_DATA);
      if(product) d.products=[product,zh?'钉钉':'DingTalk','Slack'];
      showChartDashboard(d);
      showQaBox();
    }],
  ];
  let delay=0;
  steps.forEach(([d,fn])=>{ delay+=d; setTimeout(fn,delay); });
}

/* ══════════════════════════════════════
   Wheel scroll — section snap (no gallery intercept)
══════════════════════════════════════ */
function easeInOutCubic(t){ return t<.5?4*t*t*t:1-Math.pow(-2*t+2,3)/2; }

function getSnapElements(){
  return [...document.querySelectorAll('#hero,#product,#gallery,#agents,#analyze,#pdf-section'),document.querySelector('footer')].filter(Boolean);
}

function scrollToEl(el){
  const html=document.documentElement;
  const navH=document.querySelector('.navbar').offsetHeight;
  const startY=window.scrollY, endY=Math.max(0,el.offsetTop-navH), dist=endY-startY;
  if(Math.abs(dist)<4) return;
  html.style.setProperty('scroll-snap-type','none');
  html.style.setProperty('scroll-behavior','auto');
  const t0=performance.now();
  (function tick(now){
    const t=Math.min((now-t0)/1400,1);
    window.scrollTo(0,startY+dist*easeInOutCubic(t));
    if(t<1){ requestAnimationFrame(tick); }
    else{
      html.style.removeProperty('scroll-snap-type');
      html.style.removeProperty('scroll-behavior');
      updateNavActive(el.id||'');
    }
  })(performance.now());
}

/* Timestamp cooldown replaces scrollLocked — no race condition,
   no gallery wheel intercept needed (gallery uses click/swipe).   */
function handleWheel(e){
  if(navJumping){ e.preventDefault(); return; }
  if(Math.abs(e.deltaY)<25) return;
  e.preventDefault();
  const now=performance.now();
  if(now-lastWheelTime<700) return;

  const els=getSnapElements();
  const down=e.deltaY>0;
  const next=Math.max(0,Math.min(els.length-1,currentSnapIdx+(down?1:-1)));
  if(next===currentSnapIdx) return;

  if(els[currentSnapIdx]?.id==='gallery') _resetGalleryToFirst();

  lastWheelTime=now;
  currentSnapIdx=next;
  scrollToEl(els[next]);
}

function _resetGalleryToFirst(){
  galleryIdx=0;
  const track=$('gallery-track');
  if(track&&typeof gsap!=='undefined') gsap.set(track,{x:0});
  document.querySelectorAll('.gallery-nav-dot').forEach((d,i)=>d.classList.toggle('active',i===0));
  const p=$('gallery-prev'),n=$('gallery-next');
  if(p) p.disabled=true;
  if(n) n.disabled=GALLERY_TOTAL<=1;
}

function initSectionObserver(){
  const obs=new IntersectionObserver(entries=>{
    entries.forEach(e=>{ if(e.isIntersecting&&!navJumping) updateNavActive(e.target.id); });
  },{threshold:0.55});
  document.querySelectorAll('section[id]').forEach(s=>obs.observe(s));
}

/* ══════════════════════════════════════
   Boot
══════════════════════════════════════ */
document.addEventListener('DOMContentLoaded',()=>{
  initTheme();
  applyLang();
  initUpload();
  initSectionObserver();
  renderScrollTrack();
  initParticles();
  initGallery();
  initAgentAnimations();
  $('analyze-form').addEventListener('submit',handleSubmit);
  window.addEventListener('wheel',handleWheel,{passive:false});
  // Enter to send Q&A (Shift+Enter for newline)
  $('qa-input')?.addEventListener('keydown',e=>{
    if(e.key==='Enter'&&!e.shiftKey){ e.preventDefault(); sendReportQuestion(); }
  });
});
