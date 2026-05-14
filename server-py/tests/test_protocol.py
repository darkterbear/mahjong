from server.protocol import (
    HandPhase, ClientEvent, ServerEvent, AvailableAction,
)


def test_phases_are_distinct() -> None:
    phases = {HandPhase.PRE_DICE, HandPhase.DEALING, HandPhase.FLOWER_RESOLUTION,
              HandPhase.PLAYING, HandPhase.SETTLEMENT}
    assert len(phases) == 5


def test_client_event_names() -> None:
    assert ClientEvent.ROLL_DICE.value == "roll_dice"
    assert ClientEvent.DRAW_FRONT.value == "draw_front"
    assert ClientEvent.DRAW_BACK.value == "draw_back"
    assert ClientEvent.DISCARD.value == "discard"
    assert ClientEvent.DECLARE_FLOWER.value == "declare_flower"
    assert ClientEvent.CLAIM.value == "claim"
    assert ClientEvent.DECLARE_CONCEALED_GANG.value == "declare_concealed_gang"
    assert ClientEvent.DECLARE_ADDED_GANG.value == "declare_added_gang"
    assert ClientEvent.DECLARE_SELF_HU.value == "declare_self_hu"
    assert ClientEvent.NEXT_HAND.value == "next_hand"
    assert ClientEvent.CLAIM_DECISION.value == "claim_decision"
    assert ClientEvent.CLAIM_WAIT.value == "claim_wait"


def test_server_event_names() -> None:
    assert ServerEvent.STATE_UPDATE.value == "state_update"
    assert ServerEvent.DICE_ROLLED.value == "dice_rolled"
    assert ServerEvent.DEALING_STEP.value == "dealing_step"
    assert ServerEvent.HAND_SETTLEMENT.value == "hand_settlement"
    assert ServerEvent.LOBBY_UPDATE.value == "lobby_update"


def test_available_action_names() -> None:
    assert AvailableAction.DRAW_FRONT.value == "draw_front"
    assert AvailableAction.HU.value == "hu"
    assert AvailableAction.PENG.value == "peng"
