import { useEffect, useRef } from "react";

const BAR_WIDTH = 4;
const BAR_GAP = 4;

/**
 * Bars that follow the audio level while `analyser` is feeding data ("speaking" or "listening"),
 * and a gentle synthetic motion otherwise ("thinking", "idle").
 */
export default function Waveform({ analyser, mode, height = 96 }) {
  const canvasRef = useRef(null);
  const live = useRef({ analyser, mode });
  live.current = { analyser, mode };

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas.getContext("2d");
    const styles = getComputedStyle(document.documentElement);
    const active = styles.getPropertyValue("--accent").trim();
    const resting = styles.getPropertyValue("--border-strong").trim();
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let width = 0;
    let frame = 0;
    let bins = null;
    let levels = [];

    const resize = () => {
      const ratio = window.devicePixelRatio || 1;
      width = canvas.clientWidth;
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    resize();

    const targetLevel = (index, count, time, { analyser: node, mode: current }) => {
      const centre = count / 2;
      const distance = Math.abs(index - centre) / centre; // 0 in the middle, 1 at the edges

      if (node && (current === "speaking" || current === "listening")) {
        bins = bins?.length === node.frequencyBinCount ? bins : new Uint8Array(node.frequencyBinCount);
        node.getByteFrequencyData(bins);
        const usable = Math.floor(bins.length * 0.55); // most of a voice sits in the lower bins
        const value = bins[Math.min(usable - 1, Math.floor(distance * usable))] / 255;
        return Math.min(1, value * (1.15 - distance * 0.35));
      }
      if (current === "speaking") return reduced ? 0.3 : 0.12 + 0.4 * Math.abs(Math.sin(time / 190 + index * 0.5) * Math.sin(time / 470 + index * 0.13));
      if (current === "thinking") return reduced ? 0.2 : 0.22 + 0.18 * Math.sin(time / 260 - index * 0.4);
      return reduced ? 0.05 : 0.05 + 0.025 * Math.sin(time / 900 + index * 0.3);
    };

    const draw = (time) => {
      const state = live.current;
      const count = Math.max(8, Math.floor(width / (BAR_WIDTH + BAR_GAP)));
      const offset = (width - count * (BAR_WIDTH + BAR_GAP) + BAR_GAP) / 2;
      const isActive = state.mode !== "idle";

      context.clearRect(0, 0, width, height);
      context.fillStyle = isActive ? active : resting;
      for (let i = 0; i < count; i += 1) {
        const target = targetLevel(i, count, time, state);
        levels[i] = (levels[i] ?? 0) + (target - (levels[i] ?? 0)) * 0.35;
        const barHeight = Math.max(4, levels[i] * height * 0.92);
        const x = offset + i * (BAR_WIDTH + BAR_GAP);
        const y = (height - barHeight) / 2;
        context.beginPath();
        if (context.roundRect) context.roundRect(x, y, BAR_WIDTH, barHeight, 2);
        else context.rect(x, y, BAR_WIDTH, barHeight);
        context.fill();
      }
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [height]);

  return <canvas ref={canvasRef} className="waveform" style={{ height }} aria-hidden="true" />;
}
