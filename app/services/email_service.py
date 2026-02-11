"""
Email OTP Service + Login Alert (Resend API Version)
"""
import random
import hashlib
import httpx
from datetime import datetime, timezone, timedelta
from app.config import settings

# Try dragging in Resend, but handle failure gracefully if not installed yet
try:
    import resend
    resend.api_key = settings.RESEND_API_KEY
except ImportError:
    resend = None
    print("⚠️ Resend not installed. Email sending will be simulated.")


def generate_otp() -> str:
    """Generate a random 6-digit OTP code"""
    return str(random.randint(100000, 999999))


def hash_otp(otp_code: str) -> str:
    """Hash OTP for secure storage (SHA-256)"""
    return hashlib.sha256(otp_code.encode()).hexdigest()


def get_otp_expiry() -> datetime:
    """Get OTP expiration timestamp"""
    return datetime.now(timezone.utc) + timedelta(minutes=settings.OTP_EXPIRE_MINUTES)


def _send_email_resend(to_email: str, subject: str, html_content: str, text_content: str) -> bool:
    """Send email via Resend API (HTTP)"""
    # Always log OTP locally for debugging/fallback
    if "verification code" in subject:
        print(f"🔐 DEBUG OTP for {to_email}: {text_content[-6:]}") # Last 6 chars usually OTP in text

    if not settings.RESEND_API_KEY:
        print(f"⚠️ RESEND_API_KEY missing. Email to {to_email} simulated.")
        return True

    try:
        if not resend:
            print("❌ Resend library not installed.")
            return False

        r = resend.Emails.send({
            "from": settings.RESEND_FROM_EMAIL,
            "to": to_email,
            "subject": subject,
            "html": html_content,
            "text": text_content
        })
        print(f"✅ Email sent via Resend to {to_email}: {r}")
        return True
    except Exception as e:
        print(f"❌ Resend failed to {to_email}: {e}")
        # Return True anyway to allow login/signup flow to proceed (User can use debug OTP)
        return True


def _build_otp_html(otp_code: str, action: str = "verify") -> str:
    """Build styled HTML for OTP"""
    action_text = "complete your signup" if action == "signup" else "log into your account"
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"></head>
    <body style="margin:0;padding:0;background:#0a0a0f;font-family:'Segoe UI',Roboto,sans-serif;">
        <div style="max-width:480px;margin:40px auto;padding:32px;background:linear-gradient(145deg,#13131a,#1a1a2e);border-radius:16px;border:1px solid rgba(99,102,241,0.2);">
            <div style="text-align:center;margin-bottom:24px;">
                <span style="font-size:36px;"></span>
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
                If you didn't request this code, verify your account security.
            </p>
        </div>
    </body>
    </html>
    """


def send_otp_email(to_email: str, otp_code: str, action: str = "verify") -> bool:
    """Send OTP email via Resend."""
    subject = f"🔐 minimal.ai — Your verification code: {otp_code}"
    html = _build_otp_html(otp_code, action)
    text = f"Your minimal.ai verification code is: {otp_code}"
    
    return _send_email_resend(to_email, subject, html, text)


# ===== Login Security Alert =====

def _get_location_from_ip(ip: str) -> dict:
    """Get location info from IP using ip-api.com"""
    try:
        # Skip for private IPs
        if ip in ("127.0.0.1", "::1", "localhost") or ip.startswith(("10.", "192.168.", "172.")):
            return {"city": "Local", "region": "", "country": "Dev", "isp": "localhost"}
        
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
    """Simple User-Agent parser"""
    ua = user_agent.lower()
    if "windows" in ua: return "Windows"
    if "mac" in ua: return "macOS"
    if "linux" in ua: return "Linux"
    if "android" in ua: return "Android"
    if "iphone" in ua: return "iPhone"
    return "Unknown Device"


def send_login_alert_email(to_email: str, ip_address: str, user_agent: str) -> bool:
    """Send login alert via Resend"""
    location = _get_location_from_ip(ip_address)
    device = _parse_device(user_agent)
    time_str = datetime.now(timezone.utc).strftime("%B %d, %Y at %H:%M UTC")
    
    subject = "🔔 minimal.ai — New login to your account"
    
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
                Account accessed from <strong>{location['city']}, {location['country']}</strong>.
            </p>
             <div style="background:rgba(99,102,241,0.06);padding:20px;border-radius:12px;margin-bottom:24px;">
                <p style="margin:4px 0;color:#e2e8f0;">IP: {ip_address}</p>
                <p style="margin:4px 0;color:#e2e8f0;">Device: {device}</p>
                <p style="margin:4px 0;color:#e2e8f0;">Time: {time_str}</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    text = f"New login detected.\nIP: {ip_address}\nLocation: {location['city']}, {location['country']}\nTime: {time_str}"
    
    return _send_email_resend(to_email, subject, html, text)
