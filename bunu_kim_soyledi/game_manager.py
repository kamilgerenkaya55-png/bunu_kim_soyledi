import asyncio
import random
from typing import Dict, List, Optional
from fastapi import WebSocket

class Player:
    def __init__(self, player_id: str, name: str, avatar: str, ws: WebSocket):
        self.id = player_id
        self.name = name
        self.avatar = avatar
        self.ws = ws
        self.score = 0
        self.secret = ""
        self.has_submitted = False
        self.current_vote = None  # Oy verdiği player_id

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "avatar": self.avatar,
            "score": self.score,
            "has_submitted": self.has_submitted
        }

class GameManager:
    def __init__(self):
        self.players: Dict[str, Player] = {}
        self.host_ws: Optional[WebSocket] = None
        self.state: str = "LOBBY"  # LOBBY, SUBMISSION, GUESSING, REVEAL, GAME_OVER
        
        # Oyun oturumu verileri
        self.secrets: List[Dict] = []  # [{"author_id": ..., "text": ...}]
        self.current_secret_index: int = 0
        self.countdown_task: Optional[asyncio.Task] = None
        self.time_left: int = 0
        self.chat_history: List[Dict] = []

    async def register_host(self, ws: WebSocket):
        self.host_ws = ws
        await self.send_to_host({
            "type": "state_sync",
            "state": self.state,
            "players": [p.to_dict() for p in self.players.values()],
            "chat_history": self.chat_history[-20:]
        })

    async def unregister_host(self):
        self.host_ws = None

    async def add_player(self, player_id: str, name: str, avatar: str, ws: WebSocket) -> Player:
        # Eğer aynı isimde veya ID'de varsa güncelle
        player = Player(player_id, name, avatar, ws)
        self.players[player_id] = player
        
        # Herkese yeni oyuncuyu bildir
        await self.broadcast({
            "type": "player_joined",
            "player": player.to_dict(),
            "players": [p.to_dict() for p in self.players.values()]
        })
        return player

    async def remove_player(self, player_id: str):
        if player_id in self.players:
            player = self.players.pop(player_id)
            await self.broadcast({
                "type": "player_left",
                "player_id": player_id,
                "players": [p.to_dict() for p in self.players.values()]
            })

    async def send_to_host(self, data: dict):
        if self.host_ws:
            try:
                await self.host_ws.send_json(data)
            except Exception:
                self.host_ws = None

    async def send_to_player(self, player_id: str, data: dict):
        player = self.players.get(player_id)
        if player and player.ws:
            try:
                await player.ws.send_json(data)
            except Exception:
                pass

    async def broadcast(self, data: dict):
        # Host'a gönder
        await self.send_to_host(data)
        
        # Tüm oyunculara gönder
        for player in list(self.players.values()):
            try:
                await player.ws.send_json(data)
            except Exception:
                pass

    async def add_chat_message(self, sender_name: str, avatar: str, text: str):
        msg = {
            "type": "chat_message",
            "sender": sender_name,
            "avatar": avatar,
            "text": text
        }
        self.chat_history.append(msg)
        if len(self.chat_history) > 50:
            self.chat_history.pop(0)
        await self.broadcast(msg)

    async def send_reaction(self, sender_name: str, emoji: str):
        await self.broadcast({
            "type": "reaction",
            "sender": sender_name,
            "emoji": emoji
        })

    # ==================== OYUN DÖNGÜSÜ ====================

    async def start_game(self):
        """Lobi aşamasından sır toplama aşamasına geçiş."""
        if len(self.players) < 2:
            return False, "Oyunu başlatmak için en az 2 oyuncu gereklidir."

        self.state = "SUBMISSION"
        self.secrets = []
        self.current_secret_index = 0
        
        # Oyuncuların durumlarını sıfırla
        for p in self.players.values():
            p.secret = ""
            p.has_submitted = False
            p.current_vote = None

        await self.broadcast({
            "type": "game_started",
            "state": self.state,
            "prompt": "Kimsenin senin hakkında bilmediği bir anını, sırrını veya komik bir alışkanlığını yaz!"
        })
        return True, "Oyun başladı!"

    async def submit_secret(self, player_id: str, secret_text: str):
        """Oyuncu sırrını gönderir."""
        player = self.players.get(player_id)
        if not player or self.state != "SUBMISSION":
            return

        player.secret = secret_text.strip()
        player.has_submitted = True

        # Host ve oyunculara ilerleme durumunu bildir
        submitted_count = sum(1 for p in self.players.values() if p.has_submitted)
        total_count = len(self.players)

        await self.broadcast({
            "type": "submission_progress",
            "submitted_count": submitted_count,
            "total_count": total_count,
            "player_id": player_id
        })

        # Herkes sırrını verdiyse otomatik tahmin aşamasına geç
        if submitted_count >= total_count:
            await asyncio.sleep(1)
            await self.start_guessing_phase()

    async def start_guessing_phase(self):
        """Tüm sırları karıştırır ve ilk soruyla tahmin aşamasını başlatır."""
        # Sırları topla ve karıştır
        self.secrets = [
            {"author_id": p.id, "text": p.secret}
            for p in self.players.values() if p.secret
        ]
        random.shuffle(self.secrets)
        self.current_secret_index = 0
        
        if not self.secrets:
            self.state = "LOBBY"
            await self.broadcast({"type": "state_sync", "state": self.state})
            return

        await self.next_secret()

    async def next_secret(self):
        """Sıradaki sırrı ekrana getirir ve oylama süresini başlatır."""
        if self.current_secret_index >= len(self.secrets):
            await self.finish_game()
            return

        self.state = "GUESSING"
        # Oyları sıfırla
        for p in self.players.values():
            p.current_vote = None

        current = self.secrets[self.current_secret_index]
        
        # Seçenekler (tüm oyuncular)
        options = [{"id": p.id, "name": p.name, "avatar": p.avatar} for p in self.players.values()]

        # Oylama süresi (25 saniye)
        self.time_left = 25

        await self.broadcast({
            "type": "new_round",
            "state": self.state,
            "round": self.current_secret_index + 1,
            "total_rounds": len(self.secrets),
            "secret_text": current["text"],
            "options": options,
            "time_limit": self.time_left
        })

        # Geri sayım görevini başlat
        if self.countdown_task and not self.countdown_task.done():
            self.countdown_task.cancel()
        self.countdown_task = asyncio.create_task(self._countdown_timer())

    async def _countdown_timer(self):
        try:
            while self.time_left > 0:
                await asyncio.sleep(1)
                self.time_left -= 1
                await self.broadcast({
                    "type": "timer_tick",
                    "time_left": self.time_left
                })
            # Süre bittiğinde otomatik açıkla
            await self.reveal_round()
        except asyncio.CancelledError:
            pass

    async def vote(self, voter_id: str, guessed_player_id: str):
        """Oyuncu kimin söylediğini tahmin eder."""
        if self.state != "GUESSING":
            return

        voter = self.players.get(voter_id)
        if not voter:
            return

        voter.current_vote = guessed_player_id

        # Oy verenlerin sayısını bildir
        voted_count = sum(1 for p in self.players.values() if p.current_vote is not None)
        total_voters = len(self.players)

        await self.broadcast({
            "type": "vote_progress",
            "voted_count": voted_count,
            "total_voters": total_voters,
            "voter_id": voter_id
        })

        # Herkes oy verdiyse süreyi beklemeden hemen açıkla
        if voted_count >= total_voters:
            if self.countdown_task and not self.countdown_task.done():
                self.countdown_task.cancel()
            await asyncio.sleep(0.5)
            await self.reveal_round()

    async def reveal_round(self):
        """Sırrın gerçek sahibini açıklar ve puanları dağıtır."""
        self.state = "REVEAL"
        current = self.secrets[self.current_secret_index]
        author_id = current["author_id"]
        author = self.players.get(author_id)
        author_name = author.name if author else "Bilinmeyen"
        author_avatar = author.avatar if author else "❓"

        # Puanlama hesapla
        # Doğru bilen her oyuncu +100 puan
        # Yanılan her oyuncu için yazar (blöfçü) +50 puan
        correct_voters = []
        wrong_voters = []
        votes_map = {}  # voter_id -> guessed_id

        for p in self.players.values():
            if p.current_vote:
                votes_map[p.id] = {
                    "voter_name": p.name,
                    "voter_avatar": p.avatar,
                    "voted_for_id": p.current_vote
                }
                if p.id != author_id:  # Yazar kendi kendine puan almaz
                    if p.current_vote == author_id:
                        p.score += 100
                        correct_voters.append(p.name)
                    else:
                        wrong_voters.append(p.name)

        # Yazara blöf puanı (yanılan kişi başı 50 puan)
        if author:
            author.score += len(wrong_voters) * 50

        # Skor tablosunu sırala
        leaderboard = sorted(
            [p.to_dict() for p in self.players.values()],
            key=lambda x: x["score"],
            reverse=True
        )

        await self.broadcast({
            "type": "round_reveal",
            "state": self.state,
            "secret_text": current["text"],
            "author": {
                "id": author_id,
                "name": author_name,
                "avatar": author_avatar
            },
            "correct_voters": correct_voters,
            "wrong_voters": wrong_voters,
            "votes": votes_map,
            "leaderboard": leaderboard
        })

        self.current_secret_index += 1

    async def finish_game(self):
        """Oyun biter, podyumu gösterir."""
        self.state = "GAME_OVER"
        leaderboard = sorted(
            [p.to_dict() for p in self.players.values()],
            key=lambda x: x["score"],
            reverse=True
        )

        await self.broadcast({
            "type": "game_over",
            "state": self.state,
            "leaderboard": leaderboard
        })

    async def reset_to_lobby(self):
        """Oyunu sıfırlar ve lobiye döner."""
        self.state = "LOBBY"
        self.secrets = []
        self.current_secret_index = 0
        for p in self.players.values():
            p.score = 0
            p.secret = ""
            p.has_submitted = False
            p.current_vote = None

        await self.broadcast({
            "type": "state_sync",
            "state": self.state,
            "players": [p.to_dict() for p in self.players.values()]
        })

game_manager = GameManager()
