import { useToastStore } from "../store/toast";

export default function ToastContainer() {
  const toasts = useToastStore((s) => s.toasts);
  const dismiss = useToastStore((s) => s.dismiss);

  if (toasts.length === 0) return null;

  return (
    <div className="r-toast-container">
      {toasts.map((t) => (
        <div key={t.id} className={`r-toast r-toast-${t.type}`} onClick={() => dismiss(t.id)}>
          <span className="r-toast-icon">
            {t.type === "success" ? "✓" : t.type === "error" ? "!" : "i"}
          </span>
          <span className="r-toast-msg">{t.message}</span>
        </div>
      ))}
    </div>
  );
}
