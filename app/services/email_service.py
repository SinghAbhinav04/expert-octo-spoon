"""
Email OTP Service + Login Alert

Generates 6-digit OTP codes and sends them via Gmail SMTP.
Sends login security alerts with IP, device, and location.
"""
import random
import hashlib
import ssl
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
import httpx

from app.config import settings


def generate_otp() -> str:
    """Generate a random 6-digit OTP code"""
    return str(random.randint(100000, 999999))


def hash_otp(otp_code: str) -> str:
    """Hash OTP for secure storage (SHA-256)"""
    return hashlib.sha256(otp_code.encode()).hexdigest()


def get_otp_expiry() -> datetime:
    """Get OTP expiration timestamp"""
    return datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)


def _send_email(msg: MIMEMultipart, to_email: str) -> bool:
    """Shared SMTP sender with TLS bypass"""
    if not settings.SMTP_EMAIL or not settings.SMTP_PASSWORD:
        print(f"⚠️ SMTP not configured — skipping email to {to_email}")
        return True
    
    try:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls(context=context)
            server.login(settings.SMTP_EMAIL, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_EMAIL, to_email, msg.as_string())
        
        return True
    except Exception as e:
        print(f"❌ Failed to send email to {to_email}: {e}")
        return False


def _build_otp_email(to_email: str, otp_code: str, action: str = "verify") -> MIMEMultipart:
    """Build a styled HTML email with the OTP code."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🔐 minimal.ai — Your verification code: {otp_code}"
    msg["From"] = f"minimal.ai <{settings.SMTP_EMAIL}>"
    msg["To"] = to_email

    action_text = "complete your signup" if action == "signup" else "log into your account"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
    </head>
    <body style="margin:0;padding:0;background:#0a0a0f;font-family:'Segoe UI',Roboto,sans-serif;">
        <div style="max-width:480px;margin:40px auto;padding:32px;background:linear-gradient(145deg,#13131a,#1a1a2e);border-radius:16px;border:1px solid rgba(99,102,241,0.2);">
            <div style="text-align:center;margin-bottom:24px;">
                <span style="font-size:36px;">🧠</span>
                <h1 style="color:#e2e8f0;font-size:24px;margin:8px 0 0;">minimal.ai</h1>
            </div>
            <p style="color:#94a3b8;font-size:15px;text-align:center;line-height:1.6;margin:0 0 24px;">
                Use the code below to {action_text}.<br>
                This code expires in <strong style="color:#a78bfa;">{settings.OTP_EXPIRE_MINUTES} minutes</strong>.
            </p>
            <div style="text-align:center;margin:24px 0;">
                <div style="display:inline-block;background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:16px 40px;border-radius:12px;letter-spacing:12px;font-size:32px;font-weight:700;color:#ffffff;">
                    {otp_code}
                </div>
            </div>
            <p style="color:#64748b;font-size:13px;text-align:center;margin:24px 0 0;line-height:1.5;">
                If you didn't request this code, you can safely ignore this email.
                <br>Never share this code with anyone.
            </p>
            <div style="border-top:1px solid rgba(99,102,241,0.15);margin-top:24px;padding-top:16px;text-align:center;">
                <span style="color:#475569;font-size:11px;">© 2026 minimal.ai — AI-Powered Task Execution</span>
            </div>
        </div>
    </body>
    </html>
    """

    plain = f"Your minimal.ai verification code is: {otp_code}\n\nThis code expires in {settings.OTP_EXPIRE_MINUTES} minutes.\nIf you didn't request this code, ignore this email."

    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    return msg


def send_otp_email(to_email: str, otp_code: str, action: str = "verify") -> bool:
    """Send OTP email via Gmail SMTP."""
    # ALWAYS LOG OTP FOR DEBUGGING (Since Railway blocks SMTP)
    print(f"🔐 DEBUG OTP for {to_email}: {otp_code}")

    msg = _build_otp_email(to_email, otp_code, action)
    success = _send_email(msg, to_email)
    
    if success:
        print(f"✅ OTP email sent to {to_email}")
        return True
    else:
        print(f"❌ Failed to send OTP email to {to_email} (Network/Auth Error)")
        # Allow proceeding to OTP entry screen anyway (User can read logs)
        return True


# ===== Login Security Alert =====

def _get_location_from_ip(ip: str) -> dict:
    """Get location info from IP using ip-api.com (free, no key needed)"""
    try:
        # Skip for localhost/private IPs
        if ip in ("127.0.0.1", "::1", "localhost") or ip.startswith(("10.", "192.168.", "172.")):
            return {"city": "Local", "region": "", "country": "Development", "isp": "localhost"}
        
        resp = httpx.get(f"http://ip-api.com/json/{ip}?fields=city,regionName,country,isp", timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "city": data.get("city", "Unknown"),
                "region": data.get("regionName", ""),
                "country": data.get("country", "Unknown"),
                "isp": data.get("isp", "Unknown")
            }
    except Exception:
        pass
    return {"city": "Unknown", "region": "", "country": "Unknown", "isp": "Unknown"}


