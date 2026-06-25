"""Tests for the natural language query parser."""
from __future__ import annotations

from datetime import date, timedelta

from business_agent.orchestrator.nl_query import (
    ParsedNLQuery,
    QueryIntent,
    parse_natural_language_query,
)


class TestAddressExtraction:
    def test_extract_unquoted_address(self):
        result = parse_natural_language_query(
            "compare mortgage offers for 133 Bowland Drive within last 2 months"
        )
        assert result.property_address is not None
        assert "133" in result.property_address
        assert "Bowland" in result.property_address
        assert "Drive" in result.property_address

    def test_extract_quoted_address(self):
        result = parse_natural_language_query(
            "compare mortgage offers for '133 Bowland Drive' within last 2 months"
        )
        assert result.property_address is not None
        assert "133 Bowland Drive" in result.property_address

    def test_no_address_found(self):
        result = parse_natural_language_query("compare mortgage offers within last 2 months")
        assert result.property_address is None

    def test_address_with_road(self):
        result = parse_natural_language_query("EPC for 42 Oxford Road")
        assert result.property_address is not None
        assert "Oxford Road" in result.property_address

    def test_address_with_lane(self):
        result = parse_natural_language_query("EPC for 5 Maple Lane")
        assert result.property_address is not None
        assert "Maple Lane" in result.property_address


class TestAmountExtraction:
    def test_extract_pound_amount(self):
        result = parse_natural_language_query(
            "I see a transaction of £180 on 12 June 2026"
        )
        assert result.transaction_amount is not None
        assert result.transaction_amount == 180.0

    def test_extract_dollar_amount(self):
        result = parse_natural_language_query(
            "I see a transaction of $250.50 on 12 June 2026"
        )
        assert result.transaction_amount is not None
        assert result.transaction_amount == 250.50

    def test_extract_amount_with_commas(self):
        result = parse_natural_language_query(
            "transaction of £1,200 on 12 June 2026"
        )
        assert result.transaction_amount is not None
        assert result.transaction_amount == 1200.0

    def test_no_amount(self):
        result = parse_natural_language_query("compare mortgage offers")
        assert result.transaction_amount is None


class TestDateExtraction:
    def test_extract_dmy_date(self):
        result = parse_natural_language_query(
            "transaction of £180 on 12 June 2026"
        )
        assert result.transaction_date == date(2026, 6, 12)

    def test_extract_mdy_date(self):
        result = parse_natural_language_query(
            "transaction of £180 on June 12 2026"
        )
        assert result.transaction_date == date(2026, 6, 12)

    def test_extract_iso_date(self):
        result = parse_natural_language_query(
            "transaction of £180 on 2026-06-12"
        )
        assert result.transaction_date == date(2026, 6, 12)

    def test_no_date(self):
        result = parse_natural_language_query("compare mortgage offers")
        assert result.transaction_date is None


class TestRelativeDateRange:
    def test_last_n_months(self):
        result = parse_natural_language_query(
            "compare mortgage offers for 133 Bowland Drive within last 2 months"
        )
        assert result.date_from is not None
        assert result.date_to is not None
        today = date.today()
        expected_from = today - timedelta(days=2 * 30)
        assert abs((result.date_from - expected_from).days) <= 1

    def test_past_n_months(self):
        result = parse_natural_language_query(
            "mortgage statements for 133 Bowland Drive for past 1 month"
        )
        assert result.date_from is not None

    def test_last_n_years(self):
        result = parse_natural_language_query(
            "mortgage statements for 133 Bowland Drive for past 2 years"
        )
        assert result.date_from is not None
        today = date.today()
        expected_from = today - timedelta(days=2 * 365)
        assert abs((result.date_from - expected_from).days) <= 1

    def test_last_year_no_number(self):
        result = parse_natural_language_query(
            "give me links for all completion statements within last year"
        )
        assert result.date_from is not None
        today = date.today()
        expected_from = today - timedelta(days=365)
        assert abs((result.date_from - expected_from).days) <= 1

    def test_no_relative_date(self):
        result = parse_natural_language_query("compare mortgage offers")
        assert result.date_from is None
        assert result.date_to is None


class TestIntentClassification:
    def test_compare_mortgages_intent(self):
        result = parse_natural_language_query(
            "compare mortgage offers for 133 Bowland Drive within last 2 months"
        )
        assert result.intent == QueryIntent.COMPARE_MORTGAGES
        assert result.document_type == "mortgage_offer"

    def test_epc_expiry_intent(self):
        result = parse_natural_language_query(
            "When is the EPC certificate expiring for 133 Bowland Drive"
        )
        assert result.intent == QueryIntent.EPC_EXPIRY
        assert result.document_type == "epc_certificate"

    def test_mortgage_statements_intent(self):
        result = parse_natural_language_query(
            "Show me mortgage statements for 133 Bowland Drive for past 2 years"
        )
        assert result.intent == QueryIntent.MORTGAGE_STATEMENTS

    def test_tenancy_clause_check_intent(self):
        result = parse_natural_language_query(
            "Does the tenancy agreement for 133 Bowland Drive has 'no pet' clause?"
        )
        assert result.intent == QueryIntent.TENANCY_CLAUSE_CHECK
        assert result.clause_text is not None
        assert "no pet" in result.clause_text

    def test_tenancy_clause_check_without_quotes(self):
        result = parse_natural_language_query(
            "Does the tenancy agreement for 133 Bowland Drive have a pet clause?"
        )
        assert result.intent == QueryIntent.TENANCY_CLAUSE_CHECK

    def test_bulk_document_links_intent(self):
        result = parse_natural_language_query(
            "give me the links for all completion statements within last year"
        )
        assert result.intent == QueryIntent.BULK_DOCUMENT_LINKS
        assert result.document_type == "completion_statement"

    def test_transaction_matching_intent(self):
        result = parse_natural_language_query(
            "I can see a transaction of £180 in the bank on 12 June 2026, do we have a corresponding invoice?"
        )
        assert result.intent == QueryIntent.TRANSACTION_MATCHING
        assert result.transaction_amount == 180.0
        assert result.transaction_date == date(2026, 6, 12)

    def test_general_question_intent(self):
        result = parse_natural_language_query(
            "What is the weather like today?"
        )
        assert result.intent == QueryIntent.GENERAL_QUESTION

    def test_transaction_matching_without_date(self):
        result = parse_natural_language_query(
            "I see a transaction of £250, is there a matching invoice?"
        )
        assert result.intent == QueryIntent.TRANSACTION_MATCHING
        assert result.transaction_amount == 250.0
        assert result.transaction_date is None

    def test_raw_question_preserved(self):
        text = "compare mortgage offers for 133 Bowland Drive"
        result = parse_natural_language_query(text)
        assert result.raw_question == text
        assert result.original_text == text
