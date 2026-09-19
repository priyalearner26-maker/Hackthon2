"""Email workflow agent."""

import json
import re

import httpx

from backend.agents.base import Agent
from backend.app.config import settings
from backend.core.models import AgentContext
from backend.core.ai_controls import guard_input, guard_output, track_llm_run
from backend.integrations.graph_mail import GraphMailClient, GraphMailError


_last_mailbox_error = ""


def _openai_email_completion(instruction: str, email_text: str, max_tokens: int = 700) -> str | None:
    api_key = getattr(settings, "llm_api_key", "") or getattr(settings, "openai_api_key", "")
    if not api_key or getattr(settings, "llm_provider", "openai").casefold() != "openai":
        return None

    base_url = (getattr(settings, "openai_base_url", "") or "https://api.openai.com/v1").rstrip("/")
    model = getattr(settings, "llm_model", "gpt-4o-mini") or "gpt-4o-mini"
    instruction = guard_input(instruction)
    response = httpx.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are MailMate. Analyze workplace emails accurately and never invent facts.",
                },
                {"role": "user", "content": f"{instruction}\n\nEmails:\n{email_text}"},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
        },
        timeout=45.0,
    )
    response.raise_for_status()
    answer = guard_output(str(response.json()["choices"][0]["message"]["content"]))
    track_llm_run(
        "mailmate.llm",
        provider="openai",
        model=model,
        input_text=instruction,
        output_text=answer,
    )
    return answer


def _email_prompt_data(emails: list[dict[str, str]]) -> str:
    return "\n\n".join(
        f"Subject: {email.get('subject', '(no subject)')}\n"
        f"Sender: {email.get('sender', 'Unknown sender')}\n"
        f"Body: {_body_text(email)}"
        for email in emails
    )


def _ai_summaries(emails: list[dict[str, str]]) -> dict[str, str]:
    try:
        result = _openai_email_completion(
            'Return JSON only in this shape: {"summaries":[{"subject":"exact subject","summary":"concise factual summary"}]}.',
            _email_prompt_data(emails),
        )
        payload = json.loads(result or "{}")
        return {str(item["subject"]): str(item["summary"]) for item in payload.get("summaries", []) if item.get("subject")}
    except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return {}


def _ai_action_items(emails: list[dict[str, str]]) -> list[str]:
    try:
        result = _openai_email_completion(
            'Return JSON only in this shape: {"items":[{"subject":"exact subject","action":"specific action item"}]}. Return an empty list when no action is requested.',
            _email_prompt_data(emails),
        )
        payload = json.loads(result or "{}")
        return [
            f"{item['subject']}: {re.sub(r'^\\s*\\d+[.)]\\s*', '', str(item['action'])).strip()}"
            for item in payload.get("items", [])
            if item.get("subject") and item.get("action")
        ]
    except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return []


def _ai_draft(email: dict[str, str]) -> str | None:
    try:
        return _openai_email_completion(
            "Write a professional, concise reply draft that directly acknowledges the sender's specific request and details. "
            "Do not invent dates, commitments, attachments, or facts. Return only the email body, including greeting and sign-off.",
            _email_prompt_data([email]),
            max_tokens=500,
        )
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return None


def _ai_new_draft(instruction: str) -> str | None:
    try:
        return _openai_email_completion(
            "Write a professional new email based on the user's instructions. "
            "Infer a concise subject line and include it as the first line using the format "
            "Subject: <subject>. Then write only the email body with a greeting and sign-off. "
            "Do not invent names, dates, commitments, attachments, or facts.",
            instruction,
            max_tokens=700,
        )
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return None


def _priority(email: dict[str, str]) -> str:
    importance = str(email.get("importance", "")).lower()
    body = str(email.get("body", "")).lower()
    if importance in {"high", "2"} or any(term in body for term in ("urgent", "asap", "deadline", "action required")):
        return "High"
    if importance in {"low", "0"}:
        return "Low"
    return "Medium"


