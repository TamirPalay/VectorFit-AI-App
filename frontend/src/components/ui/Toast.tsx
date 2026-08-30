import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import s from "./Toast.module.css";

type Kind = "ok" | "err" | "info";
interface Item { id: number; kind: Kind; msg: string }

const ToastCtx = createContext<(msg: string, kind?: Kind) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Item[]>([]);
  const nextId = useRef(1);

  const push = useCallback((msg: string, kind: Kind = "ok") => {
    const id = nextId.current++;
    setItems((cur) => [...cur, { id, kind, msg }]);
    setTimeout(() => setItems((cur) => cur.filter((i) => i.id !== id)), 3200);
  }, []);

  return (
    <ToastCtx.Provider value={push}>
      {children}
      {createPortal(
        <div className={s.stack}>
          {items.map((i) => (
            <div key={i.id} className={`${s.toast} ${s[i.kind]}`}>{i.msg}</div>
          ))}
        </div>,
        document.body,
      )}
    </ToastCtx.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export const useToast = () => useContext(ToastCtx);
