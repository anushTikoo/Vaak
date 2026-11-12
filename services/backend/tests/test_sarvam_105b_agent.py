import json
from unittest.mock import AsyncMock, patch

import pytest

from src.services.sarvam.client import sarvam_client
from src.services.voice.orchestrator import (
    MAX_TOOL_CALLS_PER_TURN,
    VAAK_105B_SYSTEM_PROMPT,
    extract_product_cards,
    voice_orchestrator,
)
from src.services.zepto.client import ZEPTO_TOOL_DEFINITIONS, zepto_client


@pytest.mark.asyncio
async def test_zepto_mcp_chat_tools_definition_conforms_to_openai_schema():
    """Verify that get_chat_tools generates valid OpenAI-compatible function calling schemas for all Zepto tools."""
    tools = zepto_client.get_chat_tools()
    assert len(tools) == len(ZEPTO_TOOL_DEFINITIONS)
    for tool in tools:
        assert tool["type"] == "function"
        fn = tool["function"]
        assert "name" in fn and isinstance(fn["name"], str)
        assert "description" in fn and isinstance(fn["description"], str)
        assert "parameters" in fn and isinstance(fn["parameters"], dict)
        assert fn["parameters"].get("type") == "object"
        assert "properties" in fn["parameters"]


@pytest.mark.asyncio
async def test_sarvam_105b_smart_routing_greeting_skips_zepto_mcp(client):
    """Smart routing: greetings and pleasantries must NOT bombard Zepto MCP with queries."""
    with patch.object(zepto_client, "call_tool", new_callable=AsyncMock) as mock_call_tool:
        response = await client.post(
            "/api/v1/chat/message",
            json={"message": "Namaste beta, kaise ho aap?", "language": "hi-IN"},
        )

        assert response.status_code == 200
        data = response.json()
        # Zepto MCP must NOT be called for general greetings
        mock_call_tool.assert_not_called()
        assert data["tools_invoked"] == []
        assert data["tool_logs"] == []
        assert len(data["suggested_products"]) == 0
        assert data["action_type"] == "none"
        assert len(data["reply_text"]) > 0


@pytest.mark.asyncio
async def test_sarvam_105b_smart_routing_english_greeting_skips_zepto_mcp(client):
    """English small talk / greetings must also avoid calling Zepto MCP tools."""
    with patch.object(zepto_client, "call_tool", new_callable=AsyncMock) as mock_call_tool:
        response = await client.post(
            "/api/v1/chat/message",
            json={"message": "Good morning, who are you?", "language": "en-IN"},
        )

        assert response.status_code == 200
        data = response.json()
        mock_call_tool.assert_not_called()
        assert data["tools_invoked"] == []
        assert data["action_type"] == "none"


