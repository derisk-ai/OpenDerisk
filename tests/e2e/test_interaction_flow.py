"""
E2E Tests - Interaction Flow

Tests the complete interaction flow between the system and users:
- Text input interactions
- Single/multi select interactions
- Confirmation interactions
- File upload interactions
- Progress notifications
- Authorization interactions via gateway
"""

import pytest
import asyncio
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock

from derisk.core.interaction.gateway import (
    InteractionGateway,
    MemoryConnectionManager,
    MemoryStateStore,
    get_interaction_gateway,
    set_interaction_gateway,
    send_interaction,
    deliver_response,
)
from derisk.core.interaction.protocol import (
    InteractionRequest,
    InteractionResponse,
    InteractionType,
    InteractionStatus,
    InteractionPriority,
    InteractionOption,
    create_text_input_request,
    create_confirmation_request,
    create_selection_request,
    create_authorization_request,
    create_notification,
    create_progress_update,
)


class TestTextInputInteractionE2E:
    """E2E tests for text input interactions."""

    @pytest.fixture
    def gateway(self) -> InteractionGateway:
        conn_manager = MemoryConnectionManager()
        state_store = MemoryStateStore()
        return InteractionGateway(
            connection_manager=conn_manager,
            state_store=state_store,
            default_timeout=30,
        )

    @pytest.mark.asyncio
    async def test_text_input_request_creation(self):
        """Text input request should be created with correct fields."""
        request = create_text_input_request(
            message="Please enter your API key:",
            title="API Key Required",
            default_value="sk-",
            placeholder="Enter your API key here",
            session_id="test-session",
            agent_name="TestAgent",
            required=True,
            timeout=60,
        )

        assert request.type == InteractionType.TEXT_INPUT
        assert request.message == "Please enter your API key:"
        assert request.title == "API Key Required"
        assert request.default_value == "sk-"
        assert request.session_id == "test-session"
        assert request.agent_name == "TestAgent"
        assert request.allow_skip is False  # required=True
        assert request.timeout == 60
        assert request.metadata.get("placeholder") == "Enter your API key here"

    @pytest.mark.asyncio
    async def test_text_input_response_delivered(self, gateway):
        """Text input response should be delivered to pending request."""
        received_messages: List[Dict[str, Any]] = []

        async def mock_callback(message: Dict[str, Any]):
            received_messages.append(message)

        # Add connection
        conn_manager = gateway.connection_manager
        conn_manager.add_connection("test-session", mock_callback)

        request = create_text_input_request(
            message="Enter value:",
            session_id="test-session",
        )

        # Start waiting for response (non-blocking)
        async def send_and_respond():
            await asyncio.sleep(0.05)
            response = InteractionResponse(
                request_id=request.request_id,
                session_id="test-session",
                input_value="user_input_value",
                status=InteractionStatus.RESPONDED,
            )
            await gateway.deliver_response(response)

        # Run both concurrently
        asyncio.create_task(send_and_respond())
        result = await gateway.send_and_wait(request, timeout=5)

        assert result.status == InteractionStatus.RESPONDED
        assert result.input_value == "user_input_value"
        assert len(received_messages) == 1
        assert received_messages[0]["type"] == "interaction_request"

    @pytest.mark.asyncio
    async def test_text_input_skip_allowed(self):
        """Optional text input should allow skip."""
        request = create_text_input_request(
            message="Optional input:",
            required=False,
        )

        assert request.allow_skip is True


