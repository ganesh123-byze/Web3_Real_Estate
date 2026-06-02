"""Deploying status detection for copilot create-property (text + voice)."""
from backend.ai.tools import (
    _clear_workflow_session,
    create_property_deploy_pending,
    create_property_server_submit_eligible,
    reset_current_messages,
    reset_current_thread_id,
    set_current_messages,
    set_current_thread_id,
)
from backend.tests.test_create_property_high_value_confirm import (
    _complete_filled,
    _owner,
)


def test_deploy_pending_when_user_said_yes_without_confirm_arg():
    token = set_current_thread_id("test:deploy-pending-yes")
    msg_token = set_current_messages([{"type": "human", "content": "yes"}])
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        from backend.ai import tools

        tools._set_workflow_session(
            "CREATE_PROPERTY",
            {
                "in_progress": True,
                "filled": _complete_filled(),
                "awaiting_create_confirmation": True,
            },
        )
        assert create_property_deploy_pending({}) is True
        assert create_property_deploy_pending({"confirm_create": True}) is True
        assert create_property_deploy_pending({"confirm_create": False}) is False
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_server_submit_eligible_on_yes_confirmation():
    token = set_current_thread_id("test:server-submit-eligible")
    msg_token = set_current_messages([{"type": "human", "content": "yes"}])
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        from backend.ai import tools

        tools._set_workflow_session(
            "CREATE_PROPERTY",
            {
                "in_progress": True,
                "filled": _complete_filled(),
                "awaiting_create_confirmation": True,
            },
        )
        eligible, name = create_property_server_submit_eligible(_owner())
        assert eligible is True
        assert name == "Mega Estate"
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_messages(msg_token)
        reset_current_thread_id(token)


def test_server_submit_not_eligible_while_collecting_fields():
    token = set_current_thread_id("test:server-submit-collecting")
    try:
        _clear_workflow_session("CREATE_PROPERTY")
        eligible, _ = create_property_server_submit_eligible(_owner())
        assert eligible is False
    finally:
        _clear_workflow_session("CREATE_PROPERTY")
        reset_current_thread_id(token)
