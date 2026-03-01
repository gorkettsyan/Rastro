import { useTranslation } from "react-i18next";
import { useAuthStore } from "../store/auth";

interface Props {
  textKey: string;
}

export default function LearningHint({ textKey }: Props) {
  const { t } = useTranslation();
  const user = useAuthStore((s) => s.user);

  if (!user?.learning_mode) return null;

  return (
    <div className="r-hint">
      <span className="r-hint-icon">?</span>
      <span className="r-hint-text">{t(textKey)}</span>
    </div>
  );
}