class TestConfirmationInteractionE2E:
    """E2E tests for confirmation interactions."""

    @pytest.fixture
    def gateway(self) -> InteractionGateway:
        conn_manager = MemoryConnectionManager()
        state_store = MemoryStateStore()
        return InteractionGateway(
            connection_manager=conn_manager,
            state_store=state_store,
            default_timeout=30,
        )

    @pytest.mark.asyncio
    async def test_confirmation_request_creation(self):
        """Confirmation request should have yes/no options."""
        request = create_confirmation_request(
            message="Do you want to proceed?",
            title="Confirmation",
            confirm_label="Proceed",
            cancel_label="Cancel",
            default_confirm=True,
            session_id="test-session",
        )

        assert request.type == InteractionType.CONFIRMATION
        assert request.message == "Do you want to proceed?"
        assert len(request.options) == 2

        confirm_option = next(o for o in request.options if o.value == "yes")
        cancel_option = next(o for o in request.options if o.value == "no")

        assert confirm_option.label == "Proceed"
        assert confirm_option.default is True
        assert cancel_option.label == "Cancel"
        assert cancel_option.default is False

    @pytest.mark.asyncio
    async def test_confirmation_positive_response(self, gateway):
        """Positive confirmation response should be recognized."""
        received_messages: List[Dict[str, Any]] = []

        async def mock_callback(message: Dict[str, Any]):
            received_messages.append(message)

        conn_manager = gateway.connection_manager
        conn_manager.add_connection("test-session", mock_callback)

        request = create_confirmation_request(
            message="Confirm?",
            session_id="test-session",
        )

        async def send_positive_response():
            await asyncio.sleep(0.05)
            response = InteractionResponse(
                request_id=request.request_id,
                session_id="test-session",
                choice="yes",
                status=InteractionStatus.RESPONDED,
            )
            await gateway.deliver_response(response)

        asyncio.create_task(send_positive_response())
        result = await gateway.send_and_wait(request, timeout=5)

        assert result.is_confirmed is True
        assert result.is_denied is False

    @pytest.mark.asyncio
    async def test_confirmation_negative_response(self, gateway):
        """Negative confirmation response should be recognized."""
        received_messages: List[Dict[str, Any]] = []

        async def mock_callback(message: Dict[str, Any]):
            received_messages.append(message)

        conn_manager = gateway.connection_manager
        conn_manager.add_connection("test-session", mock_callback)

        request = create_confirmation_request(
            message="Confirm?",
            session_id="test-session",
        )

        async def send_negative_response():
            await asyncio.sleep(0.05)
            response = InteractionResponse(
                request_id=request.request_id,
                session_id="test-session",
                choice="no",
                status=InteractionStatus.RESPONDED,
            )
            await gateway.deliver_response(response)

        asyncio.create_task(send_negative_response())
        result = await gateway.send_and_wait(request, timeout=5)

        assert result.is_confirmed is False
        assert result.is_denied is True


