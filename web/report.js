const parts=location.pathname.split("/").filter(Boolean), reportId=parts[1], page=parts[2];
const titles={overview:"研究总览",methodology:"方法知识与任务设计",lifecycle:"发展阶段",market:"市场与竞争",business_model:"商业模式",drivers_risks:"驱动与风险",sources:"证据与边界",evaluation:"自动评测"};
const content=document.getElementById("report-content"), nav=document.getElementById("report-nav");
function node(tag,text,cls) { const item=document.createElement(tag); if(text!==undefined) item.textContent=text; if(cls) item.className=cls; return item; }
function block(title,text) { const wrap=node("section",undefined,"report-block"); wrap.append(node("h2",title),node("p",text)); return wrap; }
function list(title,items) { const wrap=node("section",undefined,"report-block"); wrap.append(node("h2",title)); const ul=node("ul"); items.forEach(item=>ul.append(node("li",item))); wrap.append(ul); return wrap; }
function linkItem(source) { const wrap=node("article",undefined,"source-entry"), a=node("a",source.title); a.href=source.url; a.target="_blank"; a.rel="noopener noreferrer"; wrap.append(a,node("small",`${source.id} · ${source.acquisition||source.domain||""} · ${source.usage||""}`)); return wrap; }
function heading(report) { content.append(node("p",`INDUSTRY INTELLIGENCE / ${page.toUpperCase()}`,"eyebrow"),node("h1",titles[page],"page-title"),node("p",`${report.industry} · ${report.region} · ${report.horizon}`,"page-subtitle")); }
function renderNav() { Object.entries(titles).forEach(([key,title])=>{ const a=node("a",title); a.href=`/reports/${encodeURIComponent(reportId)}/${key}`; if(key===page) {a.className="active"; a.setAttribute("aria-current","page");} nav.append(a); }); }
function renderOverview(report) {
  content.append(block("核心判断",report.executive_summary));
  const grid=node("div",undefined,"overview-grid");
  grid.append(block("行业边界",report.plan.industry_definition),block("阶段判断",`${report.lifecycle_stage} · 阶段指数 ${Math.round(report.lifecycle_score)}`));
  content.append(grid,list("研究假设",report.plan.hypotheses));
  const wrap=node("section",undefined,"report-block"); wrap.append(node("h2","栏目速览"));
  report.sections.forEach(section=>{ const a=node("a",`${section.title} → ${section.executive_takeaway}`,"summary-link"); a.href=`/reports/${reportId}/${section.key}`; wrap.append(a); }); content.append(wrap);
  content.append(block("阅读说明",report.mode==="demo"?"演示模式只展示研究方法和栏目结构；不得将评分视为行业统计。":"每项事实请核对 S- 行业来源；M- 方法来源只用于任务设计。"));
  if(report.session_id)content.append(block("会话与追踪",`会话 ID：${report.session_id} ｜ Trace ID：${report.trace_id}`));
  if(report.reused)content.append(block("报告复用",`已直接返回此前生成的报告，原始生成时间：${new Date(report.generated_at).toLocaleString()}。如需最新研究，请在首页选择强制重新分析。`));
  if(report.related_reports?.length)content.append(block("历史报告参考",`本次检索了 ${report.related_reports.length} 个相关行业片段；请在证据与边界页核对报告日期和原始来源。`));
}
function renderMethodology(report) {
  const guide=report.methodology_guide;
  if(!guide) {content.append(block("暂无方法知识","此报告由旧版结构生成。"));return;}
  content.append(block("方法目标",guide.objective),list("执行顺序",guide.workflow));
  const principles=node("section",undefined,"report-block"); principles.append(node("h2","方法原则"));
  guide.principles.forEach(p=>{const item=node("article",undefined,"method-item"); item.append(node("h3",p.name),node("p",p.instruction),node("small",`方法来源：${p.method_ids.join("、")||"未绑定"}`)); principles.append(item);}); content.append(principles);
  const tasks=node("section",undefined,"report-block"); tasks.append(node("h2","由方法知识派生的 SubAgent 任务"));
  report.plan.task_specs.forEach(t=>{const item=node("article",undefined,"method-item"); item.append(node("h3",`${titles[t.key]||t.key} · ${t.key}`),node("p",t.objective),node("small",`方法：${t.method_ids.join("、")} ｜ 依赖：${t.depends_on.join(" → ")}`)); const ul=node("ul"); t.evidence_needed.forEach(v=>ul.append(node("li",v))); item.append(ul); tasks.append(item);}); content.append(tasks);
  const sources=node("section",undefined,"report-block"); sources.append(node("h2","方法来源（M-）")); report.knowledge_sources.forEach(s=>sources.append(linkItem(s))); content.append(sources,list("方法边界",guide.limitations));
}
function renderSection(report) {
  const section=report.sections.find(item=>item.key===page); if(!section) {content.append(block("无内容","该栏目尚未生成。"));return;}
  content.append(block("本栏判断",section.executive_takeaway));
  const findings=node("section",undefined,"report-block"); findings.append(node("h2","关键发现"));
  section.findings.forEach(f=>{const item=node("article",undefined,"method-item"); item.append(node("h3",f.title),node("p",f.summary),node("small",`置信度：${f.confidence} ｜ 行业证据：${f.evidence.join("、")||"待补充"}`)); findings.append(item);}); content.append(findings);
  const charts=report.charts.filter(c=>c.section_key===page);
  charts.forEach(spec=>{const wrap=node("section",undefined,"report-block"); wrap.append(node("h2",spec.title)); const div=node("div",undefined,"report-chart"); wrap.append(div,node("small",spec.note)); content.append(wrap); requestAnimationFrame(()=>{if(window.echarts){const chart=echarts.init(div);chart.setOption(spec.option);window.addEventListener("resize",()=>chart.resize());}else div.textContent="图表库未加载，请检查网络连接。";});});
  if(section.metrics.length){const metrics=node("section",undefined,"report-block");metrics.append(node("h2","指标与口径"));section.metrics.forEach(m=>metrics.append(node("p",`${m.name}：${m.value} ${m.unit} · ${m.is_estimate?"分析性估算":"来源 "+m.source_ids.join("、")}`)));content.append(metrics);}
  content.append(list("建议动作",section.recommendations));
}
function renderSources(report) {
  const wrap=node("section",undefined,"report-block");wrap.append(node("h2","行业事实来源（S-）"));
  if(!report.sources.length) wrap.append(node("p","当前无行业事实来源。方法来源不可以替代行业事实。"));
  report.sources.forEach(s=>wrap.append(linkItem(s)));content.append(wrap,list("限制",report.limitations),list("研究方法说明",report.methodology));
  if(report.related_reports?.length){const historical=node("section",undefined,"report-block");historical.append(node("h2","历史行业报告参考（R-）"));
    report.related_reports.forEach(ref=>{const item=node("article",undefined,"source-entry"),a=node("a",`${ref.industry} · ${ref.section_key}`);a.href=`/reports/${encodeURIComponent(ref.report_id)}/overview`;item.append(a,node("small",`${ref.id} · 报告时间 ${new Date(ref.generated_at).toLocaleString()} · 匹配评分 ${ref.score}`),node("p",ref.excerpt));
      ref.source_urls.forEach(url=>{const source=node("a",url);source.href=url;source.target="_blank";source.rel="noopener noreferrer";item.append(source,node("br"));});historical.append(item);});content.append(historical);}
}
async function renderEvaluation(report) {
  const headers={};const key=sessionStorage.getItem("industry-api-key");if(key)headers["X-API-Key"]=key;
  const response=await fetch(`/api/reports/${reportId}/evaluation`,{headers});
  if(!response.ok){content.append(block("无法读取评测",`HTTP ${response.status}，请检查访问凭证。`));return;}
  const result=await response.json();content.append(block("总体结果",`${Math.round(result.overall_score*100)} 分 · ${result.passed?"通过":"未通过"}`));
  const wrap=node("section",undefined,"report-block");wrap.append(node("h2","分项指标"));
  result.metrics.forEach(m=>{const row=node("div",undefined,"eval-row");row.append(node("span",m.detail),node("strong",`${Math.round(m.score*100)} 分`));wrap.append(row);});content.append(wrap,list("改进建议",result.suggestions));
}
async function loadReport() {
  renderNav();const cached=sessionStorage.getItem(`industry-report-${reportId}`);let report=cached?JSON.parse(cached):null;
  if(!report){const headers={};const key=sessionStorage.getItem("industry-api-key");if(key)headers["X-API-Key"]=key;
    const response=await fetch(`/api/reports/${reportId}`,{headers});if(!response.ok)throw new Error(`报告不可访问（HTTP ${response.status}）`);report=await response.json();}
  document.title=`${titles[page]} · ${report.industry}`;
  document.getElementById("report-context").textContent=`${report.industry} · ${new Date(report.generated_at).toLocaleString()}`;
  document.getElementById("report-mode").textContent=report.mode==="demo"?"演示模式":"证据模式";
  heading(report);
  if(page==="overview")renderOverview(report);else if(page==="methodology")renderMethodology(report);
  else if(page==="sources")renderSources(report);else if(page==="evaluation")await renderEvaluation(report);
  else renderSection(report);
}
loadReport().catch(error=>content.append(block("加载失败",error.message)));