def _body_text(email: dict[str, str]) -> str:
    body = str(email.get("body", "") or "")
    body = re.sub(r"<https?://[^>]+>", " ", body, flags=re.IGNORECASE)
    body = re.sub(r"https?://\S+", " ", body, flags=re.IGNORECASE)
    body = re.sub(r"<[^>]+>", " ", body)
    return " ".join(body.replace("\r", " ").replace("\n", " ").split())


def _outlook_sender_email(item: object) -> str:
    address = str(getattr(item, "SenderEmailAddress", "") or "").strip()
    if address and str(getattr(item, "SenderEmailType", "")).upper() != "EX":
        return address

    sender = getattr(item, "Sender", None)
    try:
        exchange_user = sender.GetExchangeUser() if sender is not None else None
        smtp_address = str(getattr(exchange_user, "PrimarySmtpAddress", "") or "").strip()
        if smtp_address:
            return smtp_address
    except Exception:
        pass

    try:
        accessor = getattr(sender, "PropertyAccessor", None)
        if accessor is not None:
            smtp_address = str(
                accessor.GetProperty("http://schemas.microsoft.com/mapi/proptag/0x39FE001E") or ""
            ).strip()
            if smtp_address:
                return smtp_address
    except Exception:
        pass

    return address


def _summarize_action(sentence: str) -> str:
    action = re.sub(r"^\s*\d+[.)]\s*", "", sentence).strip(" .")
    action = re.sub(r"^(?:hi|hello|dear)\s+[^,]+,\s*", "", action, flags=re.IGNORECASE)
    action = re.sub(r"^please\s+", "", action, flags=re.IGNORECASE)
    action = re.sub(r"\s+", " ", action).strip(" .")
    lower = action.casefold()
    if lower.startswith("we need to "):
        action = "Discuss " + action[12:]
    elif lower.startswith("prepared "):
        action = "Confirm " + action
    return action


def _action_items(email: dict[str, str]) -> list[str]:
    sentences = [part.strip(" .") for part in re.split(r"(?<=[.!?])\s+", _body_text(email)) if part.strip()]
    action_terms = ("please", "need to", "review", "prepare", "share", "send", "confirm", "complete", "submit", "action")
    ignored_starts = ("you won't", "you will not", "thank you for shopping", "privacy statement", "microsoft corporation")
    actions: list[str] = []
    for sentence in sentences:
        lower = sentence.casefold()
        if lower.startswith(ignored_starts) or not any(term in lower for term in action_terms):
            continue
        summary = _summarize_action(sentence)
        if summary and summary not in actions:
            actions.append(summary)
    return actions[:3]


def _triage(email: dict[str, str]) -> str:
    text = f"{email.get('subject', '')} {email.get('body', '')}".lower()
    unread = str(email.get("is_read", "false")).lower() != "true"
    relevant = any(term in text for term in ("action", "review", "approval", "deadline", "meeting", "project", "report"))
    sender = str(email.get("sender", "")).lower()
    important_sender = any(address.strip().lower() in sender for address in settings.mail_important_senders.split(",") if address.strip())
    has_attachments = str(email.get("has_attachments", "")).lower() == "true"
    needs_action = bool(_action_items(email))
    return (
        f"Triage: {'unread' if unread else 'read'} | {'relevant' if relevant else 'for review'} | "
        f"{'important sender' if important_sender else 'standard sender'} | "
        f"{'attachment present' if has_attachments else 'no attachment'} | "
        f"{'action needed' if needs_action else 'no action detected'}"
    )


