@crypto_contract
Feature: Room keys when people join
  Joining a room returns a room key, and clearly broken keys are turned away.

  Scenario: Everyone in the same room gets the same room key
    Given a fresh room called "crypto_room"
    And "alice" is connected
    And "bob" is connected
    When "alice" joins room "crypto_room" with a valid key
    Then the reply for "alice" should include
      | field        | value       |
      | status       | 0           |
      | room_created | true        |
      | room_name    | crypto_room |
    And the reply field "room_key" for "alice" should not be empty
    And the reply field "room_key" for "alice" should match regex "^[0-9a-f]{64}$"
    When "bob" joins room "crypto_room" with a valid key
    Then the reply for "bob" should include
      | field        | value       |
      | status       | 0           |
      | room_created | false       |
      | room_name    | crypto_room |
    And the reply field "room_key" for "bob" should match regex "^[0-9a-f]{64}$"
    And the reply field "room_key" for "alice" and "bob" should be the same

  Scenario: Different rooms get different room keys
    Given a fresh room called "crypto_room_one"
    And another fresh room called "crypto_room_two"
    And "alice" is connected
    And "bob" is connected
    When "alice" joins room "crypto_room_one" with a valid key
    And "bob" joins room "crypto_room_two" with a valid key
    Then the reply field "room_key" for "alice" and "bob" should be different

  Scenario: A clearly broken key is rejected
    Given a fresh room called "crypto_validation_room"
    And "mallory" is connected
    When "mallory" joins room "crypto_validation_room" with key "not-a-valid key!"
    Then the reply for "mallory" should include
      | field  | value |
      | status | 1     |
    And the reply field "message" for "mallory" should mention "public_key"