class TestSelectionInteractionE2E:
    """E2E tests for selection interactions."""

    @pytest.fixture
    def gateway(self) -> InteractionGateway:
        conn_manager = MemoryConnectionManager()
        state_store = MemoryStateStore()
        return InteractionGateway(
            connection_manager=conn_manager,
            state_store=state_store,
            default_timeout=30,
        )

    @pytest.mark.asyncio
    async def test_single_select_request_creation(self):
        """Single select request should have correct type and options."""
        request = create_selection_request(
            message="Choose a plan:",
            options=["Basic", "Pro", "Enterprise"],
            title="Select Plan",
            multiple=False,
            default_value="Pro",
            session_id="test-session",
        )

        assert request.type == InteractionType.SINGLE_SELECT
        assert request.message == "Choose a plan:"
        assert len(request.options) == 3
        assert request.default_value == "Pro"

        option_labels = [o.label for o in request.options]
        assert "Basic" in option_labels
        assert "Pro" in option_labels
        assert "Enterprise" in option_labels

    @pytest.mark.asyncio
    async def test_multi_select_request_creation(self):
        """Multi select request should have correct type and options."""
        request = create_selection_request(
            message="Choose features:",
            options=[
                {"label": "Feature A", "value": "a", "description": "First feature"},
                {"label": "Feature B", "value": "b", "description": "Second feature"},
                {"label": "Feature C", "value": "c", "description": "Third feature"},
            ],
            multiple=True,
            default_values=["a", "b"],
            session_id="test-session",
        )

        assert request.type == InteractionType.MULTI_SELECT
        assert len(request.options) == 3
        assert request.default_values == ["a", "b"]

        assert request.options[0].description == "First feature"
        assert request.options[1].description == "Second feature"

    @pytest.mark.asyncio
    async def test_single_select_response(self, gateway):
        """Single select response should contain the chosen option."""
        received_messages: List[Dict[str, Any]] = []

        async def mock_callback(message: Dict[str, Any]):
            received_messages.append(message)

        conn_manager = gateway.connection_manager
        conn_manager.add_connection("test-session", mock_callback)

        request = create_selection_request(
            message="Choose:",
            options=["Option 1", "Option 2", "Option 3"],
            session_id="test-session",
        )

        async def send_selection():
            await asyncio.sleep(0.05)
            response = InteractionResponse(
                request_id=request.request_id,
                session_id="test-session",
                choice="Option 2",
                status=InteractionStatus.RESPONDED,
            )
            await gateway.deliver_response(response)

        asyncio.create_task(send_selection())
        result = await gateway.send_and_wait(request, timeout=5)

        assert result.choice == "Option 2"
        assert result.status == InteractionStatus.RESPONDED

    @pytest.mark.asyncio
    async def test_multi_select_response(self, gateway):
        """Multi select response should contain all chosen options."""
        received_messages: List[Dict[str, Any]] = []

        async def mock_callback(message: Dict[str, Any]):
            received_messages.append(message)

        conn_manager = gateway.connection_manager
        conn_manager.add_connection("test-session", mock_callback)

        request = create_selection_request(
            message="Choose features:",
            options=["Feature A", "Feature B", "Feature C"],
            multiple=True,
            session_id="test-session",
        )

        async def send_multi_selection():
            await asyncio.sleep(0.05)
            response = InteractionResponse(
                request_id=request.request_id,
                session_id="test-session",
                choices=["Feature A", "Feature C"],
                status=InteractionStatus.RESPONDED,
            )
            await gateway.deliver_response(response)

        asyncio.create_task(send_multi_selection())
        result = await gateway.send_and_wait(request, timeout=5)

        assert result.choices == ["Feature A", "Feature C"]
        assert len(result.choices) == 2


