from business_agent.telegram import ui


def test_parse_callback_data_for_menu_and_actions() -> None:
    parsed_menu = ui.parse_callback_data("menu:ask")
    assert parsed_menu is not None
    assert parsed_menu.action == "menu:ask"
    assert parsed_menu.token is None

    parsed_action = ui.parse_callback_data("act:details:tok123")
    assert parsed_action is not None
    assert parsed_action.action == "act:details"
    assert parsed_action.token == "tok123"


def test_map_menu_text_to_action() -> None:
    assert ui.map_menu_text_to_action("Ask question") == "menu:ask"
    assert ui.map_menu_text_to_action("Reset context") == "menu:reset"
    assert ui.map_menu_text_to_action("unknown") is None


def test_answer_actions_keyboard_contains_expected_callbacks() -> None:
    keyboard = ui.build_answer_actions_keyboard("tok1")
    callback_values = [button["callback_data"] for row in keyboard["inline_keyboard"] for button in row]

    assert "menu:ask" in callback_values
    assert "act:refine:tok1" in callback_values
    assert "act:sources:tok1" in callback_values
    assert "act:details:tok1" in callback_values


def test_build_callback_prompt_for_refine() -> None:
    prompt = ui.build_callback_prompt(ui.ACT_REFINE, "revenue trend")
    assert "Refine this question" in prompt
    assert "revenue trend" in prompt