@pytest.mark.asyncio
async def test_sarvam_105b_agent_executes_zepto_mcp_product_search(client):
    """When a grocery intent is identified, the 105B agent calls Zepto search and returns products."""
    mock_chat_first = {
        "id": "cmpl_search",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_search_1",
                            "type": "function",
                            "function": {
                                "name": "search_products",
                                "arguments": json.dumps({"query": "milk"}),
                            },
                        }
                    ],
                },
            }
        ],
    }
    mock_chat_second = {
        "id": "cmpl_search_reply",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": "Maine aapke liye doodh dhoondh liya hai. Kya main ise cart me daal doon?",
                    "tool_calls": None,
                },
            }
        ],
    }
    with patch.object(sarvam_client, "chat_completion", side_effect=[mock_chat_first, mock_chat_second]):
        response = await client.post(
            "/api/v1/chat/message",
            json={"message": "Beta, mujhe 2 packet doodh aur bread chahiye", "language": "hi-IN"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["tools_invoked"]) >= 1
        assert "search_products" in data["tools_invoked"]
        assert len(data["suggested_products"]) >= 1
        assert data["action_type"] == "clarification_needed"
        assert data["detected_language"] == "hi-IN"


@pytest.mark.asyncio
async def test_sarvam_105b_agent_mixed_greeting_and_grocery_query(client):
    """Mixed greeting + grocery query: elderly phrases like 'Namaste beta, mujhe 2 packet doodh chahiye'

    must NOT strip tools or be ignored as a pure greeting. Zepto MCP search must be executed.
    """
    response = await client.post(
        "/api/v1/chat/message",
        json={"message": "Namaste beta, mujhe 2 packet doodh chahiye", "language": "hi-IN"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "search_products" in data["tools_invoked"]
    assert len(data["suggested_products"]) >= 1
    assert any("milk" in p["name"].lower() or "doodh" in p["name"].lower() for p in data["suggested_products"])
    assert data["action_type"] == "clarification_needed"
    assert "tool_logs" in data
    assert len(data["tool_logs"]) >= 1
    assert data["tool_logs"][0]["tool_name"] == "search_products"
    assert data["tool_logs"][0]["status"] == "success"
    assert "items found" in (data["tool_logs"][0]["summary"] or "")


@pytest.mark.asyncio
async def test_sarvam_105b_agent_enforces_rate_limiting_max_tool_calls():
    """Rate limiting: ensure that excessive tool calls in a single turn are clamped to MAX_TOOL_CALLS_PER_TURN."""
    excessive_tool_calls = [
        {
            "id": f"call_{i}",
            "type": "function",
            "function": {"name": "search_products", "arguments": '{"query": "item"}'},
        }
        for i in range(5)
    ]

    mock_chat_first = {
        "id": "cmpl_excessive",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": excessive_tool_calls,
                },
            }
        ],
    }
    mock_chat_second = {
        "id": "cmpl_second",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": "Here are your items, Ji.",
                    "tool_calls": None,
                },
            }
        ],
    }

    with patch.object(sarvam_client, "chat_completion", side_effect=[mock_chat_first, mock_chat_second]) as mock_chat, \
         patch.object(zepto_client, "call_tool", new_callable=AsyncMock) as mock_call_tool:

        mock_call_tool.return_value = {
            "status": "success",
            "response": {"items": []},
            "order_confirmation_guardrail_active": False,
        }

        res = await voice_orchestrator.process_user_intent(
            user_message="I need 10 different grocery items urgently",
            language="en-IN",
        )

        # Clamped strictly to MAX_TOOL_CALLS_PER_TURN (2) to avoid bombarding the MCP server
        assert mock_call_tool.call_count == MAX_TOOL_CALLS_PER_TURN
        assert len(res.tools_invoked) == MAX_TOOL_CALLS_PER_TURN

        # Verify assistant message in messages history was clamped to prevent OpenAI/Sarvam 400 Bad Request
        second_call_messages = mock_chat.call_args_list[1][1]["messages"]
        assistant_msg = next(m for m in second_call_messages if m.get("role") == "assistant")
        assert len(assistant_msg["tool_calls"]) == MAX_TOOL_CALLS_PER_TURN
        tool_role_msgs = [m for m in second_call_messages if m.get("role") == "tool"]
        assert len(tool_role_msgs) == MAX_TOOL_CALLS_PER_TURN


@pytest.mark.asyncio
async def test_sarvam_105b_order_confirmation_guardrail_prevents_live_order():
    """Safety guardrail: prevent any tool execution or flow from confirming a live purchase."""
    mock_chat_order = {
        "id": "cmpl_order",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_confirm",
                            "type": "function",
                            "function": {
                                "name": "confirm_order_cod",
                                "arguments": '{"confirmOrder": true, "riderTip": 20}',
                            },
                        }
                    ],
                },
            }
        ],
    }
    mock_chat_second = {
        "id": "cmpl_order_reply",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": (
                        "Aapka order summary screen par taiyaar hai. "
                        "Suraksha ke liye, kripya screen par Confirm Order button dabayein."
                    ),
                    "tool_calls": None,
                },
            }
        ],
    }

    with patch.object(sarvam_client, "chat_completion", side_effect=[mock_chat_order, mock_chat_second]):
        res = await voice_orchestrator.process_user_intent(
            user_message="Please confirm and place my order immediately",
            language="hi-IN",
        )

        assert res.order_guardrail_active is True
        assert res.action_type == "order_confirmation_requested"


