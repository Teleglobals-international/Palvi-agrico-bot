"""
Fintech industry calling agent.
Handles loan inquiries, account information, payment issues, financial products, etc.
"""

from typing import Any, Dict, List, Optional

from app.features.agents.base_agent import BaseAgent
from app.shared.models import CallDirection, IndustryType


class FintechAgent(BaseAgent):
    """Calling agent specialized for fintech industry."""

    def __init__(self):
        super().__init__(IndustryType.FINTECH)

        self._greeting_inbound = (
            "Hello! Thank you for calling our financial services center. "
            "I'm your AI assistant and I'm here to help you with your "
            "financial queries. How can I assist you today?"
        )

        self._greeting_outbound = (
            "Hello! This is your financial services assistant calling. "
            "I'm reaching out regarding your recent application. "
            "Do you have a moment to discuss?"
        )

    def get_system_prompt(self, direction: CallDirection, context: Optional[Dict[str, Any]] = None) -> str:
        """Build system prompt for fintech conversations."""
        base_prompt = (
            "You are a professional and knowledgeable fintech calling agent. "
            "Your role is to assist callers with financial product inquiries and services. "
            "You can help with:\n"
            "- Loan inquiries (personal, home, auto, business loans)\n"
            "- Credit card information and applications\n"
            "- Account balance and transaction queries\n"
            "- Payment processing issues and support\n"
            "- Insurance product information\n"
            "- Investment product overviews\n"
            "- KYC and documentation requirements\n"
            "- EMI calculations and repayment schedules\n\n"
            "Guidelines:\n"
            "- Be professional, accurate, and trustworthy\n"
            "- NEVER provide specific financial advice — always recommend consulting a financial advisor\n"
            "- NEVER ask for or confirm sensitive data like full account numbers, PINs, or passwords\n"
            "- For verification, only ask for last 4 digits of account number or registered mobile\n"
            "- Keep responses concise and conversational (suitable for phone calls)\n"
            "- Clearly explain terms, interest rates, and conditions\n"
            "- Always disclose that you are an AI assistant\n"
            "- For complex queries, offer to transfer to a human specialist\n"
            "- Comply with financial regulations in communications\n"
        )

        if direction == CallDirection.INBOUND:
            base_prompt += (
                "\nThis is an inbound call. The customer is reaching out for help. "
                "Verify their identity appropriately before discussing account specifics. "
                "Be helpful and guide them to the right solution."
            )
        else:
            base_prompt += (
                "\nThis is an outbound call. You are reaching out to the customer. "
                "Clearly identify yourself and the organization. "
                "Be respectful of their time and state the purpose clearly. "
                "Do not pressure the customer."
            )

        if context:
            base_prompt += f"\n\nAdditional context: {context}"

        return base_prompt

    def get_greeting(self, direction: CallDirection, context: Optional[Dict[str, Any]] = None) -> str:
        """Get appropriate greeting based on call direction."""
        if direction == CallDirection.INBOUND:
            return self._greeting_inbound

        if context and context.get("customer_name"):
            return (
                f"Hello {context['customer_name']}! This is your financial services assistant. "
                f"I'm calling regarding your recent application. "
                f"Do you have a moment to discuss?"
            )
        return self._greeting_outbound

    def get_domain_keywords(self) -> List[str]:
        """Return fintech domain keywords."""
        return [
            "loan", "personal loan", "home loan", "auto loan", "business loan",
            "credit", "credit card", "credit score", "cibil",
            "debit", "debit card", "account", "balance", "statement",
            "transaction", "transfer", "payment", "upi", "neft", "rtgs",
            "emi", "installment", "repayment", "interest", "rate",
            "insurance", "policy", "premium", "claim", "coverage",
            "investment", "mutual fund", "sip", "fd", "fixed deposit",
            "savings", "current account", "salary account",
            "kyc", "pan", "aadhaar", "documents", "verification",
            "apply", "application", "eligibility", "approval",
            "bank", "banking", "finance", "financial",
            "tenure", "principal", "processing fee", "foreclosure",
            "limit", "upgrade", "downgrade", "block", "unblock",
            "reward", "cashback", "points", "offer",
            "overdue", "penalty", "late fee", "dues",
        ]