class TestAuthorizationInteractionE2E:
    """E2E tests for authorization interactions via gateway."""

    @pytest.fixture
    def gateway(self) -> InteractionGateway:
        conn_manager = MemoryConnectionManager()
        state_store = MemoryStateStore()
        return InteractionGateway(
            connection_manager=conn_manager,
            state_store=state_store,
            default_timeout=30,
        )

    @pytest.mark.asyncio
    async def test_authorization_request_creation(self):
        """Authorization request should contain tool info and risk factors."""
        request = create_authorization_request(
            tool_name="bash",
            tool_description="Execute shell commands",
            arguments={"command": "ls -la"},
            risk_level="medium",
            risk_factors=["Shell command execution", "Potential file access"],
            session_id="test-session",
            agent_name="SRE-Agent",
            allow_session_grant=True,
            timeout=120,
        )

        assert request.type == InteractionType.AUTHORIZATION
        assert request.priority == InteractionPriority.HIGH
        assert "bash" in request.title
        assert request.allow_session_grant is True
        assert request.timeout == 120

        # Check authorization context
        ctx = request.authorization_context
        assert ctx["tool_name"] == "bash"
        assert ctx["arguments"] == {"command": "ls -la"}
        assert ctx["risk_level"] == "medium"
        assert len(ctx["risk_factors"]) == 2

        # Check options
        assert len(request.options) == 3  # Allow, Allow for Session, Deny
        option_values = [o.value for o in request.options]
        assert "allow" in option_values
        assert "allow_session" in option_values
        assert "deny" in option_values

    @pytest.mark.asyncio
    async def test_authorization_allow_response(self, gateway):
        """Allow response should grant one-time permission."""
        received_messages: List[Dict[str, Any]] = []

        async def mock_callback(message: Dict[str, Any]):
            received_messages.append(message)

        conn_manager = gateway.connection_manager
        conn_manager.add_connection("test-session", mock_callback)

        request = create_authorization_request(
            tool_name="bash",
            tool_description="Execute shell commands",
            arguments={"command": "ls"},
            session_id="test-session",
        )

        async def send_allow():
            await asyncio.sleep(0.05)
            response = InteractionResponse(
                request_id=request.request_id,
                session_id="test-session",
                choice="allow",
                grant_scope="once",
                status=InteractionStatus.RESPONDED,
            )
            await gateway.deliver_response(response)

        asyncio.create_task(send_allow())
        result = await gateway.send_and_wait(request, timeout=5)

        assert result.is_confirmed
        assert result.grant_scope == "once"
        assert not result.is_session_grant
        assert not result.is_always_grant

    @pytest.mark.asyncio
    async def test_authorization_session_grant(self, gateway):
        """Session grant response should be recognized."""
        received_messages: List[Dict[str, Any]] = []

        async def mock_callback(message: Dict[str, Any]):
            received_messages.append(message)

        conn_manager = gateway.connection_manager
        conn_manager.add_connection("test-session", mock_callback)

        request = create_authorization_request(
            tool_name="bash",
            tool_description="Execute shell commands",
            arguments={"command": "ls"},
            session_id="test-session",
        )

        async def send_session_grant():
            await asyncio.sleep(0.05)
            response = InteractionResponse(
                request_id=request.request_id,
                session_id="test-session",
                choice="allow_session",
                grant_scope="session",
                status=InteractionStatus.RESPONDED,
            )
            await gateway.deliver_response(response)

        asyncio.create_task(send_session_grant())
        result = await gateway.send_and_wait(request, timeout=5)

        assert result.is_session_grant
        assert result.grant_scope == "session"

    @pytest.mark.asyncio
    async def test_authorization_deny_response(self, gateway):
        """Deny response should block the operation."""
        received_messages: List[Dict[str, Any]] = []

        async def mock_callback(message: Dict[str, Any]):
            received_messages.append(message)

        conn_manager = gateway.connection_manager
        conn_manager.add_connection("test-session", mock_callback)

        request = create_authorization_request(
            tool_name="rm",
            tool_description="Delete files",
            arguments={"path": "/important"},
            session_id="test-session",
        )

        async def send_deny():
            await asyncio.sleep(0.05)
            response = InteractionResponse(
                request_id=request.request_id,
                session_id="test-session",
                choice="deny",
                status=InteractionStatus.RESPONDED,
                cancel_reason="Too dangerous",
            )
            await gateway.deliver_response(response)

        asyncio.create_task(send_deny())
        result = await gateway.send_and_wait(request, timeout=5)

        assert result.is_denied
        assert result.cancel_reason == "Too dangerous"


class TestNotificationInteractionE2E:
    """E2E tests for notification interactions."""

    @pytest.fixture
    def gateway(self) -> InteractionGateway:
        conn_manager = MemoryConnectionManager()
        state_store = MemoryStateStore()
        return InteractionGateway(
            connection_manager=conn_manager,
            state_store=state_store,
            default_timeout=30,
        )

    @pytest.mark.asyncio
    async def test_info_notification_creation(self):
        """Info notification should have correct type."""
        notification = create_notification(
            message="Operation completed successfully",
            type=InteractionType.INFO,
            title="Success",
            session_id="test-session",
        )

        assert notification.type == InteractionType.INFO
        assert notification.message == "Operation completed successfully"
        assert notification.allow_cancel is False
        assert notification.timeout == 0

    @pytest.mark.asyncio
    async def test_warning_notification_creation(self):
        """Warning notification should have correct type."""
        notification = create_notification(
            message="API rate limit approaching",
            type=InteractionType.WARNING,
            title="Warning",
        )

        assert notification.type == InteractionType.WARNING

    @pytest.mark.asyncio
    async def test_error_notification_creation(self):
        """Error notification should have correct type."""
        notification = create_notification(
            message="Connection failed",
            type=InteractionType.ERROR,
            title="Error",
        )

        assert notification.type == InteractionType.ERROR

    @pytest.mark.asyncio
    async def test_notification_fire_and_forget(self, gateway):
        """Notifications should be sent without waiting for response."""
        received_messages: List[Dict[str, Any]] = []

        async def mock_callback(message: Dict[str, Any]):
            received_messages.append(message)

        conn_manager = gateway.connection_manager
        conn_manager.add_connection("test-session", mock_callback)

        notification = create_notification(
            message="Processing started",
            type=InteractionType.INFO,
            session_id="test-session",
        )

        # Fire and forget (wait_response=False)
        result = await gateway.send(notification, wait_response=False)

        assert result is None  # No response expected
        await asyncio.sleep(0.05)  # Allow message to be sent
        assert len(received_messages) == 1