def _parse_device(user_agent: str) -> str:
    """Extract a human-readable device/browser string from User-Agent"""
    ua = user_agent.lower()
    
    # Browser
    browser = "Unknown Browser"
    if "chrome" in ua and "edg" not in ua:
        browser = "Chrome"
    elif "firefox" in ua:
        browser = "Firefox"
    elif "safari" in ua and "chrome" not in ua:
        browser = "Safari"
    elif "edg" in ua:
        browser = "Edge"
    elif "curl" in ua:
        browser = "cURL"
    elif "python" in ua:
        browser = "Python Client"
    
    # OS
    os_name = "Unknown OS"
    if "windows" in ua:
        os_name = "Windows"
    elif "macintosh" in ua or "mac os" in ua:
        os_name = "macOS"
    elif "linux" in ua:
        os_name = "Linux"
    elif "android" in ua:
        os_name = "Android"
    elif "iphone" in ua or "ipad" in ua:
        os_name = "iOS"
    
    return f"{browser} on {os_name}"


def send_login_alert_email(to_email: str, ip_address: str, user_agent: str) -> bool:
    """
    Send a security alert email when a user successfully logs in.
    Includes IP, device info, and geo-location.
    """
    location = _get_location_from_ip(ip_address)
    device = _parse_device(user_agent)
    login_time = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")
    
    loc_string = location["city"]
    if location["region"]:
        loc_string += f", {location['region']}"
    loc_string += f", {location['country']}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "🔔 minimal.ai — New login to your account"
    msg["From"] = f"minimal.ai <{settings.SMTP_EMAIL}>"
    msg["To"] = to_email

    html = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="margin:0;padding:0;background:#0a0a0f;font-family:'Segoe UI',Roboto,sans-serif;">
        <div style="max-width:480px;margin:40px auto;padding:32px;background:linear-gradient(145deg,#13131a,#1a1a2e);border-radius:16px;border:1px solid rgba(99,102,241,0.2);">
            <div style="text-align:center;margin-bottom:24px;">
                <span style="font-size:36px;">🔔</span>
                <h1 style="color:#e2e8f0;font-size:24px;margin:8px 0 0;">New Login Detected</h1>
            </div>
            
            <p style="color:#94a3b8;font-size:15px;text-align:center;line-height:1.6;margin:0 0 24px;">
                Your minimal.ai account was just accessed. Here are the details:
            </p>
            
            <!-- Details Table -->
            <div style="background:rgba(99,102,241,0.06);border:1px solid rgba(99,102,241,0.15);border-radius:12px;padding:20px;margin:0 0 24px;">
                <table style="width:100%;border-collapse:collapse;">
                    <tr>
                        <td style="color:#64748b;font-size:13px;padding:8px 0;border-bottom:1px solid rgba(99,102,241,0.1);">📍 Location</td>
                        <td style="color:#e2e8f0;font-size:14px;font-weight:500;padding:8px 0;text-align:right;border-bottom:1px solid rgba(99,102,241,0.1);">{loc_string}</td>
                    </tr>
                    <tr>
                        <td style="color:#64748b;font-size:13px;padding:8px 0;border-bottom:1px solid rgba(99,102,241,0.1);">🌐 IP Address</td>
                        <td style="color:#e2e8f0;font-size:14px;font-weight:500;padding:8px 0;text-align:right;border-bottom:1px solid rgba(99,102,241,0.1);font-family:monospace;">{ip_address}</td>
                    </tr>
                    <tr>
                        <td style="color:#64748b;font-size:13px;padding:8px 0;border-bottom:1px solid rgba(99,102,241,0.1);">💻 Device</td>
                        <td style="color:#e2e8f0;font-size:14px;font-weight:500;padding:8px 0;text-align:right;border-bottom:1px solid rgba(99,102,241,0.1);">{device}</td>
                    </tr>
                    <tr>
                        <td style="color:#64748b;font-size:13px;padding:8px 0;">🕐 Time</td>
                        <td style="color:#e2e8f0;font-size:14px;font-weight:500;padding:8px 0;text-align:right;">{login_time}</td>
                    </tr>
                </table>
            </div>
            
            <p style="color:#f59e0b;font-size:13px;text-align:center;margin:0 0 16px;line-height:1.5;">
                ⚠️ If this wasn't you, please change your password immediately.
            </p>
            
            <div style="border-top:1px solid rgba(99,102,241,0.15);margin-top:16px;padding-top:16px;text-align:center;">
                <span style="color:#475569;font-size:11px;">© 2026 minimal.ai — AI-Powered Task Execution</span>
            </div>
        </div>
    </body>
    </html>
    """

    plain = f"""New login to your minimal.ai account

Location: {loc_string}
IP Address: {ip_address}
Device: {device}
Time: {login_time}
ISP: {location['isp']}

If this wasn't you, change your password immediately."""

    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    success = _send_email(msg, to_email)
    if success:
        print(f"✅ Login alert sent to {to_email} (IP: {ip_address})")
    return success
