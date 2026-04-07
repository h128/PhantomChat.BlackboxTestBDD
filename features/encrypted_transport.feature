@crypto_contract
Feature: Encrypted transport using the room key
  The public room-key flow already lets clients protect content before it crosses the wire.

  Scenario: Two people can exchange an encrypted chat message over the existing message field
    Given a fresh room called "encrypted_chat_room"
    And "alice" is connected
    And "bob" is connected
    And "alice" joins room "encrypted_chat_room" with a generated key pair
    And "bob" joins room "encrypted_chat_room" with a generated key pair
    And "alice" should be able to open the room key from the reply
    And "bob" should be able to open the room key from the reply
    When "alice" sends the encrypted message "meet me by the lantern" using the room key
    Then the last sent chat payload for "alice" should not contain "meet me by the lantern"
    And the reply field "message" for "alice" should not mention "meet me by the lantern"
    And "bob" should receive an encrypted chat message from "alice" that opens to "meet me by the lantern"
    And the received encrypted chat payload for "bob" should not contain "meet me by the lantern"

  Scenario: A tampered encrypted chat message reaches the room but cannot be opened
    Given a fresh room called "tampered_chat_room"
    And "alice" is connected
    And "bob" is connected
    And "alice" joins room "tampered_chat_room" with a generated key pair
    And "bob" joins room "tampered_chat_room" with a generated key pair
    And "alice" should be able to open the room key from the reply
    And "bob" should be able to open the room key from the reply
    When "alice" sends a tampered encrypted message for "do not trust this" using the room key
    Then "bob" should receive an encrypted chat message from "alice" that cannot be opened

  Scenario: A room member can upload and download encrypted file bytes
    Given a fresh room called "encrypted_file_room"
    And "alice" is connected
    And "bob" is connected
    And "alice" joins room "encrypted_file_room" with a generated key pair
    And "bob" joins room "encrypted_file_room" with a generated key pair
    And "alice" should be able to open the room key from the reply
    And "bob" should be able to open the room key from the reply
    When "alice" uploads encrypted file "ledger.bin" to room "encrypted_file_room" with content
      """
      transfer funds at dawn
      """
    Then the request should finish with status 200
    And the uploaded file bytes should not equal
      """
      transfer funds at dawn
      """
    And "bob" should be told that "alice" uploaded "ledger.bin"
    When "ledger.bin" is downloaded from room "encrypted_file_room"
    Then the downloaded file bytes should not equal
      """
      transfer funds at dawn
      """
    And the downloaded encrypted file should open to
      """
      transfer funds at dawn
      """