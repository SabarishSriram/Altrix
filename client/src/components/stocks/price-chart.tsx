"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type MouseEventParams,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { cn } from "cn";
import { useTheme } from "next-themes";

import { CANVAS_COLORS, type CanvasColors } from "@/lib/chart-theme";
import { formatCompact, formatDate, formatPrice } from "@/lib/format";
import type { HistoryPoint } from "@/lib/types";

/** Chart, series and crosshair colours for one theme (canvas cannot read CSS variables). */
function chartColors(C: CanvasColors) {
  return {
    layout: {
      background: { type: ColorType.Solid, color: C.surface },
      textColor: C.text,
      panes: { separatorColor: C.border, separatorHoverColor: C.grid },
    },
    grid: { vertLines: { visible: false }, horzLines: { color: C.grid } },
    rightPriceScale: { borderColor: C.border },
    timeScale: { borderColor: C.border },
    crosshair: {
      vertLine: { color: C.crosshair, labelBackgroundColor: C.close },
      horzLine: { color: C.crosshair, labelBackgroundColor: C.close },
    },
  };
}

function markerList(points: HistoryPoint[], C: CanvasColors): SeriesMarker<Time>[] {
  return points
    .filter((p) => p.signal !== null)
    .map((p) =>
      p.signal === "BUY"
        ? { time: toTime(p.date), position: "belowBar", shape: "arrowUp", color: C.gain, size: 1 }
        : { time: toTime(p.date), position: "aboveBar", shape: "arrowDown", color: C.loss, size: 1 },
    );
}

const priceFmt = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const toTime = (iso: string) => (Date.parse(`${iso}T00:00:00Z`) / 1000) as UTCTimestamp;

export interface PriceChartProps {
  /** Points to display (already limited to the selected timeframe), oldest first. */
  points: HistoryPoint[];
  height?: number;
  showVolume?: boolean;
  className?: string;
}

