import { useTranslation } from "react-i18next";

export default function LanguageSwitcher() {
  const { i18n } = useTranslation();

  const toggle = () => {
    const next = i18n.language === "es" ? "en" : "es";
    i18n.changeLanguage(next);
    localStorage.setItem("rastro_lang", next);
  };

  return (
    <button
      onClick={toggle}
      className="text-xs font-medium text-gray-400 hover:text-gray-600 border border-gray-200 rounded px-2 py-1 transition-colors"
    >
      {i18n.language === "es" ? "EN" : "ES"}
    </button>
  );
}
