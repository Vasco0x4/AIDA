"""
Notification service - sends alerts via Telegram, Slack, and Email
"""
import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any

import httpx
from sqlalchemy.orm import Session
from sqlalchemy import func

from models.notification_config import NotificationConfig
from models.card import Card
from models.command_history import CommandHistory
from models.assessment import Assessment
from utils.logger import get_logger

logger = get_logger(__name__)


class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_configs(self):
        return self.db.query(NotificationConfig).all()

    def get_config(self, channel: str) -> Optional[NotificationConfig]:
        return self.db.query(NotificationConfig).filter(
            NotificationConfig.channel == channel
        ).first()

    def upsert_config(self, channel: str, **kwargs) -> NotificationConfig:
        config = self.get_config(channel)
        if config:
            for key, value in kwargs.items():
                if value is not None:
                    setattr(config, key, value)
        else:
            config = NotificationConfig(channel=channel, **kwargs)
            self.db.add(config)
        self.db.commit()
        self.db.refresh(config)
        return config

    def delete_config(self, channel: str) -> bool:
        config = self.get_config(channel)
        if not config:
            return False
        self.db.delete(config)
        self.db.commit()
        return True

    async def notify_finding(self, assessment_name: str, title: str, severity: str, details: str = ""):
        """Send notification for a new finding based on severity preferences"""
        configs = self.get_all_configs()
        for cfg in configs:
            if not cfg.enabled:
                continue
            if severity == "CRITICAL" and not cfg.on_critical_finding:
                continue
            if severity == "HIGH" and not cfg.on_high_finding:
                continue
            if severity not in ("CRITICAL", "HIGH"):
                continue

            message = (
                f"[{severity}] New Finding\n"
                f"Assessment: {assessment_name}\n"
                f"Title: {title}\n"
            )
            if details:
                message += f"Details: {details[:500]}\n"

            await self._send(cfg, message)

    async def notify_scan_complete(self, assessment_name: str, command: str, result_summary: str = ""):
        """Send notification when a scan completes"""
        configs = self.get_all_configs()
        for cfg in configs:
            if not cfg.enabled or not cfg.on_scan_complete:
                continue
            message = (
                f"Scan Complete\n"
                f"Assessment: {assessment_name}\n"
                f"Command: {command[:200]}\n"
            )
            if result_summary:
                message += f"Summary: {result_summary[:300]}\n"
            await self._send(cfg, message)

    async def notify_assessment_complete(self, assessment_name: str):
        """Send notification when an assessment is marked complete"""
        configs = self.get_all_configs()
        for cfg in configs:
            if not cfg.enabled or not cfg.on_assessment_complete:
                continue
            message = f"Assessment Complete: {assessment_name}"
            await self._send(cfg, message)

    async def test_channel(self, channel: str) -> tuple[bool, str]:
        """Send a test message to verify channel configuration"""
        config = self.get_config(channel)
        if not config:
            return False, f"No configuration found for channel: {channel}"

        test_message = "AIDA Test Notification - Your notification channel is configured correctly!"

        try:
            await self._send(config, test_message)
            return True, "Test notification sent successfully"
        except Exception as e:
            return False, f"Failed to send test notification: {str(e)}"

    def build_assessment_report(
        self,
        assessment_id: int,
        include_findings: bool = True,
        include_stats: bool = True,
        include_commands: bool = False,
        custom_message: str = None,
    ) -> str:
        """Build a text report for an assessment"""
        assessment = self.db.query(Assessment).filter(Assessment.id == assessment_id).first()
        if not assessment:
            return "Assessment not found"

        lines = []
        lines.append(f"{'='*40}")
        lines.append(f"AIDA Assessment Report")
        lines.append(f"{'='*40}")
        lines.append(f"Name: {assessment.name}")
        if assessment.client_name:
            lines.append(f"Client: {assessment.client_name}")
        lines.append(f"Status: {assessment.status}")
        if assessment.scope:
            lines.append(f"Scope: {assessment.scope[:300]}")
        lines.append("")

        if custom_message:
            lines.append(custom_message)
            lines.append("")

        if include_stats:
            # Count by severity
            severity_counts = (
                self.db.query(Card.severity, func.count(Card.id))
                .filter(Card.assessment_id == assessment_id, Card.card_type == "finding")
                .group_by(Card.severity)
                .all()
            )
            total_findings = sum(c for _, c in severity_counts)
            observations = self.db.query(func.count(Card.id)).filter(
                Card.assessment_id == assessment_id, Card.card_type == "observation"
            ).scalar()
            cmd_count = self.db.query(func.count(CommandHistory.id)).filter(
                CommandHistory.assessment_id == assessment_id
            ).scalar()

            lines.append("--- Statistics ---")
            lines.append(f"Total Findings: {total_findings}")
            for sev, count in sorted(severity_counts, key=lambda x: ["CRITICAL","HIGH","MEDIUM","LOW","INFO"].index(x[0]) if x[0] in ["CRITICAL","HIGH","MEDIUM","LOW","INFO"] else 99):
                lines.append(f"  {sev}: {count}")
            lines.append(f"Observations: {observations}")
            lines.append(f"Commands Executed: {cmd_count}")
            lines.append("")

        if include_findings:
            findings = (
                self.db.query(Card)
                .filter(Card.assessment_id == assessment_id, Card.card_type == "finding")
                .order_by(
                    func.array_position(
                        ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"],
                        Card.severity
                    )
                )
                .all()
            )
            if findings:
                lines.append("--- Findings ---")
                for f in findings:
                    lines.append(f"[{f.severity or 'N/A'}] {f.title}")
                    if f.target_service:
                        lines.append(f"  Target: {f.target_service}")
                    if f.status:
                        lines.append(f"  Status: {f.status}")
                    lines.append("")

        if include_commands:
            commands = (
                self.db.query(CommandHistory)
                .filter(CommandHistory.assessment_id == assessment_id)
                .order_by(CommandHistory.created_at.desc())
                .limit(20)
                .all()
            )
            if commands:
                lines.append("--- Recent Commands ---")
                for cmd in commands:
                    status_icon = "OK" if cmd.success else "FAIL"
                    lines.append(f"[{status_icon}] {cmd.command[:100]}")
                lines.append("")

        lines.append(f"{'='*40}")
        lines.append("Generated by AIDA")
        return "\n".join(lines)

    async def send_report(
        self,
        channel: str,
        assessment_id: int,
        include_findings: bool = True,
        include_stats: bool = True,
        include_commands: bool = False,
        custom_message: str = None,
    ) -> tuple[bool, str]:
        """Generate PDF report and send it as a file attachment"""
        config = self.get_config(channel)
        if not config:
            return False, f"Channel '{channel}' is not configured. Go to Settings > Notifications to set it up."
        if not config.enabled:
            return False, f"Channel '{channel}' is configured but disabled. Enable it in Settings > Notifications."

        # Generate PDF using existing report service
        from services.report_service import generate_pdf_report

        try:
            pdf_buffer = generate_pdf_report(self.db, assessment_id)
        except Exception as e:
            return False, f"Failed to generate PDF: {str(e)}"

        # Get assessment name for filename
        assessment = self.db.query(Assessment).filter(Assessment.id == assessment_id).first()
        safe_name = (assessment.name if assessment else "report").replace(" ", "_")
        filename = f"AIDA_Report_{safe_name}.pdf"

        # Build a short caption
        caption = f"AIDA Report: {assessment.name}" if assessment else "AIDA Report"
        if custom_message:
            caption += f"\n{custom_message}"

        try:
            await self._send_file(config, pdf_buffer.getvalue(), filename, caption)
            return True, f"PDF report sent via {channel}"
        except Exception as e:
            return False, f"Failed to send PDF: {str(e)}"

    async def _send_file(self, config: NotificationConfig, file_bytes: bytes, filename: str, caption: str = ""):
        """Route file to the appropriate channel sender"""
        try:
            if config.channel == "telegram":
                await self._send_telegram_file(config.config, file_bytes, filename, caption)
            elif config.channel == "slack":
                await self._send_slack_file(config.config, file_bytes, filename, caption)
            elif config.channel == "email":
                await self._send_email_file(config.config, file_bytes, filename, caption)
            else:
                raise ValueError(f"Unknown channel: {config.channel}")
        except Exception as e:
            logger.error("Failed to send file", channel=config.channel, error=str(e))
            raise

    async def _send_telegram_file(self, cfg: Dict[str, Any], file_bytes: bytes, filename: str, caption: str):
        bot_token = cfg.get("bot_token", "")
        chat_id = cfg.get("chat_id", "")
        if not bot_token or not chat_id:
            raise ValueError("Telegram bot_token and chat_id are required")

        url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url,
                data={"chat_id": chat_id, "caption": caption[:1024]},
                files={"document": (filename, file_bytes, "application/pdf")},
            )
            if resp.status_code != 200:
                raise RuntimeError(f"Telegram API error: {resp.status_code} - {resp.text}")
        logger.info("Telegram PDF sent", chat_id=chat_id, filename=filename)

    async def _send_slack_file(self, cfg: Dict[str, Any], file_bytes: bytes, filename: str, caption: str):
        webhook_url = cfg.get("webhook_url", "")
        if not webhook_url:
            raise ValueError("Slack webhook_url is required")

        # Slack webhooks don't support file uploads, send a message with a note
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json={
                "text": f"{caption}\n_PDF report generated. Use the AIDA web interface to download it._"
            })
            if resp.status_code != 200:
                raise RuntimeError(f"Slack webhook error: {resp.status_code} - {resp.text}")
        logger.info("Slack notification sent (PDF not attachable via webhook)")

    async def _send_email_file(self, cfg: Dict[str, Any], file_bytes: bytes, filename: str, caption: str):
        from email.mime.application import MIMEApplication

        smtp_host = cfg.get("smtp_host", "")
        smtp_port = cfg.get("smtp_port", 587)
        username = cfg.get("username", "")
        password = cfg.get("password", "")
        from_email = cfg.get("from_email", username)
        to_emails = cfg.get("to_emails", [])
        encryption = cfg.get("encryption", "starttls")

        if not smtp_host or not to_emails:
            raise ValueError("SMTP host and to_emails are required")

        msg = MIMEMultipart()
        msg["From"] = from_email
        msg["To"] = ", ".join(to_emails)
        msg["Subject"] = f"AIDA Report - {filename}"
        msg.attach(MIMEText(caption, "plain"))

        pdf_part = MIMEApplication(file_bytes, _subtype="pdf")
        pdf_part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(pdf_part)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._smtp_send, smtp_host, smtp_port, username, password, from_email, to_emails, msg, encryption)
        logger.info("Email PDF sent", to=to_emails, filename=filename)

    async def _send(self, config: NotificationConfig, message: str):
        """Route message to the appropriate channel sender"""
        try:
            if config.channel == "telegram":
                await self._send_telegram(config.config, message)
            elif config.channel == "slack":
                await self._send_slack(config.config, message)
            elif config.channel == "email":
                await self._send_email(config.config, message)
            else:
                logger.warning("Unknown notification channel", channel=config.channel)
        except Exception as e:
            logger.error("Failed to send notification", channel=config.channel, error=str(e))
            raise

    async def _send_telegram(self, cfg: Dict[str, Any], message: str):
        bot_token = cfg.get("bot_token", "")
        chat_id = cfg.get("chat_id", "")
        if not bot_token or not chat_id:
            raise ValueError("Telegram bot_token and chat_id are required")

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
            })
            if resp.status_code != 200:
                raise RuntimeError(f"Telegram API error: {resp.status_code} - {resp.text}")
        logger.info("Telegram notification sent", chat_id=chat_id)

    async def _send_slack(self, cfg: Dict[str, Any], message: str):
        webhook_url = cfg.get("webhook_url", "")
        if not webhook_url:
            raise ValueError("Slack webhook_url is required")

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_url, json={"text": message})
            if resp.status_code != 200:
                raise RuntimeError(f"Slack webhook error: {resp.status_code} - {resp.text}")
        logger.info("Slack notification sent")

    async def _send_email(self, cfg: Dict[str, Any], message: str):
        smtp_host = cfg.get("smtp_host", "")
        smtp_port = cfg.get("smtp_port", 587)
        username = cfg.get("username", "")
        password = cfg.get("password", "")
        from_email = cfg.get("from_email", username)
        to_emails = cfg.get("to_emails", [])
        encryption = cfg.get("encryption", "starttls")  # none, starttls, ssl
        subject = cfg.get("subject", "AIDA Security Alert")

        if not smtp_host or not to_emails:
            raise ValueError("SMTP host and to_emails are required")

        msg = MIMEMultipart()
        msg["From"] = from_email
        msg["To"] = ", ".join(to_emails)
        msg["Subject"] = subject
        msg.attach(MIMEText(message, "plain"))

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._smtp_send, smtp_host, smtp_port, username, password, from_email, to_emails, msg, encryption)
        logger.info("Email notification sent", to=to_emails, encryption=encryption)

    @staticmethod
    def _smtp_send(host, port, username, password, from_email, to_emails, msg, encryption="starttls"):
        if encryption == "ssl":
            with smtplib.SMTP_SSL(host, port) as server:
                if username and password:
                    server.login(username, password)
                server.sendmail(from_email, to_emails, msg.as_string())
        else:
            with smtplib.SMTP(host, port) as server:
                if encryption == "starttls":
                    server.starttls()
                if username and password:
                    server.login(username, password)
                server.sendmail(from_email, to_emails, msg.as_string())
