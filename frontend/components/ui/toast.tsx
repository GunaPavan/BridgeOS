"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";

import { cn } from "@/lib/utils";

type ToastVariant = "success" | "error" | "info";

interface ToastItem {
  id: string;
  title: string;
  description?: string;
  variant: ToastVariant;
}

interface ToastContextValue {
  show: (input: Omit<ToastItem, "id">) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

/** Hook to push toasts from anywhere in the tree. */
export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error("useToast must be used inside a <ToastProvider />");
  }
  return ctx;
}

let toastSeq = 0;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const timeouts = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: string) => {
    setToasts((t) => t.filter((x) => x.id !== id));
    const handle = timeouts.current.get(id);
    if (handle) clearTimeout(handle);
    timeouts.current.delete(id);
  }, []);

  const show = useCallback<ToastContextValue["show"]>(
    (input) => {
      const id = `t${++toastSeq}`;
      setToasts((t) => [...t, { ...input, id }]);
      const handle = setTimeout(() => dismiss(id), 4500);
      timeouts.current.set(id, handle);
    },
    [dismiss],
  );

  useEffect(
    () => () => {
      timeouts.current.forEach((h) => clearTimeout(h));
      timeouts.current.clear();
    },
    [],
  );

  const value = useMemo(() => ({ show }), [show]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        data-testid="toast-region"
        className="pointer-events-none fixed right-4 top-4 z-50 flex w-80 flex-col gap-2"
        role="region"
        aria-label="Notifications"
      >
        <AnimatePresence initial={false}>
          {toasts.map((t) => (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, y: -10, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -10, scale: 0.95, transition: { duration: 0.15 } }}
              transition={{ type: "spring", stiffness: 240, damping: 22 }}
              className="pointer-events-auto"
            >
              <ToastBubble toast={t} onDismiss={() => dismiss(t.id)} />
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

const VARIANT_STYLE: Record<
  ToastVariant,
  { wrap: string; icon: React.ComponentType<{ className?: string }> }
> = {
  success: {
    wrap: "border-emerald-500/30 bg-emerald-500/10 text-emerald-100",
    icon: CheckCircle2,
  },
  error: {
    wrap: "border-red-500/30 bg-red-500/10 text-red-100",
    icon: AlertCircle,
  },
  info: {
    wrap: "border-white/10 bg-surface/90 text-white",
    icon: Info,
  },
};

function ToastBubble({
  toast,
  onDismiss,
}: {
  toast: ToastItem;
  onDismiss: () => void;
}) {
  const style = VARIANT_STYLE[toast.variant];
  const Icon = style.icon;
  return (
    <div
      role="status"
      data-testid="toast"
      data-variant={toast.variant}
      className={cn(
        "flex items-start gap-3 rounded-lg border bg-background/95 p-3 shadow-xl backdrop-blur",
        style.wrap,
      )}
    >
      <Icon className="mt-0.5 h-4 w-4 shrink-0" />
      <div className="flex-1">
        <p className="text-sm font-medium">{toast.title}</p>
        {toast.description ? (
          <p className="mt-0.5 text-xs opacity-80">{toast.description}</p>
        ) : null}
      </div>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="rounded p-0.5 opacity-60 transition-opacity hover:opacity-100"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
