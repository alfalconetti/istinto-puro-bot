from dataclasses import dataclass, field
from enum import Enum, auto


class GameState(Enum):
    LOBBY = auto()
    READY_CHECK = auto()
    COUNTDOWN = auto()
    WAITING_ANSWER = auto()
    JUDGING = auto()
    GAME_OVER = auto()


@dataclass
class Player:
    user_id: int
    username: str
    score: int = 0


@dataclass
class Game:
    chat_id: int
    target_score: int
    auto_teams: bool
    players: list[Player] = field(default_factory=list)
    state: GameState = GameState.LOBBY
    ready: set[int] = field(default_factory=set)          # user_ids who pressed ready
    team_a: str = ""
    team_b: str = ""
    # message ids for cleanup
    lobby_msg_id: int | None = None
    ready_msg_id: int | None = None
    judging_msg_id: int | None = None
    countdown_msg_id: int | None = None

    @property
    def is_full(self) -> bool:
        return len(self.players) == 2

    @property
    def both_ready(self) -> bool:
        return all(p.user_id in self.ready for p in self.players)

    def get_player(self, user_id: int) -> Player | None:
        return next((p for p in self.players if p.user_id == user_id), None)

    def other_player(self, user_id: int) -> Player | None:
        return next((p for p in self.players if p.user_id != user_id), None)

    def winner(self) -> Player | None:
        for p in self.players:
            if p.score >= self.target_score:
                return p
        return None

    def score_line(self) -> str:
        p1, p2 = self.players
        return f"🏆 {p1.username}: {p1.score}  —  {p2.username}: {p2.score}"


# One game per chat
_games: dict[int, Game] = {}


def get_game(chat_id: int) -> Game | None:
    return _games.get(chat_id)


def create_game(chat_id: int, target_score: int, auto_teams: bool) -> Game:
    g = Game(chat_id=chat_id, target_score=target_score, auto_teams=auto_teams)
    _games[chat_id] = g
    return g


def remove_game(chat_id: int):
    _games.pop(chat_id, None)
