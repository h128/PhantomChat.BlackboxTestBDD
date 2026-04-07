Feature: Passing along call setup messages
  People in the same room can pass call setup details to each other.

  Scenario: Alice starts a call and Bob receives the offer
    Given a fresh room called "call_room"
    And "alice" is connected
    And "bob" is connected
    And "alice" joins room "call_room" with a valid key
    And "bob" joins room "call_room" with a valid key
    When "alice" shares the call step "OFFER" with details
      """
      {
        "type": "offer",
        "sdp": "dummy-offer-sdp"
      }
      """
    Then the reply for "alice" should include
      | field   | value                               |
      | status  | 0                                   |
      | message | Signal call dispatched successfully |
    And "bob" should receive the call details from "alice"
      | field       | value           |
      | action      | OFFER           |
      | data.type   | offer           |
      | data.sdp    | dummy-offer-sdp |
