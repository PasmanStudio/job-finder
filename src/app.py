"""
Streamlit dashboard — Job Scraper local web UI.

Run with:
  .venv/Scripts/streamlit run src/app.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time as _time
import datetime as _dt
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path

from bs4 import BeautifulSoup
import streamlit as st

# Ensure project root is on path when running via streamlit
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# On Streamlit Community Cloud the DB connection string is stored in app secrets.
# Promote it to an env var *before* importing the database layer (which reads
# DATABASE_URL at import time to pick its backend).
try:
    if not os.getenv("DATABASE_URL") and "DATABASE_URL" in st.secrets:
        os.environ["DATABASE_URL"] = st.secrets["DATABASE_URL"]
except Exception:
    pass

from src.core.database import (
    get_all_jobs,
    get_jobs_by_state,
    set_status,
    set_notes,
    get_stats,
    log_application,
    get_applications,
    application_counts,
    get_company_applications,
)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Job Scraper",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded",
)

CATEGORY_COLORS = {
    "remote":      ("#1565C0", "🌐 Remote"),
    "local":       ("#2E7D32", "📍 Argentina"),
    "relocation":  ("#6A1B9A", "✈️ Relocation"),
}

BOARD_COLORS = {
    "linkedin": "#0A66C2",
    "indeed": "#003A9B",
    "glassdoor": "#0CAA41",
    "google": "#EA4335",
    "remoteok": "#FF4B4B",
    "weworkremotely": "#1DB954",
    "getonbrd": "#FF6B35",
    "remotive": "#5C6BC0",
    "himalayas": "#00897B",
    "torre": "#7B1FA2",
}

STATE_LABELS = {
    "new": "🆕 Nuevos",
    "saved": "🔖 Guardados",
    "applied": "✅ Aplicados",
    "interview": "📞 Entrevista",
    "rejected": "❌ Descartados",
}

CHANNELS = ["LinkedIn", "Formulario empresa (ATS)", "Email", "Get on Board", "Torre", "Otro"]


def board_badge(board: str) -> str:
    color = BOARD_COLORS.get(board.lower(), "#888")
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:12px;font-size:12px;font-weight:600">{board.upper()}</span>'


def score_badge(score) -> str:
    """Colored 0-100 match-score pill (grey→amber→green)."""
    score = int(score or 0)
    if score >= 75:
        color = "#2E7D32"
    elif score >= 45:
        color = "#F9A825"
    else:
        color = "#9E9E9E"
    return (
        f'<span style="background:{color};color:white;padding:2px 8px;'
        f'border-radius:12px;font-size:12px;font-weight:700">★ {score}</span>'
    )


def applied_badge(n: int) -> str:
    if not n:
        return ""
    label = "1 vez" if n == 1 else f"{n} veces"
    return (
        f'<span style="background:#37474F;color:white;padding:2px 8px;'
        f'border-radius:12px;font-size:12px;font-weight:600">📨 Aplicado {label}</span>'
    )


def category_badges(tags_raw) -> str:
    """Parse tags JSON and return colored HTML badges for known categories."""
    try:
        tags = json.loads(tags_raw) if isinstance(tags_raw, str) else (tags_raw or [])
    except Exception:
        tags = []
    badges = []
    for tag in tags:
        if tag in CATEGORY_COLORS:
            color, label = CATEGORY_COLORS[tag]
            badges.append(
                f'<span style="background:{color};color:white;padding:2px 8px;'
                f'border-radius:12px;font-size:12px;font-weight:600">{label}</span>'
            )
    return " ".join(badges)


def _tags_list(job: dict) -> list[str]:
    raw = job.get("tags", "[]")
    try:
        return json.loads(raw) if isinstance(raw, str) else (raw or [])
    except Exception:
        return []


def _reasons_list(job: dict) -> list[str]:
    raw = job.get("match_reasons", "[]")
    try:
        return json.loads(raw) if isinstance(raw, str) else (raw or [])
    except Exception:
        return []


def _fmt_date(iso: str) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y")
    except Exception:
        return iso[:10]


def _clean_description(description: str) -> str:
    if "<" in description:
        soup = BeautifulSoup(description, "html.parser")
        for br in soup.find_all("br"):
            br.replace_with("\n")
        clean = soup.get_text(separator="\n").strip()
    else:
        clean = description
    return clean


CANDIDATE = {
    "name": "Carolina Totaro",
    "title_es": "Senior UX/UI Designer",
    "title_en": "Senior UX/UI Designer",
    "email": "caro.totaro@gmail.com",
    "linkedin": "linkedin.com/in/carolinatotaro",
    "years_exp": "6+",
    "highlight_es": (
        "con experiencia en fintech (n1u, UIN), herramientas enterprise (Salesforce/Concentrix) "
        "y productos B2B. Especializada en discovery, design systems y trabajo end-to-end en "
        "entornos agile. Diseñadora Gráfica graduada de UBA FADU."
    ),
    "highlight_en": (
        "with experience in fintech (n1u, UIN), enterprise tools (Salesforce/Concentrix) "
        "and B2B products. Specialized in discovery, design systems and end-to-end work in "
        "agile environments. Graphic Designer from UBA FADU."
    ),
}

# Short phrases to weave a tailored "I specialize in X" line, keyed by the
# match-reason keywords already computed by the scorer.
_REASON_PHRASES_ES = {
    "design system": "design systems", "design systems": "design systems",
    "fintech": "fintech", "b2b": "productos B2B", "saas": "SaaS",
    "discovery": "discovery", "product designer": "diseño de producto",
    "salesforce": "herramientas enterprise (Salesforce)", "enterprise": "productos enterprise",
    "user research": "research con usuarios", "design thinking": "design thinking",
    "gamification": "gamification",
}
_REASON_PHRASES_EN = {
    "design system": "design systems", "design systems": "design systems",
    "fintech": "fintech", "b2b": "B2B products", "saas": "SaaS",
    "discovery": "discovery", "product designer": "product design",
    "salesforce": "enterprise tools (Salesforce)", "enterprise": "enterprise products",
    "user research": "user research", "design thinking": "design thinking",
    "gamification": "gamification",
}

# Minimal stop-word frequency check — no extra dependency.
_EN_WORDS = {" the ", " and ", " for ", " with ", " you ", " we ", " our ", " your ",
             " will ", " are ", " is ", " to ", " of ", " in ", " a ", " as ", " on ",
             " experience", " design", " team", " work", " skills", " years"}
_ES_WORDS = {" el ", " la ", " los ", " las ", " de ", " que ", " y ", " para ",
             " con ", " un ", " una ", " del ", " en ", " experiencia", " diseño",
             " equipo", " trabajo", " años", " buscamos", " serás", " tus "}


def detect_language(job: dict) -> str:
    """Return 'en' or 'es' based on the offer's title + description."""
    text = f" {job.get('title','')} {job.get('description','')} ".lower()
    en = sum(text.count(w) for w in _EN_WORDS)
    es = sum(text.count(w) for w in _ES_WORDS)
    return "en" if en > es else "es"


