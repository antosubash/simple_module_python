"""Public registration API for modules that provide a mail transport."""

from mail.core.transports import MailTransportFactory, register_mail_transport

__all__ = ["MailTransportFactory", "register_mail_transport"]