/** Close with EMA20/EMA50 overlays, the strategy's BUY/SELL crossovers and optional volume. */
export function PriceChart({ points, height = 420, showVolume = true, className }: PriceChartProps) {
  const container = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const series = useRef<{
    close: ISeriesApi<"Line">;
    ema20: ISeriesApi<"Line">;
    ema50: ISeriesApi<"Line">;
    volume: ISeriesApi<"Histogram"> | null;
    markers: ISeriesMarkersPluginApi<Time>;
  } | null>(null);
  const [hoverTime, setHoverTime] = useState<number | null>(null);
  const { resolvedTheme } = useTheme();
  const C = CANVAS_COLORS[resolvedTheme === "dark" ? "dark" : "light"];
  const colorsRef = useRef(C); // read by the create/data effects below; declared first so it syncs first
  useEffect(() => {
    colorsRef.current = C;
  });

  const byTime = useMemo(() => new Map(points.map((p) => [toTime(p.date) as number, p])), [points]);

  // Create the chart once.
  useEffect(() => {
    const el = container.current;
    if (!el) return;
    const C = colorsRef.current;
    const themed = chartColors(C);
    const chart = createChart(el, {
      autoSize: true,
      layout: { ...themed.layout, fontSize: 11, fontFamily: getComputedStyle(document.body).fontFamily },
      grid: themed.grid,
      rightPriceScale: { ...themed.rightPriceScale, scaleMargins: { top: 0.08, bottom: 0.06 } },
      timeScale: { ...themed.timeScale, fixLeftEdge: true, fixRightEdge: true, minBarSpacing: 0.2 },
      crosshair: {
        mode: CrosshairMode.Magnet,
        vertLine: { ...themed.crosshair.vertLine, width: 1, style: LineStyle.Dashed },
        horzLine: { ...themed.crosshair.horzLine, width: 1, style: LineStyle.Dashed },
      },
      localization: { priceFormatter: (p: number) => priceFmt.format(p) },
      handleScroll: { vertTouchDrag: false },
    });
    const line = { priceLineVisible: false, crosshairMarkerVisible: false, lastValueVisible: false } as const;
    const ema50 = chart.addSeries(LineSeries, { ...line, color: C.ema50, lineWidth: 1, lineStyle: LineStyle.Dashed });
    const ema20 = chart.addSeries(LineSeries, { ...line, color: C.ema20, lineWidth: 1 });
    const close = chart.addSeries(LineSeries, {
      color: C.close,
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerRadius: 3,
      crosshairMarkerBorderColor: C.surface,
      crosshairMarkerBackgroundColor: C.close,
    });
    let volume: ISeriesApi<"Histogram"> | null = null;
    if (showVolume) {
      volume = chart.addSeries(
        HistogramSeries,
        { color: C.volume, priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false },
        1,
      );
      chart.panes()[0]?.setStretchFactor(4);
      chart.panes()[1]?.setStretchFactor(1);
    }
    const markers = createSeriesMarkers(close, []);
    chartRef.current = chart;
    series.current = { close, ema20, ema50, volume, markers };

    const onMove = (param: MouseEventParams<Time>) => {
      setHoverTime(typeof param.time === "number" ? param.time : null);
    };
    chart.subscribeCrosshairMove(onMove);
    return () => {
      chart.unsubscribeCrosshairMove(onMove);
      chart.remove();
      chartRef.current = null;
      series.current = null;
    };
  }, [showVolume]);

  // Push data whenever the points (timeframe) change.
  useEffect(() => {
    const s = series.current;
    if (!s) return;
    const line = (key: "close" | "ema20" | "ema50") =>
      points.map((p) => (p[key] === null ? { time: toTime(p.date) } : { time: toTime(p.date), value: p[key] }));
    s.close.setData(line("close"));
    s.ema20.setData(line("ema20"));
    s.ema50.setData(line("ema50"));
    s.volume?.setData(points.map((p) => (p.volume === null ? { time: toTime(p.date) } : { time: toTime(p.date), value: p.volume })));
    s.markers.setMarkers(markerList(points, colorsRef.current));
    chartRef.current?.timeScale().fitContent();
  }, [points, showVolume]);

  // Recolour in place when the theme changes (no re-creation, so zoom and scroll are kept).
  useEffect(() => {
    const s = series.current;
    const chart = chartRef.current;
    if (!s || !chart) return;
    chart.applyOptions(chartColors(C));
    s.close.applyOptions({ color: C.close, crosshairMarkerBackgroundColor: C.close, crosshairMarkerBorderColor: C.surface });
    s.ema20.applyOptions({ color: C.ema20 });
    s.ema50.applyOptions({ color: C.ema50 });
    s.volume?.applyOptions({ color: C.volume });
    s.markers.setMarkers(markerList(points, C));
  }, [C, points]);

  const shown = (hoverTime !== null ? byTime.get(hoverTime) : undefined) ?? points.at(-1);

  return (
    <div className={cn("relative", className)}>
      <div className="pointer-events-none absolute top-1 left-1 z-10 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md bg-background/85 px-2 py-1 text-xs">
        {shown ? (
          <>
            <span className="num font-medium">{formatDate(shown.date, "EEE, dd MMM yyyy")}</span>
            <LegendValue label="Close" value={formatPrice(shown.close)} swatch={<Swatch color={C.close} thick />} />
            <LegendValue label="EMA20" value={formatPrice(shown.ema20)} swatch={<Swatch color={C.ema20} />} />
            <LegendValue label="EMA50" value={formatPrice(shown.ema50)} swatch={<Swatch color={C.ema50} dashed />} />
            {showVolume && <LegendValue label="Vol" value={formatCompact(shown.volume)} />}
            {shown.signal && (
              <span className={cn("font-semibold", shown.signal === "BUY" ? "text-gain" : "text-loss")}>
                {shown.signal} crossover
              </span>
            )}
          </>
        ) : null}
      </div>
      <div ref={container} style={{ height }} className="w-full" role="img" aria-label="Price chart with EMA20, EMA50 and crossover markers" />
    </div>
  );
}

function LegendValue({ label, value, swatch }: { label: string; value: string; swatch?: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      {swatch}
      <span className="text-muted-foreground">{label}</span>
      <span className="num font-medium">{value}</span>
    </span>
  );
}

function Swatch({ color, dashed, thick }: { color: string; dashed?: boolean; thick?: boolean }) {
  return (
    <span
      aria-hidden
      className="inline-block w-3"
      style={{ borderTop: `${thick ? 2 : 1.5}px ${dashed ? "dashed" : "solid"} ${color}` }}
    />
  );
}