@pytest.mark.asyncio
async def test_zepto_client_call_tool_guardrail_overrides_confirm_order():
    """Verify ZeptoMCPClient.call_tool with enforce_guardrail forces confirmOrder=False."""
    result = await zepto_client.call_tool(
        name="create_order",
        arguments={"confirmOrder": True, "riderTip": 10},
        enforce_guardrail=True,
    )

    assert result["order_confirmation_guardrail_active"] is True
    assert "Live order placement was temporarily prevented" in result["guardrail_note"]
    assert result["input_arguments"]["confirmOrder"] is True  # preserved for caller record
    # But response reflects preview mode, not live confirmation
    assert result["response"]["status"] == "preview"


@pytest.mark.asyncio
async def test_zepto_client_call_tool_guardrail_intercepts_confirm_order_cod():
    """Verify ZeptoMCPClient.call_tool with guardrail intercepts confirm_order_cod live tool."""
    result = await zepto_client.call_tool(
        name="confirm_order_cod",
        arguments={"confirmOrder": True, "riderTip": 0},
        enforce_guardrail=True,
    )

    assert result["order_confirmation_guardrail_active"] is True
    assert result["response"]["status"] == "preview"


@pytest.mark.asyncio
async def test_zepto_client_call_tool_guardrail_handles_string_false():
    """Verify confirmOrder='false' (string) is NOT falsely treated as truthy by guardrail."""
    result = await zepto_client.call_tool(
        name="create_order",
        arguments={"confirmOrder": "false", "riderTip": 0},
        enforce_guardrail=True,
    )

    # String "false" was already false, so guardrail did not need to intercept
    assert result.get("order_confirmation_guardrail_active") is not True
    assert result["response"]["status"] == "preview"


def test_mock_chat_completion_turn2_produces_elder_friendly_responses():
    """Verify SarvamClient mock turn 2 responses are customized and respectful for each tool type."""
    # 1. Order preview
    res_order = sarvam_client._generate_mock_chat_completion([
        {"role": "user", "content": "place order"},
        {"role": "tool", "name": "create_order", "content": "{}"},
    ])
    order_text = res_order["choices"][0]["message"]["content"]
    assert "order summary" in order_text.lower()
    assert "ji" in order_text.lower()

    # 2. View cart
    res_cart = sarvam_client._generate_mock_chat_completion([
        {"role": "user", "content": "view cart"},
        {"role": "tool", "name": "view_cart", "content": "{}"},
    ])
    cart_text = res_cart["choices"][0]["message"]["content"]
    assert "cart" in cart_text.lower()
    assert "ji" in cart_text.lower()

    # 3. Update cart
    res_update = sarvam_client._generate_mock_chat_completion([
        {"role": "user", "content": "add milk"},
        {"role": "tool", "name": "update_cart", "content": "{}"},
    ])
    update_text = res_update["choices"][0]["message"]["content"]
    assert "updated" in update_text.lower()


@pytest.mark.asyncio
async def test_sarvam_105b_translation_pipeline_translates_to_indic_language():
    """Verify that when user speaks in an Indic language, the response is translated back."""
    mock_chat_first = {
        "id": "cmpl_1",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": "I have found the fresh milk for you. Would you like to add it?",
                    "tool_calls": None,
                },
            }
        ],
    }

    with patch.object(sarvam_client, "chat_completion", return_value=mock_chat_first), \
         patch.object(sarvam_client, "translate_text", new_callable=AsyncMock) as mock_translate:

        mock_translate.return_value = "मैंने आपके लिए ताज़ा दूध ढूंढ लिया है। क्या आप इसे कार्ट में जोड़ना चाहेंगे?"

        res = await voice_orchestrator.process_user_intent(
            user_message="दूध चाहिए",
            language="hi-IN",
        )

        mock_translate.assert_awaited_once_with(
            text="I have found the fresh milk for you. Would you like to add it?",
            target_language_code="hi-IN",
            source_language_code="auto",
        )
        assert "दूध" in res.reply_text


