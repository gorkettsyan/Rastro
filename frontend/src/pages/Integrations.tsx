import { useTranslation } from "react-i18next";
import IntegrationsPanel from "../components/IntegrationsPanel";

export default function Integrations() {
  const { t } = useTranslation();

  return (
    <main className="r-main" style={{ maxWidth: "680px" }}>
      <p className="r-page-title" style={{ marginBottom: "var(--space-xl)" }}>
        {t("integrations")}
      </p>
      <IntegrationsPanel />
    </main>
  );
}
