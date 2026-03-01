import { useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuthStore } from "../store/auth";
import LanguageSwitcher from "../components/LanguageSwitcher";

export default function Landing() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const token = useAuthStore((s) => s.token);

  useEffect(() => {
    if (token) {
      navigate("/dashboard", { replace: true });
    }
  }, [token, navigate]);

  useEffect(() => {
    document.title = t("landing_meta_title");
    const meta = document.querySelector('meta[name="description"]');
    if (meta) {
      meta.setAttribute("content", t("landing_meta_description"));
    } else {
      const el = document.createElement("meta");
      el.name = "description";
      el.content = t("landing_meta_description");
      document.head.appendChild(el);
    }
  }, [t]);

  const goLogin = () => navigate("/login");

  if (token) return null;

  return (
    <div className="r-landing">
      {/* ── Nav ── */}
      <nav className="r-landing-nav">
        <span className="r-landing-logo">Rastro</span>
        <div className="r-landing-nav-right">
          <LanguageSwitcher />
          <Link to="/login" className="r-landing-nav-link">{t("landing_login")}</Link>
          <button onClick={goLogin} className="r-landing-btn-primary">{t("landing_cta")}</button>
        </div>
      </nav>

      {/* ── Hero ── */}
      <section className="r-landing-hero">
        <h1 className="r-landing-h1">{t("landing_hero_headline")}</h1>
        <p className="r-landing-hero-sub">{t("landing_hero_subheadline")}</p>
        <button onClick={goLogin} className="r-landing-btn-primary r-landing-btn-lg">{t("landing_cta")}</button>
        <p className="r-landing-cta-note">{t("landing_cta_note")}</p>
        <div className="r-landing-screenshot-wrap">
          <img src="/dashboard.png" alt={t("landing_screenshot_alt")} className="r-landing-screenshot" />
        </div>
      </section>

      {/* ── Problem ── */}
      <section className="r-landing-section">
        <div className="r-landing-section-inner">
          <span className="r-landing-section-label">{t("landing_problem_label")}</span>
          <h2 className="r-landing-h2">{t("landing_problem_headline")}</h2>
          <div className="r-landing-grid-3">
            {[1, 2, 3].map((n) => (
              <div key={n} className="r-landing-card">
                <h3 className="r-landing-card-title">{t(`landing_problem_${n}_title`)}</h3>
                <p className="r-landing-card-desc">{t(`landing_problem_${n}_desc`)}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── How it works ── */}
      <section className="r-landing-section r-landing-section-alt">
        <div className="r-landing-section-inner">
          <span className="r-landing-section-label">{t("landing_how_label")}</span>
          <h2 className="r-landing-h2">{t("landing_how_headline")}</h2>
          <div className="r-landing-grid-3">
            {[1, 2, 3].map((n) => (
              <div key={n} className="r-landing-step">
                <span className="r-landing-step-number">{n}</span>
                <h3 className="r-landing-card-title">{t(`landing_how_${n}_title`)}</h3>
                <p className="r-landing-card-desc">{t(`landing_how_${n}_desc`)}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Features ── */}
      <section className="r-landing-section">
        <div className="r-landing-section-inner">
          <span className="r-landing-section-label">{t("landing_features_label")}</span>
          <h2 className="r-landing-h2">{t("landing_features_headline")}</h2>
          <div className="r-landing-grid-2">
            {[1, 2, 3, 4].map((n) => (
              <div key={n} className="r-landing-card">
                <h3 className="r-landing-card-title">{t(`landing_feature_${n}_title`)}</h3>
                <p className="r-landing-card-desc">{t(`landing_feature_${n}_desc`)}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Differentiation ── */}
      <section className="r-landing-section r-landing-section-alt">
        <div className="r-landing-section-inner">
          <span className="r-landing-section-label">{t("landing_diff_label")}</span>
          <h2 className="r-landing-h2">{t("landing_diff_headline")}</h2>
          <p className="r-landing-diff-body">{t("landing_diff_body")}</p>
        </div>
      </section>

      {/* ── Social proof placeholder ── */}
      <section className="r-landing-section">
        <div className="r-landing-section-inner">
          <span className="r-landing-section-label">{t("landing_proof_label")}</span>
          <div className="r-landing-proof-placeholder">
            <p>{t("landing_proof_placeholder")}</p>
          </div>
        </div>
      </section>

      {/* ── Pricing teaser ── */}
      <section className="r-landing-section r-landing-section-alt">
        <div className="r-landing-section-inner">
          <span className="r-landing-section-label">{t("landing_pricing_label")}</span>
          <h2 className="r-landing-h2">{t("landing_pricing_headline")}</h2>
          <p className="r-landing-diff-body">{t("landing_pricing_desc")}</p>
        </div>
      </section>

      {/* ── Final CTA ── */}
      <section className="r-landing-final-cta">
        <h2 className="r-landing-h2">{t("landing_final_headline")}</h2>
        <p className="r-landing-hero-sub">{t("landing_final_sub")}</p>
        <button onClick={goLogin} className="r-landing-btn-primary r-landing-btn-lg">{t("landing_cta")}</button>
      </section>

      {/* ── Footer ── */}
      <footer className="r-landing-footer">
        <span className="r-landing-footer-brand">Rastro</span>
        <div className="r-landing-footer-links">
          <a href="/privacy" className="r-landing-footer-link">{t("landing_privacy")}</a>
          <a href="/terms" className="r-landing-footer-link">{t("landing_terms")}</a>
        </div>
      </footer>
    </div>
  );
}
