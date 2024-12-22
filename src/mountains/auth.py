def logged_in(session) -> bool:
    return session.get("user_id") is not None
