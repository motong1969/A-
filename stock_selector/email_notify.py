from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from datetime import date
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path


@dataclass(frozen=True)
class EmailConfig:
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    mail_to: str
    mail_from: str


@dataclass(frozen=True)
class EmailSendResult:
    email_sent: bool
    smtp_connection: str
    gmail_auth: str
    missing_secrets: tuple[str, ...]
    error: str
    log_text: str


@dataclass(frozen=True)
class SmtpSendDetails:
    message_id: str
    smtp_ehlo_code: int
    smtp_ehlo_response: str
    smtp_starttls_code: int
    smtp_starttls_response: str
    smtp_tls_ehlo_code: int
    smtp_tls_ehlo_response: str
    smtp_login_code: int
    smtp_login_response: str
    smtp_mail_code: int
    smtp_mail_response: str
    smtp_rcpt_code: int
    smtp_rcpt_response: str
    smtp_data_code: int
    smtp_data_response: str


def load_email_config_from_env() -> EmailConfig | None:
    smtp_user = os.getenv("GMAIL_USER") or os.getenv("SMTP_USER")
    smtp_password = os.getenv("GMAIL_APP_PASSWORD") or os.getenv("SMTP_PASSWORD")
    mail_to = os.getenv("MAIL_TO") or smtp_user
    if not smtp_user or not smtp_password or not mail_to:
        return None
    return EmailConfig(
        smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_user=smtp_user,
        smtp_password=smtp_password,
        mail_to=mail_to,
        mail_from=os.getenv("MAIL_FROM", smtp_user),
    )


def send_today_stock_email_from_env(
    *,
    report_path: Path | str = Path("reports/today_stock.md"),
    trade_date: date,
) -> EmailSendResult:
    missing = missing_email_secrets()
    if missing:
        return _email_result(
            email_sent=False,
            smtp_connection="not_attempted",
            gmail_auth="not_attempted",
            missing_secrets=missing,
            error=f"missing secrets: {', '.join(missing)}",
        )
    config = load_email_config_from_env()
    if config is None:
        return _email_result(
            email_sent=False,
            smtp_connection="not_attempted",
            gmail_auth="not_attempted",
            missing_secrets=missing,
            error="email config unavailable",
        )
    if not Path(report_path).exists():
        return _email_result(
            email_sent=False,
            smtp_connection="not_attempted",
            gmail_auth="not_attempted",
            missing_secrets=(),
            error=f"report not found: {report_path}",
        )
    try:
        details = send_today_stock_email(report_path=report_path, trade_date=trade_date, config=config)
    except smtplib.SMTPAuthenticationError as exc:
        return _email_result(
            email_sent=False,
            smtp_connection="success",
            gmail_auth="failed",
            missing_secrets=(),
            error=f"gmail authentication failed: {exc.smtp_error!r}",
        )
    except (smtplib.SMTPException, OSError) as exc:
        return _email_result(
            email_sent=False,
            smtp_connection="failed",
            gmail_auth="not_attempted",
            missing_secrets=(),
            error=f"{type(exc).__name__}: {exc}",
        )
    return _email_result(
        email_sent=True,
        smtp_connection="success",
        gmail_auth="success",
        missing_secrets=(),
        error="",
        smtp_details=details,
    )


def missing_email_secrets() -> tuple[str, ...]:
    missing = []
    if not (os.getenv("GMAIL_USER") or os.getenv("SMTP_USER")):
        missing.append("GMAIL_USER")
    if not (os.getenv("GMAIL_APP_PASSWORD") or os.getenv("SMTP_PASSWORD")):
        missing.append("GMAIL_APP_PASSWORD")
    if not os.getenv("MAIL_TO"):
        missing.append("MAIL_TO")
    return tuple(missing)


def send_today_stock_email(
    *,
    report_path: Path | str,
    trade_date: date,
    config: EmailConfig,
) -> SmtpSendDetails:
    report_file = Path(report_path)
    report_text = report_file.read_text(encoding="utf-8")
    message = build_today_stock_message(report_text=report_text, trade_date=trade_date, config=config)
    with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=20) as smtp:
        ehlo_code, ehlo_response = smtp.ehlo()
        starttls_code, starttls_response = smtp.starttls()
        tls_ehlo_code, tls_ehlo_response = smtp.ehlo()
        login_code, login_response = smtp.login(config.smtp_user, config.smtp_password)
        mail_code, mail_response = smtp.mail(config.mail_from)
        rcpt_code, rcpt_response = smtp.rcpt(config.mail_to)
        data_code, data_response = smtp.data(message.as_bytes())
    return SmtpSendDetails(
        message_id=str(message["Message-ID"]),
        smtp_ehlo_code=ehlo_code,
        smtp_ehlo_response=_decode_smtp_response(ehlo_response),
        smtp_starttls_code=starttls_code,
        smtp_starttls_response=_decode_smtp_response(starttls_response),
        smtp_tls_ehlo_code=tls_ehlo_code,
        smtp_tls_ehlo_response=_decode_smtp_response(tls_ehlo_response),
        smtp_login_code=login_code,
        smtp_login_response=_decode_smtp_response(login_response),
        smtp_mail_code=mail_code,
        smtp_mail_response=_decode_smtp_response(mail_response),
        smtp_rcpt_code=rcpt_code,
        smtp_rcpt_response=_decode_smtp_response(rcpt_response),
        smtp_data_code=data_code,
        smtp_data_response=_decode_smtp_response(data_response),
    )