@pytest.mark.asyncio
async def test_sarvam_105b_tts_generates_audio_base64_in_response():
    """Verify that Sarvam TTS is called to generate speech audio in the matching language."""
    mock_b64 = "UklGRi4AAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA="
    with patch.object(sarvam_client, "generate_speech_base64", new_callable=AsyncMock) as mock_tts:
        mock_tts.return_value = mock_b64

        res = await voice_orchestrator.process_user_intent(
            user_message="Hello, do you have fresh apples?",
            language="en-IN",
        )

        mock_tts.assert_awaited_once()
        assert res.audio_base64 == mock_b64


def test_system_prompt_contains_all_core_instructions():
    """Verify VAAK_105B_SYSTEM_PROMPT includes all safety, smart-routing, elder-tone, and formatting rules."""
    prompt = VAAK_105B_SYSTEM_PROMPT
    assert "SMART INTENT ROUTING" in prompt
    assert "PREVENT BOMBARDING ZEPTO MCP" in prompt
    assert "REQUEST DISCIPLINE & RATE LIMITING" in prompt
    assert "CONVERSATIONAL TONE FOR OLDER ADULTS" in prompt
    assert "STRICT CONCISENESS" in prompt
    assert "1-2 short sentences maximum" in prompt.lower()
    assert "SPOKEN RESPONSE FORMATTING" in prompt
    assert "SAFETY GUARDRAIL - ORDER CONFIRMATION" in prompt
    assert "markdown tables" in prompt.lower()
    assert "confirmorder=false" in prompt.lower()


@pytest.mark.asyncio
async def test_session_memory_retains_recent_conversation_context():
    """Verify that VoiceOrchestrator stores and supplies prior conversation turns across turns."""
    from uuid import uuid4
    session_id = uuid4()

    mock_chat_turn1 = {
        "id": "cmpl_1",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": "Namaste! I can help you find fresh groceries.",
                    "tool_calls": None,
                },
            }
        ],
    }
    mock_chat_turn2 = {
        "id": "cmpl_2",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": "I see you asked for Nandini milk. Let me get that for you.",
                    "tool_calls": None,
                },
            }
        ],
    }

    # Clear any previous session history for this UUID
    voice_orchestrator.clear_session(session_id)

    with patch.object(sarvam_client, "chat_completion", side_effect=[mock_chat_turn1, mock_chat_turn2]) as mock_llm:
        # First turn
        res1 = await voice_orchestrator.process_user_intent(
            user_message="Hello, how can you help me today?",
            session_id=session_id,
            language="en-IN",
        )
        assert res1.session_id == session_id

        # Inspect history after Turn 1
        history_after_1 = voice_orchestrator.get_session_history(session_id)
        assert len(history_after_1) == 2
        assert history_after_1[0]["role"] == "user"
        assert history_after_1[0]["content"] == "Hello, how can you help me today?"
        assert history_after_1[1]["role"] == "assistant"
        assert history_after_1[1]["content"] == "Namaste! I can help you find fresh groceries."

        # Second turn in the same session
        res2 = await voice_orchestrator.process_user_intent(
            user_message="Do you have Nandini milk?",
            session_id=session_id,
            language="en-IN",
        )
        assert res2.session_id == session_id

        # Verify second LLM call received turn 1 history in messages list
        second_call_messages = mock_llm.call_args_list[1][1]["messages"]
        user_messages_in_prompt = [m for m in second_call_messages if m["role"] == "user"]
        assistant_messages_in_prompt = [m for m in second_call_messages if m["role"] == "assistant"]

        assert len(user_messages_in_prompt) == 2  # Turn 1 user + Turn 2 user
        assert user_messages_in_prompt[0]["content"] == "Hello, how can you help me today?"
        assert user_messages_in_prompt[1]["content"] == "Do you have Nandini milk?"
        assert len(assistant_messages_in_prompt) == 1  # Turn 1 assistant
        assert assistant_messages_in_prompt[0]["content"] == "Namaste! I can help you find fresh groceries."

        # Verify clear_session removes memory
        voice_orchestrator.clear_session(session_id)
        assert voice_orchestrator.get_session_history(session_id) == []


