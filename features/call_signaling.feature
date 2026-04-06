Feature: Call signaling
  The backend should relay call signaling envelopes between room members without exposing implementation details.

  Scenario: An SDP offer is relayed to another participant
    Given a unique room alias "call_room"
    And WebSocket client "alice" is connected
    And WebSocket client "bob" is connected
    And client "alice" joins room "call_room" with a generated libsodium-style public key
    And client "bob" joins room "call_room" with a generated libsodium-style public key
    When client "alice" sends signaling action "OFFER" with JSON payload
      """
      {
        "type": "offer",
        "sdp": "dummy-offer-sdp"
      }
      """
    Then the response for client "alice" should contain
      | field   | value                               |
      | status  | 0                                   |
      | message | Signal call dispatched successfully |
    And client "bob" should receive a "SignalCallRelay" event containing
      | field       | value           |
      | action      | OFFER           |
      | sender_uuid | alice           |
      | data.type   | offer           |
      | data.sdp    | dummy-offer-sdp |
