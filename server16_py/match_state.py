"""Read-only page signals shared by match audio and the in-game selector."""


def penalty_shootout_page(page: str) -> bool:
    return (page or '').strip().lower().rsplit('/', 1)[-1] == 'penaltykickselect'


def post_match_page(page: str) -> bool:
    page = (page or "").lower()
    # FIFA puts the taker-order screen in postGameFlow, then returns directly
    # to the same live fixture. Its scoreboard and other match assets stay put.
    if penalty_shootout_page(page):
        return False
    return any(token in page for token in (
        "postgameflow", "matchdetailsendgame", "matchresults", "matchended", "matchforfeit",
    ))


def outside_match_page(page: str) -> bool:
    page = (page or "").lower()
    # FluxHub is also the pause menu, so it must NOT end the session.
    return post_match_page(page) or any(token in page for token in (
        "training/", "skillgames/", "misc/arenaplayer", "bootflow/", "saveload_pc/bootload",
        "playnow/sideselect", "playnow/selectteam",
    ))


def pause_page(page: str) -> bool:
    page = (page or "").lower()
    return any(token in page for token in (
        "fluxhub", "stadiumpan", "instantreplay", "pause", "settings/", "profile/", "teammanagement",
    ))


class GoalClockProgress:
    """Require sustained forward clock movement, allowing integer timer ticks."""

    def __init__(self, required_hits: int = 3, sample_seconds: float = 1.0) -> None:
        self.required_hits = max(2, required_hits)
        self.sample_seconds = max(0.2, sample_seconds)
        self.reset()

    def reset(self) -> None:
        self.clock = None
        self.sample_at = None
        self.hits = 0

    def observe(self, clock: int | None, now: float) -> bool:
        if clock is None:
            self.reset()
            return False
        if self.clock is None or clock < self.clock:
            self.clock, self.sample_at, self.hits = clock, now, 0
            return False
        elapsed = now - self.sample_at
        if elapsed < self.sample_seconds:
            return False
        delta = clock - self.clock
        self.hits = self.hits + 1 if delta >= 1 and delta / elapsed >= 0.5 else 0
        self.clock, self.sample_at = clock, now
        return self.hits >= self.required_hits