def test_extract_product_cards_handles_paise_and_rupees():
    """Verify price normalization handles both rupee values and paise (>1000)."""
    tool_resp = {
        "structuredContent": {
            "products": [
                {
                    "id": "prod_1",
                    "name": "Amul Milk",
                    "price": 5400,  # 5400 paise = 54.0 rupees
                    "packSize": "1 L",
                    "isAvailable": True,
                },
                {
                    "id": "prod_2",
                    "name": "Bread",
                    "price": 45.0,  # 45.0 rupees
                    "packSize": "400 g",
                    "isAvailable": True,
                },
            ]
        }
    }
    cards = extract_product_cards("search_products", tool_resp)
    assert len(cards) == 2
    assert cards[0].price == 54.0
    assert cards[1].price == 45.0


@pytest.mark.asyncio
async def test_chat_history_api_routes_get_and_delete(client):
    """Verify that chat history endpoint returns recorded turns and allows clearing."""
    from uuid import uuid4
    session_id = uuid4()

    voice_orchestrator.append_session_turn(session_id, "User test question", "Assistant test answer")

    # GET history
    get_res = await client.get(f"/api/v1/chat/history/{session_id}")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["count"] == 2
    assert data["turns"][0]["content"] == "User test question"
    assert data["turns"][1]["content"] == "Assistant test answer"

    # DELETE history
    del_res = await client.delete(f"/api/v1/chat/history/{session_id}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "cleared"

    # Verify cleared
    verify_res = await client.get(f"/api/v1/chat/history/{session_id}")
    assert verify_res.json()["count"] == 0


@pytest.mark.asyncio
async def test_mock_intent_records_session_history():
    """Verify that _process_mock_test_intent records session history turns."""
    from uuid import uuid4
    session_id = uuid4()
    voice_orchestrator.clear_session(session_id)

    with patch.object(zepto_client, "search_products", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = []
        await voice_orchestrator.process_user_intent(
            user_message="Find brown bread",
            session_id=session_id,
            language="en-IN",
        )

        history = voice_orchestrator.get_session_history(session_id)
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Find brown bread"
        assert history[1]["role"] == "assistant"

    voice_orchestrator.clear_session(session_id)


def test_system_prompt_strictly_enforces_conciseness():
    """Verify VAAK_105B_SYSTEM_PROMPT contains strict conciseness and conversational instructions."""
    assert "STRICT CONCISENESS" in VAAK_105B_SYSTEM_PROMPT
    assert "1-2 short sentences maximum" in VAAK_105B_SYSTEM_PROMPT
    assert "straight to the point" in VAAK_105B_SYSTEM_PROMPT
    assert "conversational" in VAAK_105B_SYSTEM_PROMPT.lower()


@pytest.mark.asyncio
async def test_generate_audio_false_skips_sarvam_tts(client):
    """Opt-out: when generate_audio=False, backend completely skips Sarvam TTS synthesis."""
    with patch.object(sarvam_client, "generate_speech_base64", new_callable=AsyncMock) as mock_tts:
        response = await client.post(
            "/api/v1/chat/message",
            json={
                "message": "Namaste beta, kaise ho aap?",
                "language": "hi-IN",
                "generate_audio": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        # TTS synthesis must NOT be invoked when generate_audio is False
        mock_tts.assert_not_called()
        assert data["audio_base64"] is None
        assert data["spoken_text"] is not None
        assert len(data["spoken_text"]) > 0


@pytest.mark.asyncio
async def test_rolling_dialogue_state_tracking_across_multi_turn_session():
    """Verify SessionDialogueState compresses older context into a 1-sentence summary and tracks product IDs."""
    from uuid import uuid4

    session_id = uuid4()
    voice_orchestrator.clear_session(session_id)

    # Mock LLM to inspect messages payload sent at each turn
    with patch.object(sarvam_client, "chat_completion", new_callable=AsyncMock) as mock_llm:
        mock_llm.side_effect = [
            # Turn 1 reply
            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "I found fresh Nandini milk for you. Would you like me to add it?",
                    }
                }]
            },
            # Turn 2 reply
            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "I have also added brown bread to your cart.",
                    }
                }]
            },
            # Turn 3 reply
            {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "Your total bill is ₹99 for milk and bread.",
                    }
                }]
            },
        ]

        # Turn 1
        await voice_orchestrator.process_user_intent(
            user_message="I need Nandini milk",
            session_id=session_id,
            language="en-IN",
            generate_audio=False,
        )
        state1 = voice_orchestrator.get_session_state(session_id)
        assert state1.last_turn_user == "I need Nandini milk"
        assert state1.rolling_summary == ""  # No prior turns to summarize yet

        # Turn 2
        await voice_orchestrator.process_user_intent(
            user_message="Also add brown bread",
            session_id=session_id,
            language="en-IN",
            generate_audio=False,
        )
        state2 = voice_orchestrator.get_session_state(session_id)
        assert state2.last_turn_user == "Also add brown bread"
        # Turn 1 has now rolled into the rolling summary
        assert "I need Nandini milk" in state2.rolling_summary

        # Turn 3
        await voice_orchestrator.process_user_intent(
            user_message="What is my total?",
            session_id=session_id,
            language="en-IN",
            generate_audio=False,
        )

        # Inspect messages received by LLM in Turn 3
        turn3_messages = mock_llm.call_args_list[2][1]["messages"]
        # Exactly 4 messages: System + Turn 2 user + Turn 2 assistant + Turn 3 user
        assert len(turn3_messages) == 4
        assert turn3_messages[0]["role"] == "system"
        assert "SESSION CONTEXT:" in turn3_messages[0]["content"]
        assert "Past session summary:" in turn3_messages[0]["content"]
        assert "I need Nandini milk" in turn3_messages[0]["content"]

        assert turn3_messages[1]["role"] == "user"
        assert turn3_messages[1]["content"] == "Also add brown bread"
        assert turn3_messages[2]["role"] == "assistant"
        assert turn3_messages[2]["content"] == "I have also added brown bread to your cart."
        assert turn3_messages[3]["role"] == "user"
        assert turn3_messages[3]["content"] == "What is my total?"

    voice_orchestrator.clear_session(session_id)


