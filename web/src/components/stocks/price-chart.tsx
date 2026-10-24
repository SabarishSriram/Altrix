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

import { formatCompact, formatDate, formatPrice } from "@/lib/format";
import type { HistoryPoint } from "@/lib/types";

// Canvas colours mirror the CSS tokens in globals.css (canvas cannot read CSS variables).
const C = {
  text: "#737373",
  grid: "#f2f2f2",
  border: "#e5e5e5",
  close: "#171717",
  sma20: "#7a7a7a",
  sma50: "#2b2b2b",
  volume: "#d9d9d9",
  gain: "#16803c",
  loss: "#c8372d",
  crosshair: "#a3a3a3",
};

const priceFmt = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const toTime = (iso: string) => (Date.parse(`${iso}T00:00:00Z`) / 1000) as UTCTimestamp;

export interface PriceChartProps {
  /** Points to display (already limited to the selected timeframe), oldest first. */
  points: HistoryPoint[];
  height?: number;
  showVolume?: boolean;
  className?: string;
}

/** Close with SMA20/SMA50 overlays, the strategy's BUY/SELL crossovers and optional volume. */
export function PriceChart({ points, height = 420, showVolume = true, className }: PriceChartProps) {
  const container = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const series = useRef<{
    close: ISeriesApi<"Line">;
    sma20: ISeriesApi<"Line">;
    sma50: ISeriesApi<"Line">;
    volume: ISeriesApi<"Histogram"> | null;
    markers: ISeriesMarkersPluginApi<Time>;
  } | null>(null);
  const [hoverTime, setHoverTime] = useState<number | null>(null);

  const byTime = useMemo(() => new Map(points.map((p) => [toTime(p.date) as number, p])), [points]);

  // Create the chart once.
  useEffect(() => {
    const el = container.current;
    if (!el) return;
    const chart = createChart(el, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "#ffffff" },
        textColor: C.text,
        fontSize: 11,
        fontFamily: getComputedStyle(document.body).fontFamily,
        panes: { separatorColor: C.border, separatorHoverColor: C.grid },
      },
      grid: { vertLines: { visible: false }, horzLines: { color: C.grid } },
      rightPriceScale: { borderColor: C.border, scaleMargins: { top: 0.08, bottom: 0.06 } },
      timeScale: { borderColor: C.border, fixLeftEdge: true, fixRightEdge: true, minBarSpacing: 0.2 },
      crosshair: {
        mode: CrosshairMode.Magnet,
        vertLine: { color: C.crosshair, width: 1, style: LineStyle.Dashed, labelBackgroundColor: C.close },
        horzLine: { color: C.crosshair, width: 1, style: LineStyle.Dashed, labelBackgroundColor: C.close },
      },
      localization: { priceFormatter: (p: number) => priceFmt.format(p) },
      handleScroll: { vertTouchDrag: false },
    });
    const line = { priceLineVisible: false, crosshairMarkerVisible: false, lastValueVisible: false } as const;
    const sma50 = chart.addSeries(LineSeries, { ...line, color: C.sma50, lineWidth: 1, lineStyle: LineStyle.Dashed });
    const sma20 = chart.addSeries(LineSeries, { ...line, color: C.sma20, lineWidth: 1 });
    const close = chart.addSeries(LineSeries, {
      color: C.close,
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerRadius: 3,
      crosshairMarkerBorderColor: "#ffffff",
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
    series.current = { close, sma20, sma50, volume, markers };

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
    const line = (key: "close" | "sma20" | "sma50") =>
      points.map((p) => (p[key] === null ? { time: toTime(p.date) } : { time: toTime(p.date), value: p[key] }));
    s.close.setData(line("close"));
    s.sma20.setData(line("sma20"));
    s.sma50.setData(line("sma50"));
    s.volume?.setData(points.map((p) => (p.volume === null ? { time: toTime(p.date) } : { time: toTime(p.date), value: p.volume })));
    const markers: SeriesMarker<Time>[] = points
      .filter((p) => p.signal !== null)
      .map((p) =>
        p.signal === "BUY"
          ? { time: toTime(p.date), position: "belowBar", shape: "arrowUp", color: C.gain, size: 1 }
          : { time: toTime(p.date), position: "aboveBar", shape: "arrowDown", color: C.loss, size: 1 },
      );
    s.markers.setMarkers(markers);
    chartRef.current?.timeScale().fitContent();
  }, [points, showVolume]);

  const shown = (hoverTime !== null ? byTime.get(hoverTime) : undefined) ?? points.at(-1);

  return (
    <div className={cn("relative", className)}>
      <div className="pointer-events-none absolute top-1 left-1 z-10 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md bg-background/85 px-2 py-1 text-xs">
        {shown ? (
          <>
            <span className="num font-medium">{formatDate(shown.date, "EEE, dd MMM yyyy")}</span>
            <LegendValue label="Close" value={formatPrice(shown.close)} swatch={<Swatch color={C.close} thick />} />
            <LegendValue label="SMA20" value={formatPrice(shown.sma20)} swatch={<Swatch color={C.sma20} />} />
            <LegendValue label="SMA50" value={formatPrice(shown.sma50)} swatch={<Swatch color={C.sma50} dashed />} />
            {showVolume && <LegendValue label="Vol" value={formatCompact(shown.volume)} />}
            {shown.signal && (
              <span className={cn("font-semibold", shown.signal === "BUY" ? "text-gain" : "text-loss")}>
                {shown.signal} crossover
              </span>
            )}
          </>
        ) : null}
      </div>
      <div ref={container} style={{ height }} className="w-full" role="img" aria-label="Price chart with SMA20, SMA50 and crossover markers" />
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
