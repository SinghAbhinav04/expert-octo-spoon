"""
Email Tool — Sends emails via the existing email service as an agent tool.

This tool requires confirmation for sensitive actions.
"""
from app.agent.tool_registry import Tool, ToolResult, ToolParameter, ToolCategory


class EmailTool(Tool):
    """Send emails using the Resend email service"""

    def __init__(self):
        super().__init__(
            name="send_email",
            description=(
                "Send an email to a specified recipient. Use ONLY when the user "
                "explicitly asks to send an email. Requires email address and content."
            ),
            category=ToolCategory.COMMUNICATION,
            parameters=[
                ToolParameter(
                    name="to_email",
                    type="string",
                    description="Recipient email address",
                    required=True,
                ),
                ToolParameter(
                    name="subject",
                    type="string",
                    description="Email subject line",
                    required=True,
                ),
                ToolParameter(
                    name="body",
                    type="string",
                    description="Email body content (plain text)",
                    required=True,
                ),
            ],
            requires_confirmation=True,  # Sensitive action
        )

    async def execute(self, **kwargs) -> ToolResult:
        """Execute email send"""
        to_email = kwargs.get("to_email")
        subject = kwargs.get("subject")
        body = kwargs.get("body")

        if not to_email or not subject or not body:
            return ToolResult(
                success=False,
                error="'to_email', 'subject', and 'body' are all required",
            )

        try:
            from app.services.email_service import _send_email_resend

            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head><meta charset="utf-8"></head>
            <body style="margin:0;padding:0;background:#0a0a0f;font-family:'Segoe UI',Roboto,sans-serif;">
                <div style="max-width:560px;margin:40px auto;padding:32px;background:linear-gradient(145deg,#13131a,#1a1a2e);border-radius:16px;border:1px solid rgba(99,102,241,0.2);">
                    <div style="text-align:center;margin-bottom:24px;">
                        <h1 style="color:#e2e8f0;font-size:20px;margin:0;">minimal.ai</h1>
                    </div>
                    <div style="color:#cbd5e1;font-size:15px;line-height:1.7;white-space:pre-wrap;">{body}</div>
                    <p style="color:#64748b;font-size:12px;text-align:center;margin:24px 0 0;">
                        Sent by minimal.ai agent
                    </p>
                </div>
            </body>
            </html>
            """

            success = _send_email_resend(to_email, subject, html_content, body)

            if success:
                return ToolResult(
                    success=True,
                    output=f"Email sent to {to_email} with subject: {subject}",
                    metadata={"to": to_email, "subject": subject},
                )
            else:
                return ToolResult(
                    success=False,
                    error=f"Email service returned failure for {to_email}",
                )

        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Email sending failed: {str(e)}",
            )