def _read_outlook_mailbox(*, unread_only: bool = True) -> list[dict[str, str]] | None:
    """Read recent messages from the local Outlook inbox."""
    global _last_mailbox_error
    try:
        import pythoncom
        import win32com.client
    except Exception as exc:
        _last_mailbox_error = "The pywin32 Outlook connector is not installed."
        return None

    pythoncom.CoInitialize()
    try:
        namespace = None
        connection_errors: list[str] = []
        for factory_name in ("Dispatch", "DispatchEx"):
            try:
                factory = getattr(win32com.client, factory_name)
                outlook = factory("Outlook.Application")
                namespace = outlook.GetNamespace("MAPI")
                try:
                    namespace.Logon("", "", False, False)
                except Exception:
                    pass
                break
            except Exception as exc:
                connection_errors.append(f"{factory_name}: {exc}")

        if namespace is None:
            _last_mailbox_error = "Outlook could not open a MAPI profile. " + " | ".join(connection_errors)
            return None

        try:
            inbox = namespace.GetDefaultFolder(6)
            items = inbox.Items
            items.Sort("[ReceivedTime]", True)

            messages: list[dict[str, str]] = []
            for item in list(items):
                if not unread_only or getattr(item, "UnRead", False):
                    messages.append(
                        {
                            "subject": getattr(item, "Subject", "(no subject)"),
                            "sender": getattr(item, "SenderName", "Unknown sender"),
                            "sender_email": _outlook_sender_email(item),
                            "received_at": getattr(item, "ReceivedTime", ""),
                            "body": getattr(item, "Body", "") or "",
                            "importance": getattr(item, "Importance", ""),
                            "has_attachments": str(bool(getattr(item, "Attachments", None) and getattr(item.Attachments, "Count", 0) > 0)).lower(),
                            "attachment_names": "|".join(
                                str(getattr(item.Attachments.Item(index), "FileName", ""))
                                for index in range(1, getattr(getattr(item, "Attachments", None), "Count", 0) + 1)
                            ),
                        }
                    )
                    if len(messages) >= 10:
                        break
            return messages
        except Exception as exc:
            _last_mailbox_error = f"Outlook Inbox could not be read: {exc}"
            return None
    finally:
        pythoncom.CoUninitialize()


def send_outlook_email(recipient: str, subject: str, body: str) -> str:
    recipient = recipient.strip()
    subject = subject.strip()
    body = body.strip()
    if not recipient or not subject or not body:
        raise RuntimeError("Recipient, subject, and message body are required to send email")

    if settings.mail_provider == "graph":
        try:
            GraphMailClient().send_message(recipient, subject, body)
            return "Microsoft Graph"
        except GraphMailError as exc:
            if not settings.allow_outlook_fallback:
                raise RuntimeError(str(exc)) from exc

    try:
        import pythoncom
        import win32com.client
    except Exception as exc:
        raise RuntimeError("Microsoft Outlook desktop is required to send email") from exc

    pythoncom.CoInitialize()
    try:
        dispatch_errors: list[str] = []
        outlook = None
        for factory_name in ("Dispatch", "DispatchEx"):
            try:
                factory = getattr(win32com.client, factory_name)
                outlook = factory("Outlook.Application")
                break
            except Exception as exc:
                dispatch_errors.append(f"{factory_name}: {exc}")
        if outlook is None:
            detail = " | ".join(dispatch_errors)
            raise RuntimeError(f"Classic Outlook could not be opened. {detail}")
        namespace = outlook.GetNamespace("MAPI")
        accounts = namespace.Accounts
        if getattr(accounts, "Count", 0) < 1:
            raise RuntimeError("Classic Outlook has no configured sending account")

        message = outlook.CreateItem(0)
        message.To = recipient
        message.Subject = subject
        message.Body = body
        try:
            message.SendUsingAccount = accounts.Item(1)
        except Exception:
            pass
        message.Send()
        return "Classic Outlook"
    except Exception as exc:
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError(f"Classic Outlook could not send the email: {exc}") from exc
    finally:
        pythoncom.CoUninitialize()


def _read_mailbox(*, unread_only: bool, search_query: str = "") -> list[dict[str, str]] | None:
    """Use classic Outlook by default, with optional Microsoft Graph access."""
    if settings.mail_provider == "graph":
        try:
            if search_query:
                return GraphMailClient().search_messages(search_query)
            return GraphMailClient().list_messages(unread_only=unread_only)
        except GraphMailError:
            if not settings.allow_outlook_fallback:
                return None
    messages = _read_outlook_mailbox() if unread_only else _read_outlook_mailbox(unread_only=False)
    if search_query and messages is not None:
        needle = search_query.lower()
        messages = [
            message
            for message in messages
            if needle in " ".join(
                str(message.get(field, ""))
                for field in ("subject", "sender", "sender_email", "body")
            ).lower()
        ]
    return messages