def _tailored_strength(job: dict, phrases: dict) -> list[str]:
    picked = []
    for r in _reasons_list(job):
        p = phrases.get(r)
        if p and p not in picked:
            picked.append(p)
    return picked[:3]


def recruiter_message(job: dict) -> str:
    title = job.get("title", "")
    company = job.get("company", "")
    tags = _tags_list(job)
    is_relocation = "relocation" in tags
    lang = detect_language(job)

    if lang == "en":
        strengths = _tailored_strength(job, _REASON_PHRASES_EN)
        strength_line = (
            f" My background is a strong fit for this role, especially in "
            f"{', '.join(strengths)}." if strengths else ""
        )
        location_line = (
            "\n\nI hold EU citizenship and I'm open to relocation."
            if is_relocation else ""
        )
        company_part = f" at {company}" if company else ""
        return (
            f"Hi! I came across the {title} opening{company_part} and I'm very interested.\n\n"
            f"I'm {CANDIDATE['name']}, a {CANDIDATE['title_en']} with {CANDIDATE['years_exp']} years of experience "
            f"{CANDIDATE['highlight_en']}{strength_line}{location_line}\n\n"
            f"I'm attaching my portfolio and CV so you can review my profile. "
            f"I'd be happy to jump on a call. Thank you!"
        )

    strengths = _tailored_strength(job, _REASON_PHRASES_ES)
    strength_line = (
        f" Mi perfil encaja especialmente con esta búsqueda en "
        f"{', '.join(strengths)}." if strengths else ""
    )
    location_line = (
        "\n\nCuento con ciudadanía europea y estoy abierta a relocalización."
        if is_relocation else ""
    )
    company_part = f" en {company}" if company else ""
    return (
        f"Hola! Vi la oferta de {title}{company_part} y me interesa mucho.\n\n"
        f"Soy {CANDIDATE['name']}, {CANDIDATE['title_es']} con {CANDIDATE['years_exp']} años de experiencia "
        f"{CANDIDATE['highlight_es']}{strength_line}{location_line}\n\n"
        f"Adjunto mi portfolio y CV para que puedan evaluar mi perfil. "
        f"Quedo a disposición para una llamada. Muchas gracias!"
    )


