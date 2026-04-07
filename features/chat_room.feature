Feature: Joining a room and chatting
  People can open a room, talk to each other, and leave with clear feedback.

  Scenario: Alice opens a room and Bob joins her
    Given a fresh room called "main_room"
    And "alice" is connected
    And "bob" is connected
    When "alice" joins room "main_room" with a valid key
    Then the reply for "alice" should include
      | field        | value     |
      | status       | 0         |
      | room_created | true      |
      | room_name    | main_room |
      | members      | alice     |
    When "bob" joins room "main_room" with a valid key
    Then the reply for "bob" should include
      | field        | value     |
      | status       | 0         |
      | room_created | false     |
      | room_name    | main_room |
      | members      | alice,bob |
    And "alice" should be told that "bob" joined room "main_room"

  Scenario: Someone in the room can send a message
    Given a fresh room called "chat_room"
    And "alice" is connected
    And "bob" is connected
    And "alice" joins room "chat_room" with a valid key
    And "bob" joins room "chat_room" with a valid key
    When "alice" sends the message "hello from behave"
    Then the reply for "alice" should include
      | field   | value             |
      | status  | 0                 |
      | message | hello from behave |
    And "bob" should receive the message "hello from behave" from "alice"

  Scenario: Someone outside the room cannot send a message
    Given "alice" is connected
    When "alice" sends the message "this should fail"
    Then the reply for "alice" should include
      | field   | value                |
      | status  | 1                    |
      | message | User not in a room   |

  Scenario: Leaving the room tells the people who stayed
    Given a fresh room called "leave_room"
    And "alice" is connected
    And "bob" is connected
    And "alice" joins room "leave_room" with a valid key
    And "bob" joins room "leave_room" with a valid key
    When "bob" leaves the room
    Then the reply for "bob" should include
      | field   | value |
      | status  | 0                    |
    And "alice" should be told that "bob" left the room
    And the reply field "message" for "bob" should mention "Left room"