def list_mailbox_messages(*, unread_only: bool = True, search_query: str = "") -> list[dict[str, str]] | None:
    """Return structured mailbox records for dashboard and frontend views."""
    return _read_mailbox(unread_only=unread_only, search_query=search_query)


class EmailAgent(Agent):
    name = "email"

    def run(self, context: AgentContext) -> str:
        prompt = context.message.strip() or "your request"
        prompt_lower = prompt.lower()
        latest_request = bool(re.search(r"\b(?:latest|newest|most recent)\b", prompt_lower))
        count_match = re.search(r"\b(?:read|show|fetch|get)\s+(\d+)\s+emails?\b", prompt_lower)
        requested_count = int(count_match.group(1)) if count_match else None
        all_mail_request = bool(
            re.search(
                r"\b(?:read|unread)\s+or\s+unread\b|\bread\s+and\s+unread\b|"
                r"\bwhether\s+(?:it\s+is\s+)?read\s+or\s+unread\b|\ball\s+(?:my\s+)?emails?\b",
                prompt_lower,
            )
        )
        search_match = re.search(
            r"\b(?:search|find)\s+(?:emails?|messages?)?\s*(?:for|about|containing)?\s*[\"']?(.+?)[\"']?$",
            prompt,
            re.IGNORECASE,
        )
        search_query = search_match.group(1).strip() if search_match else ""
        if search_query.lower() in {"my emails", "emails", "messages", "mail"}:
            search_query = ""
        draft_request = "draft" in prompt_lower or "reply" in prompt_lower
        new_draft_request = bool(
            re.search(r"\b(?:draft|write|compose)\s+(?:a\s+)?(?:new\s+)?email\b", prompt_lower)
        ) and "reply" not in prompt_lower
        if new_draft_request:
            instruction = re.sub(
                r"^\s*(?:email request\s*:\s*)?(?:please\s+)?(?:draft|write|compose)\s+(?:a\s+)?(?:new\s+)?email\s*[:\-]?\s*",
                "",
                prompt,
                flags=re.IGNORECASE,
            ).strip() or "Write a professional workplace email."
            ai_draft = _ai_new_draft(instruction)
            if ai_draft:
                return f"New email draft:\n\n{ai_draft}"
            return (
                "New email draft:\n\n"
                "Subject: Follow-up\n\n"
                "Hello,\n\n"
                f"{instruction}\n\n"
                "Regards,\nSampath"
            )
        emails = (
            _read_mailbox(unread_only=False, search_query=search_query)
            if search_query
            else _read_mailbox(
                unread_only=not latest_request and not all_mail_request and not draft_request
            )
        )

        if emails is None:
            detail = f" Details: {_last_mailbox_error}" if _last_mailbox_error else ""
            return (
                "MailMate could not access the mailbox. Configure Microsoft Graph and sign in, or open the "
                f"local Outlook desktop profile before trying again.{detail}"
            )

        if not emails:
            scope = "emails" if latest_request or all_mail_request else "unread emails"
            if "action item" in prompt.lower():
                return f"No {scope} or action items were found."
            if "draft" in prompt.lower() or "reply" in prompt.lower():
                return (
                    "MailMate could not access the mailbox. Configure Microsoft Graph and sign in, or open the "
                    "local Outlook desktop profile before trying again."
                )
            return f"No {scope} were found."

        if "high priority" in prompt_lower or "only show high" in prompt_lower:
            emails = [email for email in emails if _priority(email) == "High"]
            if not emails:
                return "No high-priority unread emails were found in your local Outlook inbox."

        if "with attachment" in prompt_lower or "has attachment" in prompt_lower or "attached" in prompt_lower:
            emails = [email for email in emails if str(email.get("has_attachments", "")).lower() == "true"]
            if not emails:
                return "No emails with attachments were found."

        combined_request = draft_request and ("action" in prompt_lower or "summar" in prompt_lower)
        if combined_request:
            requested_emails = [
                email
                for email in emails
                if any(value and str(value).casefold() in prompt_lower for value in (email.get("subject"), email.get("sender")))
            ]
            email = requested_emails[0] if requested_emails else emails[0]
            subject = email.get("subject", "(no subject)")
            summary = _ai_summaries([email]).get(subject) or _body_text(email) or "No message preview was returned."
            actions = _ai_action_items([email]) or _action_items(email)
            action_lines = "\n".join(f"- {action}" for action in actions) or "- No action items detected."
            sender = email.get("sender", "there")
            ai_draft = _ai_draft(email)
            draft = ai_draft or (
                f"Hi {sender},\n\nThank you for your email regarding \"{subject}\". "
                "I will review the details and follow up with the appropriate next steps.\n\n"
                "Regards,\nSampath"
            )
            return (
                f"Email summary:\n{summary}\n\n"
                f"Action items:\n{action_lines}\n\n"
                f"Draft reply for {sender} regarding \"{subject}\":\n\n{draft}"
            )

        if "action item" in prompt_lower:
            requested_emails = [
                email
                for email in emails
                if any(value and str(value).casefold() in prompt_lower for value in (email.get("subject"), email.get("sender")))
            ]
            action_emails = requested_emails[:1] or emails
            ai_items = _ai_action_items(action_emails)
            if ai_items:
                return "Action items from your emails:\n" + "\n".join(f"- {item}" for item in ai_items)
            lines = ["Action items from your unread Outlook emails:"]
            for email in action_emails:
                actions = _action_items(email)
                if actions:
                    lines.extend(f"- {email.get('subject', '(no subject)')}: {action}" for action in actions)
            return "\n".join(lines) if len(lines) > 1 else "No action items were detected in your unread Outlook emails."

        if draft_request:
            requested = prompt_lower
            matching_emails = [
                item
                for item in emails
                if any(value and str(value).lower() in requested for value in (item.get("subject"), item.get("sender")))
            ]
            if not matching_emails:
                return (
                    "MailMate could not access the mailbox. Configure Microsoft Graph and sign in, or open the "
                    "local Outlook desktop profile before trying again."
                )

            email = matching_emails[0]
            sender = email.get("sender", "there")
            subject = email.get("subject", "your email")
            ai_draft = _ai_draft(email)
            if ai_draft:
                return f"Draft reply for {sender} regarding \"{subject}\":\n\n{ai_draft}"
            actions = _action_items(email)
            action_sentence = (
                f" I will follow up on: {'; '.join(actions)}."
                if actions
                else " I will review the details and follow up with the appropriate next steps."
            )
            return (
                f"Draft reply for {sender} regarding \"{subject}\":\n\n"
                f"Hi {sender},\n\nThank you for your email regarding \"{subject}\".{action_sentence}\n\n"
                "Regards,\nSampath"
            )

        if latest_request:
            emails = emails[:1]
            lines = ["Latest email in your mailbox:"]
        else:
            if requested_count is not None:
                emails = emails[:requested_count]
            scope = "matching email" if search_query else "unread email"
            if all_mail_request:
                scope = "email"
            lines = [f"Found {len(emails)} {scope}{'s' if len(emails) != 1 else ''} in your mailbox."]

        summaries = _ai_summaries(emails)
        for email in emails:
            subject = email.get("subject", "(no subject)")
            sender = email.get("sender", "Unknown sender")
            sender_email = str(email.get("sender_email", "")).strip()
            received_at = email.get("received_at", "")
            if received_at:
                received_at = received_at.strftime("%Y-%m-%d %H:%M") if hasattr(received_at, "strftime") else str(received_at)
            body = summaries.get(subject) or _body_text(email)

            sender_label = f"{sender} <{sender_email}>" if sender_email else sender
            lines.append(f"- {subject} | from {sender_label} | priority {_priority(email)} | received {received_at or 'recently'}")
            if body:
                lines.append(f"  Summary: {body[:240]}{'...' if len(body) > 240 else ''}")
            attachment_names = [name for name in str(email.get("attachment_names", "")).split("|") if name]
            if attachment_names:
                lines.append(f"  Attachments: {', '.join(attachment_names)}")
            elif str(email.get("has_attachments", "")).lower() == "true":
                lines.append("  Attachments: present")
            lines.append(f"  {_triage(email)}")

        return "\n".join(lines)
