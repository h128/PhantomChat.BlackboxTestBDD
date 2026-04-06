from __future__ import annotations

from dataclasses import dataclass, field

import requests


@dataclass(slots=True)
class PhantomHttpClient:
    base_url: str
    timeout_seconds: float
    verify_tls: bool
    session: requests.Session = field(init=False)

    def __post_init__(self) -> None:
        self.session = requests.Session()

    def upload_document(self, filename: str, room_name: str, user_uuid: str, content: bytes) -> requests.Response:
        response = self.session.post(
            f"{self.base_url}/upload-document/{requests.utils.quote(filename, safe='')}",
            headers={
                "Content-Length": str(len(content)),
                "x-room-name": room_name,
                "x-user-uuid": user_uuid,
            },
            data=content,
            timeout=self.timeout_seconds,
            verify=self.verify_tls,
        )
        return response

    def download_document(self, room_name: str, filename: str) -> requests.Response:
        response = self.session.get(
            f"{self.base_url}/download-document/{requests.utils.quote(room_name, safe='')}/{requests.utils.quote(filename, safe='')}",
            timeout=self.timeout_seconds,
            verify=self.verify_tls,
        )
        return response

    def close(self) -> None:
        self.session.close()
