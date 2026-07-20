"use client";

import dynamic from "next/dynamic";
import type { EquilibriumPoint } from "@/lib/types";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

export function VleChart({ points, pressure, temperature, model, calculationType }: { points: EquilibriumPoint[]; pressure?: number | null; temperature?: number | null; model: string; calculationType: string }) {
  if (!points.length) return <div className="empty-chart">当前结果不包含曲线点。</div>;
  const liquid = points.map((point) => point.liquid_composition[0]);
  const vapor = points.map((point) => point.vapor_composition[0]);
  const isIsothermal = calculationType === "isothermal_vle";
  const ordinate = points.map((point) => isIsothermal ? point.pressure_kPa : point.temperature_K);
  const condition = isIsothermal ? `${temperature?.toFixed(3) ?? "—"} K` : `${pressure?.toFixed(3) ?? "—"} kPa`;
  return (
    <div aria-label="VLE相图" data-testid="vle-chart">
      <Plot
        data={[
          { x: liquid, y: ordinate, type: "scatter", mode: "lines+markers", name: "液相 x₁", line: { color: "#2dd4bf", width: 3 } },
          { x: vapor, y: ordinate, type: "scatter", mode: "lines+markers", name: "气相 y₁", line: { color: "#fb923c", width: 3 } },
        ]}
        layout={{
          autosize: true,
          height: 390,
          margin: { l: 64, r: 24, t: 46, b: 58 },
          title: { text: `${model} · ${condition}` },
          xaxis: { title: { text: "苯摩尔分数 x₁ / y₁" }, range: [0, 1], gridcolor: "#dbe4ec" },
          yaxis: { title: { text: isIsothermal ? "压力 / kPa" : "温度 / K" }, gridcolor: "#dbe4ec" },
          paper_bgcolor: "rgba(0,0,0,0)",
          plot_bgcolor: "#f8fafc",
          font: { family: "Inter, system-ui, sans-serif", color: "#243244" },
          legend: { orientation: "h", y: 1.12 },
        }}
        config={{ responsive: true, displaylogo: false, toImageButtonOptions: { filename: "thermoequi-vle" } }}
        style={{ width: "100%" }}
      />
    </div>
  );
}
