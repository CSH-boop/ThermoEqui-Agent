"use client";

import { FormEvent, useMemo, useState } from "react";
import { exportUrl, rerunTask, sendChat } from "@/lib/api";
import type { AgentStep, CalculationEnvelope, ChatResponse, TaskManifest } from "@/lib/types";
import { VleChart } from "./VleChart";

type Tab = "chart" | "table" | "model" | "parameters" | "validation" | "runs";

const examples = [
  "计算苯-甲苯在101.325 kPa下的T-x-y曲线",
  "NRTL和Peng-Robinson有什么区别？",
  "计算氯化钠水溶液的电解质相平衡",
];

export function Workbench() {
  const [messages, setMessages] = useState<Array<{ role: "user" | "agent"; text: string }>>([
    { role: "agent", text: "描述物系与工况。我会先结构化任务，再由确定性内核计算并验证。" },
  ]);
  const [input, setInput] = useState(examples[0]);
  const [conversationId, setConversationId] = useState<string>();
  const [task, setTask] = useState<TaskManifest>();
  const [calculation, setCalculation] = useState<CalculationEnvelope>();
  const [runs, setRuns] = useState<CalculationEnvelope[]>([]);
  const [executionSteps, setExecutionSteps] = useState<AgentStep[]>([]);
  const [activeTab, setActiveTab] = useState<Tab>("chart");
  const [loading, setLoading] = useState(false);
  const [diagnostic, setDiagnostic] = useState<string>();

  const risk = useMemo(() => {
    if (!calculation) return "待计算";
    if (calculation.validation.overall_status === "failed") return "高风险";
    if (calculation.validation.overall_status === "warning") return "需复核";
    return "低风险";
  }, [calculation]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!input.trim() || loading) return;
    const message = input.trim();
    setMessages((current) => [...current, { role: "user", text: message }]);
    setLoading(true);
    setDiagnostic(undefined);
    try {
      const response: ChatResponse = await sendChat(message, conversationId);
      setConversationId(response.conversation_id);
      setExecutionSteps(response.execution_steps);
      setMessages((current) => [...current, { role: "agent", text: response.answer }]);
      if (response.task) setTask(response.task);
      if (response.calculation) {
        setCalculation(response.calculation);
        setRuns((current) => [...current, response.calculation!]);
        setActiveTab("chart");
      } else if (response.statements.some((item) => item.category === "Warning")) {
        setDiagnostic(response.statements.map((item) => item.text).join(" "));
      }
    } catch (error) {
      setDiagnostic(error instanceof Error ? error.message : "未知错误");
    } finally {
      setLoading(false);
    }
  }

  async function rerun() {
    if (!task || loading) return;
    setLoading(true);
    setDiagnostic(undefined);
    try {
      const next = await rerunTask(task);
      setCalculation(next);
      setRuns((current) => [...current, next]);
      setMessages((current) => [...current, { role: "agent", text: "已按面板条件创建新的计算运行。" }]);
    } catch (error) {
      setDiagnostic(error instanceof Error ? error.message : "重新计算失败");
    } finally {
      setLoading(false);
    }
  }

  function updatePressure(value: string) {
    if (!task) return;
    const pressure = Number(value);
    setTask({ ...task, conditions: { ...task.conditions, pressure_kPa: Number.isFinite(pressure) ? pressure : null } });
  }

  function updateTemperature(value: string) {
    if (!task) return;
    const temperature = Number(value);
    setTask({ ...task, conditions: { ...task.conditions, temperature_K: Number.isFinite(temperature) ? temperature : null } });
  }

  function updateComposition(value: string) {
    if (!task) return;
    const parsed = value.split(",").map((item) => Number(item.trim()));
    const composition = parsed.length && parsed.every(Number.isFinite) ? parsed : null;
    const field = task.calculation_type === "tp_flash" ? "feed_composition" : task.calculation_type === "dew_point" ? "vapor_composition" : "liquid_composition";
    setTask({ ...task, conditions: { ...task.conditions, [field]: composition } });
  }

  function updateModel(value: string) {
    if (task) setTask({ ...task, model_name: value });
  }

  const tabs: Array<{ id: Tab; label: string }> = [
    { id: "chart", label: "相图" }, { id: "table", label: "数据表" }, { id: "model", label: "模型卡" },
    { id: "parameters", label: "参数来源" }, { id: "validation", label: "验证报告" }, { id: "runs", label: "执行记录" },
  ];

  return (
    <main className="app-shell">
      <header className="topbar">
        <div><span className="brand-mark">TE</span><div><h1>ThermoEqui-Agent</h1><p>PHASE EQUILIBRIUM ENGINEERING WORKBENCH</p></div></div>
        <div className="runtime"><span className="status-dot" />确定性内核在线 <span>v0.1.0</span></div>
      </header>

      <aside className="sidebar">
        <p className="eyebrow">任务模板</p>
        {examples.map((example, index) => <button key={example} onClick={() => setInput(example)}><span>0{index + 1}</span>{example}</button>)}
        <div className="scope-card"><p className="eyebrow">当前边界</p><strong>非电解质 · 分子体系</strong><small>VLE / Flash / 泡露点 / 共沸搜索</small></div>
      </aside>

      <section className="conversation">
        <div className="section-heading"><div><p className="eyebrow">Conversation</p><h2>工程对话</h2></div><span>{conversationId ? "会话已保存" : "新会话"}</span></div>
        <div className="messages" aria-live="polite">
          {messages.map((message, index) => <article className={message.role} key={`${message.role}-${index}`}><label>{message.role === "agent" ? "AGENT" : "YOU"}</label><p>{message.text}</p></article>)}
          {loading && <article className="agent"><label>ENGINE</label><p>正在结构化任务、求解并执行物理校验…</p></article>}
        </div>
        <form onSubmit={submit} className="composer"><textarea aria-label="任务输入" value={input} onChange={(event) => setInput(event.target.value)} /><button disabled={loading}>运行任务 <span>↗</span></button></form>
      </section>

      <aside className="task-panel">
        <div className="section-heading"><div><p className="eyebrow">Task manifest</p><h2>当前任务</h2></div><span className={`risk ${risk}`}>{risk}</span></div>
        <dl className="facts">
          <div><dt>物系</dt><dd>{task?.components.map((item) => item.name).join(" / ") ?? "—"}</dd></div>
          <div><dt>任务</dt><dd>{task?.calculation_type ?? "—"}</dd></div>
          <div><dt>模型</dt><dd>{calculation?.result.model_name ?? task?.model_name ?? "待路由"}</dd></div>
          <div><dt>计算</dt><dd>{calculation?.result.converged ? "已收敛" : "待运行"}</dd></div>
          <div><dt>验证</dt><dd>{calculation?.validation.overall_status ?? "待验证"}</dd></div>
        </dl>
        {executionSteps.length > 0 && (
          <section className="execution-trace" aria-label="Agent execution trace">
            <p className="eyebrow">Plan · Execute · Validate</p>
            {executionSteps.map((step) => (
              <article key={`${step.phase}-${step.tool_name ?? "provider"}`}>
                <span className={`step-status ${step.status}`} />
                <div>
                  <strong>{step.phase}</strong>
                  {step.tool_name && <code>{step.tool_name}</code>}
                  <p>{step.summary}</p>
                </div>
              </article>
            ))}
          </section>
        )}
        <label className="field">模型<select aria-label="热力学模型" value={task?.model_name ?? "Ideal/Raoult"} onChange={(event) => updateModel(event.target.value)}><option>Ideal/Raoult</option><option>Wilson</option><option>NRTL</option><option>UNIQUAC</option><option>Peng-Robinson</option></select></label>
        <label className="field">压力 / kPa<input aria-label="压力 kPa" type="number" step="0.001" min="0.001" value={task?.conditions.pressure_kPa ?? ""} onChange={(event) => updatePressure(event.target.value)} /></label>
        <label className="field">温度 / K<input aria-label="温度 K" type="number" step="0.01" min="0.01" value={task?.conditions.temperature_K ?? ""} onChange={(event) => updateTemperature(event.target.value)} /></label>
        <label className="field">组成（逗号分隔）<input aria-label="摩尔组成" value={(task?.conditions.feed_composition ?? task?.conditions.vapor_composition ?? task?.conditions.liquid_composition ?? []).join(", ")} onChange={(event) => updateComposition(event.target.value)} placeholder="0.5, 0.5" /></label>
        <button className="rerun" onClick={rerun} disabled={!task || loading}>按当前条件重新计算</button>
        {diagnostic && <div className="diagnostic" role="alert"><strong>诊断信息</strong><p>{diagnostic}</p></div>}
        {calculation?.result.warnings.length ? <div className="diagnostic warning"><strong>适用域警告</strong><p>{calculation.result.warnings[0]}</p></div> : null}
      </aside>

      <section className="results">
        <nav aria-label="结果视图">{tabs.map((tab) => <button key={tab.id} className={activeTab === tab.id ? "active" : ""} onClick={() => setActiveTab(tab.id)}>{tab.label}</button>)}</nav>
        <div className="result-body">
          {!calculation && <div className="empty"><span>∿</span><h3>等待确定性计算结果</h3><p>选择示例或输入一个带组分和工况的任务。</p></div>}
          {calculation && activeTab === "chart" && <VleChart points={calculation.result.points} pressure={calculation.result.pressure_kPa} temperature={calculation.result.temperature_K} model={calculation.result.model_name} calculationType={calculation.result.calculation_type} />}
          {calculation && activeTab === "table" && <div className="table-wrap"><table><thead><tr><th>T / K</th><th>P / kPa</th><th>x₁</th><th>y₁</th><th>残差</th></tr></thead><tbody>{calculation.result.points.map((point, index) => <tr key={index}><td>{point.temperature_K.toFixed(4)}</td><td>{point.pressure_kPa.toFixed(3)}</td><td>{point.liquid_composition[0].toFixed(5)}</td><td>{point.vapor_composition[0].toFixed(5)}</td><td>{point.equilibrium_residual.toExponential(2)}</td></tr>)}</tbody></table></div>}
          {calculation && activeTab === "model" && <div className="cards">{calculation.model_recommendations.slice(0, 3).map((item) => <article key={item.model_name}><span>{item.executable ? "可执行" : "候选/受阻"}</span><h3>{item.model_name}</h3><strong>{item.score.toFixed(1)} 分</strong><p>{item.reasons.join(" ")}</p></article>)}</div>}
          {calculation && activeTab === "parameters" && <div className="cards">{calculation.parameter_sources.map((source, index) => <article key={index}><span>Database</span><h3>{source.component}</h3><p>{source.property}</p><a href={source.source_identifier} target="_blank" rel="noreferrer">{source.source_title}</a><small>{source.temperature_range_K} K</small></article>)}</div>}
          {calculation && activeTab === "validation" && <div className="validation-grid">{Object.entries(calculation.validation).filter(([, value]) => typeof value === "object" && value && "passed" in value).map(([key, value]) => { const check = value as { passed: boolean; message: string; metric?: number }; return <article key={key}><span className={check.passed ? "pass" : "fail"}>{check.passed ? "PASS" : "CHECK"}</span><h3>{key.replaceAll("_", " ")}</h3><p>{check.message}</p><small>metric: {check.metric?.toExponential(3) ?? "—"}</small></article>; })}</div>}
          {calculation && activeTab === "runs" && <div className="runs">{runs.map((run, index) => <article key={run.result.run_id}><span>RUN {String(index + 1).padStart(2, "0")}</span><div><strong>{run.result.run_id.slice(0, 8)}</strong><p>{run.result.model_name} · {run.result.pressure_kPa?.toFixed(3) ?? "—"} kPa</p></div><span className={run.validation.overall_status}>{run.validation.overall_status}</span></article>)}</div>}
        </div>
        {calculation && <footer><span>Run {calculation.result.run_id}</span><div><a href={exportUrl(calculation.result.run_id, "json")}>下载 JSON</a><a href={exportUrl(calculation.result.run_id, "csv")}>下载 CSV</a></div></footer>}
      </section>
    </main>
  );
}
