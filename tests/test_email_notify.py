from datetime import date

from stock_selector.email_notify import (
    EmailConfig,
    build_today_stock_message,
    missing_email_secrets,
    send_today_stock_email_from_env,
)


REPORT = """# 今日主板选股摘要: 2026-06-23

数据源名称：Sina
数据日期：2026-06-23
是否实时数据：是
是否允许作为正式选股依据：是
数据来源：实时数据
市场状态：谨慎
市场评分：51.94/100

## 今日推荐3只主板股票

### 1. 生益科技 (600183)
- 所属板块：C39计算机、通信和其他电子设备制造业
- 最终评分：73.30
- 推荐理由：收盘价高于20日均线

### 2. 巨化股份 (600160)
- 所属板块：C26化学原料和化学制品制造业
- 最终评分：69.00
- 推荐理由：均线多头排列

## 最近5日重复上榜观察池

| 股票 | 今日排名 | 连续上榜天数 | 最近5日出现次数 | 最新评分 | 操作建议 |
| --- | ---: | ---: | ---: | ---: | --- |
| 600160 巨化股份 | 2 | 2 | 2 | 69.00 | 暂不操作 |
| 600183 生益科技 | 1 | 1 | 1 | 73.30 | 暂不操作 |

今日优先观察股票：
1. 暂无
2. 暂无
3. 暂无
"""


def test_build_today_stock_message_uses_final_report_body() -> None:
    config = EmailConfig(
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        smtp_user="sender@gmail.com",
        smtp_password="password",
        mail_to="target@gmail.com",
        mail_from="sender@gmail.com",
    )

    message = build_today_stock_message(report_text=REPORT, trade_date=date(2026, 6, 23), config=config)
    body = message.get_content()

    assert message["Subject"] == "A股自动选股日报 2026-06-23【实时数据】"
    assert message["Message-ID"]
    assert body.startswith(REPORT.rstrip())
    assert "## 今日推荐3只主板股票" in body
    assert "### 1. 生益科技 (600183)" in body
    assert "### 2. 巨化股份 (600160)" in body
    assert "邮件审计" in body
    assert "Git Commit：unknown" in body
    assert "Workflow Run ID：local" in body
    assert "today_stock.md SHA256：" in body
    assert "Email Body SHA256：" in body
    assert "Body matches today_stock：True" in body


def test_failure_source_uses_failure_subject_and_no_first_pick() -> None:
    config = EmailConfig(
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        smtp_user="sender@gmail.com",
        smtp_password="password",
        mail_to="target@gmail.com",
        mail_from="sender@gmail.com",
    )
    failed_report = REPORT.replace("是否实时数据：是", "是否实时数据：否").replace(
        "是否允许作为正式选股依据：是", "是否允许作为正式选股依据：否"
    ).replace("数据来源：实时数据", "数据来源：实时数据获取失败")

    message = build_today_stock_message(report_text=failed_report, trade_date=date(2026, 6, 23), config=config)
    body = message.get_content()

    assert message["Subject"] == "A股自动选股日报 2026-06-23【实时数据获取失败】"
    assert body.startswith(failed_report.rstrip())
    assert "数据来源：实时数据获取失败" in body
    assert "Body matches today_stock：True" in body


def test_missing_email_secrets_are_reported(monkeypatch) -> None:
    monkeypatch.delenv("GMAIL_USER", raising=False)
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.delenv("MAIL_TO", raising=False)

    assert missing_email_secrets() == ("GMAIL_USER", "GMAIL_APP_PASSWORD", "MAIL_TO")


def test_send_today_stock_email_from_env_skips_when_config_missing(tmp_path, monkeypatch) -> None:
    report_path = tmp_path / "today_stock.md"
    report_path.write_text(REPORT, encoding="utf-8")
    monkeypatch.delenv("GMAIL_USER", raising=False)
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("GMAIL_APP_PASSWORD", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.delenv("MAIL_TO", raising=False)

    result = send_today_stock_email_from_env(report_path=report_path, trade_date=date(2026, 6, 23))

    assert result.email_sent is False
    assert result.smtp_connection == "not_attempted"
    assert result.gmail_auth == "not_attempted"
    assert result.missing_secrets == ("GMAIL_USER", "GMAIL_APP_PASSWORD", "MAIL_TO")
    assert "missing secrets" in result.error