def build_today_stock_message(*, report_text: str, trade_date: date, config: EmailConfig) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = f"A股自动选股日报 {trade_date.isoformat()}"
    message["From"] = config.mail_from
    message["To"] = config.mail_to
    message["Message-ID"] = make_msgid(domain="github-actions.local")
    message.set_content(_extract_email_body(report_text))
    return message


def _extract_email_body(report_text: str) -> str:
    lines = [
        "【今日前三】",
        *_extract_top3_summary(report_text),
        "",
        "【最近5日重复上榜统计】",
        *_extract_repeat_summary(report_text),
        "",
        "【系统建议】",
        *_extract_priority_summary(report_text),
        "",
        "【风险提示】",
        _extract_market_risk(report_text),
    ]
    return "\n".join(lines).strip()


def _extract_top3_summary(report_text: str) -> list[str]:
    section = _section_lines(report_text, "## 今日推荐3只主板股票")
    rows = []
    current_name = ""
    current_code = ""
    current_score = ""
    for line in section:
        if line.startswith("### "):
            title = line.split(". ", 1)[-1]
            current_name = title.split(" (", 1)[0]
            current_code = title.rsplit("(", 1)[-1].rstrip(")") if "(" in title else ""
            current_score = ""
            continue
        if line.startswith("- 最终评分："):
            current_score = line.split("：", 1)[1]
            if current_code:
                rows.append(f"股票代码：{current_code}\n股票名称：{current_name}\n总评分：{current_score}")
    return rows or ["暂无今日前三数据。"]


def _extract_repeat_summary(report_text: str) -> list[str]:
    section = _section_lines(report_text, "## 最近5日重复上榜观察池")
    rows = []
    for line in section:
        if not line.startswith("| ") or line.startswith("| ---") or "代码 | 名称" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 8 or cells[0] == "暂无":
            continue
        rows.append(
            f"股票代码：{cells[0]}\n股票名称：{cells[1]}\n上榜次数：{cells[3]}\n连续上榜天数：{cells[4]}"
        )
    return rows[:10] or ["暂无重复上榜统计。"]


def _extract_priority_summary(report_text: str) -> list[str]:
    section = _section_lines(report_text, "## 最近5日重复上榜观察池")
    rows = []
    capture = False
    for line in section:
        if line == "今日优先观察股票：":
            capture = True
            continue
        if capture and line.strip():
            rows.append(line)
    return rows[:3] or ["1. 暂无", "2. 暂无", "3. 暂无"]


def _extract_market_risk(report_text: str) -> str:
    for line in report_text.splitlines():
        if line.startswith("市场状态："):
            return f"今日市场风险等级：{line.split('：', 1)[1]}"
    return "今日市场风险等级：暂无数据"


def _section_lines(report_text: str, heading: str) -> list[str]:
    lines = report_text.splitlines()
    try:
        start = lines.index(heading) + 1
    except ValueError:
        return []
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return lines[start:end]


def _email_result(
    *,
    email_sent: bool,
    smtp_connection: str,
    gmail_auth: str,
    missing_secrets: tuple[str, ...],
    error: str,
    smtp_details: SmtpSendDetails | None = None,
) -> EmailSendResult:
    lines = [
        f"email_sent={str(email_sent).lower()}",
        f"smtp_connection={smtp_connection}",
        f"gmail_auth={gmail_auth}",
        f"missing_secrets={','.join(missing_secrets) if missing_secrets else 'none'}",
        f"error={error or 'none'}",
    ]
    if smtp_details is not None:
        lines.extend(
            [
                f"message_id={smtp_details.message_id}",
                f"smtp_ehlo_code={smtp_details.smtp_ehlo_code}",
                f"smtp_ehlo_response={smtp_details.smtp_ehlo_response}",
                f"smtp_starttls_code={smtp_details.smtp_starttls_code}",
                f"smtp_starttls_response={smtp_details.smtp_starttls_response}",
                f"smtp_tls_ehlo_code={smtp_details.smtp_tls_ehlo_code}",
                f"smtp_tls_ehlo_response={smtp_details.smtp_tls_ehlo_response}",
                f"smtp_login_code={smtp_details.smtp_login_code}",
                f"smtp_login_response={smtp_details.smtp_login_response}",
                f"smtp_mail_code={smtp_details.smtp_mail_code}",
                f"smtp_mail_response={smtp_details.smtp_mail_response}",
                f"smtp_rcpt_code={smtp_details.smtp_rcpt_code}",
                f"smtp_rcpt_response={smtp_details.smtp_rcpt_response}",
                f"smtp_data_code={smtp_details.smtp_data_code}",
                f"smtp_data_response={smtp_details.smtp_data_response}",
            ]
        )
    return EmailSendResult(
        email_sent=email_sent,
        smtp_connection=smtp_connection,
        gmail_auth=gmail_auth,
        missing_secrets=missing_secrets,
        error=error,
        log_text="\n".join(lines) + "\n",
    )


def _decode_smtp_response(response) -> str:
    if isinstance(response, bytes):
        return response.decode("utf-8", errors="replace").replace("\n", "\\n")
    return str(response).replace("\n", "\\n")
