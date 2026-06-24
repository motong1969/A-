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
    subject_suffix = "【实时数据获取失败】" if _is_failure_source(report_text) else "【实时数据】"
    message["Subject"] = f"A股自动选股日报 {trade_date.isoformat()}{subject_suffix}"
    message["From"] = config.mail_from
    message["To"] = config.mail_to
    message["Message-ID"] = make_msgid(domain="github-actions.local")
    message.set_content(_extract_email_body(report_text))
    return message


def _extract_email_body(report_text: str) -> str:
    lines = ["【数据来源】", _extract_data_source(report_text), ""]
    if _is_failure_source(report_text):
        lines.extend(["【实时数据获取失败】", *_extract_failure_summary(report_text), ""])
    elif _is_formal_realtime_source(report_text):
        lines.extend(["【今日首选】", *_extract_first_pick_summary(report_text), ""])
    else:
        lines.extend(["【观察名单】", *_extract_watchlist_summary(report_text), ""])
    lines.extend(
        [
            "【今日前三】",
            *([] if _is_failure_source(report_text) else _extract_top3_summary(report_text)),
            *(["未生成：实时数据获取失败。"] if _is_failure_source(report_text) else []),
            "",
            "【最近5日重复上榜统计】",
            *_extract_repeat_summary(report_text),
            "",
            "【系统建议】",
            *_extract_priority_summary(report_text),
            "",
            "【风险提示】",
            _extract_market_risk(report_text),
            "",
            "【数据验证】",
            *_extract_data_validation(report_text),
        ]
    )
    return "\n".join(lines).strip()


def _extract_first_pick_summary(report_text: str) -> list[str]:
    top3 = _top3_candidates(report_text)
    if not top3:
        return ["股票代码：暂无", "股票名称：暂无", "推荐等级：普通观察", "推荐理由：今日无可选股票。"]
    top3_codes = {item["code"] for item in top3}
    candidates = [item for item in _repeat_candidates(report_text) if item["code"] in top3_codes]
    if not candidates:
        candidates = top3
    first_pick = sorted(
        candidates,
        key=lambda item: (
            -item["list_count_5d"],
            -item["continuous_days"],
            -item["score"],
            item["rank"],
        ),
    )[0]
    level = _recommendation_level(first_pick)
    reason = (
        f"最近5日上榜 {first_pick['list_count_5d']} 次，连续上榜 {first_pick['continuous_days']} 天，"
        f"今日排名第 {first_pick['rank']}，总评分 {first_pick['score']:.2f}。"
    )
    return [
        f"股票代码：{first_pick['code']}",
        f"股票名称：{first_pick['name']}",
        f"推荐等级：{level}",
        f"推荐理由：{reason}",
    ]


def _extract_top3_summary(report_text: str) -> list[str]:
    rows = [
        f"股票代码：{item['code']}\n股票名称：{item['name']}\n总评分：{item['score']:.2f}"
        for item in _top3_candidates(report_text)
    ]
    return rows or ["暂无今日前三数据。"]


def _extract_repeat_summary(report_text: str) -> list[str]:
    rows = [
        f"股票代码：{item['code']}\n股票名称：{item['name']}\n上榜次数：{item['list_count_5d']}\n连续上榜天数：{item['continuous_days']}"
        for item in _repeat_candidates(report_text)
    ]
    return rows[:10] or ["暂无重复上榜统计。"]


def _top3_candidates(report_text: str) -> list[dict]:
    section = _section_lines(report_text, "## 今日推荐3只主板股票")
    rows = []
    current: dict | None = None
    for line in section:
        if line.startswith("### "):
            title = line.split(". ", 1)[-1]
            rank_text = line.removeprefix("### ").split(".", 1)[0]
            current = {
                "rank": _safe_int(rank_text, fallback=99),
                "name": title.split(" (", 1)[0],
                "code": title.rsplit("(", 1)[-1].rstrip(")") if "(" in title else "",
                "score": 0.0,
                "list_count_5d": 1,
                "continuous_days": 1,
            }
            rows.append(current)
            continue
        if current is not None and line.startswith("- 最终评分："):
            current["score"] = _safe_float(line.split("：", 1)[1])
    return [row for row in rows if row["code"]]


