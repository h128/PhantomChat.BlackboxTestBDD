Feature: JoinOrCreate request field validation
  The server validates every field in a JoinOrCreate request before touching room
  state, and returns a descriptive error when any field is invalid.

  Background:
    Given "alice" is connected

  Scenario Outline: room_name shorter than 5 characters is rejected
    When "alice" attempts to join with these raw fields:
      | field      | value                                                            |
      | user_uuid  | alice                                                            |
      | room_name  | <room_name>                                                      |
      | public_key | 0000000000000000000000000000000000000000000000000000000000000000 |
    Then the reply for "alice" should include
      | field  | value |
      | status | 1     |
    And the reply field "message" for "alice" should mention "room_name must be at least 5 characters"

    Examples:
      | room_name |
      | a         |
      | abcd      |

  Scenario: room_name longer than 64 characters is rejected
    When "alice" attempts to join with these raw fields:
      | field      | value                                                              |
      | user_uuid  | alice                                                              |
      | room_name  | this-room-name-is-deliberately-too-long-to-pass-server-validation  |
      | public_key | 0000000000000000000000000000000000000000000000000000000000000000   |
    Then the reply for "alice" should include
      | field  | value |
      | status | 1     |
    And the reply field "message" for "alice" should mention "room_name exceeds maximum length of 64"

  Scenario: room_name with unsafe characters is rejected
    When "alice" attempts to join with these raw fields:
      | field      | value                                                            |
      | user_uuid  | alice                                                            |
      | room_name  | bad room!                                                        |
      | public_key | 0000000000000000000000000000000000000000000000000000000000000000 |
    Then the reply for "alice" should include
      | field  | value |
      | status | 1     |
    And the reply field "message" for "alice" should mention "alphanumeric"

  Scenario: user_uuid longer than 64 characters is rejected
    When "alice" attempts to join with these raw fields:
      | field      | value                                                              |
      | user_uuid  | this-user-uuid-is-deliberately-too-long-to-pass-server-validation  |
      | room_name  | valid-room                                                         |
      | public_key | 0000000000000000000000000000000000000000000000000000000000000000   |
    Then the reply for "alice" should include
      | field  | value |
      | status | 1     |
    And the reply field "message" for "alice" should mention "user_uuid exceeds maximum length of 64"

  Scenario: user_uuid with unsafe characters is rejected
    When "alice" attempts to join with these raw fields:
      | field      | value                                                            |
      | user_uuid  | bad user!                                                        |
      | room_name  | valid-room                                                       |
      | public_key | 0000000000000000000000000000000000000000000000000000000000000000 |
    Then the reply for "alice" should include
      | field  | value |
      | status | 1     |
    And the reply field "message" for "alice" should mention "alphanumeric"

  Scenario: a request without public_key is rejected
    When "alice" attempts to join with these raw fields:
      | field     | value      |
      | user_uuid | alice      |
      | room_name | valid-room |
    Then the reply for "alice" should include
      | field  | value |
      | status | 1     |

  Scenario: an empty public_key is rejected
    When "alice" attempts to join with these raw fields:
      | field      | value      |
      | user_uuid  | alice      |
      | room_name  | valid-room |
      | public_key |            |
    Then the reply for "alice" should include
      | field  | value |
      | status | 1     |
    And the reply field "message" for "alice" should mention "public_key is required"

  Scenario: a public_key that is not 32 bytes long is rejected
    When "alice" attempts to join with these raw fields:
      | field      | value      |
      | user_uuid  | alice      |
      | room_name  | valid-room |
      | public_key | deadbeef   |
    Then the reply for "alice" should include
      | field  | value |
      | status | 1     |
    And the reply field "message" for "alice" should mention "32-byte hex-encoded key"

  Scenario: a public_key containing non-hex characters is rejected
    When "alice" attempts to join with these raw fields:
      | field      | value                                                            |
      | user_uuid  | alice                                                            |
      | room_name  | valid-room                                                       |
      | public_key | zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz |
    Then the reply for "alice" should include
      | field  | value |
      | status | 1     |
    And the reply field "message" for "alice" should mention "32-byte hex-encoded key"

  Scenario: display_name longer than 64 characters is rejected
    When "alice" attempts to join with these raw fields:
      | field        | value                                                            |
      | user_uuid    | alice                                                            |
      | room_name    | valid-room                                                       |
      | public_key   | 0000000000000000000000000000000000000000000000000000000000000000 |
      | display_name | This display name is deliberately too long to pass validation end |
    Then the reply for "alice" should include
      | field  | value |
      | status | 1     |
    And the reply field "message" for "alice" should mention "display_name exceeds maximum length of 64"
