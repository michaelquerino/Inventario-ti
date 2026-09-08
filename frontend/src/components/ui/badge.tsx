import type { ReactNode } from "react";

export type BadgeTone = "neutral" | "success" | "warning" | "danger" | "info";
export type BadgeSize = "sm" | "md" | "lg";

const toneClass: Record<BadgeTone, string> = {
  neutral: "bg-slate-100 text-slate-600",
  success: "bg-emerald-100 text-emerald-700",
  warning: "bg-amber-100 text-amber-700",
  danger: "bg-red-100 text-red-700",
  info: "bg-blue-100 text-blue-700",
};

const sizeClass: Record<BadgeSize, string> = {
  sm: "px-2 py-0.5",
  md: "px-2 py-1",
  lg: "px-2.5 py-1",
};

type BadgeProps = {
  tone?: BadgeTone;
  size?: BadgeSize;
  className?: string;
  children: ReactNode;
};

export function Badge({ tone = "neutral", size = "md", className = "", children }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full text-xs font-semibold ${toneClass[tone]} ${sizeClass[size]} ${className}`}
    >
      {children}
    </span>
  );
}
