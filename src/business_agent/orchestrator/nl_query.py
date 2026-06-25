"""Natural language query parser for property-related questions.

Parses user messages like:
- "compare mortgage offers for 133 Bowland Drive within last 2 months"
- "When is the EPC certificate expiring for 133 Bowland Drive"
- "Show me mortgage statements for 133 Bowland Drive for past 2 years"
- "Does the tenancy agreement for 133 Bowland Drive has 'no pet' clause?"
- "give me the links for all completion statements within last year"
- "I can see a transaction of £180 in the bank on 12 June 2026, do we have a corresponding invoice?"
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import Any


class QueryIntent(str, Enum):
    """Intent type for natural language queries."""
    COMPARE_MORTGAGES = "compare_mortgages"
    EPC_EXPIRY = "epc_expiry"
    MORTGAGE_STATEMENTS = "mortgage_statements"
    TENANCY_CLAUSE_CHECK = "tenancy_clause_check"
    BULK_DOCUMENT_LINKS = "bulk_document_links"
    TRANSACTION_MATCHING = "transaction_matching"
    GENERAL_QUESTION = "general_question"


@dataclass(frozen=True)
class ParsedNLQuery:
    """Result of parsing a natural language query."""
    intent: QueryIntent
    property_address: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    document_type: str | None = None
    clause_text: str | None = None
    transaction_amount: float | None = None
    transaction_date: date | None = None
    raw_question: str = ""
    original_text: str = ""


# Property address pattern: number + words + suffix
_ADDRESS_PATTERN = re.compile(
    r'(\d+\s+[A-Za-z]+(?:\s+[A-Za-z]+)*\s+'
    r'(?:Street|St|Drive|Dr|Avenue|Ave|Road|Rd|Lane|Ln|Way|Close|Court|Ct|Place|Pl))',
    re.IGNORECASE
)

# Also match property names in quotes
_QUOTED_ADDRESS_PATTERN = re.compile(r"['\"]([^'\"]+ (?:Street|St|Drive|Dr|Avenue|Ave|Road|Rd|Lane|Ln|Way|Close|Court|Ct|Place|Pl))['\"]", re.IGNORECASE)

# Quoted text pattern (for clauses)
_QUOTED_TEXT_PATTERN = re.compile(r"['\"]([^'\"]+)['\"]")

# Amount pattern: £180 or $180 or "180 pounds"
_AMOUNT_PATTERN = re.compile(r'[£$]\s*([\d,]+\.?\d*)')

# Date patterns: "12 June 2026", "June 12 2026", "2026-06-12"
_DATE_PATTERNS = [
    (re.compile(r'(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})', re.IGNORECASE), "dmy"),
    (re.compile(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})\s+(\d{4})', re.IGNORECASE), "mdy"),
    (re.compile(r'(\d{4})-(\d{2})-(\d{2})'), "iso"),
]

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}


def _extract_property_address(text: str) -> str | None:
    """Extract property address from text."""
    # Try quoted address first
    match = _QUOTED_ADDRESS_PATTERN.search(text)
    if match:
        return match.group(1)
    
    # Try unquoted address
    match = _ADDRESS_PATTERN.search(text)
    if match:
        return match.group(1)
    
    return None


def _extract_amount(text: str) -> float | None:
    """Extract monetary amount from text."""
    match = _AMOUNT_PATTERN.search(text)
    if match:
        try:
            return float(match.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def _extract_date(text: str) -> date | None:
    """Extract a date from text."""
    for pattern, fmt in _DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            try:
                if fmt == "dmy":
                    day = int(match.group(1))
                    month = _MONTHS[match.group(2).lower()]
                    year = int(match.group(3))
                elif fmt == "mdy":
                    month = _MONTHS[match.group(1).lower()]
                    day = int(match.group(2))
                    year = int(match.group(3))
                else:  # iso
                    year = int(match.group(1))
                    month = int(match.group(2))
                    day = int(match.group(3))
                return date(year, month, day)
            except (ValueError, KeyError, IndexError):
                continue
    return None


def _extract_relative_date_range(text: str) -> tuple[date | None, date | None]:
    """Extract relative date ranges like 'last 2 months', 'past 1 year', etc."""
    today = date.today()
    text_lower = text.lower()
    
    # "last N months" / "past N months" / "within last/past N months"
    match = re.search(r'(?:last|past|within\s+(?:the\s+)?(?:last\s+|past\s+)?)\s*(\d+)\s+month', text_lower)
    if match:
        n = int(match.group(1))
        date_from = today - timedelta(days=n * 30)
        return date_from, today

    # "last N years" / "past N years" / "within last/past N years"
    match = re.search(r'(?:last|past|within\s+(?:the\s+)?(?:last\s+|past\s+)?)\s*(\d+)\s+year', text_lower)
    if match:
        n = int(match.group(1))
        date_from = today - timedelta(days=n * 365)
        return date_from, today
    
    # "last year" (no number)
    if re.search(r'\blast\s+year\b', text_lower) or re.search(r'\bpast\s+year\b', text_lower):
        date_from = today - timedelta(days=365)
        return date_from, today
    
    return None, None


def _extract_quoted_text(text: str) -> str | None:
    """Extract quoted text (for clause checking)."""
    match = _QUOTED_TEXT_PATTERN.search(text)
    if match:
        return match.group(1)
    return None


def parse_natural_language_query(text: str) -> ParsedNLQuery:
    """Parse a natural language query and determine intent."""
    text_lower = text.lower().strip()
    
    # Extract common elements
    property_address = _extract_property_address(text)
    date_from, date_to = _extract_relative_date_range(text)
    amount = _extract_amount(text)
    transaction_date = _extract_date(text)
    quoted_text = _extract_quoted_text(text)
    
    # Determine intent
    
    # 1. Transaction matching: "transaction of £180... corresponding invoice"
    if amount is not None and ("invoice" in text_lower or "transaction" in text_lower or "matching" in text_lower or "corresponding" in text_lower):
        return ParsedNLQuery(
            intent=QueryIntent.TRANSACTION_MATCHING,
            transaction_amount=amount,
            transaction_date=transaction_date,
            raw_question=text,
            original_text=text,
        )
    
    # 2. Compare mortgages: "compare... mortgage offers... for <address>"
    if "compare" in text_lower and "mortgage" in text_lower:
        return ParsedNLQuery(
            intent=QueryIntent.COMPARE_MORTGAGES,
            property_address=property_address,
            date_from=date_from,
            date_to=date_to,
            document_type="mortgage_offer",
            raw_question=text,
            original_text=text,
        )
    
    # 3. EPC expiry: "epc certificate expiring"
    if "epc" in text_lower and ("expir" in text_lower or "when" in text_lower):
        return ParsedNLQuery(
            intent=QueryIntent.EPC_EXPIRY,
            property_address=property_address,
            document_type="epc_certificate",
            raw_question=text,
            original_text=text,
        )
    
    # 4. Tenancy clause check: "tenancy agreement... clause"
    if "tenancy" in text_lower and ("clause" in text_lower or "pet" in text_lower or quoted_text):
        return ParsedNLQuery(
            intent=QueryIntent.TENANCY_CLAUSE_CHECK,
            property_address=property_address,
            clause_text=quoted_text or "no pet",
            document_type="tenancy_agreement",
            raw_question=text,
            original_text=text,
        )
    
    # 5. Mortgage statements: "mortgage statements... for <address>"
    if "mortgage" in text_lower and "statement" in text_lower:
        return ParsedNLQuery(
            intent=QueryIntent.MORTGAGE_STATEMENTS,
            property_address=property_address,
            date_from=date_from,
            date_to=date_to,
            document_type="bank_statement",
            raw_question=text,
            original_text=text,
        )
    
    # 6. Bulk document links: "links for all... documents... within last year"
    if ("link" in text_lower or "all" in text_lower) and ("completion" in text_lower or "document" in text_lower or "transaction" in text_lower):
        doc_type = None
        if "completion" in text_lower:
            doc_type = "completion_statement"
        return ParsedNLQuery(
            intent=QueryIntent.BULK_DOCUMENT_LINKS,
            property_address=property_address,
            date_from=date_from,
            date_to=date_to,
            document_type=doc_type,
            raw_question=text,
            original_text=text,
        )
    
    # Default: general question
    return ParsedNLQuery(
        intent=QueryIntent.GENERAL_QUESTION,
        property_address=property_address,
        date_from=date_from,
        date_to=date_to,
        raw_question=text,
        original_text=text,
    )
