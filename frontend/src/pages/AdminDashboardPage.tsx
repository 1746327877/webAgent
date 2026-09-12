import { useEffect, useMemo, useRef, useState } from "react";
import * as echarts from "echarts";
import { useMetricsOverview, type MetricsOverview } from "@/api/admin";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

const RANGES = [
  { label: "24 小时", hours: 24 },
  { label: "7 天", hours: 168 },
  { label: "30 天", hours: 720 },
];

const CARD_DEFS: [keyof MetricsOverview["cards"], string][] = [
  ["llm_calls", "LLM 调用"],
  ["prompt_tokens", "Prompt Token"],
  ["completion_tokens", "Completion Token"],
  ["errors", "错误数"],
  ["error_rate", "错误率 %"],
  ["p95_ms", "P95 延迟 ms"],
  ["model_switches", "模型切换"],
  ["switch_ms", "切换耗时 ms"],
  ["tool_calls", "工具调用"],
  ["retrieval_calls", "检索次数"],
  ["gpu_ms", "GPU 时间 ms"],
  ["http_requests", "HTTP 请求"],
];

function fmt(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function shortTime(ts: string): string {
  return ts.slice(5, 16).replace("T", " ");
}

function Chart({
  label,
  option,
  height = 240,
}: {
  label: string;
  option: echarts.EChartsOption;
  height?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chartRef.current = chart;
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    chartRef.current?.setOption(option, true);
  }, [option]);

  return <div ref={ref} role="img" aria-label={label} style={{ height, width: "100%" }} />;
}

export default function AdminDashboardPage() {
  const [hours, setHours] = useState(24);
  const { data, isLoading, error } = useMetricsOverview(hours);

  const trendOption = useMemo<echarts.EChartsOption>(() => {
    const series = data?.series ?? [];
    return {
      tooltip: { trigger: "axis" },
      legend: { data: ["LLM 调用", "Prompt Token", "Completion Token"] },
      grid: { left: 56, right: 64, top: 40, bottom: 28 },
      xAxis: { type: "category", boundaryGap: false, data: series.map((d) => shortTime(d.hour)) },
      yAxis: [
        { type: "value", name: "调用" },
        { type: "value", name: "Token" },
      ],
      series: [
        { name: "LLM 调用", type: "line", smooth: true, data: series.map((d) => d.llm_calls) },
        {
          name: "Prompt Token",
          type: "line",
          smooth: true,
          yAxisIndex: 1,
          data: series.map((d) => d.prompt_tokens),
        },
        {
          name: "Completion Token",
          type: "line",
          smooth: true,
          yAxisIndex: 1,
          data: series.map((d) => d.completion_tokens),
        },
      ],
    };
  }, [data]);

  const agentsOption = useMemo<echarts.EChartsOption>(() => {
    const rows = data?.agents ?? [];
    return {
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: 112, right: 32, top: 16, bottom: 28 },
      xAxis: { type: "value" },
      yAxis: { type: "category", data: rows.map((a) => a.name ?? a.agent_id).reverse() },
      series: [{ name: "Token", type: "bar", data: rows.map((a) => a.tokens).reverse() }],
    };
  }, [data]);

  const modelsOption = useMemo<echarts.EChartsOption>(() => {
    const rows = data?.models ?? [];
    return {
      tooltip: { trigger: "item" },
      legend: { bottom: 0 },
      series: [
        {
          name: "Token 分布",
          type: "pie",
          radius: ["38%", "66%"],
          data: rows.map((m) => ({ name: m.model, value: m.tokens })),
        },
      ],
    };
  }, [data]);

  const vramOption = useMemo<echarts.EChartsOption>(() => {
    const rows = data?.vram ?? [];
    return {
      tooltip: { trigger: "axis" },
      grid: { left: 64, right: 24, top: 24, bottom: 28 },
      xAxis: { type: "category", boundaryGap: false, data: rows.map((v) => shortTime(v.ts)) },
      yAxis: { type: "value", name: "MB" },
      series: [
        {
          name: "显存",
          type: "line",
          smooth: true,
          areaStyle: {},
          data: rows.map((v) => v.vram_mb),
        },
      ],
    };
  }, [data]);

  const cards = data?.cards;

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="mx-auto max-w-6xl space-y-4 p-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="text-xl font-semibold">📊 可观测性</h1>
          <div className="flex gap-1">
            {RANGES.map((range) => (
              <Button
                key={range.hours}
                size="sm"
                variant={hours === range.hours ? "default" : "outline"}
                onClick={() => setHours(range.hours)}
              >
                {range.label}
              </Button>
            ))}
          </div>
        </div>

        {isLoading && <p className="text-sm text-muted-foreground">加载中…</p>}
        {error && <p className="text-sm text-red-500">{error.message}</p>}

        {cards && (
          <>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
              {CARD_DEFS.map(([key, label]) => (
                <Card key={key} size="sm">
                  <CardContent>
                    <p className="text-xs text-muted-foreground">{label}</p>
                    <div
                      data-testid={`card-${key}`}
                      className="mt-1 text-lg font-semibold tabular-nums"
                    >
                      {fmt(cards[key])}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>

            {cards.llm_calls === 0 ? (
              <Card>
                <CardContent className="py-10 text-center text-sm text-muted-foreground">
                  暂无调用数据
                </CardContent>
              </Card>
            ) : (
              <div className="grid gap-3 lg:grid-cols-2">
                <Card>
                  <CardContent>
                    <p className="mb-2 text-sm font-medium">请求与 Token 趋势</p>
                    <Chart label="请求与 Token 趋势" option={trendOption} />
                  </CardContent>
                </Card>
                <Card>
                  <CardContent>
                    <p className="mb-2 text-sm font-medium">智能体活跃排行</p>
                    <Chart label="智能体活跃排行" option={agentsOption} />
                  </CardContent>
                </Card>
                <Card>
                  <CardContent>
                    <p className="mb-2 text-sm font-medium">Token 分布</p>
                    <Chart label="Token 分布" option={modelsOption} />
                  </CardContent>
                </Card>
                <Card>
                  <CardContent>
                    <p className="mb-2 text-sm font-medium">显存曲线</p>
                    <Chart label="显存曲线" option={vramOption} />
                  </CardContent>
                </Card>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
