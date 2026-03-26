import { useState, useEffect } from "react";
import { Palette } from "lucide-react";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { themes, getStoredThemeId, applyTheme } from "@/lib/themes";
import { cn } from "@/lib/utils";

export function ThemeSwitcher() {
  const [activeId, setActiveId] = useState(getStoredThemeId);

  useEffect(() => {
    applyTheme(activeId);
  }, [activeId]);

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          aria-label="Change theme"
        >
          <Palette className="h-4 w-4" />
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-52 p-2">
        <p className="mb-2 px-2 text-xs font-medium text-muted-foreground">
          Printer Theme
        </p>
        <div className="space-y-0.5">
          {themes.map((theme) => (
            <button
              key={theme.id}
              onClick={() => setActiveId(theme.id)}
              className={cn(
                "flex w-full items-center gap-3 rounded-md px-2 py-2 text-sm transition-colors",
                activeId === theme.id
                  ? "bg-muted font-medium text-foreground"
                  : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
              )}
            >
              <span
                className="h-3.5 w-3.5 rounded-full border border-border"
                style={{ backgroundColor: theme.accent }}
              />
              {theme.name}
            </button>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
