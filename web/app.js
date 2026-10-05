const $ = (id) => document.getElementById(id);
const names = { knowledge_acquisition: "方法知识获取", task_planning: "任务规划", lifecycle: "发展阶段", market: "市场竞争", business_model: "商业模式", drivers_risks: "驱动与风险", chart: "图表生成", main_agent: "主 Agent 汇总" };
function headers() { const result = {"Content-Type":"application/json"}; const key = $("api-key").value.trim(); if (key) result["X-API-Key"] = key; return result; }
function progress(percent,label) { $("progress-bar").style.width = `${percent}%`; $("progress-label").textContent = label; }
function markAgent(key,done) { let node = document.querySelector(`[data-agent="${key}"]`); if (!node) { node = document.createElement("span"); node.className="agent-pill"; node.dataset.agent=key; node.textContent=names[key]||key; $("agent-list").append(node); } if(done) node.classList.add("done"); }
function handle(event,data) {
  if(event==="agent.started") markAgent(data.agent,false);
  if(event==="agent.completed") markAgent(data.agent,true);
  if(event==="knowledge.acquired") progress(18,`已获取 ${data.count} 个方法来源`);
  if(event==="plan.ready") progress(32,"分析任务已规划");
  if(event==="sources.collected") progress(45,`已获取 ${data.count} 个行业来源`);
  if(event==="rag.retrieved") progress(10,`已检索 ${data.count} 个历史报告参考片段`);
  if(event==="report.reused") progress(95,"命中已有行业报告，无需重复分析");
  if(event==="agent.completed" && data.agent==="chart") progress(90,"报告即将完成");
  if(event==="report") {
    progress(100,"报告已生成，正在打开总览子页");
    sessionStorage.setItem(`industry-report-${data.report_id}`,JSON.stringify(data));
    const key=$("api-key").value.trim(); if(key) sessionStorage.setItem("industry-api-key",key);
    window.location.assign(`/reports/${encodeURIComponent(data.report_id)}/overview`);
  }
  if(event==="error") throw new Error(data.message||"生成失败");
}
async function consume(response) {
  const reader=response.body.getReader(),decoder=new TextDecoder(); let buffer="";
  while(true) { const {value,done}=await reader.read(); buffer+=decoder.decode(value||new Uint8Array(),{stream:!done});
    const blocks=buffer.split("\n\n"); buffer=blocks.pop();
    for(const block of blocks) { let event="message",data=""; block.split("\n").forEach(line=>{if(line.startsWith("event:")) event=line.slice(6).trim(); if(line.startsWith("data:")) data+=line.slice(5).trim();}); if(data) handle(event,JSON.parse(data)); }
    if(done) break;
  }
}
$("research-form").addEventListener("submit",async event=>{
  event.preventDefault(); $("submit").disabled=true; $("progress").classList.remove("hidden"); $("agent-list").replaceChildren(); progress(5,"正在启动方法知识获取 Agent");
  const payload={industry:$("industry").value,region:$("region").value,horizon:$("horizon").value,anchor_sites:$("anchors").value.split(",").map(v=>v.trim()).filter(Boolean),question:$("question").value,session_id:$("session-id").value.trim()||null,use_memory:$("use-memory").checked,use_rag:$("use-rag").checked,force_refresh:$("force-refresh").checked};
  try { const response=await fetch("/api/reports/stream",{method:"POST",headers:headers(),body:JSON.stringify(payload)});
    if(!response.ok) { const body=await response.json().catch(()=>({})); throw new Error(body.detail||`HTTP ${response.status}`); }
    await consume(response);
  } catch(error) { progress(100,`失败：${error.message}`); } finally { $("submit").disabled=false; }
});
fetch("/api/health").then(r=>r.json()).then(data=>{$("mode").textContent=data.mode==="demo"?"DEMO MODE":"LIVE READY";}).catch(()=>{$("mode").textContent="OFFLINE";});
