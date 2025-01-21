from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

import requests
from attrs import define

if TYPE_CHECKING:
    from flask import Flask

GUILD_ID = "920776260496523264"
MEMBER_ROLE_ID = "974275340874678283"


class DiscordUser(TypedDict):
    id: str  # called snowflake by Discord
    username: str


class DiscordMember(TypedDict):
    """
    A partial dictionary of a returned member, with all the fields we access
    """

    user: DiscordUser
    nick: str | None
    roles: list[str]


@define
class DiscordAPI:
    api_key: str
    debug: bool

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
        members = []
        while len(members) % page_size == 0:
            res = requests.get(
                f"https://discord.com/api/v10/guilds/{GUILD_ID}/members?limit={page_size}&after={len(members)}",
                headers=self._api_headers(),
            )
            members_page: list[DiscordMember] = res.json()
            members += members_page

        return members

    def get_member(self, member_id: str) -> DiscordMember | None:
        res = requests.get(
            f"https://discord.com/api/v10/guilds/{GUILD_ID}/members/{member_id}",
            headers=self._api_headers(),
        )
        if res.status_code == 200:
            return res.json()
        else:
            return None

    def set_member_role(self, user_id: str):
        if not self.debug:
            res = requests.put(
                f"https://discord.com/api/v10/guilds/{GUILD_ID}/members/{user_id}/roles/{MEMBER_ROLE_ID}",
                headers=self._api_headers(),
            )
            print(res.content)
        else:
            print(
                f"DEBUG: Not actually posting to Discord, would set user_id {user_id} to member!"
            )

    def remove_member_role(self, user_id: str):
        if not self.debug:
            res = requests.delete(
                f"https://discord.com/api/v10/guilds/{GUILD_ID}/members/{user_id}/roles/{MEMBER_ROLE_ID}",
                headers=self._api_headers(),
            )
            print(res.content)
        else:
            print(
                f"DEBUG: Not actually posting to Discord, would remove member from user_id {user_id}!"
            )

    def is_member_role(self, member: DiscordMember) -> bool:
        return MEMBER_ROLE_ID in member["roles"]

    def member_username(self, member: DiscordMember) -> str:
        """
        Helper function to get username in form we store internally
        """

        display_name = (
            member["nick"] if member["nick"] is not None else member["user"]["username"]
        )
        full_name = f"{display_name} ({member['user']['username']})"
        if self.is_member_role(member):
            full_name += " [M]"
        return full_name