@pytest.mark.asyncio
async def test_spoken_text_in_response_is_budgeted_and_sanitized():
    """Verify spoken_text in response is ultra-concise (<= 140 chars) and clean."""
    res = await voice_orchestrator.process_user_intent(
        user_message="Hello, who are you?",
        language="en-IN",
        generate_audio=False,
    )
    assert res.spoken_text is not None
    assert len(res.spoken_text) <= 140
    assert "**" not in res.spoken_text
    assert "###" not in res.spoken_text
    assert res.audio_base64 is None


@pytest.mark.asyncio
async def test_rolling_summary_truncation_preserves_clean_grammar():
    """Verify that when rolling summary exceeds 160 characters, it retains clean grammar without corrupt prefix."""
    from uuid import uuid4

    session_id = uuid4()
    voice_orchestrator.clear_session(session_id)

    turns = [
        ("I need 2 litres of fresh organic cow milk from Nandini dairy", "Found milk"),
        ("Also add 1 packet of whole wheat brown bread and 6 farm fresh eggs", "Added bread and eggs"),
        ("Can you tell me the subtotal price and delivery fee for these items?", "Total is 150"),
        ("Please schedule the delivery to my home address right now", "Scheduled"),
    ]

    for u, a in turns:
        voice_orchestrator.append_session_turn(session_id, u, a)

    state = voice_orchestrator.get_session_state(session_id)
    summary = state.rolling_summary

    assert len(summary) <= 180
    assert summary.endswith(".")
    assert not summary.endswith("..")
    assert ".;" not in summary
    assert "User user" not in summary
    assert summary.startswith("User asked")

    voice_orchestrator.clear_session(session_id)


@pytest.mark.asyncio
async def test_process_user_intent_handles_empty_choices_safely():
    """Verify that process_user_intent does not raise IndexError if LLM returns choices: []."""
    mock_empty_choices = {"id": "cmpl_empty", "choices": []}

    with patch.object(sarvam_client, "chat_completion", return_value=mock_empty_choices):
        res = await voice_orchestrator.process_user_intent(
            user_message="Hello, can you help me?",
            language="en-IN",
            generate_audio=False,
        )

        assert res.reply_text is not None
        assert len(res.reply_text) > 0
        assert "Namaste" in res.reply_text