class TestProgressUpdateE2E:
    """E2E tests for progress update interactions."""

    @pytest.fixture
    def gateway(self) -> InteractionGateway:
        conn_manager = MemoryConnectionManager()
        state_store = MemoryStateStore()
        return InteractionGateway(
            connection_manager=conn_manager,
            state_store=state_store,
            default_timeout=30,
        )

    @pytest.mark.asyncio
    async def test_progress_update_creation(self):
        """Progress update should have correct fields."""
        progress = create_progress_update(
            message="Analyzing logs...",
            progress=0.45,
            title="Analysis",
            session_id="test-session",
        )

        assert progress.type == InteractionType.PROGRESS
        assert progress.progress_value == 0.45
        assert progress.progress_message == "Analyzing logs..."
        assert progress.allow_cancel is False

    @pytest.mark.asyncio
    async def test_progress_value_clamped(self):
        """Progress value should be clamped to 0-1 range."""
        progress_low = create_progress_update(
            message="Test",
            progress=-0.5,
        )
        assert progress_low.progress_value == 0.0

        progress_high = create_progress_update(
            message="Test",
            progress=1.5,
        )
        assert progress_high.progress_value == 1.0

    @pytest.mark.asyncio
    async def test_progress_updates_sent(self, gateway):
        """Multiple progress updates should be sent."""
        received_messages: List[Dict[str, Any]] = []

        async def mock_callback(message: Dict[str, Any]):
            received_messages.append(message)

        conn_manager = gateway.connection_manager
        conn_manager.add_connection("test-session", mock_callback)

        # Send multiple progress updates
        for i in range(5):
            progress = create_progress_update(
                message=f"Step {i + 1} of 5",
                progress=(i + 1) / 5,
                session_id="test-session",
            )
            await gateway.send(progress, wait_response=False)
            await asyncio.sleep(0.01)

        assert len(received_messages) == 5


class TestGatewayTimeoutE2E:
    """E2E tests for gateway timeout handling."""

    @pytest.fixture
    def gateway(self) -> InteractionGateway:
        conn_manager = MemoryConnectionManager()
        state_store = MemoryStateStore()
        return InteractionGateway(
            connection_manager=conn_manager,
            state_store=state_store,
            default_timeout=1,  # Short timeout for testing
        )

    @pytest.mark.asyncio
    async def test_request_timeout(self, gateway):
        """Request should timeout if no response received."""
        received_messages: List[Dict[str, Any]] = []

        async def mock_callback(message: Dict[str, Any]):
            received_messages.append(message)

        conn_manager = gateway.connection_manager
        conn_manager.add_connection("test-session", mock_callback)

        request = create_confirmation_request(
            message="Confirm?",
            session_id="test-session",
        )

        # Don't send a response - let it timeout
        result = await gateway.send_and_wait(request, timeout=0.5)

        assert result.status == InteractionStatus.EXPIRED
        assert result.cancel_reason == "Request timed out"

    @pytest.mark.asyncio
    async def test_request_cancellation(self, gateway):
        """Request can be cancelled before timeout."""
        received_messages: List[Dict[str, Any]] = []

        async def mock_callback(message: Dict[str, Any]):
            received_messages.append(message)

        conn_manager = gateway.connection_manager
        conn_manager.add_connection("test-session", mock_callback)

        request = create_confirmation_request(
            message="Confirm?",
            session_id="test-session",
        )

        async def cancel_after_delay():
            await asyncio.sleep(0.1)
            await gateway.cancel_request(
                request.request_id,
                reason="User cancelled",
            )

        asyncio.create_task(cancel_after_delay())
        result = await gateway.send_and_wait(request, timeout=5)

        assert result.status == InteractionStatus.CANCELLED
        assert result.cancel_reason == "User cancelled"