def render_job_card(job: dict, key_prefix: str, app_counts: dict) -> None:
    job_id = job["id"]
    title = job.get("title", "Sin título")
    company = job.get("company", "")
    location = job.get("location", "")
    board = job.get("board", "")
    apply_url = job.get("apply_url") or job.get("url", "#")
    apply_type = job.get("apply_type", "")
    salary = job.get("salary", "")
    posted = job.get("posted_at", "")[:10] if job.get("posted_at") else ""
    description = job.get("description", "")
    state = job.get("state", "new")
    n_applied = app_counts.get(job_id, 0)

    with st.container():
        # Header row
        col_info, col_actions = st.columns([3, 1])

        with col_info:
            st.markdown(
                f"### [{title}]({apply_url})\n"
                f"**{company}** &nbsp;·&nbsp; {location}"
                + (f" &nbsp;·&nbsp; {posted}" if posted else "")
                + (f" &nbsp;·&nbsp; 💰 {salary}" if salary else ""),
                unsafe_allow_html=True,
            )
            meta = score_badge(job.get("score", 0)) + " &nbsp;" + board_badge(board)
            cat_html = category_badges(job.get("tags", "[]"))
            if cat_html:
                meta += " &nbsp;" + cat_html
            if apply_type == "easy_apply":
                meta += ' &nbsp;<span style="background:#f90;color:white;padding:2px 8px;border-radius:12px;font-size:12px">Easy Apply</span>'
            elif apply_type == "email":
                meta += ' &nbsp;<span style="background:#888;color:white;padding:2px 8px;border-radius:12px;font-size:12px">Email</span>'
            elif apply_type == "ats":
                meta += ' &nbsp;<span style="background:#555;color:white;padding:2px 8px;border-radius:12px;font-size:12px">ATS</span>'
            ab = applied_badge(n_applied)
            if ab:
                meta += " &nbsp;" + ab
            st.markdown(meta, unsafe_allow_html=True)

            reasons = _reasons_list(job)
            if reasons:
                st.caption("🎯 Match: " + " · ".join(reasons))

        with col_actions:
            if state != "saved":
                if st.button("🔖 Guardar", key=f"{key_prefix}_{job_id}_save"):
                    set_status(job_id, "saved")
                    st.rerun()
            if state != "interview":
                if st.button("📞 Entrevista", key=f"{key_prefix}_{job_id}_interview"):
                    set_status(job_id, "interview")
                    st.rerun()
            if state != "rejected":
                if st.button("❌ Descartar", key=f"{key_prefix}_{job_id}_reject"):
                    set_status(job_id, "rejected")
                    st.rerun()
            if state != "new":
                if st.button("↩ Nuevo", key=f"{key_prefix}_{job_id}_reset"):
                    set_status(job_id, "new")
                    st.rerun()

        # ── Application logger ────────────────────────────────────────────────
        with st.expander(
            f"📨 Registrar aplicación" + (f" · ya aplicada {n_applied}×" if n_applied else "")
        ):
            apps = get_applications(job_id)
            if apps:
                st.caption("Historial:")
                for a in apps:
                    line = f"• **{_fmt_date(a['applied_at'])}**"
                    if a.get("channel"):
                        line += f" — {a['channel']}"
                    if a.get("notes"):
                        line += f" — _{a['notes']}_"
                    st.markdown(line)
                st.divider()

            ac1, ac2 = st.columns([1, 1])
            with ac1:
                app_date = st.date_input(
                    "Fecha", value=date.today(), key=f"{key_prefix}_{job_id}_appdate"
                )
            with ac2:
                channel = st.selectbox(
                    "Canal", CHANNELS, key=f"{key_prefix}_{job_id}_chan"
                )
            app_notes = st.text_input(
                "Notas (ej. contacté a la recruiter)", key=f"{key_prefix}_{job_id}_appnotes"
            )
            if st.button("Guardar aplicación", key=f"{key_prefix}_{job_id}_logapp", type="primary"):
                log_application(
                    job_id,
                    channel=channel,
                    notes=app_notes,
                    applied_at=datetime.combine(app_date, datetime.min.time()).isoformat(),
                )
                st.success("Aplicación registrada")
                st.rerun()

        # Description expander + recruiter message
        exp_col, msg_col = st.columns([2, 1])
        with exp_col:
            if description:
                with st.expander("Ver descripción (guardada — persiste aunque la oferta cierre)"):
                    clean = _clean_description(description)
                    st.write(clean)
        with msg_col:
            lang_label = "🇬🇧 EN" if detect_language(job) == "en" else "🇪🇸 ES"
            with st.expander(f"Mensaje al recruiter ({lang_label})"):
                msg = recruiter_message(job)
                st.text_area(
                    "Copiar y personalizar:",
                    value=msg,
                    height=180,
                    key=f"{key_prefix}_{job_id}_msg",
                    label_visibility="collapsed",
                )

        st.divider()


