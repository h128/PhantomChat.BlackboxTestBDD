@crypto_contract
Feature: Room keys when people join
  Joining a room returns encrypted room access details, and clearly broken keys are turned away.

  Scenario: People in the same room can open the same room key
    Given a fresh room called "crypto_room"
    And "alice" is connected
    And "bob" is connected
    When "alice" joins room "crypto_room" with a generated key pair
    Then the reply for "alice" should include
      | field        | value       |
      | status       | 0           |
      | room_created | true        |
      | room_name    | crypto_room |
    And the reply field "room_key" for "alice" should not be empty
    And the reply field "room_key" for "alice" should match regex "^[0-9a-f]+$"
    And the reply field "room_key" for "alice" should be longer than 64 characters
    And the reply field "server_pub_key" for "alice" should match regex "^[0-9a-f]{64}$"
    And "alice" should be able to open the room key from the reply
    And the opened room key for "alice" should match regex "^[0-9a-f]{64}$"
    When "bob" joins room "crypto_room" with a generated key pair
    Then the reply for "bob" should include
      | field        | value       |
      | status       | 0           |
      | room_created | false       |
      | room_name    | crypto_room |
    And the reply field "room_key" for "bob" should match regex "^[0-9a-f]+$"
    And the reply field "room_key" for "bob" should be longer than 64 characters
    And the reply field "server_pub_key" for "bob" should match regex "^[0-9a-f]{64}$"
    And "bob" should be able to open the room key from the reply
    And the opened room key for "bob" should match regex "^[0-9a-f]{64}$"
    And the opened room key for "alice" and "bob" should be the same

  Scenario: Different rooms open to different room keys
    Given a fresh room called "crypto_room_one"
    And another fresh room called "crypto_room_two"
    And "alice" is connected
    And "bob" is connected
    When "alice" joins room "crypto_room_one" with a generated key pair
    And "bob" joins room "crypto_room_two" with a generated key pair
    Then "alice" should be able to open the room key from the reply
    And "bob" should be able to open the room key from the reply
    And the opened room key for "alice" and "bob" should be different

  Scenario: A clearly broken key is rejected
    Given a fresh room called "crypto_validation_room"
    And "mallory" is connected
    When "mallory" joins room "crypto_validation_room" with key "not-a-valid key!"
    Then the reply for "mallory" should include
      | field  | value |
      | status | 1     |
    And the reply field "message" for "mallory" should mention "public_key"
