"""
notifier.py — Phase 2 notification pipeline.

Supports:
  - Windows toast notifications (via plyer, zero config needed)
  - Email digest via SMTP (Gmail app password or any SMTP server)

Usage (from main.py or standalone):
  from notifier import notify_new_jobs, notify_pipeline_complete
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from core.scraper import Job

logger = logging.getLogger(__name__)


# ── Windows toast ──────────────────────────────────────────────────────────────

def _toast(title: str, message: str) -> None:
    """Fire a Windows desktop toast notification (best-effort)."""
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="AutoApply",
            timeout=8,
        )
    except Exception as e:
        logger.debug(f"Toast notification failed: {e}")


# ── Email ──────────────────────────────────────────────────────────────────────

def _send_email(subject: str, body_html: str, cfg: dict) -> bool:
    """
    Send an HTML email via SMTP.  cfg keys:
      smtp_host, smtp_port, from_address, to_address, password
    Returns True on success.
    """
    required = ("smtp_host", "smtp_port", "from_address", "to_address", "password")
    for key in required:
        if not cfg.get(key):
            logger.debug(f"Email skipped — missing config key: {key}")
            return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["from_address"]
    msg["To"] = cfg["to_address"]
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    try:
        with smtplib.SMTP(cfg["smtp_host"], int(cfg["smtp_port"]), timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(cfg["from_address"], cfg["password"])
            server.sendmail(cfg["from_address"], cfg["to_address"], msg.as_string())
        logger.info(f"Email sent: {subject}")
        return True
    except Exception as e:
        logger.warning(f"Email failed: {e}")
        return False


def _build_jobs_email(jobs: list[Job]) -> str:
    """Build an HTML email body listing new job matches."""
    rows = []
    for job in jobs:
        score_pct = f"{getattr(job, 'match_score', 0):.0%}" if hasattr(job, "match_score") else ""
        url_link = f'<a href="{job.url}">{job.url[:60]}…</a>' if job.url else "N/A"
        rows.append(f"""
        <tr>
          <td style="padding:6px 8px"><b>{job.title}</b></td>
          <td style="padding:6px 8px">{job.company}</td>
          <td style="padding:6px 8px">{job.location}</td>
          <td style="padding:6px 8px">{score_pct}</td>
          <td style="padding:6px 8px">{url_link}</td>
        </tr>""")

    rows_html = "\n".join(rows)
    return f"""
    <html><body style="font-family:Arial,sans-serif;font-size:14px">
    <h2 style="color:#1565C0">AutoApply — {len(jobs)} New Job Match{'es' if len(jobs) != 1 else ''}</h2>
    <table border="1" cellspacing="0" cellpadding="0"
           style="border-collapse:collapse;width:100%;border-color:#ddd">
      <thead style="background:#1565C0;color:#fff">
        <tr>
          <th style="padding:8px">Title</th>
          <th style="padding:8px">Company</th>
          <th style="padding:8px">Location</th>
          <th style="padding:8px">Score</th>
          <th style="padding:8px">URL</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
    </table>
    <p style="color:#666;font-size:12px;margin-top:16px">
      Run <code>python review.py</code> to approve tailored resumes.
    </p>
    </body></html>
    """


# ── Public API ─────────────────────────────────────────────────────────────────

def notify_new_jobs(jobs: list[Job], notification_cfg: dict) -> None:
    """
    Fire toast + optional email when new job matches are found.
    notification_cfg comes from config.yaml → notifications section.
    """
    if not jobs:
        return

    count = len(jobs)
    titles = ", ".join(f"{j.title} @ {j.company}" for j in jobs[:3])
    if count > 3:
        titles += f" (+{count - 3} more)"

    # Toast
    if notification_cfg.get("windows_toast", True):
        _toast(
            title=f"AutoApply — {count} new job{'s' if count != 1 else ''} found",
            message=titles,
        )

    # Email
    email_cfg = notification_cfg.get("email", {})
    if email_cfg.get("enabled"):
        subject = f"AutoApply — {count} new job match{'es' if count != 1 else ''}"
        body = _build_jobs_email(jobs)
        _send_email(subject, body, email_cfg)


def notify_pipeline_complete(new_count: int, total_scraped: int, notification_cfg: dict) -> None:
    """Toast summary after each pipeline run (only if new jobs were found)."""
    if not new_count:
        return
    if notification_cfg.get("windows_toast", True):
        _toast(
            title="AutoApply — Pipeline complete",
            message=f"{new_count} new jobs added (scraped {total_scraped} total)",
        )
