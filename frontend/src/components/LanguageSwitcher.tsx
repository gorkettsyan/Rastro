import { useTranslation } from "react-i18next";

export default function LanguageSwitcher() {
  const { i18n } = useTranslation();

  const toggle = () => {
    const next = i18n.language === "es" ? "en" : "es";
    i18n.changeLanguage(next);
    localStorage.setItem("rastro_lang", next);
  };

  return (
    <button onClick={toggle} className="r-lang-btn">
      {i18n.language === "es" ? "EN" : "ES"}
    </button>
  );
}
