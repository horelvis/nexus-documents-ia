"""
Email service for sending notifications with templates
"""
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

try:
    from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
except Exception as fastapi_mail_error:  # pragma: no cover - module import guard
    FastMail = None
    MessageSchema = None
    ConnectionConfig = None
    MessageType = None
else:
    fastapi_mail_error = None

from pydantic import EmailStr, BaseModel
from jinja2 import Environment, FileSystemLoader, select_autoescape
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

# Email configuration
class EmailSettings(BaseModel):
    MAIL_USERNAME: str = settings.MAIL_USERNAME
    MAIL_PASSWORD: str = settings.MAIL_PASSWORD
    MAIL_FROM: EmailStr = settings.MAIL_FROM
    MAIL_FROM_NAME: str = settings.MAIL_FROM_NAME
    MAIL_PORT: int = settings.MAIL_PORT
    MAIL_SERVER: str = settings.MAIL_SERVER
    MAIL_STARTTLS: bool = settings.MAIL_STARTTLS
    MAIL_SSL_TLS: bool = settings.MAIL_SSL_TLS
    USE_CREDENTIALS: bool = settings.MAIL_USE_CREDENTIALS
    VALIDATE_CERTS: bool = settings.MAIL_VALIDATE_CERTS

# Configure email connection when FastMail is available
if FastMail and ConnectionConfig:
    conf = ConnectionConfig(
        MAIL_USERNAME=EmailSettings().MAIL_USERNAME,
        MAIL_PASSWORD=EmailSettings().MAIL_PASSWORD,
        MAIL_FROM=EmailSettings().MAIL_FROM,
        MAIL_FROM_NAME=EmailSettings().MAIL_FROM_NAME,
        MAIL_PORT=EmailSettings().MAIL_PORT,
        MAIL_SERVER=EmailSettings().MAIL_SERVER,
        MAIL_STARTTLS=EmailSettings().MAIL_STARTTLS,
        MAIL_SSL_TLS=EmailSettings().MAIL_SSL_TLS,
        USE_CREDENTIALS=EmailSettings().USE_CREDENTIALS,
        VALIDATE_CERTS=EmailSettings().VALIDATE_CERTS,
        TEMPLATE_FOLDER=Path(__file__).parent.parent / "templates" / "email"
    )
    fm = FastMail(conf)
else:  # pragma: no cover - configuration warning
    conf = None
    fm = None
    if fastapi_mail_error:
        logger.warning("FastMail is not available: %s", fastapi_mail_error)

# Initialize Jinja2 for template rendering
template_dir = Path(__file__).parent.parent / "templates" / "email"
env = Environment(
    loader=FileSystemLoader(str(template_dir)),
    autoescape=select_autoescape(['html', 'xml'])
)


