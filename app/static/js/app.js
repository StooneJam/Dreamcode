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
    submitBtn:'开始分析', navDlBtn:'报告下载', optionalTag:'可选',
    lblFileText:'上传参考文档（最多 1 个文件）', streamTitle:'智能体运行日志', thinkText:'思考中...',
    logHintText:'点击「开始分析」后，智能体实时日志将在此处显示<br>您可以看到每个 Agent 的思考过程和工具调用',
    pdfTitle:'竞品分析报告已生成', pdfFname:'竞品分析报告_飞书_2026.pdf', pdfDl:'↓  下载到本地',
    pdfEmpty:'完成分析后，PDF 报告将在此处预览',
    pdfPageInfo:(c,t)=>`第 ${c} / ${t} 页`, progress:(p,s)=>`分析进度 ${p}% · 预计剩余 ${s} 秒`,
    footerTagline:'AI 驱动的竞品分析平台', fc1Title:'产品', fc2Title:'支持',
    footerCopy:'© 2026 Dreamcode · 保留所有权利',
    errNoProduct:'请输入目标产品名称', errFiletype:'仅支持 PDF、Word、TXT 格式',
    errFilesize:'文件不能超过 20MB', loginMsg:'登录功能即将上线',
    galleryLabel:'报告样本展示', galleryHint:'向下滚动查看更多图表 ↓',
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
    submitBtn:'Start Analysis', navDlBtn:'Download Report', optionalTag:'Optional',
    lblFileText:'Upload Reference Document (max 1 file)', streamTitle:'Agent Run Log', thinkText:'Thinking...',
    logHintText:'Agent logs will stream here after you click Start Analysis.',
    pdfTitle:'Report Ready', pdfFname:'competitive_analysis_2026.pdf', pdfDl:'↓  Download',
    pdfEmpty:'PDF report will appear here after analysis.',
    pdfPageInfo:(c,t)=>`Page ${c} of ${t}`, progress:(p,s)=>`Progress ${p}% · ~${s}s`,
    footerTagline:'AI-powered Competitive Analysis', fc1Title:'Product', fc2Title:'Support',
    footerCopy:'© 2026 Dreamcode · All rights reserved',
    errNoProduct:'Please enter a target product name', errFiletype:'Only PDF, Word, TXT supported',
    errFilesize:'File must be under 20 MB', loginMsg:'Login coming soon',
    galleryLabel:'Report Samples', galleryHint:'Scroll down for more charts ↓',
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
let navJumping = false;
let scrollLocked = false;
let heroScrollTl = null;
let galleryIdx = 0;
const GALLERY_TOTAL = 4;
let particleRafId = null;

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
  if(id==='gallery') galleryIdx = 0;
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
  set('t-footer-tagline',t.footerTagline);
  set('t-fc1-title',t.fc1Title); set('t-fc2-title',t.fc2Title);
  set('t-footer-copy',t.footerCopy);
}
function setLang(l){ lang=l; applyLang(); renderScrollTrack(); }

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
    const N=720; // dense galaxy
    for(let i=0;i<N;i++){
      const t=Math.random();
      const [cx,cy]=bandCenter(t);
      const [nx,ny]=bandNormal(t);
      const spread=gauss(H*0.085); // wider band than before
      const z=Math.random();
      const r=Math.random();
      // Star colors: white-blue stars dominate, teal & purple nebula accents
      let baseR,baseG,baseB;
      if(r<0.52){       baseR=195+Math.floor(Math.random()*60); baseG=205+Math.floor(Math.random()*50); baseB=255; }
      else if(r<0.80){  baseR=64;  baseG=196; baseB=208; } // teal
      else if(r<0.92){  baseR=146; baseG=89;  baseB=242; } // purple
      else{              baseR=255; baseG=160; baseB=80;  } // warm accent
      particles.push({
        x:  cx + nx*spread,
        baseY: cy + ny*spread,
        yOffset: 0,
        size: 0.4 + z*2.8,
        opacity: 0.05 + z*0.82,
        r:baseR, g:baseG, b:baseB,
        tp: Math.random()*Math.PI*2,
        ts: 0.3 + Math.random()*1.8,
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
    particles.forEach(p=>{
      const tw = 0.5 + 0.5*Math.sin(time*0.001*p.ts + p.tp);
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

/* ── Chart 1: Grouped Bar — 4 products × 4 dimensions ── */
function buildBarChartSVG(){
  const W=560,H=330, mx=56,my=20,mxr=12,myb=62;
  const cw=W-mx-mxr, ch=H-my-myb;
  const groups=['即时通讯','视频会议','文件协作','项目管理'];
  const prods=['飞书','钉钉','Slack','Teams'];
  const colors=['#40c4d0','#49bf8a','#df7f37','#9259f2'];
  // Source: estimated 2026 Q1 product benchmark scores (0-100)
  const data=[
    [92,88,85,78],  // 飞书
    [89,80,78,90],  // 钉钉
    [85,82,90,72],  // Slack
    [80,92,86,94],  // Teams
  ];
  const gW=cw/groups.length, bW=gW*0.17, bG=gW*0.03;
  const gTot=4*bW+3*bG, gOff=(gW-gTot)/2;

  let s=`<svg viewBox="0 0 ${W} ${H}" xmlns="http://www.w3.org/2000/svg"><defs>`;
  colors.forEach((c,i)=>{
    s+=`<linearGradient id="bg${i}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="${c}" stop-opacity=".95"/>
      <stop offset="100%" stop-color="${c}" stop-opacity=".45"/>
    </linearGradient>`;
  });
  s+='</defs>';

  // Background grid
  [20,40,60,80,100].forEach(v=>{
    const y=(my+ch-(v/100)*ch).toFixed(1);
    s+=`<line x1="${mx}" y1="${y}" x2="${W-mxr}" y2="${y}" stroke="rgba(255,255,255,.07)" stroke-width="1" stroke-dasharray="4,4"/>`;
    s+=`<text x="${mx-7}" y="${y}" text-anchor="end" dominant-baseline="middle" font-size="10" fill="rgba(255,255,255,.38)" font-family="Inter">${v}</text>`;
  });

  // X axis base line
  s+=`<line x1="${mx}" y1="${my+ch}" x2="${W-mxr}" y2="${my+ch}" stroke="rgba(255,255,255,.15)" stroke-width="1"/>`;

  // Bars + value labels
  groups.forEach((g,gi)=>{
    const gx=mx+gi*gW+gOff;
    prods.forEach((_,pi)=>{
      const val=data[pi][gi], bH=(val/100)*ch;
      const bx=(gx+pi*(bW+bG)).toFixed(1);
      const by=(my+ch-bH).toFixed(1);
      const bHs=bH.toFixed(1), bWs=bW.toFixed(1);
      s+=`<rect class="gb" x="${bx}" y="${by}" width="${bWs}" height="${bHs}"
            data-by="${by}" data-bh="${bHs}"
            fill="url(#bg${pi})" rx="3"/>`;
      // Value label on top
      s+=`<text x="${(parseFloat(bx)+bW/2).toFixed(1)}" y="${(parseFloat(by)-4).toFixed(1)}"
            text-anchor="middle" font-size="8.5" fill="rgba(255,255,255,.6)" font-family="Inter">${val}</text>`;
    });
    // Group label
    s+=`<text x="${(gx+gTot/2).toFixed(1)}" y="${H-myb+18}" text-anchor="middle"
          font-size="11" fill="rgba(255,255,255,.55)" font-family="Inter">${g}</text>`;
  });

  // Legend
  prods.forEach((p,i)=>{
    const lx=mx+i*(cw/4+2);
    s+=`<rect x="${lx}" y="${H-18}" width="10" height="10" fill="${colors[i]}" rx="2"/>`;
    s+=`<text x="${lx+13}" y="${H-8}" font-size="11" fill="rgba(255,255,255,.72)" font-family="Inter">${p}</text>`;
  });
  return s+'</svg>';
}

/* ── Chart 2: Smoothed Area + Line — MAU 增长指数 ── */
function buildLineChartSVG(){
  const W=560,H=330, mx=54,my=18,mxr=12,myb=52;
  const cw=W-mx-mxr, ch=H-my-myb;
  // Index base=100, Jan–Dec 2025, three products
  const raw={
    '飞书': [100,106,112,119,127,135,143,152,161,170,181,192],
    '钉钉': [100,101,102,103,104,104,105,106,106,107,108,108],
    'Slack': [100,103,101,106,110,113,116,118,122,120,125,128],
  };
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
  s+=`<text x="${mx}" y="${my-6}" font-size="9" fill="rgba(255,255,255,.3)" font-family="Inter">指数 (1月=100)</text>`;

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
function buildRadarGallerySVG(){
  const W=560,H=330;
  const cx=W/2-20, cy=H/2+8, r=118;
  const n=5;
  const labels=['即时通讯','视频会议','文件协作','企业生态','移动端'];
  // Estimated benchmark: each product has a characteristic strength
  const data=[
    [92,88,85,90,88],   // 飞书: strong across all
    [89,80,78,85,92],   // 钉钉: mobile-strong
    [85,82,90,70,80],   // Slack: file collab king
  ];
  const colors=['#40c4d0','#49bf8a','#df7f37'];
  const prods=['飞书','钉钉','Slack'];

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
function buildDonutSVG(){
  const W=560, H=330;
  const cx=210, cy=162, Ro=120, Ri=70;
  // Source: estimated 2026 Q1 China enterprise messaging market
  const segs=[
    {label:'钉钉',  sub:'Alibaba', v:41, c:'#49bf8a'},
    {label:'飞书',  sub:'ByteDance',v:28, c:'#40c4d0'},
    {label:'企业微信',sub:'Tencent', v:22, c:'#9259f2'},
    {label:'Slack/Teams',sub:'海外',v:9,  c:'#df7f37'},
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
  s+=`<text x="${cx}" y="${cy-14}" text-anchor="middle" font-size="28" font-weight="800" fill="white" font-family="Inter" letter-spacing="-1">市场</text>`;
  s+=`<text x="${cx}" y="${cy+10}" text-anchor="middle" font-size="13" fill="rgba(255,255,255,.45)" font-family="Inter">份额 2026</text>`;

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
  const cards = [
    {title:'竞品功能评分对比',tag:'Bar Chart',svg:buildBarChartSVG()},
    {title:'用户增长趋势',tag:'Line Chart',svg:buildLineChartSVG()},
    {title:'综合竞争力雷达',tag:'Radar Chart',svg:buildRadarGallerySVG()},
    {title:'市场份额分布',tag:'Donut Chart',svg:buildDonutSVG()},
  ];

  const track = $('gallery-track');
  track.innerHTML = cards.map(c=>`
    <div class="gallery-card" style="width:${cardW}px;height:380px">
      <div class="gallery-card-hd">
        <span class="gallery-card-title">${c.title}</span>
        <span class="gallery-card-tag">${c.tag}</span>
      </div>
      <div class="gallery-card-body">${c.svg}</div>
    </div>`).join('');

  // Initial position
  gsap.set(track, {x:0});
}

function showGalleryCard(idx){
  const vp = document.querySelector('.gallery-viewport');
  if(!vp || typeof gsap==='undefined') return;
  const cardW = vp.clientWidth || 1000;
  gsap.to($('gallery-track'),{x:-idx*cardW, duration:0.7, ease:'power3.inOut'});

  // Update nav dots
  document.querySelectorAll('.gallery-nav-dot').forEach((d,i)=>d.classList.toggle('active',i===idx));

  // Animate chart for this card
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

  if(idx===0){ // Bar chart — grow bars from baseline
    card.querySelectorAll('.gb').forEach((bar,i)=>{
      const by=parseFloat(bar.dataset.by), bh=parseFloat(bar.dataset.bh);
      gsap.fromTo(bar,
        {attr:{y:by+bh, height:0}},
        {attr:{y:by, height:bh}, duration:0.65, ease:'power3.out', delay:i*0.035}
      );
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
   Log helpers
══════════════════════════════════════ */
const AGENT_COLORS={'PM Agent':'#40c4d0','Collector':'#1eab7a','Insight':'#df7f37','Reporter':'#9259f2'};

function clearPreview(){ const p=$('log-preview'); if(p) p.style.display='none'; }
function appendLog(agent,msg,dim){
  const body=$('log-body'); clearPreview();
  const line=document.createElement('div'); line.className='log-line';
  const color=AGENT_COLORS[agent]||'#9999b2';
  line.innerHTML=`<span class="log-agent" style="color:${color}">[${esc(agent)}]</span><span class="log-msg ${dim?'log-dim':'log-bright'}">${esc(msg)}</span>`;
  body.appendChild(line); body.scrollTop=body.scrollHeight;
}
function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function setThink(show){ $('think-badge').classList.toggle('show',show); }
function setProgress(pct,s){
  $('progress-fill').style.width=pct+'%';
  $('progress-text').textContent=pct>0?T('progress')(pct,s):'';
}

/* ══════════════════════════════════════
   Submit
══════════════════════════════════════ */
async function handleSubmit(e){
  e.preventDefault();
  const product=$('input-product').value.trim();
  if(!product){ $('input-product').focus(); alert(T('errNoProduct')); return; }
  const btn=$('submit-btn'); btn.disabled=true;
  $('log-body').innerHTML=''; setThink(false); setProgress(0,0);
  const fd=new FormData();
  fd.append('target_product',product);
  fd.append('user_query',$('input-query').value.trim()||product);
  if(uploadedFile) fd.append('file',uploadedFile);
  try{
    const res=await fetch('/api/analyze',{method:'POST',body:fd});
    if(!res.ok) throw new Error('HTTP '+res.status);
    const {job_id}=await res.json();
    openSSE(job_id,btn);
  } catch(_){ simulate(btn,product); }
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
      case 'done':
        eventSource.close(); setThink(false); setProgress(100,0); btn.disabled=false;
        if(msg.pdf_path) showPdf(msg.pdf_path,msg.filename);
        else { showChartDashboard(DEMO_DATA); jumpTo('pdf-section'); }
        break;
      case 'error':
        eventSource.close(); setThink(false); btn.disabled=false; appendLog('Error',msg.message,false); break;
    }
  };
  eventSource.onerror=()=>{ eventSource.close(); btn.disabled=false; };
}

function showPdf(path,filename){
  pdfPath=path;
  $('pdf-content').innerHTML=`<iframe src="/api/report/pdf?path=${encodeURIComponent(path)}" title="PDF Report"></iframe>`;
  if(filename) $('pdf-fname').textContent=filename;
  jumpTo('pdf-section');
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
  const zh=lang==='zh';
  const steps=[
    [300,()=>setThink(true)],
    [1000,()=>{ appendLog('PM Agent',zh?'分析用户查询，制定竞品分析计划...':'Parsing query, creating plan...'); setThink(false); }],
    [600,()=>{ appendLog('PM Agent','→ initial_brief({...})',true); setProgress(8,90); }],
    [900,()=>setThink(true)],
    [800,()=>{ setThink(false); appendLog('Collector',zh?'联网搜索竞品官网...':'Searching competitor websites...'); setProgress(20,75); }],
    [600,()=>appendLog('Collector','→ web_search({ query: "target pricing 2026" })',true)],
    [900,()=>{ appendLog('Collector','← web_search (2.1KB) pricing data fetched...',true); setProgress(32,62); }],
    [600,()=>setThink(true)],
    [900,()=>{ setThink(false); appendLog('Insight',zh?'App Store 情感分析，抓取用户评论...':'App Store sentiment, crawling reviews...'); setProgress(56,38); }],
    [600,()=>appendLog('Insight','→ appstore_search({ product: "...", region: "cn" })',true)],
    [900,()=>{ appendLog('Insight','← appstore_search (3.2KB) 320 reviews',true); setProgress(68,26); }],
    [600,()=>appendLog('Insight',zh?'BERT 情感分类完成...':'BERT classification done...')],
    [700,()=>{ appendLog('Reporter',zh?'开始生成报告...':'Generating report...'); setProgress(78,18); }],
    [800,()=>{ appendLog('Reporter','→ finalize_swot({...})',true); setProgress(88,8); }],
    [1200,()=>{
      setProgress(100,0); setThink(false); btn.disabled=false;
      const d=Object.assign({},DEMO_DATA);
      if(product) d.products=[product,zh?'钉钉':'DingTalk','Slack'];
      showChartDashboard(d); jumpTo('pdf-section');
    }],
  ];
  let delay=0;
  steps.forEach(([d,fn])=>{ delay+=d; setTimeout(fn,delay); });
}

/* ══════════════════════════════════════
   Wheel scroll — section snap + gallery
══════════════════════════════════════ */
function easeInOutCubic(t){ return t<.5?4*t*t*t:1-Math.pow(-2*t+2,3)/2; }

function getSnapElements(){
  return [...document.querySelectorAll('#hero,#product,#gallery,#agents,#analyze,#pdf-section'),document.querySelector('footer')].filter(Boolean);
}
function getCurrentSnapIndex(els){
  const navH=document.querySelector('.navbar').offsetHeight;
  let idx=0;
  for(let i=els.length-1;i>=0;i--){ if(els[i].offsetTop-navH<=window.scrollY+5){ idx=i; break; } }
  return idx;
}
function scrollToEl(el){
  const html=document.documentElement;
  const navH=document.querySelector('.navbar').offsetHeight;
  const startY=window.scrollY, endY=Math.max(0,el.offsetTop-navH), dist=endY-startY;
  if(Math.abs(dist)<5){ scrollLocked=false; return; }
  html.style.setProperty('scroll-snap-type','none');
  html.style.setProperty('scroll-behavior','auto');
  const t0=performance.now();
  (function tick(now){
    const t=Math.min((now-t0)/1700,1);
    window.scrollTo(0,startY+dist*easeInOutCubic(t));
    if(t<1){ requestAnimationFrame(tick); }
    else{
      html.style.removeProperty('scroll-snap-type');
      html.style.removeProperty('scroll-behavior');
      updateNavActive(el.id);
      setTimeout(()=>{ scrollLocked=false; },100);
    }
  })(performance.now());
}

function handleWheel(e){
  if(navJumping||scrollLocked){ e.preventDefault(); return; }
  if(Math.abs(e.deltaY)<20) return;
  e.preventDefault();
  const els=getSnapElements();
  const cur=getCurrentSnapIndex(els);
  const curEl=els[cur];
  const down=e.deltaY>0;

  // Gallery intercept: when on gallery, move between cards first
  if(curEl && curEl.id==='gallery'){
    if(down){
      if(galleryIdx<GALLERY_TOTAL-1){ galleryIdx++; showGalleryCard(galleryIdx); return; }
      // Last card → go to agents
    } else {
      if(galleryIdx>0){ galleryIdx--; showGalleryCard(galleryIdx); return; }
      // First card → go back to product
    }
  }

  const next=Math.max(0,Math.min(els.length-1,cur+(down?1:-1)));
  if(next===cur) return;
  scrollLocked=true;
  // Reset gallery when leaving it
  if(curEl && curEl.id==='gallery' && next!==cur){
    galleryIdx=0;
    gsap.set($('gallery-track'),{x:0});
    document.querySelectorAll('.gallery-nav-dot').forEach((d,i)=>d.classList.toggle('active',i===0));
  }
  scrollToEl(els[next]);
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
});