def render_job_list(jobs: list[dict], tab_key: str, app_counts: dict) -> None:
    if not jobs:
        st.info("No hay trabajos en esta categoría todavía.")
        return

    # Filters row
    fcol1, fcol2, fcol3, fcol4 = st.columns([1, 1, 1, 2])

    with fcol1:
        category_opts = ["Todos", "🌐 Remote", "📍 Argentina", "✈️ Relocation"]
        sel_cat = st.selectbox("Tipo", category_opts, key=f"{tab_key}_cat_filter")

    with fcol2:
        boards = sorted({j["board"] for j in jobs})
        sel_board = st.selectbox("Board", ["Todos"] + boards, key=f"{tab_key}_board_filter")

    with fcol3:
        min_score = st.slider("Match mínimo", 0, 100, 0, step=5, key=f"{tab_key}_score_filter")

    with fcol4:
        search = st.text_input("Buscar por título o empresa", key=f"{tab_key}_search")

    # Category map
    _cat_key = {"🌐 Remote": "remote", "📍 Argentina": "local", "✈️ Relocation": "relocation"}

    filtered = jobs
    if sel_cat != "Todos":
        cat_tag = _cat_key[sel_cat]
        filtered = [j for j in filtered if cat_tag in _tags_list(j)]
    if sel_board != "Todos":
        filtered = [j for j in filtered if j["board"] == sel_board]
    if min_score > 0:
        filtered = [j for j in filtered if int(j.get("score", 0) or 0) >= min_score]
    if search:
        q = search.lower()
        filtered = [
            j for j in filtered
            if q in j.get("title", "").lower() or q in j.get("company", "").lower()
        ]

    # Mini breakdown
    n_remote = sum(1 for j in jobs if "remote" in _tags_list(j))
    n_local  = sum(1 for j in jobs if "local"  in _tags_list(j))
    n_reloc  = sum(1 for j in jobs if "relocation" in _tags_list(j))
    st.caption(f"🌐 Remote: {n_remote} · 📍 AR: {n_local} · ✈️ Relocation: {n_reloc} · mostrando: {len(filtered)}")

    for job in filtered:
        render_job_card(job, tab_key, app_counts)


def render_companies() -> None:
    """Per-company application history: how many times, when, which roles."""
    companies = get_company_applications()
    if not companies:
        st.info("Todavía no registraste ninguna aplicación. Usá '📨 Registrar aplicación' en cada oferta.")
        return

    total_apps = sum(c["count"] for c in companies)
    st.caption(f"{len(companies)} empresas · {total_apps} aplicaciones en total")

    search = st.text_input("Buscar empresa", key="companies_search")
    rows = companies
    if search:
        q = search.lower()
        rows = [c for c in rows if q in c["company"].lower()]

    for c in rows:
        header = f"**{c['company']}** — {c['count']} aplicación(es) · última: {_fmt_date(c['last_applied'])}"
        with st.expander(header):
            for ev in c["events"]:
                line = f"• **{_fmt_date(ev['applied_at'])}** — [{ev['title']}]({ev.get('url', '#')})"
                if ev.get("channel"):
                    line += f" · {ev['channel']}"
                if ev.get("notes"):
                    line += f" · _{ev['notes']}_"
                st.markdown(line)


