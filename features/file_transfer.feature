Feature: File transfer
  The backend should enforce room membership for uploads and preserve uploaded bytes for download.

  Scenario: A room member can upload and download a file
    Given a unique room alias "files_room"
    And WebSocket client "alice" is connected
    And WebSocket client "bob" is connected
    And client "alice" joins room "files_room" with a generated libsodium-style public key
    And client "bob" joins room "files_room" with a generated libsodium-style public key
    When user "alice" uploads file "notes.txt" to room "files_room" with content
      """
      encrypted payload bytes
      """
    Then the last HTTP response should have status 200
    And client "bob" should receive a "FileUploaded" event containing
      | field     | value     |
      | file_name | notes.txt |
      | user_uuid | alice     |
      | poster    | false     |
    When the file "notes.txt" is downloaded from room "files_room"
    Then the downloaded content should equal
      """
      encrypted payload bytes
      """

  Scenario: A non-member cannot upload into an existing room
    Given a unique room alias "restricted_room"
    And WebSocket client "alice" is connected
    And client "alice" joins room "restricted_room" with a generated libsodium-style public key
    When user "mallory" uploads file "blocked.txt" to room "restricted_room" with content
      """
      blocked bytes
      """
    Then the last HTTP response should have status 403
    And the last HTTP response body should contain "User is not a member of the specified room"