class EmailService:
    """Service for sending emails with templates"""

    @staticmethod
    def _get_mail_client() -> "FastMail":
        """Ensure FastMail is configured before sending."""
        if fm is None:
            message = (
                "FastMail is not configured. Please verify the fastapi-mail dependency "
                "and email environment variables."
            )
            if fastapi_mail_error:
                raise RuntimeError(message) from fastapi_mail_error
            raise RuntimeError(message)
        return fm
    
    @staticmethod
    async def send_user_invitation(
        email: str,
        inviter_name: str,
        tenant_name: str,
        invitation_link: str,
        role: str = "user"
    ) -> bool:
        """Send invitation email to new user"""
        try:
            template = env.get_template("user_invitation.html")
            
            html_content = template.render(
                inviter_name=inviter_name,
                tenant_name=tenant_name,
                invitation_link=invitation_link,
                role=role,
                current_year=datetime.now().year
            )
            
            message = MessageSchema(
                subject=f"You've been invited to join {tenant_name}",
                recipients=[email],
                body=html_content,
                subtype=MessageType.html
            )
            
            mail_client = EmailService._get_mail_client()
            await mail_client.send_message(message)
            logger.info(f"Invitation email sent to {email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send invitation email: {str(e)}")
            return False
    
    @staticmethod
    async def send_team_invitation(
        email: str,
        team_name: str,
        inviter_name: str,
        invitation_link: str,
        expires_at: datetime
    ) -> bool:
        """Send team invitation email"""
        try:
            template = env.get_template("team_invitation.html")
            
            html_content = template.render(
                team_name=team_name,
                inviter_name=inviter_name,
                invitation_link=invitation_link,
                expires_at=expires_at.strftime("%B %d, %Y"),
                current_year=datetime.now().year
            )
            
            message = MessageSchema(
                subject=f"Join {team_name} team",
                recipients=[email],
                body=html_content,
                subtype=MessageType.html
            )
            
            mail_client = EmailService._get_mail_client()
            await mail_client.send_message(message)
            logger.info(f"Team invitation email sent to {email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send team invitation email: {str(e)}")
            return False
    
    @staticmethod
    async def send_password_reset(
        email: str,
        user_name: str,
        reset_link: str,
        expires_in_hours: int = 24
    ) -> bool:
        """Send password reset email"""
        try:
            template = env.get_template("password_reset.html")
            
            html_content = template.render(
                user_name=user_name,
                reset_link=reset_link,
                expires_in_hours=expires_in_hours,
                current_year=datetime.now().year
            )
            
            message = MessageSchema(
                subject="Reset your password",
                recipients=[email],
                body=html_content,
                subtype=MessageType.html
            )
            
            mail_client = EmailService._get_mail_client()
            await mail_client.send_message(message)
            logger.info(f"Password reset email sent to {email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send password reset email: {str(e)}")
            return False
    
    @staticmethod
    async def send_welcome_email(
        email: str,
        user_name: str,
        tenant_name: str,
        login_url: str
    ) -> bool:
        """Send welcome email to new user"""
        try:
            template = env.get_template("welcome.html")
            
            html_content = template.render(
                user_name=user_name,
                tenant_name=tenant_name,
                login_url=login_url,
                current_year=datetime.now().year
            )
            
            message = MessageSchema(
                subject=f"Welcome to {tenant_name}!",
                recipients=[email],
                body=html_content,
                subtype=MessageType.html
            )
            
            mail_client = EmailService._get_mail_client()
            await mail_client.send_message(message)
            logger.info(f"Welcome email sent to {email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send welcome email: {str(e)}")
            return False
    
    @staticmethod
    async def send_document_shared(
        email: str,
        recipient_name: str,
        sender_name: str,
        document_name: str,
        document_link: str,
        message: Optional[str] = None
    ) -> bool:
        """Send notification when document is shared"""
        try:
            template = env.get_template("document_shared.html")
            
            html_content = template.render(
                recipient_name=recipient_name,
                sender_name=sender_name,
                document_name=document_name,
                document_link=document_link,
                message=message,
                current_year=datetime.now().year
            )
            
            message_obj = MessageSchema(
                subject=f"{sender_name} shared a document with you",
                recipients=[email],
                body=html_content,
                subtype=MessageType.html
            )
            
            mail_client = EmailService._get_mail_client()
            await mail_client.send_message(message_obj)
            logger.info(f"Document shared email sent to {email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send document shared email: {str(e)}")
            return False
    
    @staticmethod
    async def send_share_notification(
        to_email: str,
        subject: str,
        template_data: Dict[str, Any]
    ) -> bool:
        """Send document share notification email"""
        try:
            template = env.get_template("document_share.html")
            
            # Add current year to context
            template_data['current_year'] = datetime.now().year
            
            # Format expires_at if present
            if 'expires_at' in template_data and template_data['expires_at']:
                if isinstance(template_data['expires_at'], datetime):
                    template_data['expires_at'] = template_data['expires_at'].strftime("%B %d, %Y at %I:%M %p")
            
            html_content = template.render(**template_data)
            
            message = MessageSchema(
                subject=subject,
                recipients=[to_email],
                body=html_content,
                subtype=MessageType.html
            )
            
            mail_client = EmailService._get_mail_client()
            await mail_client.send_message(message)
            logger.info(f"Share notification email sent to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send share notification email: {str(e)}")
            return False
    
    @staticmethod
    async def send_guest_otp(
        to_email: str,
        recipient_name: str,
        otp_code: str,
        expiry_minutes: int,
        tenant_name: str,
        language: str = "es"
    ) -> bool:
        """Send OTP code to site guest for portal authentication"""
        try:
            template = env.get_template("site_guest_otp.html")

            html_content = template.render(
                recipient_name=recipient_name,
                otp_code=otp_code,
                expiry_minutes=expiry_minutes,
                tenant_name=tenant_name,
                language=language,
                current_year=datetime.now().year
            )

            # Translated subjects
            subjects = {
                "en": f"Your access code for {tenant_name}",
                "fr": f"Votre code d'accès pour {tenant_name}",
                "es": f"Tu código de acceso para {tenant_name}"
            }
            subject = subjects.get(language, subjects["es"])

            message = MessageSchema(
                subject=subject,
                recipients=[to_email],
                body=html_content,
                subtype=MessageType.html
            )

            mail_client = EmailService._get_mail_client()
            await mail_client.send_message(message)
            logger.info(f"Guest OTP email sent to {to_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send guest OTP email: {str(e)}")
            return False

    @staticmethod
    async def send_guest_invitation(
        to_email: str,
        recipient_name: str,
        tenant_name: str,
        portal_url: str,
        welcome_message: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        can_view: bool = True,
        can_download: bool = False,
        language: str = "es"
    ) -> bool:
        """Send invitation to site guest to access the document portal"""
        try:
            template = env.get_template("site_guest_invitation.html")

            # Format expires_at based on language
            expires_at_str = None
            if expires_at:
                if language == "es":
                    expires_at_str = expires_at.strftime("%d de %B, %Y a las %H:%M")
                elif language == "fr":
                    expires_at_str = expires_at.strftime("%d %B %Y à %H:%M")
                else:
                    expires_at_str = expires_at.strftime("%B %d, %Y at %I:%M %p")

            html_content = template.render(
                recipient_name=recipient_name,
                tenant_name=tenant_name,
                portal_url=portal_url,
                welcome_message=welcome_message,
                expires_at=expires_at_str,
                can_view=can_view,
                can_download=can_download,
                language=language,
                current_year=datetime.now().year
            )

            # Translated subjects
            subjects = {
                "en": f"You've been invited to access {tenant_name}",
                "fr": f"Vous êtes invité à accéder à {tenant_name}",
                "es": f"Has sido invitado a acceder a {tenant_name}"
            }
            subject = subjects.get(language, subjects["es"])

            message = MessageSchema(
                subject=subject,
                recipients=[to_email],
                body=html_content,
                subtype=MessageType.html
            )

            mail_client = EmailService._get_mail_client()
            await mail_client.send_message(message)
            logger.info(f"Guest invitation email sent to {to_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send guest invitation email: {str(e)}")
            return False

    @staticmethod
    async def send_email(
        to: str,
        subject: str,
        template: str,
        **template_data: Any
    ) -> bool:
        """Send email to a single recipient using a template.

        Args:
            to: Recipient email address
            subject: Email subject
            template: Template name (without .html extension)
            **template_data: Variables to pass to the template

        Returns:
            True if email was sent successfully, False otherwise
        """
        try:
            template_obj = env.get_template(f"{template}.html")

            # Add default context
            template_data['current_year'] = datetime.now().year

            html_content = template_obj.render(**template_data)

            message = MessageSchema(
                subject=subject,
                recipients=[to],
                body=html_content,
                subtype=MessageType.html
            )

            mail_client = EmailService._get_mail_client()
            await mail_client.send_message(message)
            logger.info(f"Email sent to {to} with template {template}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to}: {str(e)}")
            return False

    @staticmethod
    async def send_bulk_email(
        recipients: List[str],
        subject: str,
        template_name: str,
        context: Dict[str, Any]
    ) -> bool:
        """Send bulk email with custom template"""
        try:
            template = env.get_template(f"{template_name}.html")
            
            # Add default context
            context['current_year'] = datetime.now().year
            
            html_content = template.render(**context)
            
            message = MessageSchema(
                subject=subject,
                recipients=recipients,
                body=html_content,
                subtype=MessageType.html
            )
            
            mail_client = EmailService._get_mail_client()
            await mail_client.send_message(message)
            logger.info(f"Bulk email sent to {len(recipients)} recipients")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send bulk email: {str(e)}")
            return False


# Singleton instance
email_service = EmailService()