def render_analytics() -> None:
    """Charts and metrics across all scraped jobs."""
    import pandas as pd

    jobs = get_all_jobs()
    if not jobs:
        st.info("Todavía no hay datos. Ejecutá el scraper para ver analytics.")
        return

    df = pd.DataFrame(jobs)
    df["score"] = pd.to_numeric(df.get("score", 0), errors="coerce").fillna(0).astype(int)

    st.subheader("Embudo")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total", len(df))
    c2.metric("Guardados", int((df["state"] == "saved").sum()))
    c3.metric("Aplicados", int((df["state"] == "applied").sum()))
    c4.metric("Entrevista", int((df["state"] == "interview").sum()))
    c5.metric("Match prom.", f'{df["score"].mean():.0f}')

    st.divider()

    col_a, col_b = st.columns(2)
    with col_a:
        st.caption("Ofertas por board")
        st.bar_chart(df["board"].value_counts())
    with col_b:
        st.caption("Distribución de match score")
        bins = pd.cut(df["score"], bins=[-1, 24, 44, 64, 84, 100],
                      labels=["0-24", "25-44", "45-64", "65-84", "85-100"])
        st.bar_chart(bins.value_counts().sort_index())

    col_c, col_d = st.columns(2)
    with col_c:
        st.caption("Por tipo")
        cat_counts = {
            "🌐 Remote": sum(1 for j in jobs if "remote" in _tags_list(j)),
            "📍 Argentina": sum(1 for j in jobs if "local" in _tags_list(j)),
            "✈️ Relocation": sum(1 for j in jobs if "relocation" in _tags_list(j)),
        }
        st.bar_chart(pd.Series(cat_counts))
    with col_d:
        st.caption("Top empresas (por # de ofertas scrapeadas)")
        top = df[df["company"].str.len() > 0]["company"].value_counts().head(10)
        st.bar_chart(top)

    if "scraped_at" in df.columns:
        st.caption("Ofertas encontradas por día")
        dates = pd.to_datetime(df["scraped_at"], errors="coerce").dt.date
        st.bar_chart(dates.value_counts().sort_index())

    st.divider()
    st.caption("🔥 Top 10 matches nuevos sin revisar")
    top_new = (
        df[df["state"] == "new"].sort_values("score", ascending=False)
        [["score", "title", "company", "board"]].head(10)
    )
    st.dataframe(top_new, use_container_width=True, hide_index=True)


def _gh_request(pat: str, path: str, method: str = "GET", body: dict | None = None) -> dict:
    """Make a GitHub API request and return parsed JSON (or {} for 204)."""
    url = f"https://api.github.com/repos/PasmanStudio/job-finder{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url, data=data,
        headers={
            "Authorization": f"Bearer {pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return {} if resp.status == 204 else json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}: {exc.read().decode()[:200]}")


