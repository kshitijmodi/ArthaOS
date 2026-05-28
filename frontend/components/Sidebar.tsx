"use client";
import { cn } from "@/lib/utils";
import { useTheme } from "@/components/ThemeProvider";
import {
  LayoutDashboard, ArrowLeftRight, TrendingUp,
  Bell, Settings, ChevronLeft, ChevronRight,
  Sun, Moon, Zap, Target,
} from "lucide-react";
import { useState } from "react";

export type View = "dashboard" | "transactions" | "investments" | "alerts" | "goals" | "settings";

interface NavItem { id: View; label: string; icon: React.ReactNode; badge?: number; }
interface Props { activeView: View; onNavigate: (v: View) => void; alertCount?: number; }

export default function Sidebar({ activeView, onNavigate, alertCount = 0 }: Props) {
  const [collapsed, setCollapsed] = useState(false);
  const { theme, toggle } = useTheme();

  const navItems: NavItem[] = [
    { id: "dashboard",    label: "Dashboard",    icon: <LayoutDashboard size={18} /> },
    { id: "transactions", label: "Transactions", icon: <ArrowLeftRight size={18} /> },
    { id: "investments",  label: "Investments",  icon: <TrendingUp size={18} /> },
    { id: "alerts",       label: "Alerts",       icon: <Bell size={18} />, badge: alertCount },
    { id: "goals",        label: "Goals",        icon: <Target size={18} /> },
  ];

  return (
    <aside className={cn(
      "flex flex-col h-screen bg-surface border-r border-border/60 transition-all duration-300 shrink-0",
      collapsed ? "w-16" : "w-60"
    )}>
      {/* Logo */}
      <div className={cn(
        "flex items-center gap-3 px-4 py-5 border-b border-border/60",
        collapsed && "justify-center px-2"
      )}>
        <div className="w-8 h-8 rounded-xl bg-accent flex items-center justify-center shrink-0 shadow-lg shadow-accent/20">
          <Zap size={14} className="text-white" />
        </div>
        {!collapsed && (
          <div>
            <p className="text-sm font-bold text-tx leading-none">ArthaOS</p>
            <p className="text-[10px] text-tx-2 mt-0.5">Finance Intelligence</p>
          </div>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 space-y-0.5 px-2 overflow-y-auto">
        {navItems.map(item => (
          <button
            key={item.id}
            onClick={() => onNavigate(item.id)}
            title={collapsed ? item.label : undefined}
            className={cn(
              "w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150 relative",
              activeView === item.id
                ? "bg-accent/10 text-accent"
                : "text-tx-2 hover:text-tx hover:bg-elevated",
              collapsed && "justify-center px-2"
            )}
          >
            <span className="shrink-0">{item.icon}</span>
            {!collapsed && <span>{item.label}</span>}
            {item.badge !== undefined && item.badge > 0 && (
              <span className={cn(
                "bg-expense text-white text-[10px] font-bold rounded-full flex items-center justify-center",
                collapsed
                  ? "absolute -top-1 -right-1 w-4 h-4"
                  : "ml-auto w-5 h-5"
              )}>
                {item.badge > 9 ? "9+" : item.badge}
              </span>
            )}
          </button>
        ))}
      </nav>

      {/* Bottom */}
      <div className="px-2 py-4 border-t border-border/60 space-y-0.5">
        <button
          onClick={toggle}
          title={collapsed ? (theme === "dark" ? "Light mode" : "Dark mode") : undefined}
          className={cn(
            "w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-tx-2 hover:text-tx hover:bg-elevated transition-all",
            collapsed && "justify-center px-2"
          )}
        >
          {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
          {!collapsed && <span>{theme === "dark" ? "Light Mode" : "Dark Mode"}</span>}
        </button>

        <button
          onClick={() => onNavigate("settings")}
          title={collapsed ? "Settings" : undefined}
          className={cn(
            "w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all",
            activeView === "settings" ? "bg-accent/10 text-accent" : "text-tx-2 hover:text-tx hover:bg-elevated",
            collapsed && "justify-center px-2"
          )}
        >
          <Settings size={18} />
          {!collapsed && <span>Settings</span>}
        </button>

        <button
          onClick={() => setCollapsed(c => !c)}
          className={cn(
            "w-full flex items-center gap-3 px-3 py-2 rounded-xl text-xs text-tx-3 hover:text-tx-2 hover:bg-elevated transition-all",
            collapsed && "justify-center px-2"
          )}
        >
          {collapsed
            ? <ChevronRight size={14} />
            : <><ChevronLeft size={14} /><span>Collapse</span></>}
        </button>
      </div>
    </aside>
  );
}