def _repeat_candidates(report_text: str) -> list[dict]:
    section = _section_lines(report_text, "## 最近5日重复上榜观察池")
    top3_by_code = {item["code"]: item for item in _top3_candidates(report_text)}
    rows = []
    for line in section:
        if not line.startswith("| ") or line.startswith("| ---") or "股票 | 今日排名" in line or "代码 | 名称" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells or cells[0] == "暂无":
            continue
        if len(cells) >= 8:
            code = cells[0]
            name = cells[1]
            list_count = _safe_int(cells[3])
            continuous = _safe_int(cells[4])
            rank = _safe_int(cells[5], fallback=99)
            score = _safe_float(cells[6])
        elif len(cells) >= 5:
            stock_parts = cells[0].split(maxsplit=1)
            code = stock_parts[0]
            name = stock_parts[1] if len(stock_parts) > 1 else ""
            rank = _safe_int(cells[1], fallback=99)
            continuous = _safe_int(cells[2])
            list_count = _safe_int(cells[3])
            score = _safe_float(cells[4])
        else:
            continue
        top3 = top3_by_code.get(code)
        rows.append(
            {
                "code": code,
                "name": name,
                "rank": rank,
                "score": score if score > 0 else (top3["score"] if top3 else 0.0),
                "list_count_5d": list_count,
                "continuous_days": continuous,
            }
        )
    return rows


def _recommendation_level(item: dict) -> str:
    if item["list_count_5d"] >= 3:
        return "强重点观察"
    if item["list_count_5d"] == 2:
        return "重点观察"
    if item["list_count_5d"] == 1 and item["rank"] == 1:
        return "短线观察"
    return "普通观察"


def _safe_int(value, *, fallback: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return fallback


def _safe_float(value) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0


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


def _extract_watchlist_summary(report_text: str) -> list[str]:
    candidates = _repeat_candidates(report_text) or _top3_candidates(report_text)
    if not candidates:
        return ["暂无观察股票。"]
    rows = []
    for index, item in enumerate(candidates[:3], start=1):
        rows.append(
            f"{index}. {item['code']} {item['name']}，今日排名第 {item['rank']}，"
            f"最近5日出现 {item['list_count_5d']} 次，连续上榜 {item['continuous_days']} 天，"
            f"总评分 {item['score']:.2f}，仅观察。"
        )
    return rows


def _extract_failure_summary(report_text: str) -> list[str]:
    section = _section_lines(report_text, "## 失败原因")
    reasons = [line.removeprefix("- ").strip() for line in section if line.startswith("- ")]
    if not reasons:
        reasons = ["所有实时行情源均不可用或未取得当天有效行情。"]
    metadata = [
        _extract_line(report_text, "数据源名称："),
        _extract_line(report_text, "数据日期："),
        _extract_line(report_text, "是否实时数据："),
        _extract_line(report_text, "是否允许作为正式选股依据："),
    ]
    return [line for line in metadata if line] + ["失败原因：" + "；".join(reasons[:5])]


def _extract_data_validation(report_text: str) -> list[str]:
    return [
        _extract_line(report_text, "数据源名称：") or "数据源名称：无",
        _extract_line(report_text, "数据日期：") or "数据日期：未知",
        _bool_line(report_text, "是否实时数据：", "is_realtime"),
        _bool_line(report_text, "是否允许作为正式选股依据：", "formal_allowed"),
    ]


def _bool_line(report_text: str, prefix: str, key: str) -> str:
    value = _extract_line(report_text, prefix).split("：", 1)[-1]
    return f"{key}={'true' if value == '是' else 'false'}"


def _extract_market_risk(report_text: str) -> str:
    for line in report_text.splitlines():
        if line.startswith("市场状态："):
            return f"今日市场风险等级：{line.split('：', 1)[1]}"
    return "今日市场风险等级：暂无数据"


def _extract_data_source(report_text: str) -> str:
    for line in report_text.splitlines():
        if line.startswith("数据来源："):
            return line
    return "数据来源：实时数据"


def _extract_line(report_text: str, prefix: str) -> str:
    for line in report_text.splitlines():
        if line.startswith(prefix):
            return line
    return ""


def _is_formal_realtime_source(report_text: str) -> bool:
    return (
        _extract_data_source(report_text) == "数据来源：实时数据"
        and _extract_line(report_text, "是否实时数据：") == "是否实时数据：是"
        and _extract_line(report_text, "是否允许作为正式选股依据：") == "是否允许作为正式选股依据：是"
    )


def _is_failure_source(report_text: str) -> bool:
    return not _is_formal_realtime_source(report_text)


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