def _trigger_scraper() -> tuple[bool, str]:
    """Dispatch scrape.yml and return (ok, error_msg)."""
    try:
        pat = st.secrets.get("GITHUB_PAT", "")
    except Exception:
        pat = ""
    if not pat:
        return False, "Secret GITHUB_PAT no configurado en Streamlit."
    try:
        _gh_request(pat, "/actions/workflows/scrape.yml/dispatches", "POST", {"ref": "main"})
        return True, ""
    except RuntimeError as exc:
        return False, str(exc)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🎨 Job Scraper")
    st.caption("Diseño UX/UI · Gráfico · Producto")

    stats = get_stats()
    st.metric("Nuevos", stats.get("new", 0))
    st.metric("Guardados", stats.get("saved", 0))
    st.metric("Aplicados", stats.get("applied", 0))
    st.metric("Entrevista", stats.get("interview", 0))
    st.metric("Descartados", stats.get("rejected", 0))

    st.divider()
    st.subheader("Scraper")

    # On Streamlit Cloud the subprocess approach doesn't work (missing scraper
    # deps). Detect cloud by the absence of a local .env file.
    _on_cloud = not Path(__file__).resolve().parents[1].joinpath(".env").exists()

    if _on_cloud:
        st.caption("El scraper corre automáticamente L/M/V a las 06:00 AR.")

        try:
            _pat = st.secrets.get("GITHUB_PAT", "")
        except Exception:
            _pat = ""

        _run = st.session_state.get("scraper_run")
        _status_box = st.empty()

        if _run:
            _elapsed = int(_time.time() - _run["started_at"])
            _mins, _secs = _elapsed // 60, _elapsed % 60
            _timer = f"{_mins}:{_secs:02d}"

            if not _run.get("run_id"):
                # Still waiting for GitHub to register the run
                _status_box.info(f"⏳ Iniciando scraper… ({_timer})")
                try:
                    _runs = _gh_request(_pat, "/actions/runs?event=workflow_dispatch&per_page=5")
                    for _r in _runs.get("workflow_runs", []):
                        if _r["created_at"] >= _run["created_after"]:
                            st.session_state.scraper_run["run_id"] = _r["id"]
                            break
                except Exception:
                    pass
                _time.sleep(3)
                st.rerun()
            else:
                try:
                    _r = _gh_request(_pat, f"/actions/runs/{_run['run_id']}")
                    _s = _r.get("status", "")
                    _c = _r.get("conclusion") or ""
                    if _s == "completed":
                        if _c == "success":
                            _status_box.success("✅ ¡Listo! Recargá la página para ver los nuevos trabajos.")
                        else:
                            _status_box.error("❌ Ocurrió un error en el scraper. Hablá con el administrador.")
                        del st.session_state.scraper_run
                    else:
                        _status_box.info(f"⏳ Scraper corriendo… ({_timer})")
                        _time.sleep(5)
                        st.rerun()
                except Exception as _exc:
                    _status_box.error(f"❌ Error al verificar estado: {_exc}")
                    del st.session_state.scraper_run
        else:
            if st.button("🔍 Buscar nuevos trabajos", type="primary"):
                ok, err = _trigger_scraper()
                if ok:
                    st.session_state.scraper_run = {
                        "started_at": _time.time(),
                        "created_after": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "run_id": None,
                    }
                    st.rerun()
                else:
                    st.error(f"No se pudo iniciar: {err}")
    else:
        st.caption("Ejecuta el scraper para buscar nuevos trabajos")
        if st.button("Buscar nuevos trabajos", type="primary"):
            with st.spinner("Scrapeando... puede tardar 1-2 min"):
                result = subprocess.run(
                    [sys.executable, "-m", "src.main", "--dry-run"],
                    cwd=str(Path(__file__).resolve().parents[1]),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            if result.returncode == 0:
                st.success("Listo!")
                st.rerun()
            else:
                st.error("Error al scrapear")
                st.code(result.stderr[-500:] if result.stderr else "")

        if st.button("Scraper completo (guarda en DB)"):
            with st.spinner("Scrapeando y guardando..."):
                result = subprocess.run(
                    [sys.executable, "-m", "src.main"],
                    cwd=str(Path(__file__).resolve().parents[1]),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            if result.returncode == 0:
                st.success("Guardado en DB!")
                st.rerun()
            else:
                st.error("Error")
                st.code(result.stderr[-500:] if result.stderr else "")

    st.divider()
    try:
        _all_flat = get_all_jobs()
        n_remote_total = sum(1 for j in _all_flat if "remote" in _tags_list(j))
        n_local_total  = sum(1 for j in _all_flat if "local"  in _tags_list(j))
        n_reloc_total  = sum(1 for j in _all_flat if "relocation" in _tags_list(j))
        st.markdown("**Por tipo**")
        st.caption(f"🌐 Remote: {n_remote_total}")
        st.caption(f"📍 Argentina: {n_local_total}")
        st.caption(f"✈️ Relocation: {n_reloc_total}")
    except Exception:
        pass

    st.caption("li_at cookie para LinkedIn autenticado: agregar LI_AT_COOKIE en .env")


# ── Main tabs ─────────────────────────────────────────────────────────────────
app_counts = application_counts()

tab_new, tab_saved, tab_applied, tab_interview, tab_rejected, tab_companies, tab_stats = st.tabs([
    f"🆕 Nuevos ({stats.get('new', 0)})",
    f"🔖 Guardados ({stats.get('saved', 0)})",
    f"✅ Aplicados ({stats.get('applied', 0)})",
    f"📞 Entrevista ({stats.get('interview', 0)})",
    f"❌ Descartados ({stats.get('rejected', 0)})",
    "🏢 Empresas",
    "📊 Analytics",
])

with tab_new:
    render_job_list(get_jobs_by_state("new"), "new", app_counts)

with tab_saved:
    render_job_list(get_jobs_by_state("saved"), "saved", app_counts)

with tab_applied:
    render_job_list(get_jobs_by_state("applied"), "applied", app_counts)

with tab_interview:
    render_job_list(get_jobs_by_state("interview"), "interview", app_counts)

with tab_rejected:
    render_job_list(get_jobs_by_state("rejected"), "rejected", app_counts)

with tab_companies:
    render_companies()

with tab_stats:
    render_analytics()
