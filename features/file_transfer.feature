Feature: Sharing files in a room
  People in a room can share files, and people outside the room cannot.

  Scenario: A room member uploads a file and someone else downloads it
    Given a fresh room called "files_room"
    And "alice" is connected
    And "bob" is connected
    And "alice" joins room "files_room" with a valid key
    And "bob" joins room "files_room" with a valid key
    When "alice" uploads file "notes.txt" to room "files_room" with content
      """
      encrypted payload bytes
      """
    Then the request should finish with status 200
    And "bob" should be told that "alice" uploaded "notes.txt"
    When "notes.txt" is downloaded from room "files_room"
    Then the downloaded file should equal
      """
      encrypted payload bytes
      """

  Scenario: Someone outside the room cannot upload a file there
    Given a fresh room called "restricted_room"
    And "alice" is connected
    And "alice" joins room "restricted_room" with a valid key
    When "mallory" tries to upload file "blocked.txt" to room "restricted_room" with content
      """
      blocked bytes
      """
    Then the request should finish with status 403
    And the last web reply should mention "User is not a member of the specified room"
