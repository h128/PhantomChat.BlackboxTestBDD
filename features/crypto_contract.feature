Feature: Crypto-related handshake contract
  The externally visible join protocol should expose stable key material and reject obviously malformed client public keys.

  Scenario: Joining a room returns stable room key material for all members
    Given a unique room alias "crypto_room"
    And WebSocket client "alice" is connected
    And WebSocket client "bob" is connected
    When client "alice" joins room "crypto_room" with a generated libsodium-style public key
    Then the response for client "alice" should contain
      | field        | value       |
      | status       | 0           |
      | room_created | true        |
      | room_name    | crypto_room |
    And the response field "room_key" for client "alice" should not be empty
    And the response field "room_key" for client "alice" should match regex "^[0-9a-f]{64}$"
    When client "bob" joins room "crypto_room" with a generated libsodium-style public key
    Then the response for client "bob" should contain
      | field        | value       |
      | status       | 0           |
      | room_created | false       |
      | room_name    | crypto_room |
    And the response field "room_key" for client "bob" should match regex "^[0-9a-f]{64}$"
    And the response field "room_key" for clients "alice" and "bob" should be equal

  Scenario: Different rooms expose different room key material
    Given a unique room alias "crypto_room_one"
    And a unique room alias "crypto_room_two"
    And WebSocket client "alice" is connected
    And WebSocket client "bob" is connected
    When client "alice" joins room "crypto_room_one" with a generated libsodium-style public key
    And client "bob" joins room "crypto_room_two" with a generated libsodium-style public key
    Then the response field "room_key" for clients "alice" and "bob" should not be equal

  Scenario: Malformed public key material is rejected
    Given a unique room alias "crypto_validation_room"
    And WebSocket client "mallory" is connected
    When client "mallory" joins room "crypto_validation_room" with public key "not-a-valid key!"
    Then the response for client "mallory" should contain
      | field  | value |
      | status | 1     |
    And the response field "message" for client "mallory" should contain "public_key"
