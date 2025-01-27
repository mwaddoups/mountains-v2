from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

import requests
from attrs import define
from cattrs import structure

if TYPE_CHECKING:
    from flask import Flask

logger = logging.getLogger(__name__)

_MEMBER_ROLE_ID = "974275340874678283"


@define
class DiscordMember:
    """
    A partial of a returned member, with all the fields we access
    """

    id: str  # called snowflake by Discord
    username: str
    nick: str | None
    roles: list[str]

    @classmethod
    def from_member_dict(cls, m: dict[str, Any]):
        """
        Unpacks this from a DiscordMember dict response
        """
        return structure(
            dict(
                id=m["user"]["id"],
                username=m["user"]["username"],
                nick=m["nick"],
                roles=m["roles"],
            ),
            cls,
        )

    @property
    def member_name(self) -> str:
        """
        Gets member name in form we use internally
        """
        display_name = self.nick if self.nick is not None else self.username
        full_name = f"{display_name} ({self.username})"
        if self.is_member:
            full_name += " [M]"
        return full_name

    @property
    def is_member(self):
        return _MEMBER_ROLE_ID in self.roles


@define
class DiscordAPI:
    api_key: str
    debug: bool
    GUILD_ID: ClassVar[str] = "920776260496523264"

    @classmethod
    def from_app(cls, app: Flask):
        return cls(debug=app.debug, api_key=app.config["DISCORD_API_KEY"])

    def _api_headers(self):
        return {
            "Authorization": f"Bot {self.api_key}",
            "User-Agent": "DiscordBot (https://discord.com/api/v10/, 10)",
        }

    def fetch_all_members(self) -> list[DiscordMember]:
        page_size = 1000
        members: list[DiscordMember] = []
        while len(members) % page_size == 0:
            res = requests.get(
                f"https://discord.com/api/v10/guilds/{self.GUILD_ID}/members?limit={page_size}&after={len(members)}",
                headers=self._api_headers(),
            )

            members_page: list[dict] = res.json()
            for m in members_page:
                members.append(DiscordMember.from_member_dict(m))

        return members

    def get_member(self, member_id: str) -> DiscordMember | None:
        res = requests.get(
            f"https://discord.com/api/v10/guilds/{self.GUILD_ID}/members/{member_id}",
            headers=self._api_headers(),
        )
        if res.status_code == 200:
            return DiscordMember.from_member_dict(res.json())
        else:
            return None

    def set_member_role(self, user_id: str):
        if not self.debug:
            res = requests.put(
                f"https://discord.com/api/v10/guilds/{self.GUILD_ID}/members/{user_id}/roles/{_MEMBER_ROLE_ID}",
                headers=self._api_headers(),
            )
            logger.debug("Set member role with response %r", res.content)
        else:
            print(
                f"DEBUG: Not actually posting to Discord, would set user_id {user_id} to member!"
            )

    def remove_member_role(self, user_id: str):
        if not self.debug:
            res = requests.delete(
                f"https://discord.com/api/v10/guilds/{self.GUILD_ID}/members/{user_id}/roles/{_MEMBER_ROLE_ID}",
                headers=self._api_headers(),
            )
            logger.debug("Removed member role with response %r", res.content)
        else:
            print(
                f"DEBUG: Not actually posting to Discord, would remove member from user_id {user_id}!"
            )