class TestGatewaySessionManagementE2E:
    """E2E tests for gateway session management."""

    @pytest.fixture
    def gateway(self) -> InteractionGateway:
        conn_manager = MemoryConnectionManager()
        state_store = MemoryStateStore()
        return InteractionGateway(
            connection_manager=conn_manager,
            state_store=state_store,
            default_timeout=30,
        )

    @pytest.mark.asyncio
    async def test_pending_requests_tracked(self, gateway):
        """Pending requests should be tracked by session."""
        async def mock_callback(message: Dict[str, Any]):
            pass

        conn_manager = gateway.connection_manager
        conn_manager.add_connection("session-1", mock_callback)
        conn_manager.add_connection("session-2", mock_callback)

        request1 = create_confirmation_request(
            message="Confirm 1?",
            session_id="session-1",
        )
        request2 = create_confirmation_request(
            message="Confirm 2?",
            session_id="session-1",
        )
        request3 = create_confirmation_request(
            message="Confirm 3?",
            session_id="session-2",
        )

        # Send requests without waiting (start them as tasks)
        task1 = asyncio.create_task(gateway.send_and_wait(request1, timeout=5))
        task2 = asyncio.create_task(gateway.send_and_wait(request2, timeout=5))
        task3 = asyncio.create_task(gateway.send_and_wait(request3, timeout=5))

        await asyncio.sleep(0.05)

        # Check pending counts
        assert gateway.pending_count() == 3
        assert gateway.pending_count("session-1") == 2
        assert gateway.pending_count("session-2") == 1

        # Cancel all
        await gateway.cancel_session_requests("session-1")
        await gateway.cancel_request(request3.request_id)

        # Wait for tasks to complete
        await asyncio.gather(task1, task2, task3)

    @pytest.mark.asyncio
    async def test_cancel_all_session_requests(self, gateway):
        """All requests for a session should be cancelled together."""
        async def mock_callback(message: Dict[str, Any]):
            pass

        conn_manager = gateway.connection_manager
        conn_manager.add_connection("test-session", mock_callback)

        requests = []
        tasks = []
        for i in range(3):
            req = create_confirmation_request(
                message=f"Confirm {i}?",
                session_id="test-session",
            )
            requests.append(req)
            tasks.append(asyncio.create_task(gateway.send_and_wait(req, timeout=10)))

        await asyncio.sleep(0.05)

        # Cancel all session requests
        cancelled_count = await gateway.cancel_session_requests(
            "test-session",
            reason="Session ended",
        )

        assert cancelled_count == 3

        # All tasks should complete with cancelled status
        results = await asyncio.gather(*tasks)
        for result in results:
            assert result.status == InteractionStatus.CANCELLED


class TestGlobalGatewayE2E:
    """E2E tests for global gateway functions."""

    @pytest.mark.asyncio
    async def test_global_gateway_instance(self):
        """Global gateway should be accessible."""
        # Set a custom gateway
        custom_gateway = InteractionGateway(default_timeout=60)
        set_interaction_gateway(custom_gateway)

        retrieved = get_interaction_gateway()
        assert retrieved is custom_gateway
        assert retrieved._default_timeout == 60

        # Reset to default
        set_interaction_gateway(InteractionGateway())

    @pytest.mark.asyncio
    async def test_send_interaction_convenience(self):
        """Convenience function should work."""
        gateway = InteractionGateway()
        set_interaction_gateway(gateway)

        async def mock_callback(message: Dict[str, Any]):
            pass

        conn_manager = gateway.connection_manager
        conn_manager.add_connection("test-session", mock_callback)

        notification = create_notification(
            message="Test",
            session_id="test-session",
        )

        # Fire and forget
        result = await send_interaction(notification, wait_response=False)
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
