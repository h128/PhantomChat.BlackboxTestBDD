Feature: Room lifecycle and chat messaging
  The chat backend should expose a stable room and messaging contract over WebSocket.

  Scenario: Two users can create and join the same room
    Given a unique room alias "main_room"
    And WebSocket client "alice" is connected
    And WebSocket client "bob" is connected
    When client "alice" joins room "main_room" with a generated libsodium-style public key
    Then the response for client "alice" should contain
      | field        | value     |
      | status       | 0         |
      | room_created | true      |
      | room_name    | main_room |
      | members      | alice     |
    When client "bob" joins room "main_room" with a generated libsodium-style public key
    Then the response for client "bob" should contain
      | field        | value     |
      | status       | 0         |
      | room_created | false     |
      | room_name    | main_room |
      | members      | alice,bob |
    And client "alice" should receive a "UserEnteredRoom" event containing
      | field     | value     |
      | room_name | main_room |
      | user_uuid | bob       |

  Scenario: A joined user can send a chat message to the room
    Given a unique room alias "chat_room"
    And WebSocket client "alice" is connected
    And WebSocket client "bob" is connected
    And client "alice" joins room "chat_room" with a generated libsodium-style public key
    And client "bob" joins room "chat_room" with a generated libsodium-style public key
    When client "alice" sends chat message "hello from behave"
    Then the response for client "alice" should contain
      | field   | value             |
      | status  | 0                 |
      | message | hello from behave |
    And client "bob" should receive a "NewMessageReceived" event containing
      | field       | value             |
      | sender_uuid | alice             |
      | message     | hello from behave |

  Scenario: The server rejects a chat message from a client outside any room
    Given WebSocket client "alice" is connected
    When client "alice" sends chat message "this should fail"
    Then the response for client "alice" should contain
      | field   | value                |
      | status  | 1                    |
      | message | User not in a room   |

  Scenario: Leaving a room notifies the remaining participants
    Given a unique room alias "leave_room"
    And WebSocket client "alice" is connected
    And WebSocket client "bob" is connected
    And client "alice" joins room "leave_room" with a generated libsodium-style public key
    And client "bob" joins room "leave_room" with a generated libsodium-style public key
    When client "bob" leaves the current room
    Then the response for client "bob" should contain
      | field   | value |
      | status  | 0                    |
    And client "alice" should receive a "LeaveRoom" event containing
      | field     | value |
      | user_uuid | bob   |
    And the response field "message" for client "bob" should contain "Left room"
