"""Tests for property command parsers."""

import pytest

from business_agent.orchestrator.commands import (
    MortgageExpiringCommand,
    PropertyListCommand,
    PropertyShowCommand,
    parse_mortgage_command,
    parse_property_command,
)


class TestParsePropertyCommand:
    def test_parse_property_list_no_args(self):
        cmd = parse_property_command("/property list")
        assert isinstance(cmd, PropertyListCommand)
        assert cmd.status is None
    
    def test_parse_property_list_with_status(self):
        cmd = parse_property_command("/property list status=owned")
        assert isinstance(cmd, PropertyListCommand)
        assert cmd.status == "owned"
    
    def test_parse_property_show(self):
        cmd = parse_property_command("/property show prop123")
        assert isinstance(cmd, PropertyShowCommand)
        assert cmd.property_id == "prop123"
    
    def test_parse_property_show_missing_id_raises(self):
        with pytest.raises(ValueError, match="property show requires a property ID"):
            parse_property_command("/property show")
    
    def test_parse_property_add(self):
        result = parse_property_command("/property add")
        assert result == "add"
    
    def test_parse_property_bare_command_defaults_to_list(self):
        cmd = parse_property_command("/property")
        assert isinstance(cmd, PropertyListCommand)
        assert cmd.status is None
    
    def test_parse_property_without_slash(self):
        cmd = parse_property_command("property list status=viewing")
        assert isinstance(cmd, PropertyListCommand)
        assert cmd.status == "viewing"
    
    def test_parse_property_unknown_subcommand_raises(self):
        with pytest.raises(ValueError, match="Unknown property subcommand"):
            parse_property_command("/property delete prop123")


class TestParseMortgageCommand:
    def test_parse_mortgage_expiring_no_args(self):
        cmd = parse_mortgage_command("/mortgage expiring")
        assert isinstance(cmd, MortgageExpiringCommand)
        assert cmd.months == 6
    
    def test_parse_mortgage_expiring_with_months(self):
        cmd = parse_mortgage_command("/mortgage expiring months=3")
        assert isinstance(cmd, MortgageExpiringCommand)
        assert cmd.months == 3
    
    def test_parse_mortgage_expiring_custom_months(self):
        cmd = parse_mortgage_command("/mortgage expiring months=12")
        assert isinstance(cmd, MortgageExpiringCommand)
        assert cmd.months == 12
    
    def test_parse_mortgage_add(self):
        result = parse_mortgage_command("/mortgage add prop456")
        assert result == "add:prop456"
    
    def test_parse_mortgage_add_missing_property_id_raises(self):
        with pytest.raises(ValueError, match="mortgage add requires a property ID"):
            parse_mortgage_command("/mortgage add")
    
    def test_parse_mortgage_bare_command_defaults_to_expiring(self):
        cmd = parse_mortgage_command("/mortgage")
        assert isinstance(cmd, MortgageExpiringCommand)
        assert cmd.months == 6
    
    def test_parse_mortgage_without_slash(self):
        cmd = parse_mortgage_command("mortgage expiring months=9")
        assert isinstance(cmd, MortgageExpiringCommand)
        assert cmd.months == 9
    
    def test_parse_mortgage_unknown_subcommand_raises(self):
        with pytest.raises(ValueError, match="Unknown mortgage subcommand"):
            parse_mortgage_command("/mortgage delete mort123")
